"""
作品 API — 创作界面后端

三种建法：
  from_outline  从大纲创建：复制章节计划为 planned 章，复制创意的人物/世界观
  from_idea     从创意创建：空作品，只带人物/世界观，章节自己一章一章加
  blank         空白创建

章节命令行（对应界面底部输入框）：
  POST /api/chapters/<id>/command   op ∈ {generate, continue, rewrite}
"""
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context

from database import (db, Project, Chapter, Outline, Idea, StoryEntity,
                      ChapterEntity, Revision, ENTITY_KINDS)
from services.deepseek_service import deepseek
from services import context_builder
from services import precha_service
from logger import get_logger

api_projects_bp = Blueprint("api_projects", __name__)
log = get_logger("api.projects")


def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ============================================================
# 作品
# ============================================================
@api_projects_bp.route("/projects", methods=["GET"])
def list_projects():
    projects = Project.query.order_by(Project.updated_at.desc()).all()
    log.debug(f"列出作品: {len(projects)} 个")
    return jsonify([p.to_dict() for p in projects])


@api_projects_bp.route("/projects/<int:project_id>", methods=["GET"])
def get_project(project_id):
    """作品详情：章节 item 列表 + 人物/世界观/设定"""
    project = Project.query.get_or_404(project_id)
    d = project.to_dict(with_chapters=True, with_entities=True)
    if project.outline_id:
        outline = db.session.get(Outline, project.outline_id)
        d["outline"] = outline.to_dict() if outline else None
    if project.idea_id:
        idea = db.session.get(Idea, project.idea_id)
        d["idea"] = idea.to_dict() if idea else None
    return jsonify(d)


@api_projects_bp.route("/projects", methods=["POST"])
def create_project():
    """
    新建作品。
    body: {source_type: 'outline'|'idea'|'blank', outline_id?, idea_id?, title?}
    """
    data = request.get_json() or {}
    source_type = data.get("source_type", "blank")
    title = (data.get("title") or "").strip()

    if source_type == "outline":
        outline_id = data.get("outline_id")
        outline = Outline.query.filter_by(id=outline_id).first()
        if not outline:
            return jsonify({"error": "大纲不存在"}), 404

        # 一个大纲只对应一个作品。否则「在创作界面改章节名，大纲页跟着变」
        # 这条保证就不成立了 —— 大纲不知道该跟哪个作品的章节走。
        # 已有作品时直接返回它，而不是复制一套章节出来。
        if not data.get("force_new"):
            existing = Project.query.filter_by(outline_id=outline.id).first()
            if existing:
                log.info(f"大纲 {outline.id} 已有作品 {existing.id}，直接复用")
                return jsonify({
                    "success": True,
                    "reused": True,
                    "project": existing.to_dict(with_chapters=True,
                                                with_entities=True),
                })
        return _create_from_outline(outline, title)

    if source_type == "idea":
        idea_id = data.get("idea_id")
        idea = Idea.query.filter_by(id=idea_id).first()
        if not idea:
            return jsonify({"error": "创意不存在"}), 404
        return _create_from_idea(idea, title)

    project = Project(title=title or "未命名作品", source_type="blank")
    db.session.add(project)
    db.session.commit()
    log.info(f"新建空白作品: id={project.id}")
    return jsonify({"success": True, "project": project.to_dict(
        with_chapters=True, with_entities=True)})


def _copy_entities(project_id, idea_id):
    """把创意上的设定模板复制成作品实例"""
    n = 0
    for e in StoryEntity.query.filter_by(idea_id=idea_id).order_by(
            StoryEntity.kind, StoryEntity.sort_order).all():
        db.session.add(e.clone_for_project(project_id))
        n += 1
    return n


def _create_from_outline(outline, title=""):
    """从大纲创建：复制章节计划（status='planned'）"""
    project = Project(
        title=title or outline.title or "未命名作品",
        synopsis=outline.synopsis or "",
        source_type="outline",
        idea_id=outline.idea_id,
        outline_id=outline.id,
    )
    db.session.add(project)
    db.session.flush()

    # 大纲已有的章节行，复制成本作品的章节
    src_chapters = Chapter.query.filter_by(outline_id=outline.id).order_by(
        Chapter.sort_key).all()
    for c in src_chapters:
        # 已经挂在别的作品下的，复制一份；没主的直接认领
        if c.project_id and c.project_id != project.id:
            db.session.add(Chapter(
                project_id=project.id, outline_id=outline.id,
                chapter_number=c.chapter_number, sort_key=c.sort_key,
                title=c.title,
                plan_scene=c.plan_scene, plan_events=c.plan_events,
                plan_emotion=c.plan_emotion, plan_settings=c.plan_settings,
                plan_notes=c.plan_notes, status="planned",
            ))
        else:
            c.project_id = project.id

    n_entities = _copy_entities(project.id, outline.idea_id) if outline.idea_id else 0
    db.session.commit()

    log.info(f"从大纲创建作品: project={project.id}, outline={outline.id}, "
             f"{len(src_chapters)}章, {n_entities}条设定")
    return jsonify({"success": True, "project": project.to_dict(
        with_chapters=True, with_entities=True)})


def _create_from_idea(idea, title=""):
    """从创意创建：空作品 + 复制人物/世界观，章节由用户逐章新建"""
    project = Project(
        title=title or idea.title or "未命名作品",
        synopsis=idea.one_liner or "",
        source_type="idea",
        idea_id=idea.id,
    )
    db.session.add(project)
    db.session.flush()
    n_entities = _copy_entities(project.id, idea.id)
    db.session.commit()

    log.info(f"从创意创建作品: project={project.id}, idea={idea.id}, "
             f"{n_entities}条设定, 0章（待新建）")
    return jsonify({"success": True, "project": project.to_dict(
        with_chapters=True, with_entities=True)})


@api_projects_bp.route("/projects/<int:project_id>", methods=["PUT"])
def update_project(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json() or {}
    for field in ("title", "synopsis", "status", "style_notes"):
        if field in data:
            setattr(project, field, data[field])
    db.session.commit()
    log.info(f"作品已更新: id={project_id}, title={project.title}")
    return jsonify({"success": True, "project": project.to_dict()})


@api_projects_bp.route("/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    ch_ids = [c.id for c in project.chapters]
    log.info(f"删除作品: id={project_id}, title={project.title}, {len(ch_ids)}章")
    if ch_ids:
        Revision.query.filter(Revision.target_type == "chapter",
                              Revision.target_id.in_(ch_ids)).delete(
            synchronize_session=False)
    db.session.delete(project)
    db.session.commit()
    return jsonify({"success": True})


# ============================================================
# 章节
# ============================================================
@api_projects_bp.route("/projects/<int:project_id>/chapters", methods=["GET"])
def list_chapters(project_id):
    Project.query.get_or_404(project_id)
    chapters = Chapter.query.filter_by(project_id=project_id).order_by(
        Chapter.sort_key).all()
    return jsonify([c.to_summary() for c in chapters])


@api_projects_bp.route("/projects/<int:project_id>/chapters", methods=["POST"])
def create_chapter(project_id):
    """
    新建章节。
    auto_precha=True（默认）时自动从前一章抽取 PRECHA 七项 ——
    这是「从 IDEA 创建」流程里，章节之间建立连续性的方式。
    """
    project = Project.query.get_or_404(project_id)
    data = request.get_json() or {}
    auto_precha = data.get("auto_precha", True)

    existing = Chapter.query.filter_by(project_id=project_id).order_by(
        Chapter.chapter_number).all()
    number = data.get("chapter_number")
    if number is None:
        number = (existing[-1].chapter_number + 1) if existing else 1
    else:
        number = int(number)
        if any(c.chapter_number == number for c in existing):
            return jsonify({"error": f"CHA{number} 已存在"}), 400

    chapter = Chapter(
        project_id=project_id,
        outline_id=project.outline_id,
        chapter_number=number,
        sort_key=float(number) * 1000.0,
        title=(data.get("title") or "").strip(),
        plan_scene=data.get("plan_scene", ""),
        plan_events=data.get("plan_events", ""),
        plan_emotion=data.get("plan_emotion", ""),
        plan_settings=data.get("plan_settings", ""),
        plan_notes=data.get("plan_notes", ""),
        status="planned",
    )

    # ---- 自动 PRECHA ----
    precha_source = None
    if auto_precha:
        prev = context_builder.previous_chapter(project_id, number)
        if prev is not None:
            info = precha_service.extract_precha_from_chapter(prev)
            for k, v in info.items():
                setattr(chapter, k, v)
            chapter.precha_auto = True
            precha_source = prev.chapter_number
            log.info(f"CHA{number} 的 PRECHA 已自动从 CHA{prev.chapter_number} 抽取")
        else:
            chapter.precha_name = "/"
            chapter.precha_link = "/"

    db.session.add(chapter)
    db.session.commit()
    log.info(f"新建章节: project={project_id}, CHA{number} {chapter.title}")
    return jsonify({"success": True, "chapter": chapter.to_dict(),
                    "precha_from": precha_source})


@api_projects_bp.route("/chapters/<int:chapter_id>", methods=["GET"])
def get_chapter(chapter_id):
    """章节详情：计划 + PRECHA + 正文 + 本章设定 + 越界自检"""
    chapter = Chapter.query.get_or_404(chapter_id)
    d = chapter.to_dict()
    entities, onstage = context_builder.visible_entities(
        chapter.project_id, chapter.chapter_number, chapter.id)
    d["entities"] = [e.to_dict() for e in entities]
    d["onstage_entity_ids"] = sorted(onstage)
    d["audit"] = context_builder.audit_snapshot(chapter)
    d["revision_count"] = Revision.query.filter_by(
        target_type="chapter", target_id=chapter_id).count()
    return jsonify(d)


@api_projects_bp.route("/chapters/<int:chapter_id>", methods=["PUT"])
def update_chapter(chapter_id):
    """
    更新章节。改 title 时大纲页会跟着变 ——
    因为大纲和创作界面共用同一行 Chapter，章节名只有一份。
    """
    chapter = Chapter.query.get_or_404(chapter_id)
    data = request.get_json() or {}

    # 正文变动落一个版本
    if "content" in data and data["content"] != chapter.content:
        if chapter.content:
            Revision.record("chapter", chapter.id, chapter.content,
                            op="manual", instruction="手动编辑")
        chapter.content = data["content"]
        chapter.recount()
        if chapter.status == "planned" and chapter.content:
            chapter.status = "draft"

    if "title" in data:
        chapter.title = data["title"]
    for field in ("plan_scene", "plan_events", "plan_emotion",
                  "plan_settings", "plan_notes", "status"):
        if field in data:
            setattr(chapter, field, data[field])

    # PRECHA 被手改过就标记，之后不再自动覆盖
    precha_fields = ("precha_name", "precha_link", "precha_time", "precha_place",
                     "precha_chars", "precha_cause", "precha_process",
                     "precha_result", "precha_media")
    if any(f in data for f in precha_fields):
        for f in precha_fields:
            if f in data:
                setattr(chapter, f, data[f])
        chapter.precha_auto = False

    db.session.commit()
    log.info(f"章节已更新: id={chapter_id}, CHA{chapter.chapter_number} "
             f"{chapter.title}, {chapter.word_count}字, {chapter.status}")
    return jsonify({"success": True, "chapter": chapter.to_dict()})


@api_projects_bp.route("/chapters/<int:chapter_id>", methods=["DELETE"])
def delete_chapter(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    log.info(f"删除章节: id={chapter_id}, CHA{chapter.chapter_number}")
    Revision.query.filter_by(target_type="chapter", target_id=chapter_id).delete(
        synchronize_session=False)
    db.session.delete(chapter)
    db.session.commit()
    return jsonify({"success": True})


@api_projects_bp.route("/chapters/<int:chapter_id>/precha/regenerate",
                       methods=["POST"])
def regenerate_precha(chapter_id):
    """重新从前一章抽取 PRECHA（手改过之后想重置，或前一章改了要刷新）"""
    chapter = Chapter.query.get_or_404(chapter_id)
    prev = context_builder.previous_chapter(chapter.project_id,
                                            chapter.chapter_number)
    if prev is None:
        return jsonify({"error": "没有前一章（或前一章还没有正文）"}), 400

    info = precha_service.extract_precha_from_chapter(prev)
    for k, v in info.items():
        setattr(chapter, k, v)
    chapter.precha_auto = True
    db.session.commit()
    log.info(f"PRECHA 重新生成: CHA{chapter.chapter_number} ← "
             f"CHA{prev.chapter_number}")
    return jsonify({"success": True, "chapter": chapter.to_dict(),
                    "precha_from": prev.chapter_number})


@api_projects_bp.route("/projects/<int:project_id>/reorder", methods=["PUT"])
def reorder_chapters(project_id):
    """
    重排章节。body: {order: [chapter_id, ...]}
    只改 sort_key 和 chapter_number，不动正文。
    """
    Project.query.get_or_404(project_id)
    order = (request.get_json() or {}).get("order") or []
    if not order:
        return jsonify({"error": "order 不能为空"}), 400

    chapters = {c.id: c for c in Chapter.query.filter_by(project_id=project_id).all()}
    if set(order) != set(chapters.keys()):
        return jsonify({"error": "order 必须包含且仅包含本作品的所有章节 id"}), 400

    # 先挪到不冲突的区间，再落位 —— 绕开 (project_id, chapter_number) 唯一约束
    for i, cid in enumerate(order, 1):
        chapters[cid].chapter_number = -i
    db.session.flush()
    for i, cid in enumerate(order, 1):
        ch = chapters[cid]
        ch.chapter_number = i
        ch.sort_key = float(i) * 1000.0
    db.session.commit()

    log.info(f"章节重排: project={project_id}, {len(order)} 章")
    result = Chapter.query.filter_by(project_id=project_id).order_by(
        Chapter.sort_key).all()
    return jsonify({"success": True, "chapters": [c.to_summary() for c in result]})


# ============================================================
# 命令行（续写 / 重写 / 按意见重写）
# ============================================================
@api_projects_bp.route("/chapters/<int:chapter_id>/command", methods=["POST"])
def chapter_command(chapter_id):
    """
    章节命令行入口（流式）。
    body: {op: 'generate'|'continue'|'rewrite', instruction?: str}
    """
    chapter = Chapter.query.get_or_404(chapter_id)
    data = request.get_json() or {}
    op = data.get("op", "generate")
    instruction = (data.get("instruction") or "").strip()

    if op not in ("generate", "continue", "rewrite"):
        return jsonify({"error": "op 必须是 generate / continue / rewrite"}), 400
    if op == "continue" and not (chapter.content or "").strip():
        return jsonify({"error": "本章还没有正文，无法续写；请先「生成」"}), 400
    if op == "rewrite" and not (chapter.content or "").strip():
        return jsonify({"error": "本章还没有正文，无法重写；请先「生成」"}), 400

    log.info(f"章节命令: CHA{chapter.chapter_number} op={op} "
             f"instruction={instruction[:60] or '(无)'}")

    ctx = context_builder.build_chapter_context(chapter, op=op,
                                               instruction=instruction)
    chapter_id_ = chapter.id
    prev_content = chapter.content or ""

    def generate():
        try:
            yield _sse({"type": "context", "snapshot": ctx["snapshot"]})

            new_text = ""
            for chunk in deepseek.chat_stream(
                ctx["user_message"],
                system_prompt=ctx["system_prompt"],
                max_tokens=8192,
            ):
                new_text += chunk
                yield _sse({"type": "text", "content": chunk})

            ch = db.session.get(Chapter, chapter_id_)

            # 续写是追加，其余是替换
            if op == "continue":
                final = (prev_content.rstrip() + "\n\n" + new_text.lstrip())
            else:
                final = new_text

            # 旧正文存版本，再写入新正文
            if prev_content:
                Revision.record("chapter", ch.id, prev_content,
                                op=op, instruction=instruction)
            ch.content = final
            ch.recount()
            ch.status = "draft"
            ch.context_snapshot = json.dumps(ctx["snapshot"], ensure_ascii=False)
            ch.knowledge_context = json.dumps(ctx["citations"], ensure_ascii=False)
            Revision.record("chapter", ch.id, final, op=op,
                            instruction=instruction or f"{op} 结果")
            db.session.commit()

            yield _sse({
                "type": "done",
                "content": final,
                "chapter": ch.to_dict(),
                "audit": context_builder.audit_snapshot(ch),
            })

        except Exception as e:
            db.session.rollback()
            log.error(f"章节命令失败: CHA{chapter.chapter_number} "
                      f"{type(e).__name__}: {e}", exc_info=True)
            yield _sse({"type": "error", "content": str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_projects_bp.route("/chapters/<int:chapter_id>/context", methods=["GET"])
def preview_context(chapter_id):
    """
    预览本章实际会注入的上下文。
    用来确认「叙述没越界」——能看到屏蔽了哪些未来设定、章节计划给到第几章。
    """
    chapter = Chapter.query.get_or_404(chapter_id)
    ctx = context_builder.build_chapter_context(chapter, op="generate")
    return jsonify({
        "snapshot": ctx["snapshot"],
        "system_prompt": ctx["system_prompt"],
        "citations": ctx["citations"],
    })


# ============================================================
# 版本历史
# ============================================================
@api_projects_bp.route("/chapters/<int:chapter_id>/revisions", methods=["GET"])
def list_chapter_revisions(chapter_id):
    Chapter.query.get_or_404(chapter_id)
    revs = (Revision.query.filter_by(target_type="chapter", target_id=chapter_id)
            .order_by(Revision.version_no.desc()).all())
    return jsonify([r.to_dict() for r in revs])


@api_projects_bp.route("/chapters/<int:chapter_id>/revisions/<int:version_no>",
                       methods=["GET"])
def get_chapter_revision(chapter_id, version_no):
    """取某一版的完整内容（用于对比）"""
    Chapter.query.get_or_404(chapter_id)
    rev = Revision.query.filter_by(
        target_type="chapter", target_id=chapter_id,
        version_no=version_no).first()
    if not rev:
        return jsonify({"error": f"版本 v{version_no} 不存在"}), 404
    return jsonify(rev.to_dict(with_content=True))


@api_projects_bp.route("/chapters/<int:chapter_id>/revert/<int:version_no>",
                       methods=["POST"])
def revert_chapter(chapter_id, version_no):
    """回滚到指定版本。当前内容会先存成一版，所以回滚本身也可撤销。"""
    chapter = Chapter.query.get_or_404(chapter_id)
    rev = Revision.query.filter_by(
        target_type="chapter", target_id=chapter_id,
        version_no=version_no).first()
    if not rev:
        return jsonify({"error": f"版本 v{version_no} 不存在"}), 404

    Revision.record("chapter", chapter.id, chapter.content or "",
                    op="revert", instruction=f"回滚前的内容（回到 v{version_no}）")
    chapter.content = rev.content
    chapter.recount()
    db.session.commit()
    log.info(f"章节回滚: CHA{chapter.chapter_number} → v{version_no}, "
             f"{chapter.word_count}字")
    return jsonify({"success": True, "chapter": chapter.to_dict()})


# ============================================================
# 作品级设定条目
# ============================================================
@api_projects_bp.route("/projects/<int:project_id>/entities", methods=["GET"])
def list_project_entities(project_id):
    Project.query.get_or_404(project_id)
    kind = request.args.get("kind")
    q = StoryEntity.query.filter_by(project_id=project_id)
    if kind:
        q = q.filter_by(kind=kind)
    items = q.order_by(StoryEntity.kind, StoryEntity.sort_order).all()
    return jsonify([e.to_dict() for e in items])


@api_projects_bp.route("/projects/<int:project_id>/entities", methods=["POST"])
def create_project_entity(project_id):
    Project.query.get_or_404(project_id)
    data = request.get_json() or {}
    kind = data.get("kind", "setting")
    if kind not in ENTITY_KINDS:
        return jsonify({"error": f"kind 必须是 {', '.join(ENTITY_KINDS)} 之一"}), 400
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "请填写名称"}), 400

    top = (StoryEntity.query.filter_by(project_id=project_id, kind=kind)
           .order_by(StoryEntity.sort_order.desc()).first())
    entity = StoryEntity(
        project_id=project_id, kind=kind, name=name,
        summary=data.get("summary", ""), detail=data.get("detail", ""),
        attributes=json.dumps(data.get("attributes") or {}, ensure_ascii=False),
        first_appear_chapter=data.get("first_appear_chapter"),
        sort_order=(top.sort_order + 1) if top else 0,
    )
    db.session.add(entity)
    db.session.commit()
    log.info(f"新增作品设定: project={project_id}, {kind}/{name}")
    return jsonify({"success": True, "entity": entity.to_dict()})


@api_projects_bp.route("/chapters/<int:chapter_id>/entities", methods=["PUT"])
def set_chapter_entities(chapter_id):
    """
    设置本章在场的设定条目。
    body: {links: [{entity_id, role}, ...]}
    设了之后，写这一章只注入这些条目，不再把全书人物都塞进提示词。
    """
    chapter = Chapter.query.get_or_404(chapter_id)
    links = (request.get_json() or {}).get("links") or []

    ChapterEntity.query.filter_by(chapter_id=chapter_id).delete(
        synchronize_session=False)
    for l in links:
        eid = l.get("entity_id")
        entity = db.session.get(StoryEntity, eid) if eid else None
        if not entity or entity.project_id != chapter.project_id:
            log.warning(f"跳过无效关联: entity_id={eid}")
            continue
        db.session.add(ChapterEntity(
            chapter_id=chapter_id, entity_id=eid,
            role=l.get("role", "onstage")))
    db.session.commit()

    result = ChapterEntity.query.filter_by(chapter_id=chapter_id).all()
    log.info(f"章节设定关联: CHA{chapter.chapter_number} → {len(result)} 条")
    return jsonify({"success": True, "links": [l.to_dict() for l in result]})
