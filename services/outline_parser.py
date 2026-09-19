"""
大纲解析器 — 把 AI 输出的 markdown 拆成 Chapter 行

为什么要拆：
    旧版大纲只是 Outline.content 里的一坨 markdown，章节从未成为数据。
    于是界面上没法「每个章节一个 item、点开看详情」，
    也没法做到「改章节名，大纲里的名字跟着变」。

拆完之后，章节列表由 Chapter 行渲染，Outline.content 只保留概要/主题部分，
原始输出存进 Outline.raw_markdown 备查。
"""
import re

from logger import get_logger

log = get_logger("service.outline")


# ============================================================
# 章节标题识别
# ============================================================
# 支持的写法：
#   ### CHA1：章节名     ### CHA1 章节名     ### 第1章：章节名
#   ### 1. 章节名        ### 终章：章节名     ## CHA1 章节名
_CHAPTER_HEADING = re.compile(
    r"^\s*#{2,4}\s*"
    r"(?:"
    r"CHA\s*(?P<cha>\d+)"                       # CHA1
    r"|第\s*(?P<zh>[0-9一二三四五六七八九十百]+)\s*章"   # 第1章 / 第一章
    r"|(?P<num>\d+)\s*[.、]"                     # 1. / 1、
    r"|(?P<final>终章|尾声|结章|最终章)"            # 终章
    r")"
    r"\s*[:：．.、\-—]?\s*"
    r"(?P<title>.*?)\s*$",
    re.MULTILINE,
)

_ZH_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _zh_to_int(s):
    """把「一」「十二」「二十」这类中文数字转成整数"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if "十" in s:
        left, _, right = s.partition("十")
        tens = _ZH_DIGITS.get(left, 1) if left else 1
        ones = _ZH_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return _ZH_DIGITS.get(s, 0)


# ============================================================
# 计划字段识别
# ============================================================
# 章节正文里的要点行 → Chapter 的 plan_* 列
_PLAN_ALIASES = {
    "plan_scene": ["场景", "地点", "时间地点", "场景设定"],
    "plan_events": ["关键事件", "事件", "主要事件", "情节", "剧情"],
    "plan_emotion": ["情感弧线", "情感", "情绪弧线", "情感变化", "人物弧线"],
    "plan_settings": ["需要展现的设定", "设定", "展现的设定", "科幻设定", "世界观要素"],
}

_BULLET = re.compile(r"^\s*[-*+•]\s*(?:\*\*)?(?P<key>[^:：*]{1,12})(?:\*\*)?\s*[:：]\s*(?P<val>.*)$")
_PLAIN = re.compile(r"^\s*(?:\*\*)?(?P<key>[^:：*]{1,12})(?:\*\*)?\s*[:：]\s*(?P<val>.*)$")


def _parse_plan_body(body):
    """
    把章节正文拆成 plan_* 字段。
    认不出的行全部收进 plan_notes，保证不丢信息。
    """
    out = {k: [] for k in _PLAN_ALIASES}
    notes = []

    # key → 字段名 的反查表
    lookup = {}
    for field, aliases in _PLAN_ALIASES.items():
        for a in aliases:
            lookup[a] = field

    current_field = None
    for line in (body or "").splitlines():
        if not line.strip():
            continue

        m = _BULLET.match(line) or _PLAIN.match(line)
        if m:
            key = m.group("key").strip()
            val = m.group("val").strip()
            field = lookup.get(key)
            if field is None:
                # 模糊匹配：「关键事件（3件）」这种带后缀的
                for alias, f in lookup.items():
                    if alias in key:
                        field = f
                        break
            if field:
                if val:
                    out[field].append(val)
                current_field = field
                continue
            notes.append(line.strip())
            current_field = None
            continue

        # 无 key 的续行：归到上一个字段
        stripped = re.sub(r"^\s*[-*+•]\s*", "", line).strip()
        if not stripped:
            continue
        if current_field:
            out[current_field].append(stripped)
        else:
            notes.append(stripped)

    result = {k: "\n".join(v).strip() for k, v in out.items()}
    result["plan_notes"] = "\n".join(notes).strip()
    return result


# ============================================================
# 主解析
# ============================================================
_HEAD_ALIASES = {
    "synopsis": ["故事概要", "概要", "故事简介", "一句话概述", "内容概要"],
    "themes": ["核心主题", "主题", "核心议题"],
    "structure_note": ["结构说明", "叙事结构", "节奏安排", "结构"],
}


def parse_outline(markdown):
    """
    解析大纲 markdown。

    Returns:
        {
          "title": str,
          "synopsis": str, "themes": str, "structure_note": str,
          "content": str,          # 章节列表之前的部分（概要/主题）
          "chapters": [ {chapter_number, title, plan_scene, plan_events,
                         plan_emotion, plan_settings, plan_notes}, ... ],
          "parsed_ok": bool,
        }
    """
    markdown = markdown or ""

    # ---- 标题 ----
    m = re.search(r"^\s*#\s+(.+?)\s*$", markdown, re.MULTILINE)
    title = m.group(1).strip() if m else ""
    if title in ("大纲标题", "标题"):
        title = ""

    # ---- 找出所有章节标题的位置 ----
    matches = list(_CHAPTER_HEADING.finditer(markdown))

    # 「章节规划」这类容器标题会被 \d+. 规则误命中，过滤掉明显不是章节的
    matches = [mm for mm in matches
               if not re.match(r"^(章节规划|章节目录|章节列表|目录)$",
                               (mm.group("title") or "").strip())]

    chapters = []
    for i, mm in enumerate(matches):
        # 章号
        if mm.group("cha"):
            num = int(mm.group("cha"))
        elif mm.group("zh"):
            num = _zh_to_int(mm.group("zh"))
        elif mm.group("num"):
            num = int(mm.group("num"))
        else:
            num = 0   # 终章，稍后按顺序补号

        body_start = mm.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[body_start:body_end]

        ch_title = (mm.group("title") or "").strip().strip("*").strip()
        if mm.group("final") and not ch_title:
            ch_title = mm.group("final")

        chapters.append({
            "chapter_number": num,
            "title": ch_title,
            "_is_final": bool(mm.group("final")),
            **_parse_plan_body(body),
        })

    # ---- 补号 + 去重 ----
    chapters = _normalize_numbers(chapters)

    # ---- 头部信息（章节列表之前的内容）----
    head_end = matches[0].start() if matches else len(markdown)
    head = markdown[:head_end]
    head_sections = _split_sections(head)

    out = {"title": title, "content": head.strip(), "chapters": chapters}
    for field, aliases in _HEAD_ALIASES.items():
        out[field] = _match_section(head_sections, aliases)

    out["parsed_ok"] = len(chapters) > 0
    if not out["parsed_ok"]:
        log.warning("大纲解析未找到任何章节标题，将退回纯 markdown 模式")
    else:
        log.info(f"大纲解析: {len(chapters)} 章, 标题={title or '(未识别)'}")
    return out


def _normalize_numbers(chapters):
    """给终章补号、修正重号，保证 chapter_number 严格递增且唯一"""
    if not chapters:
        return []
    used = set()
    next_free = 1
    for ch in chapters:
        num = ch["chapter_number"]
        if num <= 0 or num in used:
            while next_free in used:
                next_free += 1
            num = next_free
        used.add(num)
        next_free = max(next_free, num + 1)
        ch["chapter_number"] = num
        ch.pop("_is_final", None)
    chapters.sort(key=lambda c: c["chapter_number"])
    # 重新压实成 1..n，避免 AI 跳号导致洞
    for i, ch in enumerate(chapters, 1):
        ch["chapter_number"] = i
        ch["sort_key"] = float(i) * 1000.0
    return chapters


def _split_sections(markdown):
    sections, current, buf = {}, None, []
    for line in (markdown or "").splitlines():
        m = re.match(r"^\s*#{2,4}\s+(.+?)\s*$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def _match_section(sections, aliases):
    for alias in aliases:
        for t, b in sections.items():
            if t == alias:
                return b
    for alias in aliases:
        for t, b in sections.items():
            if alias in t:
                return b
    return ""


# ============================================================
# 反向渲染（导出 / 给提示词看全局大纲）
# ============================================================
def render_outline(outline, chapters):
    """把 Outline + Chapter 行渲染回 markdown"""
    parts = [f"# {outline.title}"]
    if outline.synopsis:
        parts.append(f"\n## 故事概要\n{outline.synopsis}")
    if outline.themes:
        parts.append(f"\n## 核心主题\n{outline.themes}")
    if outline.structure_note:
        parts.append(f"\n## 结构说明\n{outline.structure_note}")

    if chapters:
        parts.append("\n## 章节规划")
        for ch in chapters:
            parts.append(f"\n### CHA{ch.chapter_number}：{ch.title or ''}")
            plan = ch.plan_block()
            if plan:
                parts.append("\n".join(f"- {line}" for line in plan.splitlines()))
    return "\n".join(parts)


def chapter_plan_digest(chapters, upto=None):
    """
    给写作提示词用的章节计划摘要。
    upto 不为空时只给到第 upto 章 —— 执行「叙述者不知道未来章节」。
    """
    lines = []
    for ch in chapters:
        if upto is not None and ch.chapter_number > upto:
            break
        head = f"CHA{ch.chapter_number} {ch.title or ''}".strip()
        plan = ch.plan_block()
        lines.append(f"{head}\n{plan}" if plan else head)
    return "\n\n".join(lines)
