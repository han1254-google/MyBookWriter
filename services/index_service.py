"""
单文件即时索引服务
上传文件后自动写入 ChromaDB，无需手动 build_index
"""
import os
import sys
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge_rag"))
from config import (
    SOURCE_DIRS,
    CHROMA_DB_DIR,
    FINGERPRINT_FILE,
    EMBEDDING_MODEL,
    DEVICE,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    COLLECTION_NAME,
)

import chromadb
from sentence_transformers import SentenceTransformer
from logger import get_logger

log = get_logger("service.index")

# 懒加载全局实例
_model = None
_client = None
_collection = None


def _get_model():
    global _model
    if _model is None:
        log.info(f"加载嵌入模型: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL, device=DEVICE)
    return _model


def _get_collection():
    global _client, _collection
    if _collection is None:
        os.makedirs(CHROMA_DB_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """文本分块，与 build_index.py 保持一致"""
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
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            if para_len > chunk_size:
                for i in range(0, para_len, chunk_size - overlap):
                    sub = para[i:i + chunk_size]
                    if sub.strip():
                        chunks.append(sub.strip())
                current_chunk = ""
                current_len = 0
            else:
                if chunks and overlap > 0:
                    prev = chunks[-1]
                    overlap_text = prev[-overlap:] if len(prev) > overlap else prev
                    current_chunk = overlap_text + "\n" + para + "\n"
                    current_len = len(current_chunk)
                else:
                    current_chunk = para + "\n"
                    current_len = para_len + 1

    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks


def _extract_text(file_path):
    """从文件提取文本"""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        import fitz
        pages = []
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            text = doc[page_num].get_text("text").strip()
            if text:
                pages.append({"page": page_num + 1, "text": text})
        doc.close()
        return pages

    elif ext == ".docx":
        import docx
        doc = docx.Document(file_path)
        text = "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
        return [{"page": 1, "text": text}] if text else []

    elif ext == ".txt" or ext == ".md":
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        return [{"page": 1, "text": text}] if text.strip() else []

    return []


def index_file(file_path, library_type, folder_name):
    """
    将单个文件即时写入 ChromaDB。

    Args:
        file_path: 文件的绝对路径
        library_type: 知识库/参考库/风格库
        folder_name: 子文件夹名

    Returns:
        chunk_count: 写入的 chunk 数
    """
    log.info(f"开始索引: {os.path.basename(file_path)} → {library_type}/{folder_name}")

    try:
        # 1. 提取文本
        pages = _extract_text(file_path)
        if not pages:
            log.warning(f"文件无可提取文本: {file_path}")
            return 0

        # 2. 删除旧索引（如果有）
        collection = _get_collection()
        collection.delete(where={"source": file_path})

        # 3. 逐页分块 + 嵌入 + 写入
        model = _get_model()
        fname = os.path.basename(file_path)
        total_chunks = 0

        for page_data in pages:
            page_num = page_data["page"]
            page_text = page_data["text"]
            chunks = _chunk_text(page_text)
            if not chunks:
                continue

            embeddings = model.encode(chunks, show_progress_bar=False).tolist()

            ids = [f"{hashlib.md5(file_path.encode()).hexdigest()}_{total_chunks + i}"
                   for i in range(len(chunks))]
            metadatas = [
                {
                    "source": file_path,
                    "filename": fname,
                    "library_type": library_type,
                    "category": folder_name,
                    "page": page_num,
                    "chunk_index": i,
                    "total_chunks_on_page": len(chunks),
                }
                for i in range(len(chunks))
            ]

            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas,
            )
            total_chunks += len(chunks)

        # 4. 更新指纹
        import json
        fingerprints = {}
        if os.path.exists(FINGERPRINT_FILE):
            with open(FINGERPRINT_FILE, "r", encoding="utf-8") as f:
                fingerprints = json.load(f)

        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        fingerprints[file_path] = hasher.hexdigest()

        os.makedirs(os.path.dirname(FINGERPRINT_FILE), exist_ok=True)
        with open(FINGERPRINT_FILE, "w", encoding="utf-8") as f:
            json.dump(fingerprints, f, ensure_ascii=False, indent=2)

        log.info(f"索引完成: {fname} → {total_chunks} chunks, collection总量={collection.count()}")
        return total_chunks

    except Exception as e:
        log.error(f"索引失败: {os.path.basename(file_path)}: {type(e).__name__}: {e}", exc_info=True)
        return 0


def remove_file_index(file_path):
    """从 ChromaDB 中删除文件的索引"""
    try:
        collection = _get_collection()
        collection.delete(where={"source": file_path})

        # 更新指纹
        import json
        if os.path.exists(FINGERPRINT_FILE):
            with open(FINGERPRINT_FILE, "r", encoding="utf-8") as f:
                fingerprints = json.load(f)
            fingerprints.pop(file_path, None)
            with open(FINGERPRINT_FILE, "w", encoding="utf-8") as f:
                json.dump(fingerprints, f, ensure_ascii=False, indent=2)

        log.info(f"已从索引中删除: {os.path.basename(file_path)}")
    except Exception as e:
        log.error(f"删除索引失败: {file_path}: {e}")
