"""
创意工坊 API
"""
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context

from database import db, Idea, StoryEntity, Revision, ENTITY_KINDS
from services.deepseek_service import deepseek
from services.rag_service import rag
from services import retrieval_service as rs
from services import idea_service
from app_config import WRITING_STYLE_GUIDE
from logger import get_logger

api_ideas_bp = Blueprint("api_ideas", __name__)
log = get_logger("api.ideas")


def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@api_ideas_bp.route("/rag/files", methods=["GET"])
def get_rag_files():
    """列出向量库中所有已索引的文件（按三库分组）"""
    files = rag.files
    log.debug(f"RAG文件列表: {len(files)} 个")
    return jsonify(files)


# ============================================================
# 生成
# ============================================================
@api_ideas_bp.route("/ideas/generate", methods=["POST"])
def generate_idea():
    """三库联合检索 + DeepSeek 流式生成创意，完成后自动结构化"""
    data = request.get_json()
    user_prompt = data.get("prompt", "").strip()
    if not user_prompt:
        return jsonify({"error": "请输入提示词"}), 400

    # 用户选定的文件（source 路径列表），空 = 全库检索
    files = data.get("files") or None
    if files and not isinstance(files, list):
        files = None

    log.info(f"生成创意: prompt={user_prompt[:80]}..., files={len(files) if files else '全库'}")

    # ---- 三库联合检索（查询改写 + RRF + 来源配额）----
    if rag.is_available:
        found = rs.search_all(user_prompt, sources=files)
        knowledge_results = found["knowledge"]
        reference_results = found["reference"]
        style_results = found["style"]
        plan = found["plan"]

        knowledge_context = rs.format_context(knowledge_results, "领域知识")
        reference_context = rs.format_context(reference_results, "参考创意")
        style_context = rs.format_context(style_results, "风格参考")

        for label, hits in (("知识", knowledge_results), ("参考", reference_results),
                            ("风格", style_results)):
            st = rs.diversity_stats(hits)
            log.info(f"  {label}库: {st['count']}条 / {st['files']}文件 / "
                     f"{st['categories']}分类 / 最大单文件占比{st['max_file_share']:.0%}")
    else:
        knowledge_results = reference_results = style_results = []
        plan = {"queries": [], "terms": []}
        knowledge_context = "（知识库未构建）"
        reference_context = "（参考库未构建）"
        style_context = "（风格库未构建）"

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你是一个科幻创意生成器。用户会给你一个写作提示，你将基于三库参考内容，生成详细的科幻故事设定。

## 📚 领域知识（科学事实依据）
请以以下科学知识为基础，确保设定科学合理：
{knowledge_context}

## 📖 参考创意（他人作品风格与思路）
以下创意内容供你参考叙事方式和构思角度，请吸收其优点但不直接复制：
{reference_context}

## 🎨 风格启发（写作风格特征）
如果以下有风格参考，请在行文中融入这些风格特征：
{style_context}

## ✍️ 生成要求
请严格按以下小标题结构输出（小标题会被程序解析，不要改名、不要增删层级）：

# 设定标题
（紧接标题写一句话概括核心概念，不要小标题）

## 核心科幻概念
详细描述核心的科学/技术设想（必须与领域知识一致）

## 世界观
时间、地点、社会背景

## 主要角色
2-3 个关键角色。每个角色用 `### 角色名` 起头，写清身份、年龄、与他人的关系、
说话习惯、外貌上的标志性特征。

## 故事主题
探讨的核心问题或哲学命题

## 开篇构想
故事的第一幕设想

## 参考来源
列出本次生成实际参考的具体资料，格式：
- 📚 [文件名]：引用了什么知识点
- 📖 [文件名]：参考了什么叙事思路
- 🎨 [文件名]：融入了什么风格特征

重要原则：
- 科学设定必须与领域知识保持一致，不要凭空编造
- 如果上面某一库标注「未检索到」，就不要假装参考了它
- 从参考创意中吸取叙事技巧但创造原创内容
- 如风格参考可用，融入其语言节奏和情感处理方式"""

    def generate():
        try:
            if plan.get("queries"):
                yield _sse({"type": "plan", "queries": plan["queries"],
                            "terms": plan.get("terms", [])})

            full_text = ""
            for chunk in deepseek.chat_stream(
                user_prompt, system_prompt=system_prompt, max_tokens=8192
            ):
                full_text += chunk
                yield _sse({"type": "text", "content": chunk})

            citations = {
                "knowledge": rs.to_citations(knowledge_results),
                "reference": rs.to_citations(reference_results),
                "style": rs.to_citations(style_results),
            }

            # ---- 结构化（人物卡 / 世界观 / 设定）----
            yield _sse({"type": "status", "content": "正在结构化设定..."})
            flat_citations = (citations["knowledge"] + citations["reference"]
                              + citations["style"])
            structure = idea_service.structure_idea(full_text, citations=flat_citations)

            yield _sse({
                "type": "done",
                "full_text": full_text,
                "rag_results": citations,
                "structure": structure,
            })

        except Exception as e:
            log.error(f"创意生成流失败: {type(e).__name__}: {e}", exc_info=True)
            yield _sse({"type": "error", "content": str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# 命令行式修改（替代原右侧对话框）
# ============================================================
@api_ideas_bp.route("/ideas/<int:idea_id>/command", methods=["POST"])
def command_idea(idea_id):
    """
    按指令重写创意（流式）。对应界面底部命令行。
    op: rewrite（按意见重写整篇） / expand（就某一节展开）
    """
    idea = Idea.query.get_or_404(idea_id)
    data = request.get_json() or {}
    instruction = (data.get("instruction") or "").strip()
    op = data.get("op", "rewrite")
    section = (data.get("section") or "").strip()

    if not instruction:
        return jsonify({"error": "请输入修改意见"}), 400

    log.info(f"创意指令: id={idea_id}, op={op}, section={section or '全篇'}, "
             f"instruction={instruction[:60]}")

    scope = f"只修改「{section}」这一节，其余部分原样保留。" if section else "输出修改后的完整设定。"

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你正在帮助用户完善一个科幻故事设定。当前设定如下：

{idea.content}

用户会给出修改意见。请据此修改设定，保持科幻设定的一致性和科学性。
{scope}

输出要求：
- 保持与原文相同的小标题结构（# 标题 / ## 核心科幻概念 / ## 世界观 /
  ## 主要角色 / ## 故事主题 / ## 开篇构想 / ## 参考来源）
- 直接输出设定正文，不要写「好的」「已修改」之类的话
- 没被要求改的部分保持原样，不要顺手重写"""

    def generate():
        try:
            full_text = ""
            for chunk in deepseek.chat_stream(
                instruction, system_prompt=system_prompt, max_tokens=8192
            ):
                full_text += chunk
                yield _sse({"type": "text", "content": chunk})

            # 存版本 + 更新正文 + 重新结构化
            Revision.record("idea", idea.id, idea.content,
                            op="rewrite", instruction=instruction)
            idea.content = full_text
            structure = idea_service.structure_idea(full_text)
            idea_service.apply_structure(idea, structure)
            db.session.commit()

            yield _sse({"type": "done", "full_text": full_text,
                        "structure": structure})

        except Exception as e:
            db.session.rollback()
            log.error(f"创意指令失败: {type(e).__name__}: {e}", exc_info=True)
            yield _sse({"type": "error", "content": str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# CRUD
# ============================================================
@api_ideas_bp.route("/ideas/save", methods=["POST"])
def save_idea():
    """新建创意（带结构化数据）"""
    data = request.get_json() or {}
    content = data.get("content", "")
    structure = data.get("structure") or {}

    title = (data.get("title") or structure.get("title") or "").strip()
    if not title:
        title = idea_service.extract_title(content) or "未命名创意"

    knowledge_context = data.get("knowledge_context", "{}")
    if isinstance(knowledge_context, (list, dict)):
        knowledge_context = json.dumps(knowledge_context, ensure_ascii=False)

    idea = Idea(title=title, content=content, knowledge_context=knowledge_context)
    db.session.add(idea)
    db.session.flush()

    # 前端没带结构化结果时（比如手动新建），服务端补算一次
    if not structure and content:
        structure = idea_service.structure_idea(content)
    n_entities = idea_service.apply_structure(idea, structure) if structure else 0

    Revision.record("idea", idea.id, content, op="generate")
    db.session.commit()
    log.info(f"创意已保存: id={idea.id}, title={title}, 实体{n_entities}条, "
             f"结构化={'成功' if idea.structured_ok else '不完整'}")

    return jsonify({"success": True, "id": idea.id,
                    "idea": idea.to_dict(with_entities=True)})


@api_ideas_bp.route("/ideas/<int:idea_id>", methods=["PUT"])
def update_idea(idea_id):
    """
    更新已有创意。
    原来只有 /ideas/save 且永远 INSERT，编辑已存创意会产生副本 —— 这里修掉。
    """
    idea = Idea.query.get_or_404(idea_id)
    data = request.get_json() or {}

    if "content" in data and data["content"] != idea.content:
        Revision.record("idea", idea.id, idea.content,
                        op="manual", instruction="手动编辑")
        idea.content = data["content"]
        # 正文变了，结构化字段跟着重算（除非调用方明确给了）
        if not data.get("skip_restructure"):
            structure = idea_service.structure_idea(idea.content)
            idea_service.apply_structure(idea, structure)

    for field in ("title", "one_liner", "core_concept", "worldview",
                  "themes", "opening"):
        if field in data:
            setattr(idea, field, data[field])

    db.session.commit()
    log.info(f"创意已更新: id={idea_id}, title={idea.title}")
    return jsonify({"success": True, "idea": idea.to_dict(with_entities=True)})


@api_ideas_bp.route("/ideas/<int:idea_id>/restructure", methods=["POST"])
def restructure_idea(idea_id):
    """重新结构化（给旧数据补人物卡用）"""
    idea = Idea.query.get_or_404(idea_id)
    if not (idea.content or "").strip():
        return jsonify({"error": "创意没有正文，无法结构化"}), 400

    structure = idea_service.structure_idea(idea.content)
    n = idea_service.apply_structure(idea, structure)
    db.session.commit()
    log.info(f"创意重新结构化: id={idea_id}, 实体{n}条, "
             f"结果={'成功' if idea.structured_ok else '不完整'}")
    return jsonify({"success": True, "entity_count": n,
                    "idea": idea.to_dict(with_entities=True)})


@api_ideas_bp.route("/ideas", methods=["GET"])
def list_ideas():
    """列出所有创意"""
    ideas = Idea.query.order_by(Idea.updated_at.desc()).all()
    log.debug(f"列出创意: {len(ideas)} 个")
    return jsonify([i.to_dict() for i in ideas])


@api_ideas_bp.route("/ideas/<int:idea_id>", methods=["GET"])
def get_idea(idea_id):
    """获取创意详情（含人物卡 / 世界观 / 设定）"""
    idea = Idea.query.get_or_404(idea_id)
    log.debug(f"获取创意: id={idea_id}, title={idea.title}")
    return jsonify(idea.to_dict(with_entities=True))


@api_ideas_bp.route("/ideas/<int:idea_id>", methods=["DELETE"])
def delete_idea(idea_id):
    """删除创意"""
    idea = Idea.query.get_or_404(idea_id)
    log.info(f"删除创意: id={idea_id}, title={idea.title}")
    Revision.query.filter_by(target_type="idea", target_id=idea_id).delete(
        synchronize_session=False)
    db.session.delete(idea)
    db.session.commit()
    return jsonify({"success": True})


# ============================================================
# 结构化条目（人物卡 / 世界观 / 设定）
# ============================================================
@api_ideas_bp.route("/ideas/<int:idea_id>/entities", methods=["GET"])
def list_entities(idea_id):
    Idea.query.get_or_404(idea_id)
    kind = request.args.get("kind")
    q = StoryEntity.query.filter_by(idea_id=idea_id)
    if kind:
        q = q.filter_by(kind=kind)
    items = q.order_by(StoryEntity.kind, StoryEntity.sort_order).all()
    return jsonify([e.to_dict() for e in items])


@api_ideas_bp.route("/ideas/<int:idea_id>/entities", methods=["POST"])
def create_entity(idea_id):
    Idea.query.get_or_404(idea_id)
    data = request.get_json() or {}
    kind = data.get("kind", "setting")
    if kind not in ENTITY_KINDS:
        return jsonify({"error": f"kind 必须是 {', '.join(ENTITY_KINDS)} 之一"}), 400
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "请填写名称"}), 400

    top = (StoryEntity.query.filter_by(idea_id=idea_id, kind=kind)
           .order_by(StoryEntity.sort_order.desc()).first())
    entity = StoryEntity(
        idea_id=idea_id,
        kind=kind,
        name=name,
        summary=data.get("summary", ""),
        detail=data.get("detail", ""),
        attributes=json.dumps(data.get("attributes") or {}, ensure_ascii=False),
        first_appear_chapter=data.get("first_appear_chapter"),
        sort_order=(top.sort_order + 1) if top else 0,
    )
    db.session.add(entity)
    db.session.commit()
    log.info(f"新增条目: idea={idea_id}, {kind}/{name}")
    return jsonify({"success": True, "entity": entity.to_dict()})


@api_ideas_bp.route("/entities/<int:entity_id>", methods=["PUT"])
def update_entity(entity_id):
    entity = StoryEntity.query.get_or_404(entity_id)
    data = request.get_json() or {}

    if "kind" in data:
        if data["kind"] not in ENTITY_KINDS:
            return jsonify({"error": f"kind 必须是 {', '.join(ENTITY_KINDS)} 之一"}), 400
        entity.kind = data["kind"]
    for field in ("name", "summary", "detail", "sort_order"):
        if field in data:
            setattr(entity, field, data[field])
    if "attributes" in data:
        entity.attributes = json.dumps(data["attributes"] or {}, ensure_ascii=False)
    if "first_appear_chapter" in data:
        entity.first_appear_chapter = data["first_appear_chapter"]

    db.session.commit()
    log.info(f"更新条目: id={entity_id}, {entity.kind}/{entity.name}")
    return jsonify({"success": True, "entity": entity.to_dict()})


@api_ideas_bp.route("/entities/<int:entity_id>", methods=["DELETE"])
def delete_entity(entity_id):
    entity = StoryEntity.query.get_or_404(entity_id)
    log.info(f"删除条目: id={entity_id}, {entity.kind}/{entity.name}")
    db.session.delete(entity)
    db.session.commit()
    return jsonify({"success": True})


# ============================================================
# 版本历史
# ============================================================
@api_ideas_bp.route("/ideas/<int:idea_id>/revisions", methods=["GET"])
def list_idea_revisions(idea_id):
    Idea.query.get_or_404(idea_id)
    revs = (Revision.query.filter_by(target_type="idea", target_id=idea_id)
            .order_by(Revision.version_no.desc()).all())
    return jsonify([r.to_dict() for r in revs])


@api_ideas_bp.route("/ideas/<int:idea_id>/revert/<int:version_no>", methods=["POST"])
def revert_idea(idea_id, version_no):
    idea = Idea.query.get_or_404(idea_id)
    rev = Revision.query.filter_by(
        target_type="idea", target_id=idea_id, version_no=version_no).first()
    if not rev:
        return jsonify({"error": f"版本 v{version_no} 不存在"}), 404

    Revision.record("idea", idea.id, idea.content,
                    op="revert", instruction=f"回滚到 v{version_no}")
    idea.content = rev.content
    structure = idea_service.structure_idea(idea.content)
    idea_service.apply_structure(idea, structure)
    db.session.commit()
    log.info(f"创意回滚: id={idea_id} → v{version_no}")
    return jsonify({"success": True, "idea": idea.to_dict(with_entities=True)})
