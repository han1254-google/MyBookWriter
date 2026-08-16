"""
RAG 检索服务 — 封装 knowledge_rag/query.py
"""
import sys
import os
import time

# 确保项目根在 path 中
MYBOOKAPPS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MYBOOKAPPS_ROOT not in sys.path:
    sys.path.insert(0, MYBOOKAPPS_ROOT)

from knowledge_rag.query import KnowledgeRetriever
from app_config import RAG_TOP_K, RAG_THRESHOLD
from logger import get_logger

log = get_logger("service.rag")


class RAGService:
    """知识库检索服务"""

    def __init__(self):
        self._retriever = None

    @property
    def retriever(self):
        """懒加载 KnowledgeRetriever"""
        if self._retriever is None:
            try:
                t0 = time.time()
                self._retriever = KnowledgeRetriever()
                elapsed = (time.time() - t0) * 1000
                log.info(f"RAG 检索器已加载: {self._retriever.total_chunks} 个chunk, {elapsed:.0f}ms")
            except FileNotFoundError:
                log.warning("向量数据库未找到，请先运行 build_index.py")
                self._retriever = None
        return self._retriever

    @property
    def is_available(self):
        return self.retriever is not None

    @property
    def categories(self):
        if not self.is_available:
            return []
        return self.retriever.categories

    @property
    def files(self):
        """所有已索引文件列表 [{source, filename, library_type, category, chunks}]"""
        if not self.is_available:
            return []
        result = self.retriever.collection.get(include=["metadatas"])
        file_map = {}
        for meta in result.get("metadatas", []):
            if not meta or not meta.get("source"):
                continue
            key = meta["source"]
            if key not in file_map:
                file_map[key] = {
                    "source": key,
                    "filename": meta.get("filename", ""),
                    "library_type": meta.get("library_type", ""),
                    "category": meta.get("category", ""),
                    "chunks": 0,
                }
            file_map[key]["chunks"] += 1
        files = sorted(file_map.values(), key=lambda f: f["library_type"])
        return files

    def search(self, query, top_k=RAG_TOP_K, category=None, sources=None, threshold=RAG_THRESHOLD):
        """检索知识库，返回格式化上下文字符串。"""
        if not self.is_available:
            return "（知识库不可用，请先构建索引：python knowledge_rag/build_index.py）"

        t0 = time.time()
        result = self.retriever.query_as_context(
            query, top_k=top_k, category=category, sources=sources, threshold=threshold
        )
        elapsed = (time.time() - t0) * 1000
        log.debug(f"RAG检索: query={query[:40]}..., category={category}, files={len(sources) if sources else 'all'}, top_k={top_k}, {elapsed:.0f}ms")
        return result

    def search_structured(self, query, top_k=RAG_TOP_K, category=None, sources=None, threshold=RAG_THRESHOLD):
        """检索全库，返回结构化列表。"""
        if not self.is_available:
            return []

        t0 = time.time()
        results = self.retriever.query(
            query, top_k=top_k, category=category, sources=sources, threshold=threshold
        )
        elapsed = (time.time() - t0) * 1000
        log.debug(f"RAG检索(structured): query={query[:40]}..., {len(results)}条结果, {elapsed:.0f}ms")
        return results

    # ---- 三库分别检索 ----

    def search_knowledge(self, query, top_k=RAG_TOP_K, threshold=RAG_THRESHOLD):
        """检索知识库（领域知识）"""
        return self.search(query, top_k=top_k, threshold=threshold)

    def search_reference(self, query, top_k=RAG_TOP_K, threshold=RAG_THRESHOLD):
        """检索参考库（他人文章创意）"""
        if not self.is_available:
            return "（参考库不可用）"
        return self.retriever.query_as_context(
            query, top_k=top_k, library_type="参考库", threshold=threshold
        )

    def search_style(self, query, top_k=RAG_TOP_K, threshold=RAG_THRESHOLD):
        """检索风格库（写作风格样本）"""
        if not self.is_available:
            return "（风格库不可用）"
        return self.retriever.query_as_context(
            query, top_k=top_k, library_type="风格库", threshold=threshold
        )

    def search_all(self, query, top_k=RAG_TOP_K, sources=None, threshold=RAG_THRESHOLD):
        """检索全部三库（可限定具体文件），返回结构化结果"""
        if not self.is_available:
            return {"knowledge": [], "reference": [], "style": []}

        result = {}
        for lib_type in ["知识库", "参考库", "风格库"]:
            t0 = time.time()
            items = self.retriever.query(
                query, top_k=top_k, library_type=lib_type,
                sources=sources, threshold=threshold
            )
            elapsed = (time.time() - t0) * 1000
            log.debug(f"  {lib_type}检索: {len(items)}条, {elapsed:.0f}ms")
            result[{"知识库": "knowledge", "参考库": "reference", "风格库": "style"}[lib_type]] = items

        return result


# 全局实例
rag = RAGService()
