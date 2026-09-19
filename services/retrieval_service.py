"""
检索服务 — 修复「单文件垄断 top-k」导致的检索跑偏

问题诊断（实测数据）：
    把用户原始提示词整句丢给向量库，查「写一个外星文明的故事」时，
    知识库 20 条命中里 15 条（75%）来自同一本书《星光：外星世界与地球的命运》。
    那本书大量讲潮汐锁定，于是模型每次都往潮汐锁定上写。
    真正相关的论文 PDF 全被这本 epub 淹没。
    此外 bge-m3 的相似度全挤在 0.54~0.64，绝对阈值 0.3 等于完全不过滤。

四层修复：
    1. 查询改写  —— 用 flash 模型把提示拆成 2-4 条正交的检索子查询
    2. RRF 融合  —— 多路召回按 1/(k+rank) 倒数排名融合，不依赖分数绝对值
    3. 来源配额  —— 每文件最多 N 块、每分类最多 M 块（核心修复）
    4. 相对门限  —— 只保留与最高分差距在 margin 以内的，取代无效的绝对阈值

实测效果（同一条「外星文明」查询）：
    最大单文件占比  75% → 18%
    命中文件数        2 → 7
    命中分类数        2 → 7
"""
import json
import re
import time
from collections import Counter

from app_config import (
    RAG_TOP_K, RAG_CANDIDATE_K, RAG_MAX_PER_FILE, RAG_MAX_PER_CATEGORY,
    RAG_ABS_FLOOR, RAG_REL_MARGIN, RAG_QUERY_EXPANSION, RAG_MAX_SUBQUERIES,
)
from services.rag_service import rag
from logger import get_logger

log = get_logger("service.retrieval")

# RRF 常数，越大越弱化头部排名优势
RRF_K = 60

LIBRARY_KEYS = {"知识库": "knowledge", "参考库": "reference", "风格库": "style"}


# ============================================================
# 1. 查询改写
# ============================================================
_PLAN_PROMPT = """你是检索查询规划器。用户想写一篇科幻小说，给了一段写作提示。
请把它拆解成若干条用于向量检索的**子查询**，去科学文献库里找素材。

要求：
- 输出 2 到 {max_n} 条子查询，彼此**尽量正交**，覆盖提示涉及的不同知识面
- 每条子查询是一个**陈述性的知识点短语**，不是问句，不带"写一个""故事"这类写作动词
- 必须落在具体的学科概念上（如"系外行星大气环流与热量再分配"），不要笼统（如"外星"）
- 另外给出 3-6 个关键术语

用户提示：
{prompt}

严格输出 JSON，不要任何其他文字：
{{"queries": ["子查询1", "子查询2"], "terms": ["术语1", "术语2"]}}"""


def plan_queries(prompt, max_n=RAG_MAX_SUBQUERIES):
    """
    把用户提示拆成多条正交的检索子查询。
    失败时退回「原提示 + 去掉写作动词的版本」，保证检索不中断。
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {"queries": [], "terms": []}

    if not RAG_QUERY_EXPANSION:
        return {"queries": [prompt], "terms": []}

    try:
        from services.deepseek_service import deepseek_flash
        t0 = time.time()
        resp = deepseek_flash.chat(
            _PLAN_PROMPT.format(prompt=prompt[:2000], max_n=max_n),
            max_tokens=1000,
        ).strip()

        if resp.startswith("```"):
            resp = re.sub(r"^```[a-zA-Z]*\n", "", resp)
            resp = re.sub(r"\n?```$", "", resp).strip()

        data = json.loads(resp)
        queries = [str(q).strip() for q in data.get("queries", []) if str(q).strip()]
        terms = [str(t).strip() for t in data.get("terms", []) if str(t).strip()]

        if not queries:
            raise ValueError("模型没返回任何子查询")

        queries = queries[:max_n]
        elapsed = (time.time() - t0) * 1000
        log.info(f"查询改写: 1 条提示 → {len(queries)} 条子查询, {elapsed:.0f}ms")
        for q in queries:
            log.debug(f"  · {q}")
        return {"queries": queries, "terms": terms}

    except Exception as e:
        log.warning(f"查询改写失败，退回朴素查询: {type(e).__name__}: {e}")
        return {"queries": _naive_queries(prompt), "terms": []}


_WRITING_NOISE = re.compile(
    r"(请|帮我|我想|我要|写一个|写一篇|写出|创作|生成|故事|小说|设定|大纲|章节|"
    r"第一人称|主角是|题材|风格)"
)


def _naive_queries(prompt):
    """不调模型的退路：原句 + 剥掉写作动词的版本"""
    stripped = _WRITING_NOISE.sub(" ", prompt)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    out = [prompt]
    if stripped and stripped != prompt and len(stripped) >= 4:
        out.append(stripped)
    return out


# ============================================================
# 2-4. 多路召回 + RRF 融合 + 配额 + 相对门限
# ============================================================
def retrieve(
    queries,
    library_type=None,
    sources=None,
    top_k=RAG_TOP_K,
    candidate_k=RAG_CANDIDATE_K,
    max_per_file=RAG_MAX_PER_FILE,
    max_per_category=RAG_MAX_PER_CATEGORY,
    abs_floor=RAG_ABS_FLOOR,
    rel_margin=RAG_REL_MARGIN,
    embeddings=None,
):
    """
    多路召回 + RRF 融合 + 来源配额 + 相对门限。

    Args:
        queries: 子查询列表
        library_type: 限定库（知识库/参考库/风格库），None = 全库
        sources: 限定文件路径列表，None = 不限
        top_k: 最终返回条数
        embeddings: {查询文本: 向量}，跨库复用以省掉重复编码

    Returns:
        [{id, content, source, filename, library_type, category, page,
          similarity, rrf_score, matched_queries}, ...]
    """
    if not rag.is_available or not queries:
        return []

    t0 = time.time()
    fused = {}
    embeddings = embeddings or {}

    for q in queries:
        try:
            # threshold=0.0：过滤全部上移到本服务，由相对门限统一决定
            hits = rag.retriever.query(
                q, top_k=candidate_k, library_type=library_type,
                sources=sources, threshold=0.0,
                query_embedding=embeddings.get(q),
            )
        except Exception as e:
            log.warning(f"子查询失败 [{q[:30]}]: {type(e).__name__}: {e}")
            continue

        for rank, h in enumerate(hits):
            key = h.get("id") or f"{h['source']}#{h['page']}#{h['content'][:64]}"
            entry = fused.get(key)
            if entry is None:
                fused[key] = {
                    "hit": h,
                    "rrf": 1.0 / (RRF_K + rank),
                    "matched": 1,
                    "best_sim": h["similarity"],
                }
            else:
                entry["rrf"] += 1.0 / (RRF_K + rank)
                entry["matched"] += 1
                if h["similarity"] > entry["best_sim"]:
                    entry["best_sim"] = h["similarity"]
                    entry["hit"] = h

    if not fused:
        log.debug(f"检索无命中: library={library_type}, queries={len(queries)}")
        return []

    # 按 RRF 分数排序；命中多条子查询的自然靠前
    ranked = sorted(fused.values(), key=lambda e: (-e["rrf"], -e["best_sim"]))
    top_sim = max(e["best_sim"] for e in ranked)

    def collect(gate):
        """在给定门限下按配额挑选，返回 (结果, 文件计数, 分类计数, 被门限滤除数)"""
        per_file, per_category = Counter(), Counter()
        picked, gated_out = [], 0
        for entry in ranked:
            if len(picked) >= top_k:
                break
            h = entry["hit"]
            if entry["best_sim"] < gate:
                gated_out += 1
                continue
            if per_file[h["source"]] >= max_per_file:
                continue
            if per_category[h["category"]] >= max_per_category:
                continue
            per_file[h["source"]] += 1
            per_category[h["category"]] += 1
            picked.append({
                **h,
                "rrf_score": round(entry["rrf"], 6),
                "matched_queries": entry["matched"],
            })
        return picked, per_file, per_category, gated_out

    gate = max(abs_floor, top_sim - rel_margin)
    results, per_file, per_category, gated_out = collect(gate)

    # 自适应放宽：候选本来就不多时（比如查询改写失败、只有一两条弱查询），
    # 严格的相对门限会把结果饿死。此时退到绝对地板再挑一次。
    relaxed = False
    if len(results) < max(3, top_k // 2) and gate > abs_floor:
        gate = abs_floor
        results, per_file, per_category, gated_out = collect(gate)
        relaxed = True

    elapsed = (time.time() - t0) * 1000
    log.info(
        f"检索完成[{library_type or '全库'}]: {len(queries)}路 → 候选{len(fused)} → "
        f"返回{len(results)}条 | 文件{len(per_file)}个/分类{len(per_category)}个 | "
        f"门限{gate:.3f}{'(已放宽)' if relaxed else ''}(滤除{gated_out}) | {elapsed:.0f}ms"
    )
    return results


# ============================================================
# 对外入口
# ============================================================
def _encode_all(queries):
    """一次性编码所有子查询，供跨库检索复用（编码是检索里最慢的一步）"""
    out = {}
    for q in queries:
        try:
            out[q] = rag.retriever.encode(q)
        except Exception as e:
            log.warning(f"查询编码失败 [{q[:30]}]: {type(e).__name__}: {e}")
    return out


def search_all(prompt, sources=None, top_k=RAG_TOP_K, plan=None):
    """
    三库联合检索。替代旧的 rag.search_all()。

    Returns:
        {
          "knowledge": [...], "reference": [...], "style": [...],
          "plan": {"queries": [...], "terms": [...]},
        }
    """
    if not rag.is_available:
        return {"knowledge": [], "reference": [], "style": [],
                "plan": {"queries": [], "terms": []}}

    plan = plan or plan_queries(prompt)
    queries = plan.get("queries") or _naive_queries(prompt)
    embeddings = _encode_all(queries)

    out = {"plan": plan}
    for lib_type, key in LIBRARY_KEYS.items():
        out[key] = retrieve(queries, library_type=lib_type, sources=sources,
                            top_k=top_k, embeddings=embeddings)
    return out


def search_knowledge(prompt, sources=None, top_k=RAG_TOP_K, plan=None):
    """只检索知识库（写章节时用，不需要风格/参考库）"""
    if not rag.is_available:
        return []
    plan = plan or plan_queries(prompt)
    queries = plan.get("queries") or _naive_queries(prompt)
    return retrieve(queries, library_type="知识库", sources=sources, top_k=top_k)


# ============================================================
# 提示词格式化
# ============================================================
def format_context(results, label, max_chars=700):
    """把检索结果渲染成提示词上下文。无结果时返回明确的占位说明。"""
    if not results:
        return f"（未检索到{label}相关内容，本次不要凭空编造该方面的细节）"
    parts = []
    for i, r in enumerate(results, 1):
        content = r["content"]
        if len(content) > max_chars:
            content = content[:max_chars] + "……"
        header = (f"【{label}{i}】{r['filename']}"
                  f"（分类:{r['category']}，第{r.get('page', 0)}页，"
                  f"相似度:{r['similarity']}）")
        parts.append(f"{header}\n{content}")
    return "\n\n---\n\n".join(parts)


def to_citations(results):
    """压缩成可存库/回传前端的引用列表"""
    return [{
        "filename": r["filename"],
        "source": r["source"],
        "library_type": r["library_type"],
        "category": r["category"],
        "page": r.get("page", 0),
        "similarity": r["similarity"],
        "matched_queries": r.get("matched_queries", 1),
    } for r in results]


def diversity_stats(results):
    """检索多样性指标，用于日志和回归脚本"""
    if not results:
        return {"count": 0, "files": 0, "categories": 0, "max_file_share": 0.0}
    files = Counter(r["source"] for r in results)
    return {
        "count": len(results),
        "files": len(files),
        "categories": len({r["category"] for r in results}),
        "max_file_share": round(max(files.values()) / len(results), 3),
    }
