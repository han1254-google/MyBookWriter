"""
创意工坊 API
"""
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context

from database import db, Idea
from services.deepseek_service import deepseek
from services.rag_service import rag
from app_config import WRITING_STYLE_GUIDE

api_ideas_bp = Blueprint("api_ideas", __name__)


@api_ideas_bp.route("/ideas/generate", methods=["POST"])
def generate_idea():
    """RAG 检索 + DeepSeek 流式生成创意"""
    data = request.get_json()
    user_prompt = data.get("prompt", "").strip()
    category = data.get("category", None)
    if not user_prompt:
        return jsonify({"error": "请输入提示词"}), 400

    # RAG 检索
    rag_context = rag.search(user_prompt, category=category) if rag.is_available else "（知识库未构建）"
    rag_results = rag.search_structured(user_prompt, category=category) if rag.is_available else []

    # 系统提示
    system_prompt = f"""{WRITING_STYLE_GUIDE}

你是一个科幻创意生成器。用户会给你一个写作提示，你需要在知识库的支持下，生成详细的科幻故事设定。

知识库参考资料：
{rag_context}

请生成一个完整的科幻故事设定，包含：
## 设定标题
一句话概括

## 核心科幻概念
详细描述核心的科学/技术设想

## 世界观
时间、地点、社会背景

## 主要角色
2-3个关键角色及其特点

## 故事主题
探讨的核心问题或哲学命题

## 开篇构想
故事的第一幕设想

请确保设定与知识库中的科学知识一致，不要凭空编造违反已知科学原理的内容。"""

    def generate():
        try:
            full_text = ""
            for chunk in deepseek.chat_stream(
                user_prompt, system_prompt=system_prompt, max_tokens=4096
            ):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            # 发送 RAG 和完成信号
            yield f"data: {json.dumps({'type': 'done', 'rag_results': rag_results, 'full_text': full_text}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@api_ideas_bp.route("/ideas/chat/<int:idea_id>", methods=["POST"])
def chat_idea(idea_id):
    """对话修改创意（流式）"""
    idea = Idea.query.get_or_404(idea_id)
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "请输入消息"}), 400

    # 加载对话历史
    try:
        history = json.loads(idea.chat_history or "[]")
    except json.JSONDecodeError:
        history = []

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你正在帮助用户完善一个科幻故事设定。当前设定如下：

{idea.content}

请根据用户的反馈修改设定。保持科幻设定的一致性和科学性。"""

    def generate():
        try:
            full_response = ""
            for chunk in deepseek.chat_stream(
                user_message,
                system_prompt=system_prompt,
                history=history[-10:],  # 只保留最近10轮
                max_tokens=4096,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            # 更新对话历史
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": full_response})
            idea.chat_history = json.dumps(history, ensure_ascii=False)
            db.session.commit()

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_ideas_bp.route("/ideas/save", methods=["POST"])
def save_idea():
    """保存创意"""
    data = request.get_json()
    title = data.get("title", "未命名创意")
    content = data.get("content", "")
    knowledge_context = data.get("knowledge_context", "{}")
    chat_history = data.get("chat_history", "[]")

    idea = Idea(
        title=title,
        content=content,
        knowledge_context=json.dumps(knowledge_context, ensure_ascii=False) if isinstance(knowledge_context, (list, dict)) else knowledge_context,
        chat_history=json.dumps(chat_history, ensure_ascii=False) if isinstance(chat_history, list) else chat_history,
    )
    db.session.add(idea)
    db.session.commit()

    return jsonify({"success": True, "id": idea.id, "idea": idea.to_dict()})


@api_ideas_bp.route("/ideas", methods=["GET"])
def list_ideas():
    """列出所有创意"""
    ideas = Idea.query.order_by(Idea.updated_at.desc()).all()
    return jsonify([i.to_dict() for i in ideas])


@api_ideas_bp.route("/ideas/<int:idea_id>", methods=["GET"])
def get_idea(idea_id):
    """获取创意详情"""
    idea = Idea.query.get_or_404(idea_id)
    return jsonify(idea.to_dict())


@api_ideas_bp.route("/ideas/<int:idea_id>", methods=["DELETE"])
def delete_idea(idea_id):
    """删除创意"""
    idea = Idea.query.get_or_404(idea_id)
    db.session.delete(idea)
    db.session.commit()
    return jsonify({"success": True})
