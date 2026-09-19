"""
章节写作上下文组装器

核心职责是执行 CLAUDE.md 里那条铁律：
    「写第 N 章时，叙述者只能知道 CHA1 到 CHAn 已发生的事。
      禁止在叙事中引用未来章节的情节、场景、细节。」

旧版做法是把**整份大纲**（含后面所有章节的计划）塞进提示词，
于是模型天然知道第 7 章会发生什么，写第 1 章时就忍不住埋进去。

现在的做法：
    · 章节计划只给到当前章（chapter_plan_digest(upto=n)）
    · 人物/设定只给 first_appear_chapter <= n 的（未来才出场的人物根本不进提示词）
    · 前情只给上一章的 PRECHA 摘要 + 结尾原文
    · 实际注入了什么，全部记进 context_snapshot，可回查、可校验
"""
import json
import hashlib

from database import (db, Chapter, Project, Outline, Idea, StoryEntity,
                      ChapterEntity)
from services.rag_service import rag
from services import retrieval_service as rs
from services import outline_parser
from services.precha_service import render_precha_block, strip_precha
from app_config import WRITING_STYLE_GUIDE
from logger import get_logger

log = get_logger("service.context")

# 上一章结尾给多少字（用于接续，不是让它重写）
PREV_TAIL_CHARS = 900


# ============================================================
# 设定筛选
# ============================================================
def visible_entities(project_id, chapter_number, chapter_id=None):
    """
    取本章可见的设定条目。

    可见 = first_appear_chapter 为空（贯穿全书的世界观）
          或 first_appear_chapter <= 当前章号（已经出场过）

    如果本章显式关联了条目（ChapterEntity），优先用那份名单 ——
    这样就能精确控制「这一章只有谁在场」。
    """
    if chapter_id:
        links = ChapterEntity.query.filter_by(chapter_id=chapter_id).all()
        if links:
            picked = [l.entity for l in links if l.entity]
            onstage = [l.entity_id for l in links if l.role == "onstage"]
            return picked, set(onstage)

    q = StoryEntity.query.filter_by(project_id=project_id).filter(
        db.or_(
            StoryEntity.first_appear_chapter.is_(None),
            StoryEntity.first_appear_chapter <= chapter_number,
        )
    ).order_by(StoryEntity.kind, StoryEntity.sort_order)
    items = q.all()
    return items, set()


def render_entities(entities, onstage_ids=None):
    """按类型分组渲染设定条目"""
    if not entities:
        return "（尚未录入人物与世界观设定）"

    from database import ENTITY_KIND_LABELS
    onstage_ids = onstage_ids or set()
    groups = {}
    for e in entities:
        groups.setdefault(e.kind, []).append(e)

    order = ["worldview", "setting", "character", "location", "item", "term", "theme"]
    parts = []
    for kind in order:
        items = groups.get(kind)
        if not items:
            continue
        label = ENTITY_KIND_LABELS.get(kind, kind)
        lines = [f"### {label}"]
        for e in items:
            mark = " 【本章在场】" if e.id in onstage_ids else ""
            lines.append(e.as_prompt_block() + mark)
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


# ============================================================
# 前情
# ============================================================
def previous_chapter(project_id, chapter_number):
    """取章号小于当前章、且有正文的最后一章"""
    return (Chapter.query
            .filter(Chapter.project_id == project_id,
                    Chapter.chapter_number < chapter_number,
                    Chapter.content.isnot(None),
                    Chapter.content != "")
            .order_by(Chapter.chapter_number.desc())
            .first())


def render_previous(prev, tail_chars=PREV_TAIL_CHARS):
    """渲染前情：PRECHA 摘要 + 结尾原文"""
    if prev is None:
        return "（本章是第一章，没有前情）", 0

    body = strip_precha(prev.content)
    tail = body[-tail_chars:] if len(body) > tail_chars else body

    block = f"""上一章是 CHA{prev.chapter_number}《{prev.title or ''}》。

它的结构化摘要（时间/地点/人物/起/经/结/媒）：
{render_precha_block(prev)}

它的结尾原文（本章要从这里往下接，不要重写这段）：
```
{tail}
```"""
    return block, len(tail)


# ============================================================
# 组装
# ============================================================
def build_chapter_context(chapter, op="generate", instruction=""):
    """
    组装写某一章所需的全部上下文。

    Returns:
        {
          "system_prompt": str,
          "user_message": str,
          "snapshot": dict,        # 存进 chapter.context_snapshot
          "citations": list,       # 存进 chapter.knowledge_context
        }
    """
    project = db.session.get(Project, chapter.project_id)
    outline = db.session.get(Outline, chapter.outline_id) if chapter.outline_id else None
    if outline is None and project and project.outline_id:
        outline = db.session.get(Outline, project.outline_id)
    idea = db.session.get(Idea, project.idea_id) if project and project.idea_id else None

    n = chapter.chapter_number

    # ---- 设定（只给已出场的）----
    entities, onstage = visible_entities(project.id, n, chapter.id)
    entity_block = render_entities(entities, onstage)
    hidden = StoryEntity.query.filter(
        StoryEntity.project_id == project.id,
        StoryEntity.first_appear_chapter.isnot(None),
        StoryEntity.first_appear_chapter > n,
    ).count()
    if hidden:
        log.info(f"CHA{n}: 屏蔽 {hidden} 条未来才出场的设定（防叙述越界）")

    # ---- 章节计划：只给到当前章 ----
    all_chapters = (Chapter.query.filter_by(project_id=project.id)
                    .order_by(Chapter.sort_key).all())
    plan_digest = outline_parser.chapter_plan_digest(all_chapters, upto=n)

    # ---- 前情 ----
    prev = previous_chapter(project.id, n)
    prev_block, tail_len = render_previous(prev)

    # ---- 本章计划 ----
    this_plan = chapter.plan_block() or "（本章没有预先的计划，请依据前情自行推进）"

    # ---- 知识检索：用本章计划做种子，而不是整本大纲 ----
    citations = []
    rag_block = "（知识库未构建）"
    seed = " ".join(filter(None, [
        chapter.title, chapter.plan_scene, chapter.plan_settings, chapter.plan_events
    ])).strip()
    if not seed:
        seed = " ".join(filter(None, [project.title, project.synopsis]))
    if rag.is_available and seed:
        hits = rs.search_knowledge(seed)
        rag_block = rs.format_context(hits, "领域知识")
        citations = rs.to_citations(hits)
        st = rs.diversity_stats(hits)
        log.info(f"CHA{n} 知识检索: {st['count']}条 / {st['files']}文件 / "
                 f"最大单文件占比{st['max_file_share']:.0%}")

    # ---- 设定概述（IDEA 的核心概念，不给开篇构想以免越界）----
    idea_block = "（无设定）"
    if idea:
        idea_parts = []
        if idea.one_liner:
            idea_parts.append(f"核心：{idea.one_liner}")
        if idea.core_concept:
            idea_parts.append(f"核心科幻概念：\n{idea.core_concept}")
        if idea.themes:
            idea_parts.append(f"故事主题：\n{idea.themes}")
        idea_block = "\n\n".join(idea_parts) or (idea.content[:1500] or "（无设定）")

    style_extra = f"\n\n## 本作品额外的风格要求\n{project.style_notes}" if project.style_notes else ""

    # ---- 操作指令 ----
    op_section, user_message = _render_op(chapter, op, instruction, n)

    system_prompt = f"""{WRITING_STYLE_GUIDE}{style_extra}

你是科幻小说作家，现在写的是 **CHA{n}**。

## ⚠️ 叙述范围铁律（最重要）
你的叙述者是第一人称。**他此刻只知道 CHA1 到 CHA{n} 已经发生的事。**
- 禁止提及、暗示、预告任何 CHA{n} 之后才会发生的情节、场景、人物、物件
- 下面给你的章节计划**只到 CHA{n} 为止**，这是故意的，不要去推测后面
- 禁止上帝视角。只写"我"能看到、听到、知道的事

## 故事设定（IDEA）
{idea_block}

## 人物与世界观（截至 CHA{n} 已出场的）
{entity_block}

## 章节计划（CHA1 — CHA{n}）
{plan_digest}

## 本章（CHA{n}）要写的
{this_plan}

## 前情
{prev_block}

## 领域知识参考
{rag_block}

{op_section}

## 输出格式
只输出正文，不要输出标题行，不要输出 PRECHA 元数据 —— 这些由程序管理。
直接从正文第一句开始写。"""

    prompt_hash = hashlib.md5(system_prompt.encode("utf-8")).hexdigest()[:12]
    snapshot = {
        "op": op,
        "instruction": instruction,
        "chapter_number": n,
        "entity_ids": [e.id for e in entities],
        "entity_count": len(entities),
        "hidden_future_entities": hidden,
        "plan_upto": n,
        "prev_chapter_id": prev.id if prev else None,
        "prev_chapter_number": prev.chapter_number if prev else None,
        "prev_tail_chars": tail_len,
        "rag_seed": seed[:200],
        "rag_hits": len(citations),
        "rag_files": sorted({c["filename"] for c in citations}),
        "model": "deepseek",
        "prompt_chars": len(system_prompt),
        "prompt_hash": prompt_hash,
    }

    return {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "snapshot": snapshot,
        "citations": citations,
    }


def _render_op(chapter, op, instruction, n):
    """按操作类型生成任务说明和 user 消息"""
    body = strip_precha(chapter.content) if chapter.content else ""

    if op == "continue":
        tail = body[-2500:] if len(body) > 2500 else body
        section = f"""## 本次任务：续写
本章已经写了 {len(body)} 字。下面是已写部分的结尾，请**从这里继续往下写**，
不要重复已写的内容，不要重新开头。

已写部分的结尾：
```
{tail}
```

{f'用户的续写要求：{instruction}' if instruction else ''}

只输出**新增**的部分，不要把前面已写的内容再抄一遍。"""
        return section, f"请继续写 CHA{n}。"

    if op == "rewrite":
        section = f"""## 本次任务：重写
本章已有一稿（{len(body)} 字），下面是原稿。请**整章重写**。

用户的修改意见：
{instruction or '（未给出具体意见，请按风格指南改进）'}

原稿：
```
{body[:12000]}
```

输出重写后的完整正文。"""
        return section, f"请按修改意见重写 CHA{n}。"

    # generate
    section = "## 本次任务：从零写出本章正文"
    if instruction:
        section += f"\n\n用户的额外要求：\n{instruction}"
    return section, f"请写出 CHA{n} 的正文。"


# ============================================================
# 校验（给测试和界面用）
# ============================================================
def audit_snapshot(chapter):
    """
    检查某章的上下文快照有没有越界。
    返回 {ok, issues: [...]}
    """
    try:
        snap = json.loads(chapter.context_snapshot or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "issues": ["context_snapshot 不是合法 JSON"]}

    if not snap:
        return {"ok": True, "issues": [], "note": "尚无快照（该章未经 AI 生成）"}

    issues = []
    n = chapter.chapter_number

    if snap.get("plan_upto") and snap["plan_upto"] > n:
        issues.append(f"章节计划给到了 CHA{snap['plan_upto']}，超过本章 CHA{n}")

    for eid in snap.get("entity_ids", []):
        e = db.session.get(StoryEntity, eid)
        if e and e.first_appear_chapter and e.first_appear_chapter > n:
            issues.append(
                f"设定「{e.name}」标注首次出场 CHA{e.first_appear_chapter}，"
                f"却被注入了 CHA{n}")

    prev_num = snap.get("prev_chapter_number")
    if prev_num is not None and prev_num >= n:
        issues.append(f"前情用的是 CHA{prev_num}，不早于本章 CHA{n}")

    return {"ok": not issues, "issues": issues}
