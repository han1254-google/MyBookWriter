"""
检索质量回归脚本 — 对比修复前/后的多样性指标

修复前：单查询 + top_k=20 + 绝对阈值 0.3（现状）
修复后：查询改写 + RRF 融合 + 来源配额 + 相对门限

通过标准：
  最大单文件占比 < 30%   （修复前实测 75%，一本书垄断了整个 top-k）
  命中文件数     >= 5

用法：
  python scripts/eval_retrieval.py                          # 跑内置样例
  python scripts/eval_retrieval.py "查询1" "查询2"           # 跑指定查询
  python scripts/eval_retrieval.py --no-expansion "查询"     # 不调模型改写（离线可用）
"""
import os
import sys
import argparse
from collections import Counter

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_config import RAG_TOP_K
from services.rag_service import rag
from services import retrieval_service as rs

DEFAULT_QUERIES = [
    "写一个外星文明的故事",
    "潮汐锁定星球上的原住民如何发展文明",
    "硅基生命的生物化学基础",
    "一个发生在珊瑚礁生态站的故事",
]

PASS_MAX_FILE_SHARE = 0.30
PASS_MIN_FILES = 5


def stats_of(hits):
    if not hits:
        return {"count": 0, "files": 0, "categories": 0, "max_file_share": 0.0}
    files = Counter(h["source"] for h in hits)
    return {
        "count": len(hits),
        "files": len(files),
        "categories": len({h["category"] for h in hits}),
        "max_file_share": max(files.values()) / len(hits),
    }


def show_breakdown(hits, indent="      "):
    c = Counter((h["category"], os.path.basename(h["filename"])[:34]) for h in hits)
    for (cat, fname), n in c.most_common():
        print(f"{indent}{n:2d}× [{cat}] {fname}")


def run_one(query, use_expansion=True):
    print("=" * 74)
    print(f"查询: {query}")
    print("=" * 74)

    # ---- 修复前：单查询 + 绝对阈值 0.3 + top_k 20 ----
    before = rag.retriever.query(query, top_k=20, library_type="知识库", threshold=0.3)

    # ---- 修复后：改写 + RRF + 配额 + 相对门限 ----
    if use_expansion:
        plan = rs.plan_queries(query)
    else:
        plan = {"queries": rs._naive_queries(query), "terms": []}
    after = rs.retrieve(plan["queries"], library_type="知识库", top_k=RAG_TOP_K)

    sb, sa = stats_of(before), stats_of(after)

    print(f"\n  子查询 ({len(plan['queries'])} 条):")
    for q in plan["queries"]:
        print(f"      · {q}")
    if plan.get("terms"):
        print(f"  关键术语: {'、'.join(plan['terms'])}")

    print(f"\n  [修复前] {sb['count']} 条命中:")
    show_breakdown(before)
    print(f"\n  [修复后] {sa['count']} 条命中:")
    show_breakdown(after)

    print(f"\n  {'指标':<18s}{'修复前':>10s}{'修复后':>10s}")
    print(f"  {'-' * 38}")
    print(f"  {'最大单文件占比':<16s}{sb['max_file_share']:>9.0%}{sa['max_file_share']:>10.0%}")
    print(f"  {'命中文件数':<18s}{sb['files']:>10d}{sa['files']:>10d}")
    print(f"  {'命中分类数':<18s}{sb['categories']:>10d}{sa['categories']:>10d}")

    passed = (sa["max_file_share"] < PASS_MAX_FILE_SHARE
              and sa["files"] >= PASS_MIN_FILES)
    print(f"\n  判定: {'通过' if passed else '未通过'}"
          f"  (要求 单文件占比<{PASS_MAX_FILE_SHARE:.0%} 且 文件数>={PASS_MIN_FILES})")
    print()
    return passed, sb, sa


def main():
    parser = argparse.ArgumentParser(description="检索质量回归")
    parser.add_argument("queries", nargs="*", help="要测的查询，不给则用内置样例")
    parser.add_argument("--no-expansion", action="store_true",
                        help="不调用模型做查询改写（离线/省 token）")
    args = parser.parse_args()

    if not rag.is_available:
        print("[!] 向量库不可用，请先运行 python knowledge_rag/build_index.py")
        sys.exit(1)

    queries = args.queries or DEFAULT_QUERIES
    print(f"\n向量库: {rag.retriever.total_chunks} chunks, "
          f"查询改写: {'关' if args.no_expansion else '开'}\n")

    results = [run_one(q, use_expansion=not args.no_expansion) for q in queries]

    n_pass = sum(1 for p, _, _ in results if p)
    avg_before = sum(b["max_file_share"] for _, b, _ in results) / len(results)
    avg_after = sum(a["max_file_share"] for _, _, a in results) / len(results)

    print("=" * 74)
    print(f"  汇总: {n_pass}/{len(results)} 条查询通过")
    print(f"  平均最大单文件占比: {avg_before:.0%} → {avg_after:.0%}")
    print("=" * 74)
    sys.exit(0 if n_pass == len(results) else 1)


if __name__ == "__main__":
    main()
