"""
写作 API — 章节生成、保存、导出
"""
import json
import re
from flask import Blueprint, request, jsonify, Response, stream_with_context

from database import db, Idea, Outline, Chapter
from services.deepseek_service import deepseek
from services.rag_service import rag
from app_config import WRITING_STYLE_GUIDE, PRECHA_TEMPLATE
from logger import get_logger

api_writing_bp = Blueprint("api_writing", __name__)
log = get_logger("api.writing")


def _extract_precha(chapter_text, prev_chapter):
    """从生成的章节文本中提取 PRECHA 信息"""
    precha_name = prev_chapter.title if prev_chapter else "/"
    precha_link = f"CHA{prev_chapter.chapter_number}.md" if prev_chapter else "/"

    # 尝试提取时间、地点等
    time_match = re.search(r'时间[：:]\s*(.+?)(?:\n|$)', chapter_text)
    place_match = re.search(r'地点[：:]\s*(.+?)(?:\n|$)', chapter_text)
    chars_match = re.search(r'人物[：:]\s*(.+?)(?:\n|$)', chapter_text)
    cause_match = re.search(r'起[：:]\s*(.+?)(?:\n|$)', chapter_text)
    process_match = re.search(r'经[：:]\s*(.+?)(?:\n|$)', chapter_text)
    result_match = re.search(r'结[：:]\s*(.+?)(?:\n|$)', chapter_text)
    media_match = re.search(r'媒[：:]\s*(.+?)(?:\n|$)', chapter_text)

    precha_content = f"""时间：{time_match.group(1) if time_match else ''}
地点：{place_match.group(1) if place_match else ''}
人物：{chars_match.group(1) if chars_match else ''}
起：{cause_match.group(1) if cause_match else ''}
经：{process_match.group(1) if process_match else ''}
结：{result_match.group(1) if result_match else ''}
媒：{media_match.group(1) if media_match else ''}"""

    return {
        "precha_name": precha_name,
        "precha_link": precha_link,
        "precha_content": precha_content,
    }


@api_writing_bp.route("/writing/start", methods=["POST"])
def start_writing():
    """从大纲开始写作，生成第一章"""
    data = request.get_json()
    outline_id = data.get("outline_id")
    if not outline_id:
        return jsonify({"error": "请选择大纲"}), 400

    outline = Outline.query.get_or_404(outline_id)
    idea = Idea.query.get(outline.idea_id) if outline.idea_id else None
    log.info(f"开始写作: outline_id={outline_id}, title={outline.title}")

    # 构建上下文
    idea_text = idea.content if idea else "（无设定）"
    rag_context = rag.search(outline.title + " " + outline.content[:200]) if rag.is_available else ""

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你是一个科幻小说作家。请根据以下设定和大纲，写出第一章。

## IDEA 设定
{idea_text}

## 完整大纲
{outline.content}

## 知识库参考资料
{rag_context}

## PRECHA 模板要求
第一章的前章信息为"/"（首章无前章）。

请严格使用以下模板格式输出：

# CHA1 章节名

## PRECHA
`上一章节的名字和文件链接`
prechaName /
prechaLink /
（首章，无前章）

## CONTENT

（正文开始）

写作要求：
- 第一人称叙事，叙述者是观察者
- 用具体数字和真实物件
- 不直接说情感，通过动作和环境表现
- 结尾落在具体画面或动作上
- 对话稀疏简短，不超过5轮
- 如遇沉重场景，用自嘲化解"""

    def generate():
        try:
            full_text = ""
            for chunk in deepseek.chat_stream(
                f"请写出第一章。", system_prompt=system_prompt, max_tokens=8192
            ):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            # 自动提取章节标题
            title_match = re.search(r'#\s*CHA\d+\s*(.+)', full_text)
            chapter_title = title_match.group(1).strip() if title_match else "第1章"

            yield f"data: {json.dumps({'type': 'done', 'full_text': full_text, 'chapter_title': chapter_title, 'chapter_number': 1}, ensure_ascii=False)}\n\n"

        except Exception as e:
            log.error(f"写作首章生成失败: {type(e).__name__}: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_writing_bp.route("/writing/chapter", methods=["POST"])
def generate_chapter():
    """生成下一个章节（带 PRECHA 上下文）"""
    data = request.get_json()
    outline_id = data.get("outline_id")
    chapter_num = data.get("chapter_number")

    if not outline_id or not chapter_num:
        return jsonify({"error": "缺少参数"}), 400

    outline = Outline.query.get_or_404(outline_id)
    idea = Idea.query.get(outline.idea_id) if outline.idea_id else None
    log.info(f"生成章节: outline_id={outline_id}, chapter_num={chapter_num}")

    # 获取上一章
    prev_chapter = Chapter.query.filter_by(
        outline_id=outline_id, chapter_number=chapter_num - 1
    ).first()

    if not prev_chapter or prev_chapter.status != "completed":
        log.warning(f"上一章未完成: prev_chapter={prev_chapter.id if prev_chapter else None}")
        return jsonify({"error": "请先完成上一章"}), 400

    # 构建上下文
    idea_text = idea.content if idea else ""
    rag_context = rag.search(
        outline.title + " " + (prev_chapter.content[:300] if prev_chapter else "")
    ) if rag.is_available else ""

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你是一个科幻小说作家。现在要写的是 **第{chapter_num}章**，不是第1章，不是上一章。请严格基于上下文创作全新的内容。

## IDEA 设定
{idea_text}

## 完整大纲
{outline.content}

## ⚠️ 上一章（CHA{chapter_num - 1}）的实际内容——你已经写完的，不要重复写它
**本章必须从上一章的结尾处继续推进剧情，不得重复上一章的任何段落。**

上一章结尾（请从这里继续写）：
```
{prev_chapter.content[-800:] if prev_chapter.content else '（无）'}
```

上一章 PRECHA 摘要：
{prev_chapter.precha_content}

## 知识库参考资料
{rag_context}

请严格使用以下模板格式输出（注意：标题是 CHA{chapter_num}，不是 CHA1）：

# CHA{chapter_num} 章节名

## PRECHA
`上一章节的名字和文件链接`
prechaName {prev_chapter.title}
prechaLink CHA{chapter_num - 1}.md

## PRECHA CONTENT
（在 PRECHA CONTENT 中填入上一章的时间、地点、人物、起因、经过、结果、媒）

## CONTENT

（正文从上一章结尾处开始，向前推进剧情）

⚠️ 严禁重复上一章的任何内容。你是继续写，不是复读。"""

    def generate():
        try:
            full_text = ""
            for chunk in deepseek.chat_stream(
                f"请写出第{chapter_num}章。",
                system_prompt=system_prompt,
                max_tokens=8192,
            ):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            # 提取章节标题
            title_match = re.search(r'#\s*CHA\d+\s*(.+)', full_text)
            chapter_title = title_match.group(1).strip() if title_match else f"第{chapter_num}章"

            yield f"data: {json.dumps({'type': 'done', 'full_text': full_text, 'chapter_title': chapter_title, 'chapter_number': chapter_num}, ensure_ascii=False)}\n\n"

        except Exception as e:
            log.error(f"章节生成失败(ch{chapter_num}): {type(e).__name__}: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_writing_bp.route("/writing/chat/<int:chapter_id>", methods=["POST"])
def chat_chapter(chapter_id):
    """对话修改当前章节（流式）"""
    chapter = Chapter.query.get_or_404(chapter_id)
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "请输入消息"}), 400

    log.info(f"章节对话: chapter_id={chapter_id}, msg={user_message[:60]}...")

    outline = Outline.query.get(chapter.outline_id)
    idea = Idea.query.get(outline.idea_id) if outline and outline.idea_id else None

    system_prompt = f"""{WRITING_STYLE_GUIDE}

你正在帮助用户修改小说章节。

## 当前章节
{chapter.content[:3000]}

## IDEA 设定
{idea.content[:500] if idea else '无'}

## 大纲
{outline.content[:1000] if outline else '无'}

请根据用户的反馈修改这一章。"""

    def generate():
        try:
            full_response = ""
            for chunk in deepseek.chat_stream(
                user_message, system_prompt=system_prompt, max_tokens=4096
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'full_text': full_response}, ensure_ascii=False)}\n\n"

        except Exception as e:
            log.error(f"章节对话失败(ch{chapter_id}): {type(e).__name__}: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_writing_bp.route("/writing/save", methods=["POST"])
def save_chapter():
    """保存章节"""
    data = request.get_json()
    outline_id = data.get("outline_id")
    chapter_number = data.get("chapter_number")
    title = data.get("title", "")
    content = data.get("content", "")
    status = data.get("status", "draft")

    if not outline_id or not chapter_number:
        return jsonify({"error": "缺少参数"}), 400

    chapter = Chapter.query.filter_by(
        outline_id=outline_id, chapter_number=chapter_number
    ).first()

    if not chapter:
        prev_chapter = Chapter.query.filter_by(
            outline_id=outline_id, chapter_number=chapter_number - 1
        ).first()
        precha_info = _extract_precha(content, prev_chapter)
        chapter = Chapter(
            outline_id=outline_id,
            chapter_number=chapter_number,
            title=title,
            content=content,
            status=status,
            precha_name=precha_info["precha_name"],
            precha_link=precha_info["precha_link"],
            precha_content=precha_info["precha_content"],
        )
        db.session.add(chapter)
        log.info(f"章节已创建: outline_id={outline_id}, ch{chapter_number}, title={title}, status={status}")
    else:
        chapter.title = title
        chapter.content = content
        chapter.status = status
        log.info(f"章节已更新: outline_id={outline_id}, ch{chapter_number}, title={title}, status={status}")

    db.session.commit()
    return jsonify({"success": True, "chapter": chapter.to_dict()})


@api_writing_bp.route("/writing/chapters/<int:outline_id>", methods=["GET"])
def get_chapters(outline_id):
    """获取某大纲所有章节"""
    chapters = Chapter.query.filter_by(outline_id=outline_id).order_by(
        Chapter.chapter_number
    ).all()
    log.debug(f"列出章节: outline_id={outline_id}, {len(chapters)} 章")
    return jsonify([c.to_dict() for c in chapters])


@api_writing_bp.route("/writing/export/<int:outline_id>", methods=["POST"])
def export_book(outline_id):
    """导出全书为单一 Markdown"""
    outline = Outline.query.get_or_404(outline_id)
    chapters = Chapter.query.filter_by(
        outline_id=outline_id, status="completed"
    ).order_by(Chapter.chapter_number).all()

    if not chapters:
        log.warning(f"导出失败: 没有已完成的章节, outline_id={outline_id}")
        return jsonify({"error": "没有已完成的章节"}), 400

    full_book = f"# {outline.title}\n\n"
    full_book += outline.content + "\n\n---\n\n"

    for ch in chapters:
        content = ch.content
        content_match = re.search(r'## CONTENT\s*\n(.+)', content, re.DOTALL)
        if content_match:
            content = content_match.group(1)
        full_book += f"# CHA{ch.chapter_number} {ch.title}\n\n{content}\n\n---\n\n"

    log.info(f"导出全书: outline_id={outline_id}, title={outline.title}, {len(chapters)} 章, {len(full_book)} 字")
    return jsonify({
        "success": True,
        "title": outline.title,
        "full_text": full_book,
        "chapter_count": len(chapters),
    })
