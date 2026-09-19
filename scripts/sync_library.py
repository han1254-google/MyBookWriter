"""
资料库对齐脚本 — 让数据库和向量索引说同一套话

归并脚本（merge_categories.py）只按别名表搬文件夹，之后留下三类不一致：

  1. chunk_count 全是 0 —— 重建索引时没有回写，界面上「向量块」永远显示 0
  2. 索引里的分类是旧的 —— 文件在数据库里已经是「微生物与生态」，
     向量元数据里还写着「未分类」，检索结果照着旧的显示
  3. 剩下几个 AI 没归好类的文件 —— 旧版 classify_file 不给 AI 看现有分类，
     经常返回空；现在分类器修好了，可以让它重新判一次

这个脚本只改元数据和文件位置，**不重新嵌入** —— 正文没变，向量就还有效。

用法：
  python scripts/sync_library.py --dry-run   # 只报告差异
  python scripts/sync_library.py             # 执行
  python scripts/sync_library.py --reclassify  # 顺带让 AI 重判未分类的文件
"""
import os
import sys
import shutil
import argparse
from collections import Counter, defaultdict

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_config import LIBRARIES_DIR


def load_index_state():
    """返回 (全部条目, source路径 -> 条目 id 列表)"""
    from knowledge_rag.query import KnowledgeRetriever
    col = KnowledgeRetriever().collection
    data = col.get(limit=col.count(), include=["metadatas"])
    by_source = defaultdict(list)
    for cid, meta in zip(data["ids"], data["metadatas"]):
        by_source[normalize(meta.get("source", ""))].append((cid, meta))
    return col, by_source


def load_index_by_name():
    """退回用的第二把钥匙：按文件名找 —— 文件被搬走时 source 路径会失效"""
    from knowledge_rag.query import KnowledgeRetriever
    col = KnowledgeRetriever().collection
    data = col.get(limit=col.count(), include=["metadatas"])
    by_name = defaultdict(list)
    for cid, meta in zip(data["ids"], data["metadatas"]):
        by_name[meta.get("filename", "")].append((cid, meta))
    return by_name


def normalize(path):
    return os.path.normcase(os.path.normpath(path or ""))


def collect_db_files():
    """source 路径 -> (LibraryFile 快照)"""
    from app import create_app
    from database import LibraryFile
    app = create_app()
    with app.app_context():
        return app, {normalize(f.stored_path): {
            "id": f.id,
            "library_type": f.library_type,
            "folder_name": f.folder_name,
            "category_id": f.category_id,
            "original_filename": f.original_filename,
            "stored_path": f.stored_path,
        } for f in LibraryFile.query.all()}


def plan_sync(index_by_source, db_by_path, index_by_name=None):
    """找出索引元数据与数据库不一致的条目"""
    by_name = index_by_name or {}
    fixes, unmatched = [], []
    for source, entries in index_by_source.items():
        rec = db_by_path.get(source)
        if not rec:
            # 文件被搬过：source 是老路径，退回按文件名认领
            name = entries[0][1].get("filename", "")
            rec = next((r for r in db_by_path.values()
                        if os.path.basename(r["stored_path"]) == name), None)
            if not rec:
                unmatched.append((source, len(entries)))
                continue
        want = (rec["library_type"], rec["folder_name"])
        for cid, meta in entries:
            have = (meta.get("library_type"), meta.get("category"))
            if have != want or normalize(meta.get("source", "")) != normalize(rec["stored_path"]):
                fixes.append((cid, meta, rec, want, have))
    return fixes, unmatched


def apply_metadata(col, fixes):
    """按 id 批量改写元数据 —— 一次 update，不重新嵌入"""
    updates = {}
    for cid, meta, rec, want, _have in fixes:
        new_meta = dict(meta)
        new_meta["library_type"], new_meta["category"] = want
        new_meta["source"] = rec["stored_path"]
        updates[cid] = new_meta
    ids = list(updates)
    if not ids:
        return 0
    col.update(ids=ids, metadatas=[updates[i] for i in ids])
    return len(ids)


def backfill_counts(index_by_source, db_by_path):
    """chunk_count 按索引实际块数回写"""
    from app import create_app
    from database import db, LibraryFile
    app = create_app()
    n = 0
    with app.app_context():
        for f in LibraryFile.query.all():
            real = len(index_by_source.get(normalize(f.stored_path), []))
            if f.chunk_count != real:
                f.chunk_count = real
                n += 1
        # 索引里有、数据库里没有的（路径对不上的）单独报出来
        db.session.commit()
    return n


def repair_names(dry_run=True):
    """
    修好被 secure_filename 削掉的文件名。

    旧版上传接口对文件名跑 secure_filename()，中文名会被整段吃掉：
    《星光：外星世界与地球的命运.epub》在库里就叫 "epub"。
    真名一直在磁盘路径上，用它覆盖回来即可。
    """
    from app import create_app
    from database import db, LibraryFile
    app = create_app()
    broken = []
    with app.app_context():
        for lf in LibraryFile.query.all():
            real = os.path.basename(lf.stored_path)
            if lf.original_filename != real:
                broken.append((lf.id, lf.original_filename, real))
                if not dry_run:
                    lf.original_filename = real
        if not dry_run:
            db.session.commit()
    return broken


def reclassify_uncategorized(dry_run=True):
    """
    让 AI 重判「未分类」的文件。
    分类器现在会把现有分类清单给模型看，不会再一律返回空。
    """
    from app import create_app
    from database import db, LibraryFile
    from services.file_service import extract_text
    from services.library_service import classify_file, ensure_category

    app = create_app()
    moved, failed = [], []
    with app.app_context():
        todo = LibraryFile.query.filter(
            LibraryFile.folder_name == "未分类").all()
        print(f"\n  待重判: {len(todo)} 个文件")
        for lf in todo:
            if not os.path.exists(lf.stored_path):
                failed.append((lf.original_filename, "文件不在磁盘上"))
                continue
            try:
                preview = extract_text(lf.stored_path, max_chars=2000)
                cls = classify_file(lf.original_filename, preview, lf.library_type)
            except Exception as e:
                failed.append((lf.original_filename, f"{type(e).__name__}: {e}"))
                continue

            new_lib, new_cat = cls["library_type"], cls["folder_name"]
            print(f"    {lf.original_filename[:52]:<54} {lf.library_type}/未分类"
                  f" → {new_lib}/{new_cat}")
            if cls.get("reason"):
                print(f"        理由: {cls['reason'][:100]}")
            if dry_run:
                moved.append((lf.id, new_lib, new_cat))
                continue

            cat_id = ensure_category(new_lib, new_cat, cls.get("reason", ""))
            target_dir = os.path.join(LIBRARIES_DIR, new_lib, new_cat)
            os.makedirs(target_dir, exist_ok=True)
            target = os.path.join(target_dir, lf.original_filename)
            if normalize(target) != normalize(lf.stored_path):
                if os.path.exists(target):
                    failed.append((lf.original_filename, "目标已存在同名文件"))
                    continue
                shutil.move(lf.stored_path, target)
            lf.library_type, lf.folder_name = new_lib, new_cat
            lf.category_id, lf.stored_path = cat_id, target
            db.session.commit()
            moved.append((lf.id, new_lib, new_cat))
    return moved, failed


def index_missing(dry_run=True):
    """
    给 chunk_count 为 0 的文件补索引。

    增量重建按文件指纹跳过已处理的文件，指纹一旦记上但没真进库，
    这个文件就再也不会被索引 —— 检索里永远看不到它。
    """
    from app import create_app
    from database import LibraryFile
    from services.index_service import index_file

    app = create_app()
    done, failed = [], []
    with app.app_context():
        todo = LibraryFile.query.filter(LibraryFile.chunk_count == 0).all()
        print(f"    待补索引: {len(todo)} 个文件")
        for lf in todo:
            if not os.path.exists(lf.stored_path):
                failed.append((lf.original_filename, "文件不在磁盘上"))
                continue
            if dry_run:
                print(f"      {lf.original_filename[:60]}")
                done.append(lf.id)
                continue
            try:
                n = index_file(lf.stored_path, lf.library_type, lf.folder_name)
                done.append(lf.id)
                print(f"      {lf.original_filename[:56]:<58} {n} 块")
            except Exception as e:
                failed.append((lf.original_filename, f"{type(e).__name__}: {e}"))
                print(f"      [失败] {lf.original_filename[:50]}: {e}")
    return len(done), failed


def main():
    ap = argparse.ArgumentParser(description="资料库对齐")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不改动")
    ap.add_argument("--reclassify", action="store_true",
                    help="让 AI 重判「未分类」的文件（需要 API）")
    ap.add_argument("--index-missing", action="store_true",
                    help="给没有任何索引块的文件补建索引（需要 GPU）")
    args = ap.parse_args()

    print("=" * 78)
    print("  资料库对齐：数据库 ↔ 向量索引")
    print("=" * 78)

    print("\n[1] 读取向量索引...")
    col, index_by_source = load_index_state()
    print(f"  索引 {col.count()} 块，来自 {len(index_by_source)} 个 source 路径")

    app, db_by_path = collect_db_files()
    print(f"  数据库 {len(db_by_path)} 个文件")

    # ---- 文件名修复 ----
    # 先修名字：分类器要拿文件名去判，名字是 "epub" 时它什么也判不出来
    print("\n[2] 文件名修复（secure_filename 把中文名削没了）")
    broken = repair_names(dry_run=args.dry_run)
    if broken:
        for _id, have, want in broken[:10]:
            print(f"    {have!r:<14} → {want[:58]}")
        if len(broken) > 10:
            print(f"    …… 共 {len(broken)} 条")
        print(f"    {'（dry-run）将' if args.dry_run else '已'}修复 {len(broken)} 条")
    else:
        print("    无需修复")

    # ---- 重判未分类 ----
    if args.reclassify:
        print("\n[3] AI 重判未分类文件")
        moved, failed = reclassify_uncategorized(dry_run=args.dry_run)
        print(f"\n    重判 {len(moved)} 个，失败 {len(failed)} 个")
        for name, why in failed:
            print(f"      [跳过] {name[:50]}: {why}")
    else:
        print("\n[3] 跳过未分类重判（加 --reclassify 启用）")

    # ---- 元数据对齐 ----
    # 放在重判之后：重判会搬动文件，索引里的 source 路径得跟着改
    print("\n[4] 索引元数据 vs 数据库")
    if args.dry_run:
        _col_after, index_by_source = load_index_state()
    index_by_name = load_index_by_name()
    fixes, unmatched = plan_sync(index_by_source, db_by_path, index_by_name)
    if fixes:
        by_pair = Counter(((m.get("library_type"), m.get("category")),
                           (r["library_type"], r["folder_name"]))
                          for _, m, r, _, _ in fixes)
        for (have, want), n in by_pair.most_common():
            print(f"    {n:>5} 块  {have[0]}/{have[1]}  →  {want[0]}/{want[1]}")
        print(f"    {'（dry-run）将' if args.dry_run else '已'}改写 {len(fixes)} 块")
    else:
        print("    无差异")
    if unmatched:
        print(f"\n    索引里有 {len(unmatched)} 个 source 在数据库里找不到：")
        for src, n in sorted(unmatched, key=lambda x: -x[1])[:10]:
            print(f"      {n:>5} 块  {os.path.basename(src)}")
    if not args.dry_run:
        apply_metadata(col, fixes)

    # ---- 补索引 ----
    # 有些文件根本没进过索引（增量重建的指纹把它跳过了），检索永远看不到它们
    print("\n[5] 补索引漏掉的文件")
    if args.index_missing:
        n_done, failed_idx = index_missing(dry_run=args.dry_run)
        print(f"    补了 {n_done} 个，失败 {len(failed_idx)} 个")
        for name, why in failed_idx:
            print(f"      [跳过] {name[:50]}: {why}")
    else:
        from app import create_app
        from database import LibraryFile as _LF
        _app = create_app()
        with _app.app_context():
            n_missing = _LF.query.filter(_LF.chunk_count == 0).count()
        print(f"    {n_missing} 个文件没有索引块（加 --index-missing 补上）")

    # ---- chunk_count 回填 ----
    print("\n[6] 回填 chunk_count")
    if args.dry_run:
        print(f"    {len(db_by_path)} 个文件需要核对（dry-run 不写库）")
    else:
        _col2, idx_now = load_index_state()
        n = backfill_counts(idx_now, db_by_path)
        print(f"    更新 {n} 条记录的 chunk_count")

    print("\n" + "=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
