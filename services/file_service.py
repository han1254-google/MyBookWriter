"""
文件处理服务 — 提取 PDF/DOCX/TXT/EPUB 文本

两种提取模式：
  extract_text()  取开头若干字 —— 用于分类
  sample_text()   全文均匀抽样 —— 用于摘要

为什么要区分：
  原来摘要也是拿开头 2000 字生成的，而 PDF 的开头是标题页/作者/机构，
  epub 的开头是版权页/目录，导致摘要讲的全是封面信息而不是正文内容。
"""
import os
import re


def extract_text(filepath, max_chars=500):
    """提取文件开头的文本（用于分类）。支持 PDF / DOCX / TXT / MD / EPUB。"""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".pdf":
            return _extract_pdf(filepath, max_chars)
        elif ext == ".docx":
            return _extract_docx(filepath, max_chars)
        elif ext in (".txt", ".md"):
            return _extract_txt(filepath, max_chars)
        elif ext == ".epub":
            return _extract_epub(filepath, max_chars)
        else:
            return f"[不支持的格式: {ext}]"
    except Exception as e:
        return f"[提取失败: {e}]"


def extract_full_text(filepath):
    """提取文件全部文本"""
    return extract_text(filepath, max_chars=None)


def _extract_pdf(filepath, max_chars):
    import fitz
    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text("text")
        if max_chars and len(text) >= max_chars:
            break
    doc.close()
    return text[:max_chars] if max_chars else text


def _extract_docx(filepath, max_chars):
    import docx
    doc = docx.Document(filepath)
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return text[:max_chars] if max_chars else text


def _extract_txt(filepath, max_chars):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return text[:max_chars] if max_chars else text


def _extract_epub(filepath, max_chars):
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.read_epub(filepath)
    text = ""
    for item in book.get_items_of_type(9):  # ITEM_DOCUMENT = 9
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text += soup.get_text() + "\n"
        if max_chars and len(text) >= max_chars:
            break
    return text[:max_chars] if max_chars else text


# ============================================================
# 全文抽样（摘要用）
# ============================================================
HEAD_CHARS = 1500      # 开头留多少（交代主题）
SAMPLE_COUNT = 8       # 从正文均匀取几段
SAMPLE_CHARS = 800     # 每段多长
TOC_CHARS = 1200       # 目录最多留多长


def sample_text(filepath, head=HEAD_CHARS, n_samples=SAMPLE_COUNT,
                sample_chars=SAMPLE_CHARS):
    """
    生成用于摘要的抽样文本：目录 + 开头 + 正文均匀抽样。

    这样摘要才会讲正文在说什么，而不是照抄标题页。

    Returns:
        (sample_text, meta)  meta = {char_count, page_count, toc_found}
    """
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".pdf":
            pages, toc = _read_pdf_pages(filepath)
        elif ext == ".epub":
            pages, toc = _read_epub_sections(filepath)
        elif ext == ".docx":
            pages, toc = [_extract_docx(filepath, None)], ""
        elif ext in (".txt", ".md"):
            pages, toc = [_extract_txt(filepath, None)], _markdown_toc(
                _extract_txt(filepath, None))
        else:
            return f"[不支持的格式: {ext}]", {}
    except Exception as e:
        return f"[抽样失败: {e}]", {}

    pages = [p for p in pages if p and p.strip()]
    full = "\n\n".join(pages)
    meta = {
        "char_count": len(full),
        "page_count": len(pages),
        "toc_found": bool(toc.strip()),
    }

    if not full.strip():
        return "", meta

    parts = []
    if toc.strip():
        parts.append(f"【目录】\n{toc.strip()[:TOC_CHARS]}")
    parts.append(f"【开头】\n{full[:head]}")

    # 从开头之后的部分均匀取样
    body = full[head:]
    if len(body) > sample_chars:
        step = max(1, len(body) // n_samples)
        for i in range(n_samples):
            start = i * step
            if start >= len(body):
                break
            seg = body[start:start + sample_chars].strip()
            if len(seg) < 100:
                continue
            pct = int(100 * start / max(1, len(body)))
            parts.append(f"【正文 {pct}% 处】\n{seg}")

    return "\n\n".join(parts), meta


def _read_pdf_pages(filepath):
    """返回 (页文本列表, 目录文本)"""
    import fitz
    doc = fitz.open(filepath)
    pages = [doc[i].get_text("text").strip() for i in range(len(doc))]
    toc_entries = []
    try:
        for level, title, _page in doc.get_toc():
            toc_entries.append("  " * max(0, level - 1) + str(title))
    except Exception:
        pass
    doc.close()
    return pages, "\n".join(toc_entries)


def _read_epub_sections(filepath):
    """返回 (章节文本列表, 目录文本)"""
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.read_epub(filepath)
    sections = []
    for item in book.get_items_of_type(9):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        txt = soup.get_text("\n").strip()
        if txt:
            sections.append(txt)

    toc_entries = []

    def walk(nodes, depth=0):
        for node in nodes:
            if isinstance(node, (list, tuple)):
                walk(node, depth)
            else:
                title = getattr(node, "title", None)
                if title:
                    toc_entries.append("  " * depth + str(title))
                children = getattr(node, "subitems", None)
                if children:
                    walk(children, depth + 1)

    try:
        walk(book.toc)
    except Exception:
        pass

    return sections, "\n".join(toc_entries)


def _markdown_toc(text):
    """从 markdown 里提取标题作为目录"""
    if not text:
        return ""
    lines = []
    for m in re.finditer(r"^(#{1,4})\s+(.+?)\s*$", text, re.MULTILINE):
        lines.append("  " * (len(m.group(1)) - 1) + m.group(2))
    return "\n".join(lines)
