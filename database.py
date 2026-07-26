"""
SQLAlchemy 数据模型
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()


class Idea(db.Model):
    """创意/设定"""
    __tablename__ = "ideas"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(200), default="未命名创意")
    content = db.Column(db.Text, default="")
    knowledge_context = db.Column(db.Text, default="{}")   # JSON: RAG结果
    chat_history = db.Column(db.Text, default="[]")        # JSON: 对话历史
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    outlines = db.relationship("Outline", backref="idea", lazy="dynamic",
                               cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "knowledge_context": self.knowledge_context,
            "chat_history": self.chat_history,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Outline(db.Model):
    """大纲"""
    __tablename__ = "outlines"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idea_id = db.Column(db.Integer, db.ForeignKey("ideas.id"), nullable=True)
    title = db.Column(db.String(200), default="未命名大纲")
    content = db.Column(db.Text, default="")
    knowledge_context = db.Column(db.Text, default="{}")
    chat_history = db.Column(db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    chapters = db.relationship("Chapter", backref="outline", lazy="dynamic",
                               cascade="all, delete-orphan", order_by="Chapter.chapter_number")

    def to_dict(self):
        return {
            "id": self.id,
            "idea_id": self.idea_id,
            "title": self.title,
            "content": self.content,
            "knowledge_context": self.knowledge_context,
            "chat_history": self.chat_history,
            "chapter_count": self.chapters.count(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Chapter(db.Model):
    """章节（带 PRECHA 元数据）"""
    __tablename__ = "chapters"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    outline_id = db.Column(db.Integer, db.ForeignKey("outlines.id"), nullable=False)
    chapter_number = db.Column(db.Integer, default=1)
    title = db.Column(db.String(200), default="")
    # PRECHA 字段
    precha_name = db.Column(db.String(200), default="")
    precha_link = db.Column(db.String(200), default="")
    precha_content = db.Column(db.Text, default="")
    # 正文
    content = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="draft")  # draft / completed
    knowledge_context = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "outline_id": self.outline_id,
            "chapter_number": self.chapter_number,
            "title": self.title,
            "precha_name": self.precha_name,
            "precha_link": self.precha_link,
            "precha_content": self.precha_content,
            "content": self.content,
            "status": self.status,
            "knowledge_context": self.knowledge_context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LibraryFile(db.Model):
    """上传文件追踪"""
    __tablename__ = "library_files"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    library_type = db.Column(db.String(20), default="知识库")  # 知识库/参考库/风格库
    folder_name = db.Column(db.String(100), default="")
    original_filename = db.Column(db.String(500), default="")
    stored_path = db.Column(db.String(1000), default="")   # 实际存储路径
    file_type = db.Column(db.String(20), default="")       # pdf/docx/txt/epub
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "library_type": self.library_type,
            "folder_name": self.folder_name,
            "original_filename": self.original_filename,
            "stored_path": self.stored_path,
            "file_type": self.file_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
