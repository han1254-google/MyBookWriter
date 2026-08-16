"""
大纲工坊 API
"""
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context

from database import db, Idea, Outline
from services.deepseek_service import deepseek
from services.rag_service import rag
from app_config import WRITING_STYLE_GUIDE
from logger import get_logger

api_outlines_bp = Blueprint("api_outlines", __name__)
log = get_logger("api.outlines")


@api_outlines_bp.route("/outlines/generate", methods=["POST"])
def generate_outline():
    """生成大纲（流式）"""
    data = request.get_json()
    idea_id = data.get("idea_id", None)
    user_prompt = data.get("prompt", "").strip()

    if not idea_id and not user_prompt:
        return jsonify({"error": "请选择创意或输入提示"}), 400

    log.info(f"生成大纲: idea_id={idea_id}, prompt={user_prompt[:80] if user_prompt else 'N/A'}")

    # 构建上下文
    idea_context = ""
    rag_context = ""
    if idea_id:
        idea = Idea.query.get(idea_id)
        if idea:
            idea_context = f"""基于以下故事设定生成大纲：

{idea.content}"""
            # RAG 检索相关科学知识
            rag_context = rag.search(idea.title + " " + idea.content[:200]) if rag.is_available else ""
    else:
        rag_context = rag.search(user_prompt) if rag.is_available else ""

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你是一个科幻故事大纲规划师。请根据用户的设定，生成一个完整的章节目录式大纲。

知识库参考资料：
{rag_context}

请按照以下格式生成大纲：

# 大纲标题

## 故事概要
一句话概述

## 核心主题
2-3个核心主题

## 章节规划

### CHA1：章节名
- 场景
- 关键事件
- 情感弧线
- 需要展现的设定

### CHA2：章节名
（同上格式）

...（7-10章）

### 终章：章节名
- 场景
- 结局方式
- 回归的意象

请确保每章之间有清晰的因果关系和情感递进。"""

    user_msg = idea_context or user_prompt

    def generate():
        try:
            full_text = ""
            for chunk in deepseek.chat_stream(
                user_msg, system_prompt=system_prompt, max_tokens=8192
            ):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'full_text': full_text}, ensure_ascii=False)}\n\n"

        except Exception as e:
            log.error(f"大纲生成流失败: {type(e).__name__}: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_outlines_bp.route("/outlines/chat/<int:outline_id>", methods=["POST"])
def chat_outline(outline_id):
    """对话修改大纲（流式）"""
    outline = Outline.query.get_or_404(outline_id)
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "请输入消息"}), 400

    log.info(f"大纲对话: outline_id={outline_id}, msg={user_message[:60]}...")

    try:
        history = json.loads(outline.chat_history or "[]")
    except json.JSONDecodeError:
        history = []

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你正在帮助用户完善一个故事大纲。当前大纲：

{outline.content}

请根据用户的反馈修改大纲。保持章节结构的清晰和故事逻辑的连贯。"""

    def generate():
        try:
            full_response = ""
            for chunk in deepseek.chat_stream(
                user_message,
                system_prompt=system_prompt,
                history=history[-10:],
                max_tokens=4096,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": full_response})
            outline.chat_history = json.dumps(history, ensure_ascii=False)
            db.session.commit()

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            log.error(f"大纲对话流失败: {type(e).__name__}: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_outlines_bp.route("/outlines/save", methods=["POST"])
def save_outline():
    """保存大纲"""
    data = request.get_json()
    idea_id = data.get("idea_id", None)
    title = data.get("title", "未命名大纲")
    content = data.get("content", "")
    knowledge_context = data.get("knowledge_context", "{}")

    outline = Outline(
        idea_id=idea_id,
        title=title,
        content=content,
        knowledge_context=json.dumps(knowledge_context, ensure_ascii=False) if isinstance(knowledge_context, (list, dict)) else knowledge_context,
    )
    db.session.add(outline)
    db.session.commit()
    log.info(f"大纲已保存: id={outline.id}, title={title}, idea_id={idea_id}")

    return jsonify({"success": True, "id": outline.id, "outline": outline.to_dict()})


@api_outlines_bp.route("/outlines", methods=["GET"])
def list_outlines():
    """列出所有大纲"""
    outlines = Outline.query.order_by(Outline.updated_at.desc()).all()
    log.debug(f"列出大纲: {len(outlines)} 个")
    return jsonify([o.to_dict() for o in outlines])


@api_outlines_bp.route("/outlines/<int:outline_id>", methods=["GET"])
def get_outline(outline_id):
    """获取大纲详情"""
    outline = Outline.query.get_or_404(outline_id)
    log.debug(f"获取大纲: id={outline_id}, title={outline.title}")
    return jsonify(outline.to_dict())


@api_outlines_bp.route("/outlines/<int:outline_id>", methods=["DELETE"])
def delete_outline(outline_id):
    """删除大纲"""
    outline = Outline.query.get_or_404(outline_id)
    log.info(f"删除大纲: id={outline_id}, title={outline.title}")
    db.session.delete(outline)
    db.session.commit()
    return jsonify({"success": True})
