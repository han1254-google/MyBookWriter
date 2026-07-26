"""
文件上传 API
"""
import os
import json
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from database import db, LibraryFile
from services.library_service import classify_file, save_file, list_libraries, delete_file
from services.file_service import extract_text

api_upload_bp = Blueprint("api_upload", __name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".epub"}


@api_upload_bp.route("/upload", methods=["POST"])
def upload_file():
    """上传文件并自动分类"""
    if "file" not in request.files:
        return jsonify({"error": "未选择文件"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "文件名为空"}), 400

    # 验证扩展名
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"不支持的格式: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    # 保存临时文件用于提取文本
    safe_name = secure_filename(file.filename)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        # 提取文本预览
        content_preview = extract_text(tmp_path, max_chars=500)

        # DeepSeek 分类
        classification = classify_file(safe_name, content_preview)
        library_type = classification["library_type"]
        folder_name = classification["folder_name"]

        # 保存文件
        file.seek(0)  # 重置文件指针
        stored_path = save_file(file, library_type, folder_name)

        # 写入数据库
        lib_file = LibraryFile(
            library_type=library_type,
            folder_name=folder_name,
            original_filename=safe_name,
            stored_path=stored_path,
            file_type=ext.lstrip("."),
        )
        db.session.add(lib_file)
        db.session.commit()

        return jsonify({
            "success": True,
            "id": lib_file.id,
            "library_type": library_type,
            "folder_name": folder_name,
            "filename": safe_name,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@api_upload_bp.route("/libraries", methods=["GET"])
def get_libraries():
    """列出所有库结构"""
    data = list_libraries()
    # 合并数据库记录
    files = LibraryFile.query.order_by(LibraryFile.created_at.desc()).all()
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
    return jsonify([f.to_dict() for f in files])


@api_upload_bp.route("/libraries/<int:file_id>", methods=["DELETE"])
def delete_library_file(file_id):
    """删除文件"""
    lib_file = LibraryFile.query.get_or_404(file_id)
    # 删除物理文件
    if os.path.exists(lib_file.stored_path):
        delete_file(lib_file.stored_path)
    db.session.delete(lib_file)
    db.session.commit()
    return jsonify({"success": True})
