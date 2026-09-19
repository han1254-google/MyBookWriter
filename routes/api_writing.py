"""
写作导出 API

章节的生成/保存/续写/重写已迁移到 routes/api_projects.py（按作品组织），
这里只保留导出相关的接口。

导出按 **作品(project)** 取章节，而不是按大纲 —— 因为「从 IDEA 创建」的作品没有大纲。
"""
import os
from flask import Blueprint, request, jsonify, send_file

from database import db, Project, Chapter, Outline
from services.precha_service import strip_precha
from logger import get_logger

api_writing_bp = Blueprint("api_writing", __name__)
log = get_logger("api.writing")


def _resolve_project(project_id=None, outline_id=None):
    """按作品 id 或大纲 id 定位作品（兼容旧链接里传的是 outline_id）"""
    if project_id:
        return db.session.get(Project, project_id)
    if outline_id:
        proj = Project.query.filter_by(outline_id=outline_id).first()
        if proj:
            return proj
        outline = db.session.get(Outline, outline_id)
        if outline and outline.project_id:
            return db.session.get(Project, outline.project_id)
    return None


def _export_chapters(project, only_completed=True):
    """取用于导出的章节：有正文的，按章号排序"""
    q = Chapter.query.filter(
        Chapter.project_id == project.id,
        Chapter.content.isnot(None),
        Chapter.content != "",
    )
    if only_completed:
        completed = q.filter(Chapter.status == "completed").order_by(
            Chapter.chapter_number).all()
        # 一章都没定稿时，退回导出所有有正文的，避免「导出为空」
        if completed:
            return completed, True
    return q.order_by(Chapter.chapter_number).all(), False


def build_markdown(project, chapters):
    """构建不含 PRECHA 元数据的干净 Markdown 全书"""
    lines = [f"# {project.title}\n"]
    if project.synopsis:
        lines.append(f"> {project.synopsis}\n")
    for ch in chapters:
        body = strip_precha(ch.content)
        title = ch.title or f"第{ch.chapter_number}章"
        lines.append(f"\n# {title}\n\n{body}\n")
    return "\n".join(lines)


@api_writing_bp.route("/writing/export/<int:project_id>", methods=["POST"])
def export_markdown(project_id):
    """导出全书为单一 Markdown 文本"""
    data = request.get_json(silent=True) or {}
    only_completed = data.get("only_completed", True)

    project = _resolve_project(project_id=project_id,
                               outline_id=data.get("outline_id"))
    if project is None:
        project = _resolve_project(outline_id=project_id)   # 兼容旧链接
    if project is None:
        return jsonify({"error": "作品不存在"}), 404

    chapters, used_completed = _export_chapters(project, only_completed)
    if not chapters:
        log.warning(f"导出失败: 没有任何有正文的章节, project={project.id}")
        return jsonify({"error": "还没有写好的章节可以导出"}), 400

    full_book = build_markdown(project, chapters)
    word_count = sum(c.word_count or 0 for c in chapters)
    log.info(f"导出全书: project={project.id}, {project.title}, "
             f"{len(chapters)}章, {word_count}字, "
             f"{'仅定稿' if used_completed else '含草稿'}")

    return jsonify({
        "success": True,
        "title": project.title,
        "full_text": full_book,
        "chapter_count": len(chapters),
        "word_count": word_count,
        "only_completed": used_completed,
    })


@api_writing_bp.route("/writing/export/<int:project_id>/<fmt>", methods=["POST"])
def export_book_file(project_id, fmt):
    """导出电子书文件（epub / pdf）"""
    if fmt not in ("epub", "pdf"):
        return jsonify({"error": "格式不支持，请使用 epub 或 pdf"}), 400

    project = _resolve_project(project_id=project_id)
    if project is None:
        project = _resolve_project(outline_id=project_id)
    if project is None:
        return jsonify({"error": "作品不存在"}), 404

    from scripts.export_book import export_book as _export
    try:
        result = _export(project.id, fmt)
        if not result or fmt not in result:
            return jsonify({
                "error": f"{fmt.upper()} 导出失败，请确认已安装 pandoc"
                         + ("（PDF 还需要 fpdf2：pip install fpdf2）"
                            if fmt == "pdf" else "")
            }), 500

        file_path = result[fmt]
        fname = os.path.basename(file_path)
        log.info(f"导出{fmt}: project={project.id}, file={fname}")
        return send_file(file_path, as_attachment=True, download_name=fname)
    except Exception as e:
        log.error(f"导出{fmt}失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@api_writing_bp.route("/writing/chapters/<int:project_id>", methods=["GET"])
def get_chapters_legacy(project_id):
    """
    兼容旧前端：按作品或大纲 id 列章节。
    新代码请用 GET /api/projects/<id>/chapters。
    """
    project = _resolve_project(project_id=project_id)
    if project is None:
        project = _resolve_project(outline_id=project_id)
    if project is None:
        return jsonify([])
    chapters = Chapter.query.filter_by(project_id=project.id).order_by(
        Chapter.sort_key).all()
    return jsonify([c.to_summary() for c in chapters])
