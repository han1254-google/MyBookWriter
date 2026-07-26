"""
库管理服务 — DeepSeek 决策文件分类 + 文件存取
"""
import os
import json
import time
import shutil
from datetime import datetime, timezone

from app_config import LIBRARIES_DIR
from services.deepseek_service import deepseek_flash
from services.file_service import extract_text
from logger import get_logger

log = get_logger("service.library")


def classify_file(filename, content_preview, library_type=""):
    """
    调用 DeepSeek 决定文件应归入哪个文件夹。
    如果用户已指定 library_type，则只让 AI 建议文件夹名。
    返回: {"library_type": "知识库", "folder_name": "大气生物"}
    """
    if library_type:
        # 用户已指定库类型，AI 只需建议文件夹名
        prompt = f"""你是一个文件分类助手。文件将被存入「{library_type}」库。
请根据文件名和内容预览，建议一个合适的文件夹名（简洁，2-6个字）。

文件名：{filename}
文件内容预览（前500字）：
{content_preview[:500]}

请只回复一个 JSON 对象，不要其他文字：
{{"folder_name": "建议的文件夹名"}}"""
    else:
        prompt = f"""你是一个文件分类助手。请根据以下文件信息，判断它应该归入哪个资料库。

三个资料库的定义：
1. **知识库**：科学论文、科普资料、学术研究，按学科主题（如"大气生物""潮汐锁定""硅基生命""物理学""思维""法律法规"等）分文件夹
2. **参考库**：文学作品、小说、参考文献，按作品/作者分文件夹
3. **风格库**：个人写作样本、风格参考、写作技巧资料，按主题分文件夹

文件名：{filename}
文件内容预览（前500字）：
{content_preview[:500]}

请只回复一个 JSON 对象，不要其他文字：
{{"library_type": "知识库/参考库/风格库", "folder_name": "建议的文件夹名"}}"""

    try:
        t0 = time.time()
        resp = deepseek_flash.chat(prompt, max_tokens=200)
        elapsed = (time.time() - t0) * 1000
        resp = resp.strip()
        if resp.startswith("```"):
            resp = resp.split("\n", 1)[1]
            if resp.endswith("```"):
                resp = resp[:-3]
            resp = resp.strip()
        result = json.loads(resp)
        log.info(f"AI分类完成: {result.get('folder_name', '?')} ({elapsed:.0f}ms)")
        return {
            "library_type": library_type or result.get("library_type", "知识库"),
            "folder_name": result.get("folder_name", "未分类"),
        }
    except Exception as e:
        log.warning(f"AI分类失败，使用默认值: {type(e).__name__}: {e}")
        return {"library_type": library_type or "知识库", "folder_name": "未分类"}


def save_file(file_storage, library_type, folder_name):
    """
    保存上传的文件到指定库的文件夹。
    返回: 存储路径
    """
    # 清理文件夹名中的非法字符
    safe_folder = "".join(c for c in folder_name if c not in r'\/:*?"<>|').strip()
    if not safe_folder:
        safe_folder = "未分类"

    target_dir = os.path.join(LIBRARIES_DIR, library_type, safe_folder)
    os.makedirs(target_dir, exist_ok=True)

    # 保存文件
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
    for lib in ["知识库", "参考库", "风格库"]:
        lib_path = os.path.join(LIBRARIES_DIR, lib)
        if os.path.exists(lib_path):
            folders = {}
            for folder in os.listdir(lib_path):
                folder_path = os.path.join(lib_path, folder)
                if os.path.isdir(folder_path):
                    files = [
                        f for f in os.listdir(folder_path)
                        if os.path.isfile(os.path.join(folder_path, f))
                    ]
                    folders[folder] = files
            result[lib] = folders
    return result


def delete_file(file_path):
    """删除文件"""
    if os.path.exists(file_path):
        os.remove(file_path)
        parent = os.path.dirname(file_path)
        if not os.listdir(parent):
            os.rmdir(parent)


def extract_style(text, filename):
    """
    对风格库上传的文件，提取写作风格特征。
    返回格式化的风格描述字符串。
    """
    prompt = f"""你是一个文学风格分析师。请分析以下文章的写作风格特征。

文件名：{filename}
文章内容（前3000字）：
{text[:3000]}

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
        from services.deepseek_service import deepseek
        result = deepseek.chat(prompt, max_tokens=1024)
        elapsed = (time.time() - t0) * 1000
        log.info(f"风格提取完成: {len(result)} 字符, {elapsed:.0f}ms")
        return result.strip()
    except Exception as e:
        log.warning(f"风格提取失败: {type(e).__name__}: {e}")
        return ""
