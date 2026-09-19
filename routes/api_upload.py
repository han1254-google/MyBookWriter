"""
文件上传 API
"""
import os
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

from database import db, LibraryFile, LibraryCategory
from services.library_service import (
    classify_file, save_file, list_libraries, delete_file, extract_style,
    ensure_category, summarize_file, load_taxonomy,
)
from services.file_service import extract_text, sample_text
from services.index_service import index_file, remove_file_index
from logger import get_logger

api_upload_bp = Blueprint("api_upload", __name__)
log = get_logger("api.upload")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".epub"}


def _safe_filename(name):
    """
    只剥路径分隔符和非法字符，**保留中文**。

    原先是 werkzeug.secure_filename()，它按 ASCII 白名单过滤，
    《星光：外星世界与地球的命运.epub》会被削成 "epub" ——
    于是库里文件名全变成 epub/pdf，而分类器拿到的"文件名"也是这俩字。
    """
    name = os.path.basename((name or "").replace("\\", "/"))
    name = "".join(c for c in name if c not in r'\/:*?"<>|' and ord(c) >= 32)
    return name.strip().strip(".") or "未命名"


def _auto_summarize(app, file_id):
    """
    后台生成 AI 摘要。
    用全文抽样（目录 + 开头 + 正文均匀节选）而不是开头 2000 字 ——
    PDF 的开头是标题页、epub 的开头是版权页，拿它生成的摘要讲的全是封面信息。
    """
    try:
        with app.app_context():
            lib_file = db.session.get(LibraryFile, file_id)
            if not lib_file or lib_file.ai_summary:
                return

            sample = lib_file.summary_sample
            if not sample and lib_file.stored_path:
                sample, meta = sample_text(lib_file.stored_path)
                lib_file.summary_sample = sample
                lib_file.char_count = meta.get("char_count", 0)
                lib_file.page_count = meta.get("page_count", 0)
            if not (sample or "").strip():
                sample = lib_file.content_preview or ""
            if not sample.strip():
                lib_file.summary_status = "failed"
                db.session.commit()
                log.warning(f"无可用文本，摘要跳过: id={file_id}")
                return

            lib_file.ai_summary = summarize_file(lib_file.original_filename, sample)
            lib_file.summary_status = "ok"
            db.session.commit()
            log.info(f"自动摘要完成: id={file_id}, {len(lib_file.ai_summary)} 字符")
    except Exception as e:
        log.error(f"自动摘要失败: id={file_id}: {e}", exc_info=True)
        try:
            with app.app_context():
                lf = db.session.get(LibraryFile, file_id)
                if lf:
                    lf.summary_status = "failed"
                    db.session.commit()
        except Exception:
            pass


def _index_and_count(app, file_id, stored_path, library_type, folder_name):
    """索引文件并回写 chunk 数与索引时间"""
    chunks = index_file(stored_path, library_type, folder_name)
    try:
        with app.app_context():
            lf = db.session.get(LibraryFile, file_id)
            if lf:
                lf.chunk_count = chunks
                lf.indexed_at = datetime.now(timezone.utc)
                db.session.commit()
    except Exception as e:
        log.warning(f"回写索引信息失败: id={file_id}: {e}")


@api_upload_bp.route("/upload", methods=["POST"])
def upload_file():
    """上传文件并自动分类"""
    if "file" not in request.files:
        log.warning("上传请求无文件")
        return jsonify({"error": "未选择文件"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "文件名为空"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        log.warning(f"不支持的文件格式: {ext} ({file.filename})")
        return jsonify({"error": f"不支持的格式: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    user_library = request.form.get("library_type", "").strip()
    VALID_LIBRARIES = {"知识库", "参考库", "风格库"}
    if user_library not in VALID_LIBRARIES:
        user_library = ""

    safe_name = _safe_filename(file.filename)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    log.info(f"开始处理上传: {safe_name} (ext={ext}, size={os.path.getsize(tmp_path)}B, user_library={user_library or 'AI自动'})")

    try:
        # 分类用开头（题名/摘要最能说明归属），摘要用全文抽样
        content_preview = extract_text(tmp_path, max_chars=2000)
        summary_sample, sample_meta = sample_text(tmp_path)
        log.debug(f"文本提取完成: 预览 {len(content_preview)} 字, "
                  f"抽样 {len(summary_sample)} 字, "
                  f"全文 {sample_meta.get('char_count', 0)} 字")

        classification = classify_file(safe_name, content_preview, user_library)
        library_type = classification["library_type"]
        folder_name = classification["folder_name"]
        log.info(f"分类结果: {library_type}/{folder_name} "
                 f"({'新建分类' if classification['is_new'] else '复用现有分类'})")

        # AI 新建的分类落库，下次上传即可复用（这是避免分类无限膨胀的关键）
        category_id = ensure_category(
            library_type, folder_name,
            description=classification.get("reason", ""),
            reason=classification.get("reason", ""),
        )

        # 风格库特殊处理：AI 提取风格特征
        style_analysis = ""
        if library_type == "风格库":
            log.info("风格库文件，开始提取风格特征...")
            style_analysis = extract_style(summary_sample or content_preview, safe_name)
            log.debug(f"风格分析: {style_analysis[:100]}...")

        file.seek(0)
        stored_path = save_file(file, library_type, folder_name)
        log.info(f"文件已保存: {stored_path}")

        lib_file = LibraryFile(
            library_type=library_type,
            folder_name=folder_name,
            category_id=category_id,
            original_filename=safe_name,
            stored_path=stored_path,
            file_type=ext.lstrip("."),
            style_analysis=style_analysis,
            content_preview=content_preview[:2000],
            summary_sample=summary_sample,
            summary_status="pending",
            classify_reason=classification.get("reason", ""),
            char_count=sample_meta.get("char_count", 0),
            page_count=sample_meta.get("page_count", 0),
        )
        db.session.add(lib_file)
        db.session.commit()
        log.info(f"数据库记录已创建: id={lib_file.id}, type={library_type}, folder={folder_name}")

        # 自动写入向量数据库 + 生成AI摘要（后台线程）
        import threading
        from flask import current_app
        app_ref = current_app._get_current_object()
        threading.Thread(
            target=_index_and_count,
            args=(app_ref, lib_file.id, stored_path, library_type, folder_name),
            daemon=True,
        ).start()
        threading.Thread(
            target=_auto_summarize,
            args=(app_ref, lib_file.id),
            daemon=True,
        ).start()

        return jsonify({
            "success": True,
            "id": lib_file.id,
            "library_type": library_type,
            "folder_name": folder_name,
            "filename": safe_name,
            "is_new_category": classification["is_new"],
            "classify_reason": classification.get("reason", ""),
        })

    except Exception as e:
        log.error(f"上传失败: {type(e).__name__}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
            log.debug(f"临时文件已清理: {tmp_path}")


@api_upload_bp.route("/libraries", methods=["GET"])
def get_libraries():
    """列出所有库结构"""
    data = list_libraries()
    files = LibraryFile.query.order_by(LibraryFile.created_at.desc()).all()
    log.debug(f"列出库: {len(files)} 个文件")
    return jsonify({
        "structure": data,
        "files": [f.to_dict() for f in files],
    })


@api_upload_bp.route("/libraries/<lib_type>", methods=["GET"])
def get_library_files(lib_type):
    """获取某库下的文件"""
    files = LibraryFile.query.filter_by(library_type=lib_type).order_by(
        LibraryFile.created_at.desc()
    ).all()
    log.debug(f"查询库文件: {lib_type} -> {len(files)} 个")
    return jsonify([f.to_dict() for f in files])


@api_upload_bp.route("/libraries/<int:file_id>", methods=["DELETE"])
def delete_library_file(file_id):
    """删除文件"""
    lib_file = LibraryFile.query.get_or_404(file_id)
    log.info(f"删除文件: id={file_id}, path={lib_file.stored_path}")
    if os.path.exists(lib_file.stored_path):
        remove_file_index(lib_file.stored_path)
        delete_file(lib_file.stored_path)
    db.session.delete(lib_file)
    db.session.commit()
    return jsonify({"success": True})


@api_upload_bp.route("/libraries/<int:file_id>/summarize", methods=["POST"])
def summarize_library_file(file_id):
    """AI 生成文件摘要。force=true 可强制重算（给旧数据补正用）"""
    lib_file = LibraryFile.query.get_or_404(file_id)
    force = (request.get_json(silent=True) or {}).get("force", False)

    if lib_file.ai_summary and not force:
        return jsonify({"success": True, "summary": lib_file.ai_summary, "cached": True})

    # 抽样缺失（旧数据）时现场补算
    sample = lib_file.summary_sample
    if (not sample or force) and lib_file.stored_path and os.path.exists(lib_file.stored_path):
        sample, meta = sample_text(lib_file.stored_path)
        lib_file.summary_sample = sample
        lib_file.char_count = meta.get("char_count", 0)
        lib_file.page_count = meta.get("page_count", 0)
    if not (sample or "").strip():
        sample = lib_file.content_preview or ""
    if not sample.strip():
        lib_file.summary_status = "failed"
        db.session.commit()
        return jsonify({"error": "无法提取文件内容"}), 400

    log.info(f"生成摘要: id={file_id}, file={lib_file.original_filename}, "
             f"抽样{len(sample)}字")

    try:
        lib_file.ai_summary = summarize_file(lib_file.original_filename, sample)
        lib_file.summary_status = "ok"
        summary = lib_file.ai_summary
        db.session.commit()
        log.info(f"摘要生成完成: id={file_id}, {len(summary)} 字符")
        return jsonify({"success": True, "summary": lib_file.ai_summary, "cached": False})
    except Exception as e:
        log.error(f"摘要生成失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@api_upload_bp.route("/libraries/search", methods=["GET"])
def search_files():
    """搜索文件（按文件名和内容预览）"""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    # SQLite LIKE 搜索（中英文通用）
    pattern = f"%{q}%"
    results = LibraryFile.query.filter(
        (LibraryFile.original_filename.like(pattern)) |
        (LibraryFile.content_preview.like(pattern)) |
        (LibraryFile.ai_summary.like(pattern))
    ).order_by(LibraryFile.created_at.desc()).limit(30).all()

    log.debug(f"搜索: q={q} -> {len(results)} 条")
    return jsonify([f.to_dict() for f in results])


@api_upload_bp.route("/categories", methods=["GET"])
def get_categories():
    """分类清单（按库分组，带文件数）——上传页的分类下拉用这个"""
    from database import LibraryFile as LF
    counts = dict(
        db.session.query(LF.folder_name, db.func.count(LF.id))
        .group_by(LF.folder_name).all()
    )
    cats = (LibraryCategory.query
            .filter_by(is_active=True)
            .order_by(LibraryCategory.library_type, LibraryCategory.sort_order)
            .all())
    grouped = {}
    for c in cats:
        d = c.to_dict()
        d["file_count"] = counts.get(c.name, 0)
        grouped.setdefault(c.library_type, []).append(d)
    return jsonify(grouped)


@api_upload_bp.route("/categories", methods=["POST"])
def create_category():
    """手动新增分类"""
    data = request.get_json() or {}
    lib = data.get("library_type", "知识库")
    name = (data.get("name") or "").strip()
    if lib not in ("知识库", "参考库", "风格库"):
        return jsonify({"error": "library_type 无效"}), 400
    if not name:
        return jsonify({"error": "请填写分类名"}), 400
    if LibraryCategory.query.filter_by(library_type=lib, name=name).first():
        return jsonify({"error": f"{lib}下已存在分类「{name}」"}), 400

    cat = LibraryCategory(
        library_type=lib, name=name,
        description=data.get("description", ""),
        aliases=json.dumps(data.get("aliases") or [], ensure_ascii=False),
        sort_order=data.get("sort_order", 500),
    )
    db.session.add(cat)
    db.session.commit()
    log.info(f"手动新增分类: {lib}/{name}")
    return jsonify({"success": True, "category": cat.to_dict()})


@api_upload_bp.route("/categories/<int:cat_id>", methods=["PUT"])
def update_category(cat_id):
    """改分类名/说明。改名时同步库里所有文件的 folder_name（不移动磁盘文件）"""
    cat = LibraryCategory.query.get_or_404(cat_id)
    data = request.get_json() or {}
    old_name = cat.name

    for field in ("name", "description", "sort_order", "is_active"):
        if field in data:
            setattr(cat, field, data[field])
    if "aliases" in data:
        cat.aliases = json.dumps(data["aliases"] or [], ensure_ascii=False)

    if cat.name != old_name:
        n = LibraryFile.query.filter_by(
            library_type=cat.library_type, folder_name=old_name
        ).update({"folder_name": cat.name}, synchronize_session=False)
        log.info(f"分类改名: {old_name} → {cat.name}，同步 {n} 个文件记录")
    db.session.commit()
    return jsonify({"success": True, "category": cat.to_dict()})


@api_upload_bp.route("/libraries/<int:file_id>/download", methods=["GET"])
def download_file(file_id):
    """下载原始文件"""
    lib_file = LibraryFile.query.get_or_404(file_id)
    if not os.path.exists(lib_file.stored_path):
        return jsonify({"error": "文件不存在"}), 404

    from flask import send_file
    log.info(f"下载文件: id={file_id}, file={lib_file.original_filename}")
    return send_file(
        lib_file.stored_path,
        as_attachment=True,
        download_name=lib_file.original_filename,
    )
