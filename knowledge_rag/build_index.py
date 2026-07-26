"""
向量知识库索引构建脚本
功能：
  - 扫描知识库目录中的所有 PDF 文件
  - 提取文本并按段落分块
  - 生成向量嵌入并存入 ChromaDB
  - 增量更新：只处理新增/修改的 PDF，清理已删除文件的旧向量
  - 每个 chunk 附带来源元数据（文件路径、分类、页码）

用法：
  python build_index.py              # 增量更新（默认）
  python build_index.py --full       # 完全重建（清空旧数据）
"""
import os
import sys
import json
import re
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# 确保 config 在 sentence_transformers 之前导入（设置 HF_ENDPOINT 等环境变量）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    KNOWLEDGE_BASE_DIR,
    CHROMA_DB_DIR,
    FINGERPRINT_FILE,
    EMBEDDING_MODEL,
    DEVICE,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    COLLECTION_NAME,
)

import fitz  # PyMuPDF
import docx  # python-docx
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
from tqdm import tqdm


# ============================================================
# PDF 文本提取
# ============================================================
def extract_text_from_pdf(pdf_path: str) -> List[Dict[str, object]]:
    """
    从 PDF 中提取文本，返回按页组织的列表。
    每页包含页码和文本内容。
    """
    pages = []
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").strip()
            if text:  # 跳过空白页
                pages.append({
                    "page": page_num + 1,
                    "text": text,
                })
        doc.close()
    except Exception as e:
        print(f"  [!] 提取失败 [{pdf_path}]: {e}")
    return pages


# ============================================================
# DOCX 文本提取
# ============================================================
def extract_text_from_docx(docx_path: str) -> List[Dict[str, object]]:
    """
    从 DOCX 中提取文本，整篇作为一个"页"。
    格式与 extract_text_from_pdf 保持一致。
    """
    try:
        doc = docx.Document(docx_path)
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        full_text = "\n".join(paragraphs)
        if full_text:
            return [{"page": 1, "text": full_text}]
    except Exception as e:
        print(f"  [!] 提取失败 [{docx_path}]: {e}")
    return []


# ============================================================
# TXT 文本提取
# ============================================================
def extract_text_from_txt(txt_path: str) -> List[Dict[str, object]]:
    """
    从 TXT 中提取文本，按 Markdown 标题（# ## ###）分页，
    或按固定长度分页。
    """
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  [!] 提取失败 [{txt_path}]: {e}")
        return []

    if not content.strip():
        return []

    # 按 Markdown 标题分割
    sections = re.split(r'\n(?=#{1,3}\s)', content)
    pages = []
    page_num = 0
    for section in sections:
        section = section.strip()
        if not section:
            continue
        # 如果单个 section 太长，继续按段落分
        if len(section) > 3000:
            paragraphs = section.split('\n\n')
            sub_text = ''
            for para in paragraphs:
                if len(sub_text) + len(para) > 3000:
                    if sub_text.strip():
                        page_num += 1
                        pages.append({"page": page_num, "text": sub_text.strip()})
                    sub_text = para
                else:
                    sub_text += '\n\n' + para if sub_text else para
            if sub_text.strip():
                page_num += 1
                pages.append({"page": page_num, "text": sub_text.strip()})
        else:
            page_num += 1
            pages.append({"page": page_num, "text": section})

    return pages


# ============================================================
# 文本分块
# ============================================================
def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    将长文本切分为重叠的块。
    优先按段落边界切分，保持语义完整性。
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    paragraphs = text.split("\n")
    current_chunk = ""
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_len = len(para)

        if current_len + para_len <= chunk_size:
            current_chunk += para + "\n"
            current_len += para_len + 1
        else:
            # 当前块已满，保存并开始新块
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            # 如果段落本身超过 chunk_size，硬切
            if para_len > chunk_size:
                for i in range(0, para_len, chunk_size - overlap):
                    sub = para[i:i + chunk_size]
                    if sub.strip():
                        chunks.append(sub.strip())
                current_chunk = ""
                current_len = 0
            else:
                # 重叠：保留前一块末尾的部分内容
                if chunks and overlap > 0:
                    prev = chunks[-1]
                    overlap_text = prev[-overlap:] if len(prev) > overlap else prev
                    current_chunk = overlap_text + "\n" + para + "\n"
                    current_len = len(current_chunk)
                else:
                    current_chunk = para + "\n"
                    current_len = para_len + 1

    # 收尾
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


# ============================================================
# 文件指纹管理
# ============================================================
def compute_file_fingerprint(filepath: str) -> str:
    """计算文件的 MD5 指纹，用于检测文件变更"""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_fingerprints() -> Dict[str, str]:
    """加载已存储的文件指纹"""
    if os.path.exists(FINGERPRINT_FILE):
        with open(FINGERPRINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_fingerprints(fingerprints: Dict[str, str]) -> None:
    """保存文件指纹"""
    os.makedirs(os.path.dirname(FINGERPRINT_FILE), exist_ok=True)
    with open(FINGERPRINT_FILE, "w", encoding="utf-8") as f:
        json.dump(fingerprints, f, ensure_ascii=False, indent=2)


# ============================================================
# 获取分类名称（PDF 所在的第一级子目录名）
# ============================================================
def get_category(pdf_path: str) -> str:
    """获取 PDF 的分类名 = 知识库下的一级子目录名"""
    rel = os.path.relpath(pdf_path, KNOWLEDGE_BASE_DIR)
    parts = rel.replace("\\", "/").split("/")
    if len(parts) > 1:
        return parts[0]
    return "未分类"


# ============================================================
# 索引构建核心逻辑
# ============================================================
def build_index(full_rebuild: bool = False) -> None:
    """
    构建/更新向量索引。

    Args:
        full_rebuild: 是否完全重建（清空旧数据重新导入）
    """
    print("=" * 60)
    print("  科幻写作 · 向量知识库构建器")
    print("=" * 60)

    # ---- 1. 扫描知识库文件 ----
    print("\n[1/5] 扫描知识库目录...")
    support_exts = (".pdf", ".docx", ".txt")
    doc_files = []
    for root, _, files in os.walk(KNOWLEDGE_BASE_DIR):
        for fname in files:
            if fname.lower().endswith(support_exts):
                doc_files.append(os.path.join(root, fname))

    if not doc_files:
        print(f"  [!] 在 {KNOWLEDGE_BASE_DIR} 下没有找到支持的文件（PDF/DOCX）")
        return

    print(f"  找到 {len(doc_files)} 个文件")

    # ---- 2. 加载嵌入模型 ----
    print(f"\n[2/5] 加载嵌入模型: {EMBEDDING_MODEL} ...")
    model = SentenceTransformer(EMBEDDING_MODEL, device=DEVICE)
    print(f"  模型已加载 (device={DEVICE})")

    # ---- 3. 初始化 ChromaDB ----
    print(f"\n[3/5] 初始化向量数据库: {CHROMA_DB_DIR} ...")
    os.makedirs(CHROMA_DB_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)

    if full_rebuild:
        try:
            client.delete_collection(COLLECTION_NAME)
            print("  已删除旧 collection，准备完全重建")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"  Collection: {COLLECTION_NAME}")

    # ---- 4. 增量检测 ----
    print(f"\n[4/5] 检测文件变更...")
    old_fingerprints = load_fingerprints()
    new_fingerprints = {}
    to_process = []
    skipped = 0

    if full_rebuild:
        to_process = doc_files
        print(f"  完全重建模式：将处理所有 {len(doc_files)} 个文件")
    else:
        for pdf_path in doc_files:
            fp = compute_file_fingerprint(pdf_path)
            new_fingerprints[pdf_path] = fp
            if old_fingerprints.get(pdf_path) != fp:
                to_process.append(pdf_path)
            else:
                skipped += 1

        # 检测已删除的文件
        deleted_files = set(old_fingerprints.keys()) - set(new_fingerprints.keys())
        if deleted_files:
            print(f"  检测到 {len(deleted_files)} 个已删除文件，正在清理旧向量...")
            for del_path in deleted_files:
                collection.delete(where={"source": del_path})
                print(f"    - 已清理: {os.path.basename(del_path)}")

        print(f"  新增/修改: {len(to_process)} 篇, 跳过(未变): {skipped} 篇")

    if not to_process:
        print("\n  [OK] 没有需要更新的文件，索引已是最新。")
        return

    # ---- 5. 处理文件并入库 ----
    print(f"\n[5/5] 提取文本、分块、生成嵌入...")
    total_chunks = 0

    for file_path in tqdm(to_process, desc="  处理进度", unit="篇"):
        category = get_category(file_path)
        fname = os.path.basename(file_path)

        # 如果是增量更新，先清理该文件的旧数据
        if not full_rebuild and old_fingerprints.get(file_path):
            collection.delete(where={"source": file_path})

        # 根据文件类型提取文本
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            pages = extract_text_from_pdf(file_path)
        elif ext == ".docx":
            pages = extract_text_from_docx(file_path)
        elif ext == ".txt":
            pages = extract_text_from_txt(file_path)
        else:
            continue
        if not pages:
            continue

        # 分块 + 生成嵌入
        for page_data in pages:
            page_num = page_data["page"]
            page_text = page_data["text"]
            chunks = chunk_text(page_text)

            if not chunks:
                continue

            # 批量生成嵌入
            embeddings = model.encode(chunks, show_progress_bar=False).tolist()

            # 准备 ChromaDB 数据
            ids = [f"{hashlib.md5(file_path.encode()).hexdigest()}_{total_chunks + i}"
                   for i in range(len(chunks))]
            metadatas = [
                {
                    "source": file_path,
                    "filename": fname,
                    "category": category,
                    "page": page_num,
                    "chunk_index": i,
                    "total_chunks_on_page": len(chunks),
                }
                for i in range(len(chunks))
            ]

            # 入库
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas,
            )
            total_chunks += len(chunks)

    # 保存指纹
    save_fingerprints(
        {fp: compute_file_fingerprint(fp) for fp in doc_files}
    )

    # ---- 完成 ----
    print(f"\n{'=' * 60}")
    print(f"  [OK] 索引构建完成！")
    print(f"  处理文件: {len(to_process)} 篇")
    print(f"  生成 chunk: {total_chunks} 个")
    print(f"  Collection 总量: {collection.count()} 条")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="构建科幻写作向量知识库")
    parser.add_argument(
        "--full", action="store_true",
        help="完全重建索引（清空旧数据）"
    )
    args = parser.parse_args()
    build_index(full_rebuild=args.full)
