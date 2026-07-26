"""
RAG 检索服务 — 封装 knowledge_rag/query.py
"""
import sys
import os

# 确保项目根在 path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from knowledge_rag.query import KnowledgeRetriever
from app_config import RAG_TOP_K, RAG_THRESHOLD


class RAGService:
    """知识库检索服务"""

    def __init__(self):
        self._retriever = None

    @property
    def retriever(self):
        """懒加载 KnowledgeRetriever"""
        if self._retriever is None:
            try:
                self._retriever = KnowledgeRetriever()
            except FileNotFoundError:
                print("[RAG] 向量数据库未找到，请先运行 build_index.py")
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

    def search(self, query, top_k=RAG_TOP_K, category=None, threshold=RAG_THRESHOLD):
        """
        检索知识库，返回格式化上下文字符串。
        """
        if not self.is_available:
            return "（知识库不可用，请先构建索引：python knowledge_rag/build_index.py）"

        return self.retriever.query_as_context(
            query, top_k=top_k, category=category, threshold=threshold
        )

    def search_structured(self, query, top_k=RAG_TOP_K, category=None, threshold=RAG_THRESHOLD):
        """
        检索知识库，返回结构化列表。
        """
        if not self.is_available:
            return []

        return self.retriever.query(
            query, top_k=top_k, category=category, threshold=threshold
        )


# 全局实例
rag = RAGService()
