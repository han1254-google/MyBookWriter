"""
改写工坊 API
"""
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context

from services.deepseek_service import deepseek
from app_config import WRITING_STYLE_GUIDE
from logger import get_logger

api_rewrite_bp = Blueprint("api_rewrite", __name__)
log = get_logger("api.rewrite")


@api_rewrite_bp.route("/rewrite/analyze", methods=["POST"])
def analyze_article():
    """分析文章，返回风格诊断"""
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "请粘贴文章内容"}), 400

    if len(text) < 100:
        return jsonify({"error": "文章太短，请至少粘贴100字"}), 400

    log.info(f"分析文章: {len(text)} 字")

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你是一个专业的写作分析师。请对以下文章进行全面诊断。

分析维度：
1. **叙事视角**：是否为第一人称？叙述者是否保持了观察者的姿态？
2. **语言节奏**：长短句搭配是否得当？是否有高雅与世俗的切换？
3. **细节与数字**：是否有具体数字、真实品牌和地名？
4. **情感处理**：是否避免直接说出情感？是否用动作和物件承载情绪？
5. **幽默运用**：是否有恰当的自嘲式幽默调节节奏？
6. **对话质量**：对话是否稀疏简短？每句是否都在推动情节？
7. **结尾方式**：是否落在具体画面或动作上？是否避免总结道理？
8. **写作禁令检查**：是否有违禁项（直接情感陈述、陈词滥调、上帝视角等）？

请以 JSON 格式返回分析结果：
{{
  "scores": {{"叙事视角": 8, "语言节奏": 7, ...}},
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["问题1", "问题2"],
  "suggestions": ["改进建议1", "改进建议2"],
  "overall": "总体评价（2-3句）"
}}"""

    try:
        response = deepseek.chat(
            f"请分析以下文章：\n\n{text[:5000]}",
            system_prompt=system_prompt,
            max_tokens=2048,
        )
        # 尝试解析 JSON
        try:
            # 去掉可能的 markdown 代码块包装
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()
            result = json.loads(clean)
        except json.JSONDecodeError:
            result = {"raw_analysis": response}

        log.info(f"分析完成: {len(response)} 字符响应")
        return jsonify({"success": True, "analysis": result})

    except Exception as e:
        log.error(f"分析失败: {type(e).__name__}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@api_rewrite_bp.route("/rewrite/rewrite", methods=["POST"])
def rewrite_article():
    """改写文章（流式）"""
    data = request.get_json()
    text = data.get("text", "").strip()
    instructions = data.get("instructions", "").strip()

    if not text:
        return jsonify({"error": "请粘贴文章内容"}), 400

    log.info(f"改写文章: {len(text)} 字, instructions={instructions[:60] if instructions else '无'}")

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你是一个专业的写作修改顾问。请对用户的文章进行改写。

改写要求：
1. 保持原意和核心情节不变
2. 严格遵循写作风格指南
3. 加入具体数字和真实细节
4. 用动作和物件承载情感，不说"他很难过"之类的话
5. 长短句搭配，高雅与世俗切换
6. 对话不超过5轮，每句都在推动情节
7. 结尾落在具体画面或动作上
8. 适当加入自嘲式幽默调节沉重段落

用户额外要求：{instructions if instructions else '无'}

请在改写后，先简要说明改了什么（3-5条），然后用 --- 分隔，输出改写后的全文。"""

    def generate():
        try:
            full_text = ""
            for chunk in deepseek.chat_stream(
                f"请改写以下文章：\n\n{text[:8000]}",
                system_prompt=system_prompt,
                max_tokens=8192,
            ):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'full_text': full_text}, ensure_ascii=False)}\n\n"

        except Exception as e:
            log.error(f"改写流失败: {type(e).__name__}: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
