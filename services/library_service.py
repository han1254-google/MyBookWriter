"""
库管理服务 — DeepSeek 决策文件分类 + 文件存取

分类为什么以前不准：
    旧版 classify_file() 从不把现有文件夹列表交给 AI，
    所以每传一个文件它就凭空造一个新名字，结果知识库里出现了
    潮汐锁定 / 系外行星 / 系外卫星 / 行星大气 / 行星环流 / 行星科学 / 外星世界
    这 7 个其实是同一主题的文件夹，还有 大堡礁微生物 与 珊瑚礁微生物 这种纯重复。

现在的做法：
    把 library_categories 表里的规范分类名 + 判定说明列进提示词，
    让 AI **从清单里选**，只在确实无法归入时才允许新建，
    并要求它给出分类理由存档（classify_reason），方便你回头审计它为什么分错。
"""
import os
import json
import time
from datetime import datetime, timezone

from app_config import LIBRARIES_DIR, LIBRARY_TAXONOMY
from services.deepseek_service import deepseek_flash
from logger import get_logger

log = get_logger("service.library")

VALID_LIBRARIES = ("知识库", "参考库", "风格库")


# ============================================================
# 分类清单
# ============================================================
def load_taxonomy(library_type=None):
    """
    读取分类清单。优先用数据库里的 library_categories（可从 UI 维护），
    拿不到（例如脚本在 app context 外运行）时退回 app_config 的种子常量。

    Returns: {库类型: [{name, description}, ...]}
    """
    try:
        from database import LibraryCategory
        rows = (LibraryCategory.query
                .filter_by(is_active=True)
                .order_by(LibraryCategory.library_type,
                          LibraryCategory.sort_order)
                .all())
        if rows:
            out = {}
            for r in rows:
                if library_type and r.library_type != library_type:
                    continue
                out.setdefault(r.library_type, []).append(
                    {"name": r.name, "description": r.description or ""})
            if out:
                return out
    except Exception as e:
        log.debug(f"读取 library_categories 失败，使用种子常量: {type(e).__name__}: {e}")

    out = {}
    for lib, items in LIBRARY_TAXONOMY.items():
        if library_type and lib != library_type:
            continue
        out[lib] = [{"name": it["name"], "description": it["desc"]} for it in items]
    return out


def _render_taxonomy(taxonomy):
    """渲染成提示词里的分类清单"""
    lines = []
    for lib, items in taxonomy.items():
        lines.append(f"### {lib}")
        for it in items:
            if it["name"] == "未分类":
                continue
            lines.append(f"- {it['name']}：{it['description']}")
        lines.append("")
    return "\n".join(lines).strip()


def _valid_names(taxonomy):
    return {lib: {it["name"] for it in items} for lib, items in taxonomy.items()}


# ============================================================
# 分类
# ============================================================
_PROMPT_WITH_LIB = """你是资料分类助手。文件将被存入「{library_type}」库。
请**从下面的分类清单里选一个**最合适的分类。

{taxonomy}

判定规则（重要）：
- 必须优先从清单里选。清单里有能容纳它的分类，就不要新建。
- 只有当这个文件的主题**完全无法**归入任何现有分类时，才把 is_new 设为 true
  并给出一个新分类名（要足够宽泛，能容纳同主题的后续文件，不要用书名/篇名当分类名）。
- 分类名不要用具体作品名。比如一本讲潮汐锁定的书应归入「行星与系外世界」，
  而不是新建一个「潮汐锁定」。

文件名：{filename}
文件内容预览：
{preview}

严格输出 JSON，不要任何其他文字：
{{"category": "分类名", "is_new": false, "reason": "一句话说明为什么选它"}}"""


_PROMPT_FULL = """你是资料分类助手。请判断这个文件该进哪个库、哪个分类。

三个库的定位：
- **知识库**：科学论文、科普资料、学术研究。用于给小说提供**科学事实依据**。
- **参考库**：小说、纪实、历史、神话等**叙事作品**，用于参考写法和构思。
- **风格库**：写作风格样本、文体分析资料，用于提取语言风格特征。

关键判定（这一步最容易错）：
- 判断依据是**文件的体裁**，不是题材。一本讲战争史的纪实散文，即使内容严肃，
  也属于「参考库」而不是「知识库」——它是叙事文本，不是科学依据。
- 只有论文、科普、教科书这类**以陈述事实为目的**的文本才进知识库。
- 小说（包括硬科幻小说）一律进参考库。

现有分类清单：

{taxonomy}

判定规则：
- 必须优先从清单里选。清单里有能容纳它的分类，就不要新建。
- 只有完全无法归入时才把 is_new 设为 true 并给新分类名（要宽泛，不要用书名）。

文件名：{filename}
文件内容预览：
{preview}

严格输出 JSON，不要任何其他文字：
{{"library_type": "知识库/参考库/风格库", "category": "分类名",
  "is_new": false, "reason": "一句话说明为什么这样分"}}"""


def _parse_json(resp):
    resp = (resp or "").strip()
    if resp.startswith("```"):
        resp = resp.split("\n", 1)[1] if "\n" in resp else resp
        if resp.rstrip().endswith("```"):
            resp = resp.rstrip()[:-3]
        resp = resp.strip()
    return json.loads(resp)


def classify_file(filename, content_preview, library_type=""):
    """
    调用 DeepSeek 决定文件归属。

    Returns:
        {"library_type": str, "folder_name": str, "reason": str, "is_new": bool}
    """
    taxonomy = load_taxonomy(library_type or None)
    rendered = _render_taxonomy(taxonomy)
    preview = (content_preview or "")[:1500]

    if library_type:
        prompt = _PROMPT_WITH_LIB.format(
            library_type=library_type, taxonomy=rendered,
            filename=filename, preview=preview)
    else:
        prompt = _PROMPT_FULL.format(
            taxonomy=rendered, filename=filename, preview=preview)

    try:
        t0 = time.time()
        result = _parse_json(deepseek_flash.chat(prompt, max_tokens=800))
        elapsed = (time.time() - t0) * 1000

        lib = library_type or result.get("library_type", "知识库")
        if lib not in VALID_LIBRARIES:
            log.warning(f"AI 返回了无效库类型 {lib!r}，退回知识库")
            lib = "知识库"

        category = str(result.get("category", "") or "").strip() or "未分类"
        is_new = bool(result.get("is_new"))
        reason = str(result.get("reason", "") or "").strip()[:500]

        # 校验：AI 说选了现有分类，就必须真的在清单里
        known = _valid_names(load_taxonomy()).get(lib, set())
        if not is_new and category not in known:
            log.warning(f"AI 声称选用现有分类但清单里没有 {category!r}，"
                        f"按新建处理")
            is_new = True

        log.info(f"AI分类: {lib}/{category} "
                 f"({'新建' if is_new else '复用'}, {elapsed:.0f}ms) — {reason}")
        return {"library_type": lib, "folder_name": category,
                "reason": reason, "is_new": is_new}

    except Exception as e:
        log.warning(f"AI分类失败，使用默认值: {type(e).__name__}: {e}")
        return {"library_type": library_type or "知识库", "folder_name": "未分类",
                "reason": f"分类失败: {e}", "is_new": False}


def ensure_category(library_type, name, description="", reason=""):
    """
    确保分类在 library_categories 里存在，返回其 id。
    AI 新建的分类落库后，下次上传就能被复用，不会再重复造名字。
    """
    try:
        from database import db, LibraryCategory
        cat = LibraryCategory.query.filter_by(
            library_type=library_type, name=name).first()
        if cat:
            return cat.id
        top = (LibraryCategory.query.filter_by(library_type=library_type)
               .order_by(LibraryCategory.sort_order.desc()).first())
        cat = LibraryCategory(
            library_type=library_type,
            name=name,
            description=description or reason,
            aliases="[]",
            sort_order=(top.sort_order + 1) if top and top.sort_order < 900 else 500,
            is_active=True,
        )
        db.session.add(cat)
        db.session.commit()
        log.info(f"新建分类: {library_type}/{name}")
        return cat.id
    except Exception as e:
        log.warning(f"落库新分类失败: {type(e).__name__}: {e}")
        return None


# ============================================================
# 风格提取
# ============================================================
def extract_style(text, filename):
    """对风格库上传的文件，提取写作风格特征"""
    prompt = f"""你是一个文学风格分析师。请分析以下文章的写作风格特征。

文件名：{filename}
文章内容：
{text[:6000]}

请从以下维度提取风格特征：

1. **叙事视角**：第几人称？叙述者姿态？与读者的距离？
2. **语言节奏**：句子长度偏好？段落节奏？标点使用习惯？
3. **词汇特征**：口语化程度？书面语比例？特有词汇/方言？
4. **修辞手法**：偏好比喻类型？意象选择？象征体系？
5. **情感处理**：直接还是含蓄？用景物承载还是内心独白？
6. **对话风格**：稀疏还是密集？简短还是长篇？方言使用？
7. **结构与节奏**：开篇方式？结尾习惯？章节过渡？
8. **独特印记**：最鲜明的个人风格特征（2-3条）

请以简洁的要点形式输出，每条1-2行。总长度控制在500字以内。
不要写"分析如下"之类的开头，直接列要点。"""

    try:
        t0 = time.time()
        from services.deepseek_service import deepseek_flash
        result = deepseek_flash.chat(prompt, max_tokens=2000)
        elapsed = (time.time() - t0) * 1000
        log.info(f"风格提取完成: {len(result)} 字符, {elapsed:.0f}ms")
        return result.strip()
    except Exception as e:
        log.warning(f"风格提取失败: {type(e).__name__}: {e}")
        return ""


# ============================================================
# 摘要
# ============================================================
_SUMMARY_PROMPT = """请总结这份资料的核心内容，用中文，4-6 句话。

下面给你的是全文抽样（目录 + 开头 + 正文若干处节选），
**请基于正文节选来总结，不要只照抄标题页和目录**。

要求：
- 说清这份资料在讲什么、给出了哪些具体结论或数据
- 保留关键的具体数字、物种名、地名、年份
- 直接写摘要，不要「本文」「这份资料」之类的开头
- 不要评价，不要写"值得一读"这种话

文件名：{filename}

{sample}"""


def summarize_file(filename, sample):
    """基于全文抽样生成摘要。抽样由 file_service.sample_text() 产出。"""
    if not (sample or "").strip():
        raise ValueError("抽样文本为空，无法生成摘要")
    t0 = time.time()
    summary = deepseek_flash.chat(
        _SUMMARY_PROMPT.format(filename=filename, sample=sample[:14000]),
        max_tokens=1500,
    ).strip()
    log.info(f"摘要生成: {filename} → {len(summary)} 字符, "
             f"{(time.time() - t0) * 1000:.0f}ms")
    return summary


# ============================================================
# 文件存取
# ============================================================
def save_file(file_storage, library_type, folder_name):
    """保存上传的文件到指定库的文件夹，返回存储路径"""
    safe_folder = "".join(c for c in folder_name if c not in r'\/:*?"<>|').strip()
    if not safe_folder:
        safe_folder = "未分类"

    target_dir = os.path.join(LIBRARIES_DIR, library_type, safe_folder)
    os.makedirs(target_dir, exist_ok=True)

    original_name = file_storage.filename
    stored_path = os.path.join(target_dir, original_name)

    # 如已存在同名文件，加时间戳
    if os.path.exists(stored_path):
        name, ext = os.path.splitext(original_name)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        stored_path = os.path.join(target_dir, f"{name}_{ts}{ext}")

    file_storage.save(stored_path)
    return stored_path


def list_libraries():
    """列出所有库的目录结构"""
    result = {}
    for lib in VALID_LIBRARIES:
        lib_path = os.path.join(LIBRARIES_DIR, lib)
        if os.path.exists(lib_path):
            folders = {}
            for folder in sorted(os.listdir(lib_path)):
                folder_path = os.path.join(lib_path, folder)
                if os.path.isdir(folder_path):
                    folders[folder] = [
                        f for f in sorted(os.listdir(folder_path))
                        if os.path.isfile(os.path.join(folder_path, f))
                    ]
            result[lib] = folders
    return result


def delete_file(file_path):
    """删除文件，目录空了顺手清理"""
    if os.path.exists(file_path):
        os.remove(file_path)
        parent = os.path.dirname(file_path)
        try:
            if not os.listdir(parent):
                os.rmdir(parent)
        except OSError:
            pass
