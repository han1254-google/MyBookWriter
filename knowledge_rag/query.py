"""
向量知识库查询接口
支持三库分类检索（知识库/参考库/风格库）

命令行用法：
  python query.py "潮汐锁定对气候的影响"                          # 全库检索
  python query.py "硅基生命" --library-type 知识库                  # 按库过滤
  python query.py "写作风格" --library-type 风格库 --top-k 10       # 风格库检索
  python query.py "法律法规 出版" --category 法律法规               # 按分类过滤

Python API 用法：
  from query import KnowledgeRetriever
  retriever = KnowledgeRetriever()
  results = retriever.query("潮汐锁定的行星有什么特点？", library_type="知识库")
  context = retriever.query_as_context("硅基生命", library_type="参考库")
"""
import os
import sys
import argparse
from typing import List, Dict, Optional

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    CHROMA_DB_DIR,
    EMBEDDING_MODEL,
    DEVICE,
    COLLECTION_NAME,
    DEFAULT_TOP_K,
    SIMILARITY_THRESHOLD,
)

import chromadb
from sentence_transformers import SentenceTransformer


class KnowledgeRetriever:
    """三库联合检索器"""

    def __init__(self):
        if not os.path.exists(CHROMA_DB_DIR):
            raise FileNotFoundError(
                f"向量数据库不存在: {CHROMA_DB_DIR}\n"
                f"请先运行 python build_index.py 构建索引"
            )
        self.client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        self.collection = self.client.get_collection(COLLECTION_NAME)
        self.model = SentenceTransformer(EMBEDDING_MODEL, device=DEVICE)

    @property
    def total_chunks(self) -> int:
        return self.collection.count()

    @property
    def categories(self) -> List[str]:
        result = self.collection.get()
        cats = set()
        for meta in result.get("metadatas", []):
            if meta and "category" in meta:
                cats.add(meta["category"])
        return sorted(cats)

    @property
    def library_types(self) -> List[str]:
        """所有库类型"""
        result = self.collection.get()
        types = set()
        for meta in result.get("metadatas", []):
            if meta and "library_type" in meta:
                types.add(meta["library_type"])
        return sorted(types)

    def query(
        self,
        query_text: str,
        top_k: int = DEFAULT_TOP_K,
        library_type: Optional[str] = None,
        category: Optional[str] = None,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> List[Dict]:
        """
        查询知识库，支持按 library_type 和 category 过滤。

        Args:
            query_text: 查询文本
            top_k: 返回的 chunk 数量
            library_type: 库类型过滤（"知识库"/"参考库"/"风格库"），None=全库
            category: 分类过滤（如 "潮汐锁定"）
            threshold: 相似度阈值

        Returns:
            [{content, source, filename, library_type, category, page, similarity}, ...]
        """
        query_embedding = self.model.encode([query_text]).tolist()

        # 构建 ChromaDB where 过滤条件
        where_filter = None
        conditions = []
        if library_type:
            conditions.append({"library_type": library_type})
        if category:
            conditions.append({"category": category})

        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        raw = self.collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        results = []
        if raw["ids"] and raw["ids"][0]:
            for i in range(len(raw["ids"][0])):
                distance = raw["distances"][0][i]
                similarity = 1 - distance
                if similarity < threshold:
                    continue
                metadata = raw["metadatas"][0][i] or {}
                # 兼容旧索引：无 library_type 的旧数据默认归入"知识库"
                lt = metadata.get("library_type", "") or "知识库"
                results.append({
                    "content": raw["documents"][0][i],
                    "source": metadata.get("source", ""),
                    "filename": metadata.get("filename", ""),
                    "library_type": lt,
                    "category": metadata.get("category", ""),
                    "page": metadata.get("page", 0),
                    "similarity": round(similarity, 4),
                })

        return results

    def query_as_context(
        self,
        query_text: str,
        top_k: int = DEFAULT_TOP_K,
        library_type: Optional[str] = None,
        category: Optional[str] = None,
        threshold: float = SIMILARITY_THRESHOLD,
        include_source: bool = True,
    ) -> str:
        """查询并返回拼接好的上下文字符串"""
        results = self.query(
            query_text, top_k=top_k,
            library_type=library_type, category=category, threshold=threshold
        )
        if not results:
            lib_label = f"「{library_type}」" if library_type else "知识库"
            return f"（未在{lib_label}中找到相关内容）"

        parts = []
        for i, r in enumerate(results, 1):
            if include_source:
                header = f"【来源{i}】{r['filename']} (库:{r['library_type']}, 分类:{r['category']}, 第{r['page']}页, 相似度:{r['similarity']})"
            else:
                header = f"【资料{i}】"
            parts.append(f"{header}\n{r['content']}")
        return "\n\n---\n\n".join(parts)

    def list_libraries(self) -> None:
        """打印三库统计"""
        types = self.library_types
        print("\n三库统计:")
        print("-" * 50)
        for lt in sorted(types):
            result = self.collection.get(where={"library_type": lt})
            count = len(result["ids"]) if result["ids"] else 0
            print(f"  📚 {lt}: {count} 个 chunk")


# ============================================================
# 命令行入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="三库向量知识库查询",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python query.py "潮汐锁定对行星气候有什么影响？"
  python query.py "硅基生命的可能性" --library-type 知识库 --top-k 10
  python query.py "写作风格分析" --library-type 风格库
  python query.py --list-libraries
        """
    )
    parser.add_argument("query", nargs="?", help="查询文本")
    parser.add_argument("--top-k", "-k", type=int, default=DEFAULT_TOP_K,
                        help=f"返回结果数量 (默认: {DEFAULT_TOP_K})")
    parser.add_argument("--library-type", "-l", type=str, default=None,
                        help="库类型过滤: 知识库/参考库/风格库")
    parser.add_argument("--category", "-c", type=str, default=None,
                        help="按分类过滤")
    parser.add_argument("--threshold", "-t", type=float, default=SIMILARITY_THRESHOLD,
                        help=f"相似度阈值 (默认: {SIMILARITY_THRESHOLD})")
    parser.add_argument("--list-libraries", action="store_true",
                        help="列出三库统计")
    args = parser.parse_args()

    try:
        retriever = KnowledgeRetriever()
    except FileNotFoundError as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    if args.list_libraries:
        retriever.list_libraries()
        return

    if not args.query:
        parser.print_help()
        return

    print(f"\n🔍 查询: \"{args.query}\"")
    if args.library_type:
        print(f"📚 库类型: {args.library_type}")
    if args.category:
        print(f"📁 分类: {args.category}")
    print("-" * 60)

    results = retriever.query(
        args.query,
        top_k=args.top_k,
        library_type=args.library_type,
        category=args.category,
        threshold=args.threshold,
    )

    if not results:
        print("  (未找到相关内容)")
        return

    for i, r in enumerate(results, 1):
        print(f"\n{'─' * 50}")
        print(f"📄 [{i}] {r['filename']}")
        print(f"   库:{r['library_type']} | 分类:{r['category']} | 页码:{r['page']} | 相似度:{r['similarity']}")
        print(f"{'─' * 50}")
        content = r["content"]
        if len(content) > 600:
            content = content[:600] + f"\n... (共 {len(r['content'])} 字)"
        print(content)

    print(f"\n{'=' * 60}")
    print(f"共找到 {len(results)} 条相关结果")


if __name__ == "__main__":
    main()
