"""
文件处理服务 — 提取 PDF/DOCX/TXT/EPUB 文本
"""
import os
import re


def extract_text(filepath, max_chars=500):
    """
    提取文件文本（前 max_chars 字用于分类）。
    支持: PDF, DOCX, TXT, EPUB
    """
    ext = os.path.splitext(filepath)[1].lower()

    try:
        if ext == ".pdf":
            return _extract_pdf(filepath, max_chars)
        elif ext == ".docx":
            return _extract_docx(filepath, max_chars)
        elif ext == ".txt" or ext == ".md":
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
