"""
库管理服务 — DeepSeek 决策文件分类 + 文件存取
"""
import os
import json
import shutil
from datetime import datetime, timezone

from app_config import LIBRARIES_DIR
from services.deepseek_service import deepseek_flash
from services.file_service import extract_text


def classify_file(filename, content_preview):
    """
    调用 DeepSeek 决定文件应归入哪个库的哪个文件夹。
    返回: {"library_type": "知识库", "folder_name": "大气生物"}
    """
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
        resp = deepseek_flash.chat(prompt, max_tokens=200)
        # 尝试提取 JSON
        resp = resp.strip()
        # 处理可能的 markdown 代码块
        if resp.startswith("```"):
            resp = resp.split("\n", 1)[1]
            if resp.endswith("```"):
                resp = resp[:-3]
            resp = resp.strip()
        result = json.loads(resp)
        return {
            "library_type": result.get("library_type", "知识库"),
            "folder_name": result.get("folder_name", "未分类"),
        }
    except Exception as e:
        # 默认归入知识库的未分类
        return {"library_type": "知识库", "folder_name": "未分类"}


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
        # 如果父目录为空，也删除
        parent = os.path.dirname(file_path)
        if not os.listdir(parent):
            os.rmdir(parent)
