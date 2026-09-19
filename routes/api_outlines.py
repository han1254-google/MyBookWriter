"""
大纲工坊 API

与旧版的区别：
  1. 不再硬编码「7-10章」和「### 终章」，也不再要求起承转合 —— 章节数由故事需要决定
  2. 生成后把 markdown 解析成 Chapter 行，章节成为一等公民（可单独点开、改名、编计划）
  3. 章节名只有一份（Chapter.title），所以在创作界面改名，大纲页自然同步
"""
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context

from database import db, Idea, Outline, Project, Chapter, Revision, StoryEntity
from services.deepseek_service import deepseek
from services.rag_service import rag
from services import retrieval_service as rs
from services import outline_parser
from app_config import WRITING_STYLE_GUIDE
from logger import get_logger

api_outlines_bp = Blueprint("api_outlines", __name__)
log = get_logger("api.outlines")


def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ============================================================
# 生成
# ============================================================
@api_outlines_bp.route("/outlines/generate", methods=["POST"])
def generate_outline():
    """生成大纲（流式）"""
    data = request.get_json() or {}
    idea_id = data.get("idea_id")
    user_prompt = (data.get("prompt") or "").strip()
    # 章节数：不给就让 AI 自己定（这是「不强制起承转合」的一部分）
    chapter_count = data.get("chapter_count")
    structure_hint = (data.get("structure_hint") or "").strip()

    if not idea_id and not user_prompt:
        return jsonify({"error": "请选择创意或输入提示"}), 400

    log.info(f"生成大纲: idea_id={idea_id}, chapter_count={chapter_count or '由AI决定'}, "
             f"prompt={user_prompt[:60] if user_prompt else 'N/A'}")

    # ---- 上下文 ----
    idea = Idea.query.filter_by(id=idea_id).first() if idea_id else None
    if idea:
        idea_context = f"基于以下故事设定生成大纲：\n\n{idea.content}"
        retrieval_seed = " ".join(filter(None, [
            idea.title, idea.one_liner, idea.core_concept or idea.content[:300]
        ]))
        # 创意里已有的人物，写进提示词，避免大纲另起一套人名
        entities = StoryEntity.query.filter_by(idea_id=idea.id).order_by(
            StoryEntity.kind, StoryEntity.sort_order).all()
        entity_block = "\n".join(e.as_prompt_block() for e in entities)
    else:
        idea_context = user_prompt
        retrieval_seed = user_prompt
        entity_block = ""

    rag_context = "（知识库未构建）"
    citations = []
    if rag.is_available:
        hits = rs.search_knowledge(retrieval_seed)
        rag_context = rs.format_context(hits, "领域知识")
        citations = rs.to_citations(hits)
        st = rs.diversity_stats(hits)
        log.info(f"  知识库: {st['count']}条 / {st['files']}文件 / "
                 f"最大单文件占比{st['max_file_share']:.0%}")

    # ---- 章节数要求 ----
    if chapter_count:
        count_rule = (f"本次请规划 **{int(chapter_count)} 章**。")
    else:
        count_rule = (
            "章节数由故事本身的需要决定 —— 该几章就几章，不要为了凑数硬加，"
            "也不要为了简洁硬砍。短故事 5 章、长故事 20 章都可以。"
        )

    entity_section = ""
    if entity_block:
        entity_section = f"""
## 已确定的人物与设定（必须沿用，不要另起名字）
{entity_block}
"""

    structure_section = ""
    if structure_hint:
        structure_section = f"""
## 用户指定的结构要求
{structure_hint}
"""

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你是一个科幻故事大纲规划师。请根据用户的设定，生成章节规划。

## 知识库参考资料
{rag_context}
{entity_section}{structure_section}
## 结构自由度（重要）
- **不要套用起承转合、三幕式或任何固定模板。** 故事该怎么走就怎么走。
- 不要强行安排"高潮章""转折章"。如果这个故事的情绪是平缓下沉的，就让它平缓下沉。
- 结尾章不必叫"终章"，按它实际在讲什么来命名。
- {count_rule}

## 输出格式（小标题会被程序解析，请严格遵守层级和命名）

# 大纲标题

## 故事概要
一到三句话概述

## 核心主题
2-3 个核心主题

## 章节规划

### CHA1：章节名
- 场景：这一章发生在哪、什么时候
- 关键事件：这一章实际发生了什么（按顺序写清）
- 情感弧线：叙述者的情绪从哪走到哪
- 需要展现的设定：这一章要落地哪些世界观/科幻设定

### CHA2：章节名
（同上四项）

……依此类推，章号连续，不要跳号

## 要求
- 每章标题用 `### CHAn：章节名` 格式，n 是连续的阿拉伯数字
- 四个要点的名字（场景/关键事件/情感弧线/需要展现的设定）不要改
- 章节之间要有清晰的因果关系和情感递进，但递进不等于必须越来越激烈
- 章节名落在具体的物件、数字或动作上，不要用抽象概念当章节名"""

    def generate():
        try:
            full_text = ""
            for chunk in deepseek.chat_stream(
                idea_context, system_prompt=system_prompt, max_tokens=8192
            ):
                full_text += chunk
                yield _sse({"type": "text", "content": chunk})

            parsed = outline_parser.parse_outline(full_text)
            yield _sse({
                "type": "done",
                "full_text": full_text,
                "parsed": parsed,
                "citations": citations,
            })

        except Exception as e:
            log.error(f"大纲生成流失败: {type(e).__name__}: {e}", exc_info=True)
            yield _sse({"type": "error", "content": str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# 保存（同时建作品 + 章节行）
# ============================================================
@api_outlines_bp.route("/outlines/save", methods=["POST"])
def save_outline():
    """
    保存大纲。会一并创建：
      - 一个 Project（作品），作为章节的归属
      - 每章一行 Chapter（status='planned'，只有计划没有正文）
      - 从创意复制一份 StoryEntity 到作品下
    """
    data = request.get_json() or {}
    idea_id = data.get("idea_id")
    content = data.get("content", "")
    parsed = data.get("parsed")

    if not parsed and content:
        parsed = outline_parser.parse_outline(content)
    parsed = parsed or {}

    title = (data.get("title") or parsed.get("title") or "").strip() or "未命名大纲"
    knowledge_context = data.get("knowledge_context", "{}")
    if isinstance(knowledge_context, (list, dict)):
        knowledge_context = json.dumps(knowledge_context, ensure_ascii=False)

    outline = Outline(
        idea_id=idea_id,
        title=title,
        content=parsed.get("content") or content,
        raw_markdown=content,
        synopsis=parsed.get("synopsis", ""),
        themes=parsed.get("themes", ""),
        structure_note=parsed.get("structure_note", ""),
        parsed_ok=bool(parsed.get("parsed_ok")),
        knowledge_context=knowledge_context,
    )
    db.session.add(outline)
    db.session.flush()

    project = Project(
        title=title,
        synopsis=parsed.get("synopsis", ""),
        source_type="outline",
        idea_id=idea_id,
        outline_id=outline.id,
        status="writing",
    )
    db.session.add(project)
    db.session.flush()
    outline.project_id = project.id

    # 章节行
    chapters = parsed.get("chapters") or []
    for c in chapters:
        db.session.add(Chapter(
            project_id=project.id,
            outline_id=outline.id,
            chapter_number=c["chapter_number"],
            sort_key=c.get("sort_key") or float(c["chapter_number"]) * 1000.0,
            title=c.get("title", ""),
            plan_scene=c.get("plan_scene", ""),
            plan_events=c.get("plan_events", ""),
            plan_emotion=c.get("plan_emotion", ""),
            plan_settings=c.get("plan_settings", ""),
            plan_notes=c.get("plan_notes", ""),
            status="planned",
        ))

    # 创意里的人物/世界观复制成作品实例（之后作品内独立演化）
    n_entities = 0
    if idea_id:
        for e in StoryEntity.query.filter_by(idea_id=idea_id).all():
            db.session.add(e.clone_for_project(project.id))
            n_entities += 1

    Revision.record("outline", outline.id, content, op="generate")
    db.session.commit()

    log.info(f"大纲已保存: id={outline.id}, project={project.id}, title={title}, "
             f"{len(chapters)}章, 复制{n_entities}条设定")
    return jsonify({
        "success": True,
        "id": outline.id,
        "project_id": project.id,
        "outline": outline.to_dict(),
        "chapters": [c.to_summary() for c in project.chapters],
    })


# ============================================================
# 命令行式修改（替代原右侧对话框）
# ============================================================
@api_outlines_bp.route("/outlines/<int:outline_id>/command", methods=["POST"])
def command_outline(outline_id):
    """按指令重写大纲（流式）。完成后重新解析章节行。"""
    outline = Outline.query.get_or_404(outline_id)
    data = request.get_json() or {}
    instruction = (data.get("instruction") or "").strip()
    if not instruction:
        return jsonify({"error": "请输入修改意见"}), 400

    log.info(f"大纲指令: id={outline_id}, instruction={instruction[:60]}")

    chapters = _outline_chapters(outline)
    current = outline_parser.render_outline(outline, chapters)

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你正在帮助用户修改故事大纲。当前大纲：

{current}

用户会给出修改意见。请据此修改大纲。

要求：
- **不要套用起承转合或任何固定模板**，也不要为了凑章数硬加内容
- 保持 `### CHAn：章节名` 的章节标题格式和四个要点（场景/关键事件/情感弧线/需要展现的设定）
- 没被要求改的章节保持原样，不要顺手重写
- 直接输出修改后的完整大纲，不要写「好的」「已修改」之类的话"""

    def generate():
        try:
            full_text = ""
            for chunk in deepseek.chat_stream(
                instruction, system_prompt=system_prompt, max_tokens=8192
            ):
                full_text += chunk
                yield _sse({"type": "text", "content": chunk})

            parsed = outline_parser.parse_outline(full_text)
            Revision.record("outline", outline.id, current,
                            op="rewrite", instruction=instruction)
            n = _apply_parsed_chapters(outline, parsed, full_text)
            db.session.commit()

            yield _sse({"type": "done", "full_text": full_text,
                        "parsed": parsed, "chapter_count": n})

        except Exception as e:
            db.session.rollback()
            log.error(f"大纲指令失败: {type(e).__name__}: {e}", exc_info=True)
            yield _sse({"type": "error", "content": str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _apply_parsed_chapters(outline, parsed, raw):
    """
    把解析结果写回大纲和章节行。
    已有正文的章节**只更新计划字段，不碰正文和状态** —— 改大纲不能把写好的稿子弄丢。
    """
    outline.content = parsed.get("content") or raw
    outline.raw_markdown = raw
    for f in ("synopsis", "themes", "structure_note"):
        if parsed.get(f):
            setattr(outline, f, parsed[f])
    outline.parsed_ok = bool(parsed.get("parsed_ok"))
    if parsed.get("title"):
        outline.title = parsed["title"]

    if not outline.project_id:
        return 0

    existing = {c.chapter_number: c
                for c in Chapter.query.filter_by(project_id=outline.project_id).all()}
    incoming = parsed.get("chapters") or []
    seen = set()

    for c in incoming:
        num = c["chapter_number"]
        seen.add(num)
        ch = existing.get(num)
        if ch is None:
            db.session.add(Chapter(
                project_id=outline.project_id,
                outline_id=outline.id,
                chapter_number=num,
                sort_key=c.get("sort_key") or float(num) * 1000.0,
                title=c.get("title", ""),
                plan_scene=c.get("plan_scene", ""),
                plan_events=c.get("plan_events", ""),
                plan_emotion=c.get("plan_emotion", ""),
                plan_settings=c.get("plan_settings", ""),
                plan_notes=c.get("plan_notes", ""),
                status="planned",
            ))
            continue

        # 已存在：更新计划，保留正文。
        # 标题只在**还没写正文**时才跟着大纲改 ——
        # 已经动笔的章节，作者写的时候定的标题才是权威的，
        # 不能被大纲里的计划标题覆盖掉。
        if c.get("title") and not ch.content:
            ch.title = c["title"]
        for f in ("plan_scene", "plan_events", "plan_emotion",
                  "plan_settings", "plan_notes"):
            if c.get(f):
                setattr(ch, f, c[f])

    # 大纲里被删掉的章节：有正文的保留（只解除大纲关联），没正文的删除
    for num, ch in existing.items():
        if num in seen:
            continue
        if ch.content:
            log.info(f"CHA{num} 已从大纲移除但有正文，保留章节: {ch.title}")
        else:
            db.session.delete(ch)

    return len(incoming)


# ============================================================
# CRUD
# ============================================================
@api_outlines_bp.route("/outlines", methods=["GET"])
def list_outlines():
    outlines = Outline.query.order_by(Outline.updated_at.desc()).all()
    log.debug(f"列出大纲: {len(outlines)} 个")
    return jsonify([o.to_dict() for o in outlines])


def _outline_chapters(outline):
    """
    取大纲自己那个作品的章节。

    注意不能用 outline_id 查 —— 一个大纲可以派生出多个作品，
    那些作品的章节也带着同一个 outline_id，直接按 outline_id 查会把它们混在一起。
    """
    if outline.project_id:
        q = Chapter.query.filter_by(project_id=outline.project_id)
    else:
        q = Chapter.query.filter_by(outline_id=outline.id)
    return q.order_by(Chapter.sort_key).all()


@api_outlines_bp.route("/outlines/<int:outline_id>", methods=["GET"])
def get_outline(outline_id):
    """大纲详情 + 章节 item 列表"""
    outline = Outline.query.get_or_404(outline_id)
    chapters = _outline_chapters(outline)
    d = outline.to_dict()
    d["chapters"] = [c.to_summary() for c in chapters]
    log.debug(f"获取大纲: id={outline_id}, {len(chapters)} 章")
    return jsonify(d)


@api_outlines_bp.route("/outlines/<int:outline_id>", methods=["PUT"])
def update_outline(outline_id):
    """改大纲头部字段（概要/主题/结构说明）"""
    outline = Outline.query.get_or_404(outline_id)
    data = request.get_json() or {}
    for field in ("title", "synopsis", "themes", "structure_note", "content"):
        if field in data:
            setattr(outline, field, data[field])
    # 标题改了，作品名跟着改
    if "title" in data and outline.project_id:
        proj = db.session.get(Project, outline.project_id)
        if proj:
            proj.title = data["title"]
    db.session.commit()
    log.info(f"大纲已更新: id={outline_id}, title={outline.title}")
    return jsonify({"success": True, "outline": outline.to_dict()})


@api_outlines_bp.route("/outlines/<int:outline_id>", methods=["DELETE"])
def delete_outline(outline_id):
    outline = Outline.query.get_or_404(outline_id)
    log.info(f"删除大纲: id={outline_id}, title={outline.title}")
    Revision.query.filter_by(target_type="outline", target_id=outline_id).delete(
        synchronize_session=False)
    # 章节归 Project 管，这里只解除关联，不连带删掉写好的正文
    Chapter.query.filter_by(outline_id=outline_id).update(
        {"outline_id": None}, synchronize_session=False)
    db.session.delete(outline)
    db.session.commit()
    return jsonify({"success": True})


@api_outlines_bp.route("/outlines/<int:outline_id>/reparse", methods=["POST"])
def reparse_outline(outline_id):
    """
    重新解析章节行（给旧数据补章节 item 用）。
    旧大纲的章节从来没被解析成行，这个接口把它们补出来。
    """
    outline = Outline.query.get_or_404(outline_id)
    source = outline.raw_markdown or outline.content
    if not (source or "").strip():
        return jsonify({"error": "大纲没有内容可解析"}), 400

    # 没有作品的旧大纲，顺手补一个
    if not outline.project_id:
        proj = Project.query.filter_by(outline_id=outline.id).first()
        if not proj:
            proj = Project(title=outline.title, source_type="outline",
                           idea_id=outline.idea_id, outline_id=outline.id)
            db.session.add(proj)
            db.session.flush()
        outline.project_id = proj.id

    parsed = outline_parser.parse_outline(source)
    n = _apply_parsed_chapters(outline, parsed, source)
    db.session.commit()

    chapters = Chapter.query.filter_by(project_id=outline.project_id).order_by(
        Chapter.sort_key).all()
    log.info(f"大纲重新解析: id={outline_id}, {n} 章")
    return jsonify({
        "success": True,
        "chapter_count": n,
        "project_id": outline.project_id,
        "chapters": [c.to_summary() for c in chapters],
    })


# ============================================================
# 版本历史
# ============================================================
@api_outlines_bp.route("/outlines/<int:outline_id>/revisions", methods=["GET"])
def list_outline_revisions(outline_id):
    Outline.query.get_or_404(outline_id)
    revs = (Revision.query.filter_by(target_type="outline", target_id=outline_id)
            .order_by(Revision.version_no.desc()).all())
    return jsonify([r.to_dict() for r in revs])
