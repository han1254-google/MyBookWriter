"""
数据库迁移 v1 → v2

做四件事：
  1. 给 ideas / outlines / library_files 补新列（ALTER TABLE ADD COLUMN，幂等）
  2. 重建 chapters 表 —— outline_id 从 NOT NULL 改为可空，并新增 project_id / sort_key /
     拆开的 PRECHA 列等。SQLite 不支持 ALTER COLUMN，只能「重命名旧表 + 建新表 + 搬数据」
  3. 回填：为每个大纲建一个作品，把旧章节挂上去，拆解旧 precha_content，重算字数
  4. seed library_categories，并为每个旧章节留一条 v1 版本记录

用法：
  python scripts/migrate_v2.py --dry-run    # 只打印将执行的 DDL，不改库
  python scripts/migrate_v2.py              # 执行（自动备份）
"""
import os
import re
import sys
import json
import shutil
import sqlite3
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_config import DB_PATH, LIBRARY_TAXONOMY

# ============================================================
# 需要补充的列： 表名 -> [(列名, SQL 类型与默认值)]
# ============================================================
NEW_COLUMNS = {
    "ideas": [
        ("one_liner", "TEXT DEFAULT ''"),
        ("core_concept", "TEXT DEFAULT ''"),
        ("worldview", "TEXT DEFAULT ''"),
        ("themes", "TEXT DEFAULT ''"),
        ("opening", "TEXT DEFAULT ''"),
        ("sources", "TEXT DEFAULT '[]'"),
        ("structured_ok", "BOOLEAN DEFAULT 0"),
    ],
    "outlines": [
        ("project_id", "INTEGER"),
        ("raw_markdown", "TEXT DEFAULT ''"),
        ("synopsis", "TEXT DEFAULT ''"),
        ("themes", "TEXT DEFAULT ''"),
        ("structure_note", "TEXT DEFAULT ''"),
        ("parsed_ok", "BOOLEAN DEFAULT 0"),
    ],
    "library_files": [
        ("category_id", "INTEGER"),
        ("summary_sample", "TEXT DEFAULT ''"),
        ("summary_status", "VARCHAR(20) DEFAULT 'pending'"),
        ("classify_reason", "VARCHAR(500) DEFAULT ''"),
        ("char_count", "INTEGER DEFAULT 0"),
        ("page_count", "INTEGER DEFAULT 0"),
        ("chunk_count", "INTEGER DEFAULT 0"),
        ("indexed_at", "DATETIME"),
    ],
}

CHAPTERS_BACKUP = "chapters_v1_backup"


# ============================================================
# 工具
# ============================================================
def table_exists(conn, table):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def columns_of(conn, table):
    if not table_exists(conn, table):
        return []
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def count_of(conn, table):
    if not table_exists(conn, table):
        return 0
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def backup_db():
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    dst = f"{DB_PATH}.bak-{ts}"
    shutil.copy2(DB_PATH, dst)
    return dst


# 旧 precha_content 拆解 —— 复用 services/precha_service.py 的正则，
# 避免两份实现漂移（旧 api_writing.py 的版本用了 \s* 会吃掉换行，是错的）
from services.precha_service import split_precha  # noqa: E402


def count_words(text):
    """中文字符 + 英文单词"""
    if not text:
        return 0
    han = len(re.findall(r"[一-鿿]", text))
    words = len(re.findall(r"[A-Za-z]+", text))
    return han + words


# ============================================================
# Step 1: 补列
# ============================================================
def plan_add_columns(conn):
    """返回待执行的 ALTER 语句列表"""
    stmts = []
    for table, cols in NEW_COLUMNS.items():
        if not table_exists(conn, table):
            print(f"  [跳过] 表不存在: {table}")
            continue
        existing = set(columns_of(conn, table))
        for name, decl in cols:
            if name in existing:
                continue
            stmts.append(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {decl}')
    return stmts


# ============================================================
# Step 2: 重建 chapters
# ============================================================
def read_old_chapters(conn):
    """读出旧 chapters 全部行（dict 列表）"""
    src = CHAPTERS_BACKUP if table_exists(conn, CHAPTERS_BACKUP) else "chapters"
    if not table_exists(conn, src):
        return []
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(f'SELECT * FROM "{src}" ORDER BY id')]
    conn.row_factory = None
    return rows


def needs_chapters_rebuild(conn):
    cols = columns_of(conn, "chapters")
    if not cols:
        return False
    return "project_id" not in cols


# ============================================================
# 主流程
# ============================================================
def migrate(dry_run=False):
    print("=" * 62)
    print("  MyBookApps 数据库迁移 v1 → v2")
    print("=" * 62)

    if not os.path.exists(DB_PATH):
        print(f"\n[!] 数据库不存在: {DB_PATH}")
        print("    直接启动 app.py 即可创建全新 v2 库，无需迁移。")
        return

    conn = sqlite3.connect(DB_PATH)

    # ---- 迁移前快照 ----
    before = {t: count_of(conn, t) for t in ("ideas", "outlines", "chapters", "library_files")}
    print(f"\n数据库: {DB_PATH}")
    print("迁移前记录数:")
    for t, n in before.items():
        print(f"  {t:16s} {n}")

    # ---- Step 1: 规划补列 ----
    print("\n[1/5] 规划新增列 ...")
    alter_stmts = plan_add_columns(conn)
    if alter_stmts:
        for s in alter_stmts:
            print(f"  + {s}")
    else:
        print("  （所有列已存在，无需变更）")

    rebuild = needs_chapters_rebuild(conn)
    print(f"\n[2/5] chapters 表重建: {'需要' if rebuild else '不需要（已是 v2 结构）'}")
    if rebuild:
        print(f'  + ALTER TABLE "chapters" RENAME TO "{CHAPTERS_BACKUP}"')
        print("  + (SQLAlchemy create_all 建新 chapters 表)")
        print(f"  + INSERT ... SELECT 搬迁 {before['chapters']} 行")

    if dry_run:
        old_chapters = read_old_chapters(conn)
        n_outlines = count_of(conn, "outlines")
        print("\n[3/5] 回填计划 ...")
        print(f"  + 为 {n_outlines} 个大纲各建 1 个作品(project)")
        print(f"  + {len(old_chapters)} 个章节设置 project_id / sort_key / word_count")
        print(f"  + 拆解 {sum(1 for c in old_chapters if c.get('precha_content'))} 条 precha_content 到独立列")
        print(f"  + 为 {len(old_chapters)} 个章节各建 1 条 revisions(v1)")
        seeds = sum(len(v) for v in LIBRARY_TAXONOMY.values())
        print(f"\n[4/5] seed library_categories: {seeds} 条")
        print("\n[5/5] --dry-run 模式，未做任何修改。")
        conn.close()
        return

    # ---- 备份 ----
    conn.close()
    bak = backup_db()
    print(f"\n已备份: {bak}")
    conn = sqlite3.connect(DB_PATH)

    # ---- 执行补列 ----
    print("\n[1/5] 执行新增列 ...")
    for s in alter_stmts:
        conn.execute(s)
    conn.commit()
    print(f"  完成 {len(alter_stmts)} 条 ALTER")

    # ---- 重建 chapters ----
    old_chapters = []
    if rebuild:
        print("\n[2/5] 重建 chapters 表 ...")
        old_chapters = read_old_chapters(conn)
        if table_exists(conn, CHAPTERS_BACKUP):
            conn.execute(f'DROP TABLE "{CHAPTERS_BACKUP}"')
        conn.execute(f'ALTER TABLE "chapters" RENAME TO "{CHAPTERS_BACKUP}"')
        conn.commit()
        print(f"  旧表已保留为 {CHAPTERS_BACKUP}（{len(old_chapters)} 行）")
    else:
        print("\n[2/5] chapters 已是 v2 结构，跳过重建")
    conn.close()

    # ---- 建新表（交给 SQLAlchemy，保证与模型定义一致）----
    print("\n[3/5] 创建 v2 新表 ...")
    from app import create_app
    from database import (db, Idea, Project, Chapter, Outline, Revision,
                          LibraryCategory, LibraryFile)

    app = create_app()          # create_app 内部会调 db.create_all()
    with app.app_context():
        created = [t for t in ("projects", "story_entities", "chapter_entities",
                               "revisions", "library_categories", "chapters")]
        print(f"  已确保存在: {', '.join(created)}")

        # ---- seed 分类体系 ----
        print("\n[4/5] seed library_categories ...")
        seeded = 0
        for lib_type, items in LIBRARY_TAXONOMY.items():
            for it in items:
                exists = LibraryCategory.query.filter_by(
                    library_type=lib_type, name=it["name"]
                ).first()
                if exists:
                    # 别名可能有更新，覆盖写回
                    exists.description = it["desc"]
                    exists.aliases = json.dumps(it["aliases"], ensure_ascii=False)
                    exists.sort_order = it["sort"]
                    continue
                db.session.add(LibraryCategory(
                    library_type=lib_type,
                    name=it["name"],
                    description=it["desc"],
                    aliases=json.dumps(it["aliases"], ensure_ascii=False),
                    sort_order=it["sort"],
                    is_active=True,
                ))
                seeded += 1
        db.session.commit()
        print(f"  新增 {seeded} 条分类，共 {LibraryCategory.query.count()} 条")

        # ---- 回填 ----
        print("\n[5/5] 回填作品与章节 ...")

        # 为每个大纲建一个作品（幂等：已有则复用）
        outline_to_project = {}
        for outline in Outline.query.order_by(Outline.id):
            proj = Project.query.filter_by(outline_id=outline.id).first()
            if not proj:
                proj = Project(
                    title=outline.title or "未命名作品",
                    synopsis=outline.synopsis or "",
                    source_type="outline",
                    idea_id=outline.idea_id,
                    outline_id=outline.id,
                    status="writing",
                )
                db.session.add(proj)
                db.session.flush()
            outline.project_id = proj.id
            outline_to_project[outline.id] = proj.id
        db.session.commit()
        print(f"  作品: {Project.query.count()} 个")

        # 搬迁章节
        migrated = 0
        if old_chapters:
            # 没有大纲归属的章节需要一个兜底作品
            orphan_project_id = None
            for row in old_chapters:
                old_outline_id = row.get("outline_id")
                project_id = outline_to_project.get(old_outline_id)
                if project_id is None:
                    if orphan_project_id is None:
                        orphan = Project(title="未归档章节", source_type="blank",
                                         status="writing")
                        db.session.add(orphan)
                        db.session.flush()
                        orphan_project_id = orphan.id
                    project_id = orphan_project_id

                num = row.get("chapter_number") or 1
                # 同一作品内章号冲突时顺延，避免违反唯一约束
                while Chapter.query.filter_by(project_id=project_id,
                                              chapter_number=num).first():
                    num += 1

                precha = split_precha(row.get("precha_content"))
                content = row.get("content") or ""
                ch = Chapter(
                    project_id=project_id,
                    outline_id=old_outline_id,
                    chapter_number=num,
                    sort_key=float(num) * 1000.0,
                    title=row.get("title") or "",
                    precha_name=row.get("precha_name") or "",
                    precha_link=row.get("precha_link") or "",
                    precha_content=row.get("precha_content") or "",
                    precha_auto=True,
                    content=content,
                    word_count=count_words(content),
                    status=row.get("status") or "draft",
                    knowledge_context=row.get("knowledge_context") or "{}",
                    context_snapshot="{}",
                    **precha,
                )
                db.session.add(ch)
                db.session.flush()
                # 留一条 v1 版本作为历史起点
                Revision.record(
                    "chapter", ch.id, content,
                    op="manual", instruction="迁移自 v1 数据",
                )
                migrated += 1
            db.session.commit()
        print(f"  章节: 搬迁 {migrated} 行，当前共 {Chapter.query.count()} 行")
        print(f"  版本记录: {Revision.query.count()} 条")

        # ---- 回填资料文件的 category_id ----
        linked = 0
        for lf in LibraryFile.query.all():
            if lf.category_id:
                continue
            cat = LibraryCategory.query.filter_by(
                library_type=lf.library_type, name=lf.folder_name
            ).first()
            if cat:
                lf.category_id = cat.id
                linked += 1
            if lf.ai_summary:
                lf.summary_status = "ok"
        db.session.commit()
        print(f"  资料文件: {linked} 个直接匹配到规范分类"
              f"（其余待 merge_categories.py 归并）")

        # ---- 迁移后校验 ----
        after = {
            "ideas": Idea.query.count(),
            "outlines": Outline.query.count(),
            "chapters": Chapter.query.count(),
            "library_files": LibraryFile.query.count(),
        }

    print("\n" + "=" * 62)
    print("  迁移完成")
    print("=" * 62)
    print(f"{'表':16s} {'迁移前':>8s} {'迁移后':>8s}")
    ok = True
    for t in before:
        b, a = before[t], after[t]
        flag = "OK" if a >= b else "!! 记录丢失"
        if a < b:
            ok = False
        print(f"{t:16s} {b:>8d} {a:>8d}   {flag}")
    print()
    if ok:
        print("  下一步: python scripts/merge_categories.py --dry-run")
    else:
        print(f"  [!] 记录数下降，请从备份恢复: {bak}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MyBookApps 数据库迁移 v1 → v2")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印将执行的变更，不修改数据库")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
