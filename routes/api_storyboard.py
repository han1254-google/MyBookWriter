"""
视觉化 / 分镜生成 API
"""
import json
from flask import Blueprint, request, Response, stream_with_context
from database import Idea
from services.deepseek_service import deepseek
from logger import get_logger

api_storyboard_bp = Blueprint("api_storyboard", __name__)
log = get_logger("api.storyboard")

# 预定义前缀模板
PRESET_PREFIXES = {
    "平原没有故事": """The Electric State Simon Stålenhag original illustration painting style, hand-painted oil texture, soft diffused rural light, desolate quiet melancholic graphic novel tone, adapted Chinese literary novel 《平原没有故事》, Huaihai Plain flat rural sci-fi mystery, timeline 2025–2060, alien spacecraft buried 60 meters underground outside Xiwa Village, microscopic proliferative alien spores floating high altitude forming thick natural-looking spore clouds that look almost like ordinary clouds, spore collective para-intelligence cloud consciousness hidden beneath normal cloud appearance, locals call the matte windowless cubic lab "Big Black Block", uncanny extraterrestrial subtle anomalies hidden within mundane farm life, protagonist Zhang Chengyuan always tiny distant figure, NO human close-ups, NO character front faces, all human figures back/side/overhead distant silhouette, Zhang Chengyuan wears a faded light gray-blue cotton shirt, dark washed blue trousers, old white sneakers, and in colder seasons a worn gray thin cotton jacket with a simple scarf, low saturation earth muted palette, faint atmospheric spore haze everywhere, subtle film grain, soft dark edge vignette, 2.39:1 ultra-wide panoramic composition, 35–85mm natural rural lens, minimal restrained sci-fi elements hidden in sky/horizon, vast endless flat wheat fields, poplar alleys, dirt tractor roads, old brick farmhouses, electric tricycles, faint faded white Chinese documentary subtitle centered at bottom frame, no exaggerated alien monsters or glowing neon, quiet uncanny rural desolation, spore clouds look naturally cloudy but slightly thicker, slower, denser, and faintly colder than normal clouds""",
}

# 字幕位置选项
SUBTITLE_POSITIONS = {
    "bottom-center": "centered faint faded white Chinese documentary subtitle centered at bottom frame",
    "bottom-left": "small faded white Chinese subtitle at bottom-left corner",
    "bottom-right": "small faded white Chinese subtitle at bottom-right corner",
    "top-center": "faint white Chinese subtitle centered at top of frame",
    "none": "no text, no subtitles, no words in image",
}


@api_storyboard_bp.route("/storyboard/generate", methods=["POST"])
def generate_storyboard():
    """生成分镜描述和绘图提示词"""
    data = request.get_json()
    idea_id = data.get("idea_id")
    scene_count = data.get("scene_count", 5)
    preset_key = data.get("preset_key", "")
    custom_prefix = data.get("custom_prefix", "").strip()
    subtitle_position = data.get("subtitle_position", "bottom-center")
    custom_notes = data.get("custom_notes", "").strip()

    if not idea_id:
        return {"error": "请选择创意"}, 400
    if scene_count < 2 or scene_count > 20:
        return {"error": "分镜数量 2-20"}, 400

    idea = Idea.query.get(idea_id)
    if not idea:
        return {"error": "创意不存在"}, 404

    # 确定前缀
    prefix = custom_prefix or PRESET_PREFIXES.get(preset_key, "")
    subtitle_rule = SUBTITLE_POSITIONS.get(subtitle_position, SUBTITLE_POSITIONS["bottom-center"])

    log.info(f"分镜生成: idea={idea.title}, scenes={scene_count}, preset={preset_key or 'custom'}, sub={subtitle_position}")

    prefix_section = ""
    if prefix:
        prefix_section = f"""
## 🎨 统一绘图前缀（每张图必须以此开头）
以下内容必须放在每个分镜的 image_prompt 最前面：
```
{prefix}
```
"""

    subtitle_section = f"""
## 📝 字幕规则
每个分镜必须有 1-2 句中文字幕，字幕格式：{subtitle_rule}
字幕内容必须由你（AI）根据当个分镜的场景来写。字幕要求：简洁、冷淡、像纪录片旁白，不煽情。
"""

    custom_notes_section = f"## 📌 额外要求\n{custom_notes}" if custom_notes else ""

    system_prompt = f"""你是一个专业的电影分镜师和 AI 绘图提示词工程师。请根据以下故事设定，生成 {scene_count} 个分镜。

## 📖 故事设定
{idea.content[:5000]}
{prefix_section}
{subtitle_section}
## ⚠️ 一致性要求（极其重要）
- 所有分镜共享同一套角色外貌、服装、建筑风格、色调
- 角色外貌在每个分镜中必须一致（头发颜色、体型、标志性服装）
- 关键场景元素（建筑、植物、天气、光线方向）跨分镜保持一致
- 每个 image_prompt 必须包含统一前缀（上面 🎨 部分）
- 如果故事有时间推进，角色的年龄/季节变化必须渐进

{custom_notes_section}

## 📐 输出格式
请严格按照以下 JSON 数组格式输出，不要其他文字。每个元素是一个分镜：

```json
[
  {{
    "scene_number": 1,
    "scene_title": "分镜标题（中文，4-8字）",
    "time_of_day": "时间段/季节",
    "description": "场景描述（中文，50-100字）",
    "image_prompt": "统一前缀 + 场景专属英文描述（英文，适配DALL-E/GPT-4o）",
    "subtitle": "中文字幕（1-2句）"
  }},
  ...
]
```

注意：
- image_prompt 必须以统一前缀开头（如果有的话），再加上场景专属描述
- image_prompt 中的场景描述部分用英文，确保与 AI 绘图工具兼容
- subtitle 用中文
- 输出纯 JSON，不要 markdown 代码块包裹"""

    def generate():
        try:
            full_text = ""
            for chunk in deepseek.chat_stream(
                "请生成分镜。", system_prompt=system_prompt, max_tokens=8192
            ):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            # 尝试解析 JSON
            try:
                clean = full_text.strip()
                if clean.startswith("```"):
                    lines = clean.split("\n")
                    lines = lines[1:]
                    if lines[-1].strip() == "```":
                        lines = lines[:-1]
                    clean = "\n".join(lines)
                scenes = json.loads(clean)
                log.info(f"分镜生成完成: {len(scenes)} 个场景")
                yield f"data: {json.dumps({'type': 'done', 'scenes': scenes, 'full_text': full_text}, ensure_ascii=False)}\n\n"
            except json.JSONDecodeError:
                yield f"data: {json.dumps({'type': 'done', 'raw_text': full_text}, ensure_ascii=False)}\n\n"

        except Exception as e:
            log.error(f"分镜生成失败: {type(e).__name__}: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_storyboard_bp.route("/storyboard/presets", methods=["GET"])
def get_presets():
    """获取所有预定义前缀和字幕位置选项"""
    return {
        "presets": [{"key": k, "label": k, "preview": v[:120] + "..."} for k, v in PRESET_PREFIXES.items()],
        "subtitle_positions": [{"key": k, "label": {"bottom-center": "底部居中", "bottom-left": "左下角", "bottom-right": "右下角", "top-center": "顶部居中", "none": "无字幕"}.get(k, k)} for k in SUBTITLE_POSITIONS],
    }
