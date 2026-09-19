"""
电子书导出工具
用法:
  python scripts/export_book.py <project_id>            # 同时导出 EPUB + PDF
  python scripts/export_book.py <project_id> epub       # 仅 EPUB
  python scripts/export_book.py <project_id> pdf        # 仅 PDF

按**作品**取章节（「从 IDEA 创建」的作品没有大纲，不能按 outline_id 取）。
传入大纲 ID 也能用，会自动解析到对应作品。
"""
import os
import sys
import re
import shutil
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_config import MYBOOKAPPS_ROOT
from database import db, Project, Chapter
from services.precha_service import strip_precha
from app import create_app


def build_markdown(project, chapters):
    """构建不含元数据的干净 Markdown 全书"""
    lines = [f"# {project.title}\n"]
    for ch in chapters:
        body = strip_precha(ch.content)
        title = ch.title or f"第{ch.chapter_number}章"
        lines.append(f"# {title}\n\n{body}\n")
    return "\n\n".join(lines)


def export_epub(md_text, title, output_dir):
    """pandoc → EPUB（带目录）"""
    md_path = os.path.join(output_dir, "_book.md")
    epub_path = os.path.join(output_dir, f"{title}.epub")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    subprocess.run([
        "pandoc", md_path,
        "-o", epub_path,
        "--toc", "--toc-depth=2",
        f"--metadata", f"title={title}",
    ], check=True, capture_output=True)

    os.remove(md_path)
    return epub_path


def export_pdf(md_text, title, output_dir):
    """pandoc → HTML → fpdf2 + CJK 字体 → PDF"""
    pdf_path = os.path.join(output_dir, f"{title}.pdf")

    # 1. pandoc markdown → HTML
    md_path = os.path.join(output_dir, "_book.md")
    html_path = os.path.join(output_dir, "_book.html")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    subprocess.run([
        "pandoc", md_path,
        "-o", html_path,
        "--standalone",
        f"--metadata", f"title={title}",
    ], check=True, capture_output=True)

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 2. fpdf2 渲染 PDF（带 CJK 字体）
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    # 查找系统中文字体
    font_path = None
    for candidate in [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]:
        if os.path.exists(candidate):
            font_path = candidate
            break

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    if font_path:
        pdf.add_font("CJK", "", font_path)
        pdf.add_font("CJK", "B", font_path)
    else:
        pdf.add_font("CJK", "", "Helvetica")
        pdf.add_font("CJK", "B", "Helvetica")

    # 简单 HTML 解析：提取纯文本段落
    # 去掉 HTML 标签
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&mdash;', '—', text)
    text = re.sub(r'&[a-z]+;', '', text)

    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

    for para in paragraphs:
        if para.startswith('#') or len(para) < 40 and para.isascii():
            # 标题
            pdf.set_font("CJK", "B", 14)
            clean = para.lstrip('#').strip()
            pdf.cell(0, 10, clean, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)
        else:
            pdf.set_font("CJK", "", 10)
            pdf.multi_cell(0, 6, para)
            pdf.ln(1)

    pdf.output(pdf_path)

    # 清理
    os.remove(md_path)
    os.remove(html_path)
    return pdf_path


def natural_key(filename):
    """CHA1 < CHA2 < … < CHA10 < 终章 —— 按数字比，不按字典序"""
    m = re.search(r"(\d+)", filename)
    return (int(m.group(1)) if m else 10 ** 9, filename)


# 这些不是正文：设定、大纲、创作指南、法条参考
SKIP_MARKERS = ("IDEA", "OUTLINE", "创作指南", "法条参考")


def collect_chapter_files(book_dir):
    names = []
    for fn in os.listdir(book_dir):
        if not fn.lower().endswith(".md") or fn.startswith("_"):
            continue
        if any(marker in fn for marker in SKIP_MARKERS):
            continue
        names.append(fn)
    return sorted(names, key=natural_key)


def export_from_dir(book_dir, fmt="both"):
    """
    按目录导出（write_books/XX 那种手写章节的目录）。

    导出电子书的原始用法，与作品库那条路线并存 —— 不是所有稿子都在数据库里。
    """
    if not os.path.isdir(book_dir):
        print(f"错误：目录不存在 {book_dir}")
        return None

    files = collect_chapter_files(book_dir)
    if not files:
        print(f"错误：{book_dir} 下没有章节 .md")
        return None

    title = os.path.basename(os.path.normpath(book_dir))
    lines = [f"# {title}\n"]
    for fn in files:
        with open(os.path.join(book_dir, fn), "r", encoding="utf-8") as f:
            body = strip_precha(f.read())
        stem = os.path.splitext(fn)[0]
        lines.append(f"# {stem}\n\n{body}\n")

    output_dir = os.path.join(book_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    print(f"📖 导出: {title}")
    print(f"   章节数: {len(files)}")
    for fn in files:
        print(f"     - {fn}")

    return _write_formats("\n\n".join(lines), title, output_dir, fmt)


def _write_formats(md_text, title, output_dir, fmt):
    """EPUB / PDF 的落盘，两条导出路线共用"""
    results = {}
    if fmt in ("epub", "both"):
        epub_path = export_epub(md_text, title, output_dir)
        results["epub"] = epub_path
        print(f"   EPUB: {epub_path} ({os.path.getsize(epub_path) / 1024:.1f} KB)")
    if fmt in ("pdf", "both"):
        pdf_path = export_pdf(md_text, title, output_dir)
        results["pdf"] = pdf_path
        print(f"   PDF:  {pdf_path} ({os.path.getsize(pdf_path) / 1024:.1f} KB)")
    return results


def export_book(project_id, fmt="both"):
    """
    主入口。按**作品**取章节 ——
    「从 IDEA 创建」的作品没有大纲，所以不能再按 outline_id 取。
    传入的 id 若不是作品 id，会尝试当作大纲 id 解析（兼容旧调用）。
    """
    app = create_app()
    with app.app_context():
        project = db.session.get(Project, project_id)
        if project is None:
            # 兼容：传进来的可能是大纲 id
            project = Project.query.filter_by(outline_id=project_id).first()
        if project is None:
            print(f"错误：作品 id={project_id} 不存在")
            return None

        chapters = (
            Chapter.query
            .filter(Chapter.project_id == project.id,
                    Chapter.status == "completed",
                    Chapter.content.isnot(None),
                    Chapter.content != "")
            .order_by(Chapter.chapter_number)
            .all()
        )
        if not chapters:
            # 一章都没定稿时，退回导出所有有正文的，避免导出为空
            chapters = (
                Chapter.query
                .filter(Chapter.project_id == project.id,
                        Chapter.content.isnot(None),
                        Chapter.content != "")
                .order_by(Chapter.chapter_number)
                .all()
            )
            if chapters:
                print(f"提示：没有已定稿章节，改为导出 {len(chapters)} 个有正文的章节")
        if not chapters:
            print("错误：没有任何有正文的章节")
            return None

        raw_title = project.title or "未命名"
        # 清理文件名中的特殊字符（Windows 不允许《》等）
        safe_title = re.sub(r'[\\/*?:"<>|《》]', '', raw_title)
        if not safe_title.strip():
            safe_title = "未命名"

        title = safe_title
        output_dir = os.path.join(MYBOOKAPPS_ROOT, "output", title)
        os.makedirs(output_dir, exist_ok=True)

        print(f"📖 导出: {title}")
        print(f"   章节数: {len(chapters)}")

        md_text = build_markdown(project, chapters)
        return _write_formats(md_text, title, output_dir, fmt)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="电子书导出工具")
    parser.add_argument("target",
                        help="作品 ID（也接受大纲 ID），或章节所在目录如 write_books/XX")
    parser.add_argument("format", nargs="?", default="both",
                        choices=["epub", "pdf", "both"])
    args = parser.parse_args()

    # 数字当作品 ID 查库，其余当目录扫 .md —— 「导出 XX」两种都认
    if str(args.target).strip().isdigit():
        export_book(int(args.target), args.format)
    else:
        export_from_dir(args.target, args.format)
