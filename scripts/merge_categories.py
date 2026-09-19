"""
分类归并脚本 — 把散乱的旧文件夹合并到规范分类

背景：
    旧版 classify_file() 不给 AI 看现有文件夹，导致每传一个文件就新造一个分类名。
    知识库里出现了 7 个其实同主题的文件夹（潮汐锁定/系外行星/系外卫星/行星大气/
    行星环流/行星科学/外星世界），以及 大堡礁微生物 与 珊瑚礁微生物 这种纯重复。

    更严重的是**库类型也错了**：《王树增战争系列》(6920 chunks，占知识库 36%) 和
    《古人的生活》(1920) 是叙事散文却躺在「知识库」里，污染所有科学检索。
    跨库纠正的收益比合并文件夹更大。

归并依据 app_config.LIBRARY_TAXONOMY 的 aliases 和 CROSS_LIBRARY_FIXES。

用法：
  python scripts/merge_categories.py --dry-run     # 打印映射表，不动任何文件
  python scripts/merge_categories.py               # 执行（移动文件 + 更新数据库）
  python scripts/merge_categories.py --reindex     # 执行后自动重建向量索引
"""
import os
import sys
import json
import shutil
import argparse
from collections import defaultdict

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_config import LIBRARIES_DIR, LIBRARY_TAXONOMY, CROSS_LIBRARY_FIXES


# ============================================================
# 构建映射表
# ============================================================
def build_alias_map():
    """(库, 旧文件夹名) -> (新库, 新分类名)"""
    mapping = {}
    for lib, items in LIBRARY_TAXONOMY.items():
        for it in items:
            for alias in it["aliases"]:
                mapping[(lib, alias)] = (lib, it["name"])
            # 规范名映射到自己，便于统一处理
            mapping[(lib, it["name"])] = (lib, it["name"])
    # 跨库纠正优先级最高
    mapping.update(CROSS_LIBRARY_FIXES)
    return mapping


def scan_folders():
    """扫描磁盘上实际存在的 (库, 文件夹) 及其文件数"""
    found = []
    for lib in ("知识库", "参考库", "风格库"):
        lib_path = os.path.join(LIBRARIES_DIR, lib)
        if not os.path.isdir(lib_path):
            continue
        for folder in sorted(os.listdir(lib_path)):
            fpath = os.path.join(lib_path, folder)
            if not os.path.isdir(fpath):
                continue
            files = [f for f in os.listdir(fpath)
                     if os.path.isfile(os.path.join(fpath, f))]
            found.append((lib, folder, files))
    return found


def plan_moves():
    """
    返回 (moves, unmapped)
      moves:    [(旧库, 旧文件夹, 新库, 新分类, [文件名]), ...]  需要变动的
      unmapped: [(库, 文件夹, 文件数), ...]                     清单里没有的
    """
    alias_map = build_alias_map()
    moves, unmapped = [], []

    for lib, folder, files in scan_folders():
        target = alias_map.get((lib, folder))
        if target is None:
            unmapped.append((lib, folder, len(files)))
            continue
        new_lib, new_cat = target
        if (new_lib, new_cat) == (lib, folder):
            continue   # 已经在正确位置
        moves.append((lib, folder, new_lib, new_cat, files))

    return moves, unmapped


# ============================================================
# 打印
# ============================================================
def print_plan(moves, unmapped):
    print("\n" + "=" * 78)
    print("  归并映射表")
    print("=" * 78)

    if not moves:
        print("\n  所有文件夹都已在规范分类下，无需归并。")
    else:
        cross = [m for m in moves if m[0] != m[2]]
        same = [m for m in moves if m[0] == m[2]]

        if cross:
            print("\n  ▸ 跨库纠正（体裁判错，收益最大）")
            print(f"    {'旧位置':<34s}  →  {'新位置':<30s} 文件")
            print("    " + "-" * 72)
            for lib, folder, nlib, ncat, files in cross:
                print(f"    {lib + '/' + folder:<34s}  →  "
                      f"{nlib + '/' + ncat:<30s} {len(files)}")

        if same:
            print("\n  ▸ 同库内合并（重叠主题）")
            grouped = defaultdict(list)
            for lib, folder, nlib, ncat, files in same:
                grouped[(nlib, ncat)].append((folder, len(files)))
            for (nlib, ncat), srcs in sorted(grouped.items()):
                total = sum(n for _, n in srcs)
                print(f"\n    {nlib}/{ncat}  ← 合并 {len(srcs)} 个文件夹，"
                      f"共 {total} 个文件")
                for folder, n in sorted(srcs, key=lambda x: -x[1]):
                    print(f"        · {folder} ({n})")

    if unmapped:
        print("\n  ▸ 清单里没有的文件夹（保持原样，不动）")
        for lib, folder, n in unmapped:
            print(f"    {lib}/{folder} ({n} 个文件)")

    total_files = sum(len(m[4]) for m in moves)
    print(f"\n  合计: 变动 {len(moves)} 个文件夹，移动 {total_files} 个文件")
    print("=" * 78)


# ============================================================
# 执行
# ============================================================
def execute_moves(moves):
    """移动磁盘文件。返回 [(旧绝对路径, 新绝对路径), ...]"""
    moved = []
    for lib, folder, nlib, ncat, files in moves:
        src_dir = os.path.join(LIBRARIES_DIR, lib, folder)
        dst_dir = os.path.join(LIBRARIES_DIR, nlib, ncat)
        os.makedirs(dst_dir, exist_ok=True)

        for fname in files:
            src = os.path.join(src_dir, fname)
            dst = os.path.join(dst_dir, fname)
            if os.path.exists(dst):
                base, ext = os.path.splitext(fname)
                dst = os.path.join(dst_dir, f"{base}_{folder}{ext}")
                print(f"    [重名] {fname} → {os.path.basename(dst)}")
            shutil.move(src, dst)
            moved.append((src, dst))

        # 源目录空了就删掉
        try:
            if os.path.isdir(src_dir) and not os.listdir(src_dir):
                os.rmdir(src_dir)
        except OSError as e:
            print(f"    [警告] 无法删除空目录 {src_dir}: {e}")

        print(f"    {lib}/{folder} → {nlib}/{ncat} ({len(files)} 个文件)")
    return moved


def sync_database(moves, moved_paths):
    """更新 library_files 的库类型/分类/路径，并挂上 category_id"""
    from app import create_app
    from database import db, LibraryFile, LibraryCategory

    path_map = dict(moved_paths)
    app = create_app()
    with app.app_context():
        # 确保目标分类都已存在
        for _lib, _folder, nlib, ncat, _files in moves:
            if not LibraryCategory.query.filter_by(
                    library_type=nlib, name=ncat).first():
                db.session.add(LibraryCategory(
                    library_type=nlib, name=ncat, description="",
                    aliases="[]", sort_order=500, is_active=True))
        db.session.commit()

        cat_ids = {(c.library_type, c.name): c.id
                   for c in LibraryCategory.query.all()}
        move_map = {(lib, folder): (nlib, ncat)
                    for lib, folder, nlib, ncat, _ in moves}

        updated = 0
        for lf in LibraryFile.query.all():
            target = move_map.get((lf.library_type, lf.folder_name))
            if target:
                lf.library_type, lf.folder_name = target
                updated += 1
            # 路径可能因移动而变
            if lf.stored_path in path_map:
                lf.stored_path = path_map[lf.stored_path]
            lf.category_id = cat_ids.get((lf.library_type, lf.folder_name))
        db.session.commit()

        print(f"\n  数据库: 更新 {updated} 条文件记录，"
              f"{LibraryFile.query.filter(LibraryFile.category_id.isnot(None)).count()}"
              f"/{LibraryFile.query.count()} 条已挂上规范分类")

        # 汇总现状
        rows = (db.session.query(LibraryFile.library_type,
                                 LibraryFile.folder_name,
                                 db.func.count(LibraryFile.id))
                .group_by(LibraryFile.library_type, LibraryFile.folder_name)
                .order_by(LibraryFile.library_type).all())
        print("\n  归并后的分类分布:")
        for lib, folder, n in rows:
            print(f"    {lib}/{folder}: {n}")


def reindex():
    """重建向量索引 —— 文件路径变了，旧向量的 source 元数据全部失效"""
    print("\n" + "=" * 78)
    print("  重建向量索引（文件路径已变，必须重建）")
    print("=" * 78)
    import subprocess
    script = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "knowledge_rag", "build_index.py")
    result = subprocess.run([sys.executable, script, "--full"])
    return result.returncode == 0


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="分类归并")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印映射表，不修改任何文件")
    parser.add_argument("--reindex", action="store_true",
                        help="归并后自动重建向量索引")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="跳过确认")
    args = parser.parse_args()

    moves, unmapped = plan_moves()
    print_plan(moves, unmapped)

    if args.dry_run:
        print("\n  --dry-run 模式，未做任何修改。")
        print("  确认映射表无误后，去掉 --dry-run 执行。")
        return

    if not moves:
        return

    if not args.yes:
        print("\n  这会移动磁盘文件并修改数据库。")
        answer = input("  确认执行？(输入 yes 继续): ").strip().lower()
        if answer != "yes":
            print("  已取消。")
            return

    print("\n执行归并 ...")
    moved_paths = execute_moves(moves)
    sync_database(moves, moved_paths)

    print("\n归并完成。")
    if args.reindex:
        if reindex():
            print("\n索引重建完成。建议跑一遍检索回归：")
            print("  python scripts/eval_retrieval.py")
    else:
        print("\n[!] 文件路径已变，向量索引里的 source 元数据已失效，必须重建：")
        print("    python knowledge_rag/build_index.py --full")


if __name__ == "__main__":
    main()
