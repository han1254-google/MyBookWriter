"""
创意工坊 API
"""
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context

from database import db, Idea
from services.deepseek_service import deepseek
from services.rag_service import rag
from app_config import WRITING_STYLE_GUIDE
from logger import get_logger

api_ideas_bp = Blueprint("api_ideas", __name__)
log = get_logger("api.ideas")


def _format_rag_context(results, label):
    """将 RAG 搜索结果格式化为提示词上下文"""
    if not results:
        return f"（无{label}相关内容）"
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"【{label}{i}】{r['filename']} (分类:{r['category']}, 相似度:{r['similarity']})\n{r['content'][:600]}")
    return "\n\n---\n\n".join(parts)


@api_ideas_bp.route("/ideas/generate", methods=["POST"])
def generate_idea():
    """三库联合检索 + DeepSeek 流式生成创意"""
    data = request.get_json()
    user_prompt = data.get("prompt", "").strip()
    if not user_prompt:
        return jsonify({"error": "请输入提示词"}), 400

    log.info(f"生成创意: prompt={user_prompt[:80]}...")

    # ---- 三库联合检索 ----
    if rag.is_available:
        all_results = rag.search_all(user_prompt)
        knowledge_results = all_results.get("knowledge", [])
        reference_results = all_results.get("reference", [])
        style_results = all_results.get("style", [])

        # 拼接知识库上下文（科学事实）
        knowledge_context = _format_rag_context(knowledge_results, "领域知识")
        # 拼接参考库上下文（他人创意）
        reference_context = _format_rag_context(reference_results, "参考创意")
        # 拼接风格库上下文（写作风格）
        style_context = _format_rag_context(style_results, "风格参考")

        log.info(f"三库检索: 知识={len(knowledge_results)}条, 参考={len(reference_results)}条, 风格={len(style_results)}条")
    else:
        knowledge_context = "（知识库未构建）"
        reference_context = "（参考库未构建）"
        style_context = "（风格库未构建）"

    # ---- 综合提示词 ----
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
请生成一个完整的科幻故事设定，包含以下结构：

# 设定标题
一句话概括核心概念

## 核心科幻概念
详细描述核心的科学/技术设想（必须与领域知识一致）

## 世界观
时间、地点、社会背景

## 主要角色
2-3个关键角色及其特点

## 故事主题
探讨的核心问题或哲学命题

## 开篇构想
故事的第一幕设想

## 参考来源
列出本次使用的主要参考资料（如果有的话）

重要原则：
- 科学设定必须与领域知识保持一致，不要凭空编造
- 从参考创意中吸取叙事技巧但创造原创内容
- 如风格参考可用，融入其语言节奏和情感处理方式"""

    def generate():
        try:
            full_text = ""
            for chunk in deepseek.chat_stream(
                user_prompt, system_prompt=system_prompt, max_tokens=4096
            ):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            # 构建结构化 RAG 结果返回前端
            rag_info = {
                "knowledge": [{"filename": r["filename"], "category": r["category"], "similarity": r["similarity"]}
                              for r in knowledge_results] if rag.is_available else [],
                "reference": [{"filename": r["filename"], "category": r["category"], "similarity": r["similarity"]}
                              for r in reference_results] if rag.is_available else [],
                "style": [{"filename": r["filename"], "category": r["category"], "similarity": r["similarity"]}
                          for r in style_results] if rag.is_available else [],
            }
            yield f"data: {json.dumps({'type': 'done', 'rag_results': rag_info, 'full_text': full_text}, ensure_ascii=False)}\n\n"

        except Exception as e:
            log.error(f"创意生成流失败: {type(e).__name__}: {e}", exc_info=True)
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

    log.info(f"创意对话: idea_id={idea_id}, msg={user_message[:60]}...")

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
            log.error(f"创意对话流失败: {type(e).__name__}: {e}", exc_info=True)
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
    log.info(f"创意已保存: id={idea.id}, title={title}")

    return jsonify({"success": True, "id": idea.id, "idea": idea.to_dict()})


@api_ideas_bp.route("/ideas", methods=["GET"])
def list_ideas():
    """列出所有创意"""
    ideas = Idea.query.order_by(Idea.updated_at.desc()).all()
    log.debug(f"列出创意: {len(ideas)} 个")
    return jsonify([i.to_dict() for i in ideas])


@api_ideas_bp.route("/ideas/<int:idea_id>", methods=["GET"])
def get_idea(idea_id):
    """获取创意详情"""
    idea = Idea.query.get_or_404(idea_id)
    log.debug(f"获取创意: id={idea_id}, title={idea.title}")
    return jsonify(idea.to_dict())


@api_ideas_bp.route("/ideas/<int:idea_id>", methods=["DELETE"])
def delete_idea(idea_id):
    """删除创意"""
    idea = Idea.query.get_or_404(idea_id)
    log.info(f"删除创意: id={idea_id}, title={idea.title}")
    db.session.delete(idea)
    db.session.commit()
    return jsonify({"success": True})
