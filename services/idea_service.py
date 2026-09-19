"""
创意结构化服务

AI 生成的创意是一坨 markdown，界面上只能整篇看/整篇改。
这里把它拆成 核心概念 / 世界观 / 主题 / 开篇 + 人物卡，
存进 ideas 的结构化列和 story_entities 表，让详情页可以分区展示、逐项编辑。

拆解走两条路：
  1. 先用 markdown 标题做确定性解析（AI 按模板输出时，这一步就够了，零成本）
  2. 人物等需要语义理解的部分，再用 flash 模型抽一次
"""
import json
import re

from database import db, StoryEntity
from logger import get_logger

log = get_logger("service.idea")


# ============================================================
# 1. 确定性解析：按 markdown 标题切块
# ============================================================
# 标题别名 → ideas 的列名
_SECTION_ALIASES = {
    "one_liner": ["一句话概括核心概念", "一句话概括", "核心一句话"],
    "core_concept": ["核心科幻概念", "核心概念", "科幻概念", "核心设想"],
    "worldview": ["世界观", "世界设定", "时代背景"],
    "themes": ["故事主题", "主题", "核心主题", "哲学命题"],
    "opening": ["开篇构想", "开篇", "第一幕", "开场"],
}

_CHARACTER_HEADINGS = ["主要角色", "角色", "人物", "主要人物", "关键角色"]
_SOURCE_HEADINGS = ["参考来源", "来源", "引用来源"]


def split_sections(markdown):
    """
    把 markdown 按 ## / ### 标题切成 {标题: 正文} 字典。
    标题保留原文，供后续按别名匹配。
    """
    if not markdown:
        return {}
    sections = {}
    current = None
    buf = []
    for line in markdown.splitlines():
        m = re.match(r"^\s*#{2,4}\s+(.+?)\s*$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def _match_section(sections, aliases):
    """按别名找一个章节（先精确，再包含）"""
    for alias in aliases:
        for title, body in sections.items():
            if title == alias:
                return body
    for alias in aliases:
        for title, body in sections.items():
            if alias in title:
                return body
    return ""


def extract_title(markdown):
    """取一级标题作为创意标题"""
    if not markdown:
        return ""
    m = re.search(r"^\s*#\s+(.+?)\s*$", markdown, re.MULTILINE)
    if not m:
        return ""
    title = m.group(1).strip()
    # AI 有时照抄模板里的占位符
    if title in ("设定标题", "创意标题", "标题"):
        return ""
    return title.strip("《》 ")


def parse_markdown(markdown):
    """
    确定性解析。返回 {one_liner, core_concept, worldview, themes, opening,
                    _characters_raw, _sources_raw}
    """
    sections = split_sections(markdown)
    out = {}
    for field, aliases in _SECTION_ALIASES.items():
        out[field] = _match_section(sections, aliases)

    # 一句话概念常常紧跟在一级标题后面，不带自己的小标题
    if not out["one_liner"]:
        m = re.search(r"^\s*#\s+.+?\n+([^\n#][^\n]*)", markdown or "", re.MULTILINE)
        if m:
            out["one_liner"] = m.group(1).strip()

    out["_characters_raw"] = _match_section(sections, _CHARACTER_HEADINGS)
    out["_sources_raw"] = _match_section(sections, _SOURCE_HEADINGS)
    return out


# ============================================================
# 2. 语义抽取：人物卡 + 世界观要素
# ============================================================
_ENTITY_PROMPT = """从下面的科幻故事设定里抽取结构化条目。

严格输出 JSON，不要任何其他文字：
{{
  "characters": [
    {{"name": "人物名", "summary": "一行概括这个人是谁",
      "detail": "更完整的描述",
      "role": "在故事里的身份/职业", "age": "年龄或年龄段",
      "relation": "与其他人物的关系", "speech_habit": "说话习惯或口头禅",
      "physical_mark": "外貌或身体上的标志性特征"}}
  ],
  "worldview": [
    {{"name": "要素名（如 时代、地理、社会结构、技术水平）",
      "summary": "一行概括", "detail": "完整描述"}}
  ],
  "settings": [
    {{"name": "设定名（关键科幻设定、组织、制度、物件、术语）",
      "summary": "一行概括", "detail": "完整描述"}}
  ]
}}

要求：
- 只抽**设定里实际写了**的内容，不要发挥和补充
- characters 里只放有名字或明确指称的人物，不要放群体
- 字段没有就留空字符串，不要编
- 每类最多 8 条

故事设定：
{content}"""


def extract_entities(markdown, use_flash=True):
    """
    从创意 markdown 抽取人物/世界观/设定条目。
    返回 [{kind, name, summary, detail, attributes}, ...]；失败返回 []。
    """
    if not (markdown or "").strip():
        return []

    try:
        from services.deepseek_service import deepseek_flash, deepseek
        client = deepseek_flash if use_flash else deepseek
        resp = client.chat(
            _ENTITY_PROMPT.format(content=markdown[:8000]),
            max_tokens=3000,
        ).strip()

        if resp.startswith("```"):
            resp = re.sub(r"^```[a-zA-Z]*\n", "", resp)
            resp = re.sub(r"\n?```$", "", resp).strip()

        data = json.loads(resp)
    except Exception as e:
        log.warning(f"实体抽取失败: {type(e).__name__}: {e}")
        return []

    out = []
    char_attrs = ("role", "age", "relation", "speech_habit", "physical_mark")

    for i, c in enumerate(data.get("characters") or []):
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        attrs = {k: str(c.get(k, "") or "").strip() for k in char_attrs}
        out.append({
            "kind": "character",
            "name": name[:200],
            "summary": str(c.get("summary", "") or "").strip()[:500],
            "detail": str(c.get("detail", "") or "").strip(),
            "attributes": {k: v for k, v in attrs.items() if v},
            "sort_order": i,
        })

    for kind, key in (("worldview", "worldview"), ("setting", "settings")):
        for i, s in enumerate(data.get(key) or []):
            name = str(s.get("name", "")).strip()
            if not name:
                continue
            out.append({
                "kind": kind,
                "name": name[:200],
                "summary": str(s.get("summary", "") or "").strip()[:500],
                "detail": str(s.get("detail", "") or "").strip(),
                "attributes": {},
                "sort_order": i,
            })

    log.info(f"实体抽取: {sum(1 for e in out if e['kind'] == 'character')} 人物, "
             f"{sum(1 for e in out if e['kind'] == 'worldview')} 世界观, "
             f"{sum(1 for e in out if e['kind'] == 'setting')} 设定")
    return out


# ============================================================
# 3. 组装
# ============================================================
def structure_idea(markdown, citations=None, with_entities=True):
    """
    把创意 markdown 结构化。
    返回 {title, one_liner, core_concept, worldview, themes, opening,
          sources, entities, structured_ok}
    """
    parsed = parse_markdown(markdown)
    entities = extract_entities(markdown) if with_entities else []

    # 人物没抽到时，退回把「主要角色」整段塞进一条 setting，至少不丢信息
    if with_entities and not any(e["kind"] == "character" for e in entities):
        raw = parsed.get("_characters_raw") or ""
        if raw.strip():
            entities.append({
                "kind": "character", "name": "（未拆分的角色描述）",
                "summary": "AI 拆解失败，保留原文", "detail": raw,
                "attributes": {}, "sort_order": 0,
            })

    result = {
        "title": extract_title(markdown),
        "one_liner": parsed["one_liner"],
        "core_concept": parsed["core_concept"],
        "worldview": parsed["worldview"],
        "themes": parsed["themes"],
        "opening": parsed["opening"],
        "sources": citations or [],
        "entities": entities,
    }
    # 主体字段至少命中两项，才算结构化成功
    hit = sum(1 for f in ("core_concept", "worldview", "themes", "opening")
              if result[f].strip())
    result["structured_ok"] = hit >= 2
    if not result["structured_ok"]:
        log.warning(f"创意结构化命中不足（{hit}/4 个主体字段），"
                    f"可能是 AI 未按模板输出")
    return result


def apply_structure(idea, structure, replace_entities=True):
    """
    把 structure_idea() 的结果写进 Idea 和 story_entities。
    调用方负责 commit。
    """
    for field in ("one_liner", "core_concept", "worldview", "themes", "opening"):
        if structure.get(field):
            setattr(idea, field, structure[field])
    if structure.get("sources") is not None:
        idea.sources = json.dumps(structure["sources"], ensure_ascii=False)
    idea.structured_ok = bool(structure.get("structured_ok"))

    entities = structure.get("entities") or []
    if not entities:
        return 0

    if replace_entities:
        StoryEntity.query.filter_by(idea_id=idea.id).delete(synchronize_session=False)

    for e in entities:
        db.session.add(StoryEntity(
            idea_id=idea.id,
            kind=e["kind"],
            name=e["name"],
            summary=e.get("summary", ""),
            detail=e.get("detail", ""),
            attributes=json.dumps(e.get("attributes", {}), ensure_ascii=False),
            sort_order=e.get("sort_order", 0),
        ))
    return len(entities)
