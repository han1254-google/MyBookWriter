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

        # 自动写入向量数据库（后台线程，不阻塞响应）
        import threading
        threading.Thread(
            target=index_file,
            args=(stored_path, library_type, folder_name),
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
        # 从向量数据库移除
        remove_file_index(lib_file.stored_path)
        # 删物理文件
        delete_file(lib_file.stored_path)
    db.session.delete(lib_file)
    db.session.commit()
    return jsonify({"success": True})
