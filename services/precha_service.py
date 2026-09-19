"""
PRECHA 服务 — 上一章摘要的解析、渲染与自动生成

PRECHA 是本项目的核心机制：写 CHAn 时，叙述者的知识范围截止于 CHAn 的时间点，
所以必须显式地把「上一章发生了什么」压缩成 时间/地点/人物/起/经/结/媒 七项，
而不是把前文原样塞进提示词。
"""
import re
import json

from database import PRECHA_FIELDS, PRECHA_LABELS
from logger import get_logger

log = get_logger("service.precha")


# ============================================================
# 解析
# ============================================================
# 注意：分隔符后只能吃空格和 TAB，**不能用 \s*** ——
# \s 包含 \n，会把换行吃掉，导致空字段捕获到下一行的标签
# （旧 routes/api_writing.py 就是这个 bug，PRECHA 一直是错位数据）。
_FIELD_PATTERNS = {
    "precha_time":    r"^[ \t]*时间[：:][ \t]*(.*)$",
    "precha_place":   r"^[ \t]*地点[：:][ \t]*(.*)$",
    "precha_chars":   r"^[ \t]*人物[：:][ \t]*(.*)$",
    "precha_cause":   r"^[ \t]*起[：:][ \t]*(.*)$",
    "precha_process": r"^[ \t]*经[：:][ \t]*(.*)$",
    "precha_result":  r"^[ \t]*结[：:][ \t]*(.*)$",
    "precha_media":   r"^[ \t]*媒[：:][ \t]*(.*)$",
}

_NAME_PATTERN = r"^[ \t]*prechaName[ \t]+(.*)$"
_LINK_PATTERN = r"^[ \t]*prechaLink[ \t]+(.*)$"


def split_precha(text):
    """
    把 PRECHA CONTENT 文本块拆成独立字段。
    返回 {precha_time, precha_place, precha_chars, precha_cause,
          precha_process, precha_result, precha_media}
    """
    out = {f: "" for f in PRECHA_FIELDS}
    if not text:
        return out
    for field, pattern in _FIELD_PATTERNS.items():
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            out[field] = m.group(1).strip()
    return out


def parse_precha_header(text):
    """从章节文本里取 prechaName / prechaLink"""
    name = re.search(_NAME_PATTERN, text or "", re.MULTILINE)
    link = re.search(_LINK_PATTERN, text or "", re.MULTILINE)
    return {
        "precha_name": (name.group(1).strip() if name else ""),
        "precha_link": (link.group(1).strip() if link else ""),
    }


def strip_precha(text):
    """去掉 PRECHA 元数据，只留 CONTENT 正文（导出和字数统计用）"""
    if not text:
        return ""
    m = re.search(r"##\s*CONTENT\s*\n(.+)", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 没有 PRECHA 结构时，去掉首行标题
    m2 = re.search(r"^#[^\n]*\n(.+)", text, re.DOTALL)
    if m2:
        return m2.group(1).strip()
    return text.strip()


# ============================================================
# 渲染
# ============================================================
def render_precha_block(chapter):
    """把 Chapter 的 PRECHA 字段渲染成 markdown 块"""
    lines = [
        "## PRECHA",
        "`上一章节的名字和文件链接`",
        f"prechaName {chapter.precha_name or '/'}",
        f"prechaLink {chapter.precha_link or '/'}",
        "",
        "## PRECHA CONTENT",
        "`用于记录上一章节的内容（时间地点人物 起因经过结果等等）`",
    ]
    for f in PRECHA_FIELDS:
        lines.append(f"{PRECHA_LABELS[f]}：{getattr(chapter, f, '') or ''}")
    return "\n".join(lines)


def render_full_chapter(chapter):
    """渲染完整章节文件（标题 + PRECHA + 正文），对应 CHAn.md 的格式"""
    return (
        f"# {chapter.label} {chapter.title or ''}\n\n"
        f"{render_precha_block(chapter)}\n\n"
        f"## CONTENT\n\n"
        f"{strip_precha(chapter.content) if chapter.content else ''}\n"
    )


def is_empty(precha_dict):
    """七项是否全空"""
    return not any((precha_dict.get(f) or "").strip() for f in PRECHA_FIELDS)


# ============================================================
# 自动生成（从上一章正文抽取）
# ============================================================
_EXTRACT_PROMPT = """你要把一章小说压缩成结构化摘要，供下一章的作者参考。

请严格输出 JSON，不要任何其他文字：
{{
  "时间": "本章发生的时间，尽量具体到年月日或时刻",
  "地点": "本章出现的地点，多个用、分隔",
  "人物": "本章出场的人物姓名，多个用、分隔",
  "起": "本章的起因（一句话）",
  "经": "本章的经过（2-4句，写清关键事件顺序）",
  "结": "本章的结果，特别是结尾落在什么画面或动作上（1-2句）",
  "媒": "本章出现的关键物件、媒介或信息载体（如某个零件、某张报纸、某条消息）"
}}

要求：
- 只写这一章**实际发生**的事，不要推测后续
- 保留具体数字、日期、品牌、地名——这些是下一章接续的锚点
- 不要评价、不要总结主题

章节标题：{title}

章节正文：
{content}"""


def extract_precha_from_chapter(prev_chapter, use_flash=True):
    """
    用 AI 从上一章正文抽取 PRECHA 七项。
    返回 dict（含 precha_name / precha_link / 七个字段）。
    失败时退回正则解析，再失败则返回空字段。
    """
    base = {
        "precha_name": prev_chapter.title or "",
        "precha_link": prev_chapter.filename,
    }

    body = strip_precha(prev_chapter.content)
    if not body.strip():
        log.warning(f"上一章无正文，PRECHA 留空: ch{prev_chapter.id}")
        base.update({f: "" for f in PRECHA_FIELDS})
        return base

    # 正文可能很长，取首尾拼接（开头交代背景，结尾是下一章的接续点）
    if len(body) > 9000:
        sample = body[:4500] + "\n\n……（中略）……\n\n" + body[-4500:]
    else:
        sample = body

    prompt = _EXTRACT_PROMPT.format(title=prev_chapter.title or "", content=sample)

    try:
        from services.deepseek_service import deepseek_flash, deepseek
        client = deepseek_flash if use_flash else deepseek
        resp = client.chat(prompt, max_tokens=1500).strip()

        if resp.startswith("```"):
            resp = re.sub(r"^```[a-zA-Z]*\n", "", resp)
            resp = re.sub(r"\n?```$", "", resp).strip()

        data = json.loads(resp)
        mapping = {
            "precha_time": "时间",
            "precha_place": "地点",
            "precha_chars": "人物",
            "precha_cause": "起",
            "precha_process": "经",
            "precha_result": "结",
            "precha_media": "媒",
        }
        for field, key in mapping.items():
            base[field] = str(data.get(key, "") or "").strip()
        log.info(f"PRECHA 自动生成成功: ch{prev_chapter.id} → {prev_chapter.title}")
        return base

    except Exception as e:
        log.warning(f"PRECHA AI 抽取失败，回退正则: {type(e).__name__}: {e}")
        fallback = split_precha(prev_chapter.content)
        # 旧数据里 precha_content 存的是「上一章的上一章」，只在实在没办法时用
        if is_empty(fallback):
            fallback = split_precha(prev_chapter.precha_content)
        base.update(fallback)
        return base
