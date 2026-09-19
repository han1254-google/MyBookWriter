"""
SQLAlchemy 数据模型

层级结构：
    Project (作品)  ← 根容器
      ├── idea_id    → Idea      (来源创意，可空)
      ├── outline_id → Outline   (来源大纲，可空)
      ├── StoryEntity[]          (人物 / 世界观 / 故事设定)
      └── Chapter[]              (章节：大纲计划 + PRECHA + 正文，同一行)
            ├── ChapterEntity[]  (本章涉及哪些设定)
            └── Revision[]       (版本历史，支撑 续写/重写/回滚)
"""
import json
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt else None


def _loads(raw, fallback):
    """宽松解析 JSON 列，坏数据不抛异常"""
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback


# ============================================================
# 创意
# ============================================================
class Idea(db.Model):
    """创意/设定。content 保留 AI 原始 markdown，结构化字段供界面分区展示。"""
    __tablename__ = "ideas"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(200), default="未命名创意")
    content = db.Column(db.Text, default="")               # AI 原始 markdown 全文
    knowledge_context = db.Column(db.Text, default="{}")   # JSON: RAG 结果
    chat_history = db.Column(db.Text, default="[]")        # JSON: 历史遗留，新界面不再使用

    # ---- 结构化字段 ----
    one_liner = db.Column(db.Text, default="")      # 一句话核心概念
    core_concept = db.Column(db.Text, default="")   # 核心科幻概念
    worldview = db.Column(db.Text, default="")      # 世界观
    themes = db.Column(db.Text, default="")         # 故事主题
    opening = db.Column(db.Text, default="")        # 开篇构想
    sources = db.Column(db.Text, default="[]")      # JSON: 实际引用来源
    structured_ok = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    outlines = db.relationship("Outline", backref="idea", lazy="dynamic",
                               cascade="all, delete-orphan",
                               foreign_keys="Outline.idea_id")
    entities = db.relationship("StoryEntity", backref="idea", lazy="dynamic",
                               cascade="all, delete-orphan",
                               foreign_keys="StoryEntity.idea_id")

    def to_dict(self, with_entities=False):
        d = {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "knowledge_context": self.knowledge_context,
            "chat_history": self.chat_history,
            "one_liner": self.one_liner or "",
            "core_concept": self.core_concept or "",
            "worldview": self.worldview or "",
            "themes": self.themes or "",
            "opening": self.opening or "",
            "sources": _loads(self.sources, []),
            "structured_ok": bool(self.structured_ok),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }
        if with_entities:
            d["entities"] = [e.to_dict() for e in
                             self.entities.order_by(StoryEntity.kind, StoryEntity.sort_order)]
        return d


# ============================================================
# 大纲
# ============================================================
class Outline(db.Model):
    """大纲。章节不再塞在 content 里，而是 Chapter 行；content 只存概要/主题部分。"""
    __tablename__ = "outlines"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idea_id = db.Column(db.Integer, db.ForeignKey("ideas.id"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    title = db.Column(db.String(200), default="未命名大纲")
    content = db.Column(db.Text, default="")               # 概要/主题（不含章节列表）
    raw_markdown = db.Column(db.Text, default="")          # AI 原始输出存档
    synopsis = db.Column(db.Text, default="")              # 故事概要
    themes = db.Column(db.Text, default="")                # 核心主题
    structure_note = db.Column(db.Text, default="")        # 结构说明，可为空（不强制起承转合）
    parsed_ok = db.Column(db.Boolean, default=False)
    knowledge_context = db.Column(db.Text, default="{}")
    chat_history = db.Column(db.Text, default="[]")        # 历史遗留
    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    chapters = db.relationship("Chapter", backref="outline", lazy="dynamic",
                               order_by="Chapter.sort_key",
                               foreign_keys="Chapter.outline_id")

    def chapter_count(self):
        """
        本大纲对应作品的章节数。
        不能直接数 self.chapters —— 一个大纲可派生多个作品，
        那些作品的章节也带着同一个 outline_id，会被重复计入。
        """
        if self.project_id:
            return Chapter.query.filter_by(project_id=self.project_id).count()
        return self.chapters.count()

    def to_dict(self):
        return {
            "id": self.id,
            "idea_id": self.idea_id,
            "project_id": self.project_id,
            "title": self.title,
            "content": self.content,
            "raw_markdown": self.raw_markdown or "",
            "synopsis": self.synopsis or "",
            "themes": self.themes or "",
            "structure_note": self.structure_note or "",
            "parsed_ok": bool(self.parsed_ok),
            "knowledge_context": self.knowledge_context,
            "chat_history": self.chat_history,
            "chapter_count": self.chapter_count(),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


# ============================================================
# 作品（根容器）
# ============================================================
class Project(db.Model):
    """作品。从大纲创建、从创意创建、或空白创建，都归到这里。"""
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(200), default="未命名作品")
    synopsis = db.Column(db.Text, default="")
    source_type = db.Column(db.String(20), default="blank")   # outline / idea / blank
    idea_id = db.Column(db.Integer, db.ForeignKey("ideas.id"), nullable=True)
    outline_id = db.Column(db.Integer, db.ForeignKey("outlines.id"), nullable=True)
    status = db.Column(db.String(20), default="writing")      # writing / done / archived
    style_notes = db.Column(db.Text, default="")              # 叠加在全局风格指南之上
    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    chapters = db.relationship("Chapter", backref="project", lazy="dynamic",
                               cascade="all, delete-orphan",
                               order_by="Chapter.sort_key",
                               foreign_keys="Chapter.project_id")
    entities = db.relationship("StoryEntity", backref="project", lazy="dynamic",
                               cascade="all, delete-orphan",
                               foreign_keys="StoryEntity.project_id")

    def to_dict(self, with_chapters=False, with_entities=False):
        chapters = list(self.chapters)
        d = {
            "id": self.id,
            "title": self.title,
            "synopsis": self.synopsis or "",
            "source_type": self.source_type,
            "idea_id": self.idea_id,
            "outline_id": self.outline_id,
            "status": self.status,
            "style_notes": self.style_notes or "",
            "chapter_count": len(chapters),
            "word_count": sum(c.word_count or 0 for c in chapters),
            "completed_count": sum(1 for c in chapters if c.status == "completed"),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }
        if with_chapters:
            d["chapters"] = [c.to_summary() for c in chapters]
        if with_entities:
            d["entities"] = [e.to_dict() for e in
                             self.entities.order_by(StoryEntity.kind, StoryEntity.sort_order)]
        return d


# ============================================================
# 故事圣经：人物 / 世界观 / 设定
# ============================================================
ENTITY_KINDS = ("character", "worldview", "setting", "location", "item", "term", "theme")

ENTITY_KIND_LABELS = {
    "character": "人物",
    "worldview": "世界观",
    "setting": "故事设定",
    "location": "地点",
    "item": "物件",
    "term": "术语",
    "theme": "主题",
}


class StoryEntity(db.Model):
    """
    结构化故事设定。
    idea_id 上的实体是「模板」，建作品时复制成 project_id 上的「实例」。
    first_appear_chapter 用于在数据层执行「禁止叙述越界」：
    写 CHAn 时只注入 first_appear_chapter 为空或 <= n 的实体。
    """
    __tablename__ = "story_entities"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idea_id = db.Column(db.Integer, db.ForeignKey("ideas.id"), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)
    kind = db.Column(db.String(20), default="setting", index=True)
    name = db.Column(db.String(200), default="")
    summary = db.Column(db.String(500), default="")   # 一行摘要，列表显示
    detail = db.Column(db.Text, default="")           # 完整描述 markdown
    attributes = db.Column(db.Text, default="{}")     # JSON 自由属性
    first_appear_chapter = db.Column(db.Integer, nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    def to_dict(self):
        return {
            "id": self.id,
            "idea_id": self.idea_id,
            "project_id": self.project_id,
            "kind": self.kind,
            "kind_label": ENTITY_KIND_LABELS.get(self.kind, self.kind),
            "name": self.name,
            "summary": self.summary or "",
            "detail": self.detail or "",
            "attributes": _loads(self.attributes, {}),
            "first_appear_chapter": self.first_appear_chapter,
            "sort_order": self.sort_order or 0,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }

    def clone_for_project(self, project_id):
        """把创意上的模板实体复制成作品实例"""
        return StoryEntity(
            project_id=project_id,
            kind=self.kind,
            name=self.name,
            summary=self.summary,
            detail=self.detail,
            attributes=self.attributes,
            first_appear_chapter=self.first_appear_chapter,
            sort_order=self.sort_order,
        )

    def as_prompt_block(self):
        """渲染成提示词片段"""
        label = ENTITY_KIND_LABELS.get(self.kind, self.kind)
        parts = [f"- [{label}] {self.name}"]
        if self.summary:
            parts.append(f"  {self.summary}")
        if self.detail:
            parts.append(f"  {self.detail.strip()}")
        attrs = _loads(self.attributes, {})
        if attrs:
            kv = "，".join(f"{k}：{v}" for k, v in attrs.items() if v)
            if kv:
                parts.append(f"  （{kv}）")
        return "\n".join(parts)


# ============================================================
# 章节（大纲计划 + PRECHA + 正文，同一行）
# ============================================================
CHAPTER_PLAN_FIELDS = ("plan_scene", "plan_events", "plan_emotion", "plan_settings", "plan_notes")

PRECHA_FIELDS = ("precha_time", "precha_place", "precha_chars",
                 "precha_cause", "precha_process", "precha_result", "precha_media")

PRECHA_LABELS = {
    "precha_time": "时间",
    "precha_place": "地点",
    "precha_chars": "人物",
    "precha_cause": "起",
    "precha_process": "经",
    "precha_result": "结",
    "precha_media": "媒",
}


class Chapter(db.Model):
    """
    章节。一行同时承载「大纲计划」和「正文草稿」——
    这样改 title 时大纲页和创作页天然同步，不需要双向同步逻辑。
    """
    __tablename__ = "chapters"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    outline_id = db.Column(db.Integer, db.ForeignKey("outlines.id"), nullable=True, index=True)
    chapter_number = db.Column(db.Integer, default=1)
    sort_key = db.Column(db.Float, default=1000.0)   # 支持插入排序而不重编号
    title = db.Column(db.String(200), default="")

    # ---- 大纲计划侧 ----
    plan_scene = db.Column(db.Text, default="")      # 场景
    plan_events = db.Column(db.Text, default="")     # 关键事件
    plan_emotion = db.Column(db.Text, default="")    # 情感弧线
    plan_settings = db.Column(db.Text, default="")   # 需要展现的设定
    plan_notes = db.Column(db.Text, default="")      # 备注

    # ---- PRECHA 侧（拆列以便表单编辑）----
    precha_name = db.Column(db.String(200), default="")
    precha_link = db.Column(db.String(200), default="")
    precha_time = db.Column(db.String(300), default="")
    precha_place = db.Column(db.String(300), default="")
    precha_chars = db.Column(db.String(500), default="")
    precha_cause = db.Column(db.Text, default="")
    precha_process = db.Column(db.Text, default="")
    precha_result = db.Column(db.Text, default="")
    precha_media = db.Column(db.Text, default="")
    precha_auto = db.Column(db.Boolean, default=True)     # False = 用户手改过
    precha_content = db.Column(db.Text, default="")       # 旧数据兼容，只读

    # ---- 正文侧 ----
    content = db.Column(db.Text, default="")
    word_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="planned")  # planned / draft / completed

    # ---- 上下文快照（可复现 + 校验叙述不越界）----
    context_snapshot = db.Column(db.Text, default="{}")
    knowledge_context = db.Column(db.Text, default="{}")

    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        db.UniqueConstraint("project_id", "chapter_number", name="uq_chapter_project_number"),
    )

    entity_links = db.relationship("ChapterEntity", backref="chapter", lazy="dynamic",
                                   cascade="all, delete-orphan")

    # ---- 派生属性 ----
    @property
    def label(self):
        return f"CHA{self.chapter_number}"

    @property
    def filename(self):
        return f"CHA{self.chapter_number}.md"

    def recount(self):
        """重算字数：中文字符 + 英文单词"""
        import re
        text = self.content or ""
        han = len(re.findall(r"[一-鿿]", text))
        words = len(re.findall(r"[A-Za-z]+", text))
        self.word_count = han + words
        return self.word_count

    def has_plan(self):
        return any(getattr(self, f, None) for f in CHAPTER_PLAN_FIELDS)

    def has_precha(self):
        return any(getattr(self, f, None) for f in PRECHA_FIELDS)

    def precha_block(self):
        """渲染 PRECHA 为 markdown 块（导出 / 提示词用）"""
        lines = [
            "## PRECHA",
            f"prechaName {self.precha_name or '/'}",
            f"prechaLink {self.precha_link or '/'}",
            "",
            "## PRECHA CONTENT",
        ]
        for f in PRECHA_FIELDS:
            lines.append(f"{PRECHA_LABELS[f]}：{getattr(self, f, '') or ''}")
        return "\n".join(lines)

    def plan_block(self):
        """渲染大纲计划为提示词片段"""
        labels = {
            "plan_scene": "场景",
            "plan_events": "关键事件",
            "plan_emotion": "情感弧线",
            "plan_settings": "需要展现的设定",
            "plan_notes": "备注",
        }
        lines = [f"{labels[f]}：{getattr(self, f)}" for f in CHAPTER_PLAN_FIELDS
                 if getattr(self, f, None)]
        return "\n".join(lines)

    def to_summary(self):
        """列表用的轻量字典（不含正文）"""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "outline_id": self.outline_id,
            "chapter_number": self.chapter_number,
            "sort_key": self.sort_key,
            "label": self.label,
            "title": self.title,
            "status": self.status,
            "word_count": self.word_count or 0,
            "has_plan": self.has_plan(),
            "has_precha": self.has_precha(),
            "has_content": bool(self.content),
            "updated_at": _iso(self.updated_at),
        }

    def to_dict(self):
        d = self.to_summary()
        d.update({
            "plan_scene": self.plan_scene or "",
            "plan_events": self.plan_events or "",
            "plan_emotion": self.plan_emotion or "",
            "plan_settings": self.plan_settings or "",
            "plan_notes": self.plan_notes or "",
            "precha_name": self.precha_name or "",
            "precha_link": self.precha_link or "",
            "precha_time": self.precha_time or "",
            "precha_place": self.precha_place or "",
            "precha_chars": self.precha_chars or "",
            "precha_cause": self.precha_cause or "",
            "precha_process": self.precha_process or "",
            "precha_result": self.precha_result or "",
            "precha_media": self.precha_media or "",
            "precha_auto": bool(self.precha_auto),
            "precha_content": self.precha_content or "",
            "content": self.content or "",
            "context_snapshot": _loads(self.context_snapshot, {}),
            "knowledge_context": _loads(self.knowledge_context, {}),
            "created_at": _iso(self.created_at),
        })
        return d


class ChapterEntity(db.Model):
    """章节 ↔ 设定关联。写某章时只注入相关实体，不把全书人物塞进提示词。"""
    __tablename__ = "chapter_entities"

    chapter_id = db.Column(db.Integer, db.ForeignKey("chapters.id"), primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("story_entities.id"), primary_key=True)
    role = db.Column(db.String(20), default="onstage")   # onstage / mentioned / context

    entity = db.relationship("StoryEntity", lazy="joined")

    def to_dict(self):
        return {
            "chapter_id": self.chapter_id,
            "entity_id": self.entity_id,
            "role": self.role,
            "entity": self.entity.to_dict() if self.entity else None,
        }


# ============================================================
# 版本历史
# ============================================================
REVISION_OPS = ("generate", "continue", "rewrite", "manual", "revert")

REVISION_OP_LABELS = {
    "generate": "生成",
    "continue": "续写",
    "rewrite": "重写",
    "manual": "手动保存",
    "revert": "回滚",
}


class Revision(db.Model):
    """通用版本表，支撑底部命令行的 续写/重写/回滚。"""
    __tablename__ = "revisions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    target_type = db.Column(db.String(16), default="chapter")   # chapter / idea / outline
    target_id = db.Column(db.Integer, nullable=False)
    version_no = db.Column(db.Integer, default=1)
    op = db.Column(db.String(16), default="manual")
    instruction = db.Column(db.Text, default="")     # 用户在命令行输入的修改意见
    content = db.Column(db.Text, default="")
    char_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=_now)

    __table_args__ = (
        db.Index("ix_revision_target", "target_type", "target_id", "version_no"),
    )

    def to_dict(self, with_content=False):
        d = {
            "id": self.id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "version_no": self.version_no,
            "op": self.op,
            "op_label": REVISION_OP_LABELS.get(self.op, self.op),
            "instruction": self.instruction or "",
            "char_count": self.char_count or 0,
            "created_at": _iso(self.created_at),
        }
        if with_content:
            d["content"] = self.content or ""
        return d

    @staticmethod
    def next_version(target_type, target_id):
        top = (Revision.query
               .filter_by(target_type=target_type, target_id=target_id)
               .order_by(Revision.version_no.desc())
               .first())
        return (top.version_no + 1) if top else 1

    @classmethod
    def record(cls, target_type, target_id, content, op="manual", instruction=""):
        """追加一个版本。调用方负责 commit。"""
        rev = cls(
            target_type=target_type,
            target_id=target_id,
            version_no=cls.next_version(target_type, target_id),
            op=op,
            instruction=instruction or "",
            content=content or "",
            char_count=len(content or ""),
        )
        db.session.add(rev)
        return rev


# ============================================================
# 资料库
# ============================================================
class LibraryCategory(db.Model):
    """
    分类体系 — 单一真相来源。
    description 会被写进分类提示词，是分类准确率的关键；
    aliases 记录旧文件夹名，驱动归并脚本。
    """
    __tablename__ = "library_categories"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    library_type = db.Column(db.String(20), default="知识库", index=True)
    name = db.Column(db.String(50), default="")
    description = db.Column(db.String(300), default="")   # 给 AI 看的判定说明
    aliases = db.Column(db.Text, default="[]")            # JSON: 旧名/别名
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=_now)

    __table_args__ = (
        db.UniqueConstraint("library_type", "name", name="uq_category_type_name"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "library_type": self.library_type,
            "name": self.name,
            "description": self.description or "",
            "aliases": _loads(self.aliases, []),
            "is_active": bool(self.is_active),
            "sort_order": self.sort_order or 0,
        }


class LibraryFile(db.Model):
    """上传文件追踪"""
    __tablename__ = "library_files"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    library_type = db.Column(db.String(20), default="知识库")  # 知识库/参考库/风格库
    folder_name = db.Column(db.String(100), default="")
    category_id = db.Column(db.Integer, db.ForeignKey("library_categories.id"), nullable=True)
    original_filename = db.Column(db.String(500), default="")
    stored_path = db.Column(db.String(1000), default="")
    file_type = db.Column(db.String(20), default="")
    style_analysis = db.Column(db.Text, default="")        # 风格库：AI 提取的风格特征
    content_preview = db.Column(db.Text, default="")       # 开头文本（分类用）
    summary_sample = db.Column(db.Text, default="")        # 全文抽样（摘要用，不只是开头）
    ai_summary = db.Column(db.Text, default="")
    summary_status = db.Column(db.String(20), default="pending")   # pending/ok/failed
    classify_reason = db.Column(db.String(500), default="")        # AI 的分类理由，可审计
    char_count = db.Column(db.Integer, default=0)
    page_count = db.Column(db.Integer, default=0)
    chunk_count = db.Column(db.Integer, default=0)
    indexed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    def to_dict(self):
        return {
            "id": self.id,
            "library_type": self.library_type,
            "folder_name": self.folder_name,
            "category_id": self.category_id,
            "original_filename": self.original_filename,
            "stored_path": self.stored_path,
            "file_type": self.file_type,
            "style_analysis": self.style_analysis,
            "content_preview": self.content_preview[:200] if self.content_preview else "",
            "ai_summary": self.ai_summary,
            "summary_status": self.summary_status or "pending",
            "classify_reason": self.classify_reason or "",
            "char_count": self.char_count or 0,
            "page_count": self.page_count or 0,
            "chunk_count": self.chunk_count or 0,
            "indexed_at": _iso(self.indexed_at),
            "created_at": _iso(self.created_at),
        }
