"""
电子书导出工具
用法:
  python scripts/export_book.py <outline_id>            # 同时导出 EPUB + PDF
  python scripts/export_book.py <outline_id> epub       # 仅 EPUB
  python scripts/export_book.py <outline_id> pdf        # 仅 PDF
"""
import os
import sys
import re
import shutil
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_config import MYBOOKAPPS_ROOT
from database import db, Outline, Chapter
from app import create_app


def clean_chapter(content):
    """去掉 PRECHA 元数据，只保留 CONTENT 部分"""
    m = re.search(r'## CONTENT\s*\n(.+)', content, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 如果没有 PRECHA，返回原文
    m2 = re.search(r'^#.*?\n(.+)', content, re.DOTALL)
    if m2:
        return m2.group(1).strip()
    return content.strip()


def build_markdown(outline, chapters):
    """构建不含元数据的干净 Markdown 全书"""
    lines = []
    lines.append(f"# {outline.title}\n")
    for ch in chapters:
        body = clean_chapter(ch.content)
        lines.append(f"# {ch.title}\n\n{body}\n")
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


def export_book(outline_id, fmt="both"):
    """主入口"""
    app = create_app()
    with app.app_context():
        outline = Outline.query.get(outline_id)
        if not outline:
            print(f"错误：大纲 id={outline_id} 不存在")
            return None

        chapters = (
            Chapter.query
            .filter_by(outline_id=outline_id, status="completed")
            .order_by(Chapter.chapter_number)
            .all()
        )
        if not chapters:
            print("错误：没有已完成的章节")
            return None

        raw_title = outline.title or "未命名"
        # 清理文件名中的特殊字符（Windows 不允许《》等）
        safe_title = re.sub(r'[\\/*?:"<>|《》]', '', raw_title)
        if not safe_title.strip():
            safe_title = "未命名"

        title = safe_title
        output_dir = os.path.join(MYBOOKAPPS_ROOT, "output", title)
        os.makedirs(output_dir, exist_ok=True)

        print(f"📖 导出: {title}")
        print(f"   章节数: {len(chapters)}")

        md_text = build_markdown(outline, chapters)
        results = {}

        if fmt in ("epub", "both"):
            epub_path = export_epub(md_text, title, output_dir)
            epub_size = os.path.getsize(epub_path) / 1024
            results["epub"] = epub_path
            print(f"   EPUB: {epub_path} ({epub_size:.1f} KB)")

        if fmt in ("pdf", "both"):
            pdf_path = export_pdf(md_text, title, output_dir)
            pdf_size = os.path.getsize(pdf_path) / 1024
            results["pdf"] = pdf_path
            print(f"   PDF:  {pdf_path} ({pdf_size:.1f} KB)")

        return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="电子书导出工具")
    parser.add_argument("outline_id", type=int, help="大纲 ID")
    parser.add_argument("format", nargs="?", default="both",
                        choices=["epub", "pdf", "both"])
    args = parser.parse_args()
    export_book(args.outline_id, args.format)
