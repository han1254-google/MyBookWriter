"""
文件上传 API
"""
import os
import json
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from database import db, LibraryFile
from services.library_service import classify_file, save_file, list_libraries, delete_file, extract_style
from services.file_service import extract_text
from services.index_service import index_file, remove_file_index
from logger import get_logger

api_upload_bp = Blueprint("api_upload", __name__)
log = get_logger("api.upload")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".epub"}


def _auto_summarize(file_id):
    """后台生成AI摘要（不阻塞上传响应）"""
    from services.deepseek_service import deepseek_flash
    try:
        lib_file = LibraryFile.query.get(file_id)
        if not lib_file or not lib_file.content_preview or lib_file.ai_summary:
            return
        prompt = f"""请用3-5句话总结以下文档的核心内容，用中文，简洁直接。
文件名：{lib_file.original_filename}
内容：{lib_file.content_preview[:3000]}"""
        summary = deepseek_flash.chat(prompt, max_tokens=500)
        lib_file.ai_summary = summary.strip()
        db.session.commit()
        log.info(f"自动摘要完成: id={file_id}, {len(summary)} 字符")
    except Exception as e:
        log.error(f"自动摘要失败: id={file_id}: {e}")


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

    safe_name = secure_filename(file.filename)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    log.info(f"开始处理上传: {safe_name} (ext={ext}, size={os.path.getsize(tmp_path)}B, user_library={user_library or 'AI自动'})")

    try:
        content_preview = extract_text(tmp_path, max_chars=2000)
        log.debug(f"文本提取完成: {len(content_preview)} 字符")

        classification = classify_file(safe_name, content_preview, user_library)
        library_type = classification["library_type"]
        folder_name = classification["folder_name"]
        log.info(f"分类结果: {library_type}/{folder_name}")

        # 风格库特殊处理：AI 提取风格特征
        style_analysis = ""
        if library_type == "风格库":
            log.info(f"风格库文件，开始提取风格特征...")
            style_analysis = extract_style(content_preview, safe_name)
            log.debug(f"风格分析: {style_analysis[:100]}...")

        file.seek(0)
        stored_path = save_file(file, library_type, folder_name)
        log.info(f"文件已保存: {stored_path}")

        lib_file = LibraryFile(
            library_type=library_type,
            folder_name=folder_name,
            original_filename=safe_name,
            stored_path=stored_path,
            file_type=ext.lstrip("."),
            style_analysis=style_analysis,
            content_preview=content_preview[:2000],
        )
        db.session.add(lib_file)
        db.session.commit()
        log.info(f"数据库记录已创建: id={lib_file.id}, type={library_type}, folder={folder_name}")

        # 自动写入向量数据库 + 生成AI摘要（后台线程，不阻塞响应）
        import threading
        threading.Thread(
            target=index_file,
            args=(stored_path, library_type, folder_name),
            daemon=True,
        ).start()
        # 后台生成AI摘要
        threading.Thread(
            target=_auto_summarize,
            args=(lib_file.id,),
            daemon=True,
        ).start()

        return jsonify({
            "success": True,
            "id": lib_file.id,
            "library_type": library_type,
            "folder_name": folder_name,
            "filename": safe_name,
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
def summarize_file(file_id):
    """AI 生成文件摘要"""
    lib_file = LibraryFile.query.get_or_404(file_id)
    if lib_file.ai_summary:
        return jsonify({"success": True, "summary": lib_file.ai_summary, "cached": True})

    if not lib_file.content_preview:
        return jsonify({"error": "无法提取文件内容"}), 400

    log.info(f"生成摘要: id={file_id}, file={lib_file.original_filename}")
    from services.deepseek_service import deepseek_flash

    prompt = f"""请用 3-5 句话总结以下文档的核心内容。用中文。简洁、直接。

文件名：{lib_file.original_filename}
内容预览：
{lib_file.content_preview[:3000]}

格式：直接写摘要，不要"本文"之类的开头。"""

    try:
        summary = deepseek_flash.chat(prompt, max_tokens=500)
        lib_file.ai_summary = summary.strip()
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
