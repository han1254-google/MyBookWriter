"""
页面路由 — HTML 渲染
"""
from flask import Blueprint, render_template
from database import db, Idea, Outline, Chapter, LibraryFile
from services.rag_service import rag

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    """首页仪表盘"""
    stats = {
        "ideas": Idea.query.count(),
        "outlines": Outline.query.count(),
        "chapters": Chapter.query.count(),
        "files": LibraryFile.query.count(),
    }
    recent_ideas = Idea.query.order_by(Idea.updated_at.desc()).limit(5).all()
    recent_outlines = Outline.query.order_by(Outline.updated_at.desc()).limit(5).all()
    rag_available = rag.is_available
    rag_categories = rag.categories if rag_available else []

    return render_template("index.html",
                           stats=stats,
                           recent_ideas=recent_ideas,
                           recent_outlines=recent_outlines,
                           rag_available=rag_available,
                           rag_categories=rag_categories)


@pages_bp.route("/upload")
def upload_page():
    """上传管理页"""
    from services.library_service import list_libraries
    libraries = list_libraries()
    recent_files = LibraryFile.query.order_by(LibraryFile.created_at.desc()).limit(20).all()
    return render_template("upload.html",
                           libraries=libraries,
                           recent_files=recent_files)


@pages_bp.route("/ideas")
def ideas_page():
    """创意工坊列表"""
    ideas = Idea.query.order_by(Idea.updated_at.desc()).all()
    rag_categories = rag.categories if rag.is_available else []
    return render_template("ideas.html", ideas=ideas, rag_categories=rag_categories)


@pages_bp.route("/ideas/<int:idea_id>")
def idea_detail(idea_id):
    """创意详情/对话页"""
    idea = Idea.query.get_or_404(idea_id)
    return render_template("ideas_detail.html", idea=idea)


@pages_bp.route("/outlines")
def outlines_page():
    """大纲工坊列表"""
    outlines = Outline.query.order_by(Outline.updated_at.desc()).all()
    ideas = Idea.query.order_by(Idea.updated_at.desc()).all()
    return render_template("outlines.html", outlines=outlines, ideas=ideas)


@pages_bp.route("/outlines/<int:outline_id>")
def outline_detail(outline_id):
    """大纲详情页"""
    outline = Outline.query.get_or_404(outline_id)
    chapters = Chapter.query.filter_by(outline_id=outline_id).order_by(Chapter.chapter_number).all()
    return render_template("outlines_detail.html", outline=outline, chapters=chapters)


@pages_bp.route("/writing")
def writing_page():
    """写作工坊入口"""
    outlines = Outline.query.order_by(Outline.updated_at.desc()).all()
    # 已经写了章节的大纲
    writing_outlines = []
    for o in outlines:
        ch_count = Chapter.query.filter_by(outline_id=o.id).count()
        if ch_count > 0:
            writing_outlines.append({"outline": o, "chapter_count": ch_count})
    return render_template("writing.html",
                           outlines=outlines,
                           writing_outlines=writing_outlines)


@pages_bp.route("/writing/<int:outline_id>")
@pages_bp.route("/writing/<int:outline_id>/<int:chapter_num>")
def writing_chapter(outline_id, chapter_num=None):
    """章节写作页"""
    outline = Outline.query.get_or_404(outline_id)
    idea = Idea.query.get(outline.idea_id) if outline.idea_id else None
    chapters = Chapter.query.filter_by(outline_id=outline_id).order_by(Chapter.chapter_number).all()

    if chapter_num is None:
        # 默认到下一个待写章节
        chapter_num = len(chapters) + 1

    # 获取当前章节（可能不存在）
    current_chapter = Chapter.query.filter_by(
        outline_id=outline_id, chapter_number=chapter_num
    ).first()

    # 获取上一章（用于 PRECHA）
    prev_chapter = Chapter.query.filter_by(
        outline_id=outline_id, chapter_number=chapter_num - 1
    ).first()

    rag_categories = rag.categories if rag.is_available else []

    return render_template("writing_chapter.html",
                           outline=outline,
                           idea=idea,
                           chapters=chapters,
                           chapter_num=chapter_num,
                           current_chapter=current_chapter,
                           prev_chapter=prev_chapter,
                           rag_categories=rag_categories)


@pages_bp.route("/rewrite")
def rewrite_page():
    """改写工坊"""
    return render_template("rewrite.html")
