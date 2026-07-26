"""
MyBookApps 全局配置
"""
import os
import sys

# ---- 项目根目录 ----
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MYBOOKAPPS_ROOT = os.path.dirname(os.path.abspath(__file__))

# ---- DeepSeek API（Anthropic 兼容端点）----
DEEPSEEK_BASE_URL = "https://api.deepseek.com/anthropic"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-v4-pro[1m]"
DEEPSEEK_FLASH_MODEL = "deepseek-v4-flash"

# ---- 路径 ----
LIBRARIES_DIR = os.path.join(MYBOOKAPPS_ROOT, "libraries")
DATA_DIR = os.path.join(MYBOOKAPPS_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "mybookapps.db")

# 知识库原始文件目录（用于 RAG 检索）
KNOWLEDGE_BASE_DIR = os.path.join(MYBOOKAPPS_ROOT, "知识库")

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
for lib in ["知识库", "参考库", "风格库"]:
    os.makedirs(os.path.join(LIBRARIES_DIR, lib), exist_ok=True)

# ---- 写作风格指南（从 CLAUDE.md 提取）----
WRITING_STYLE_GUIDE = """## 写作风格要求

### 叙事视角
- 第一人称。"我"是观察者和记录者，不是英雄。
- 自我审视式的叙述：能看到自己的局限、可笑和软弱，但不沉溺于自怜。
- 叙述者对自己的评价永远是向下修正的。

### 语言风格
- 长句铺陈，短句截断。长句用于描写、回忆、氛围渲染；短句用于情感爆发点或幽默。
- 口语化但不随意，偶尔穿插极精炼的书面语甚至文言节奏。
- 高雅与世俗的瞬时切换是标志性手法。宏大叙事被日常琐碎打断，形成反差和幽默。
- 比喻来自日常生活和工程经验，不来自文学修辞手册。

### 细节与数字
- 具体数字 > 抽象形容词。不说"等了很久"，说"从一点半等到五点"。
- 年份、时刻、价格、温度、街道名、公交线路——这些都是叙事骨架。
- 品牌和地名必须真实具体。

### 幽默
- 自我解嘲式幽默，永远是拿自己开刀，从不嘲弄弱者。
- 在一段沉重或煽情即将到来时，用一句自嘲把它打碎。

### 对话
- 稀疏、简短、有力。
- 方言用于农村人物，但不滥用。
- 对话出现时必定在做至少一件事：推动情节、揭示性格、制造情绪转折。

### 情感处理
- 不煽情。不说"我很悲伤"。写动作、写物、写环境，让读者自己哭。
- 具体物件承载情绪。物件比抒情段落更锋利。

### 结构
- 环形结构：开头的意象或句子在结尾以变形的方式回归。
- 章节之间的过渡靠意象的呼应，不靠过渡句。

### 结尾
- 落在一个具体的画面或动作上，不落在结论或道理上。
- 开放式，不闭合，像一扇没关紧的窗。

### 写作禁令
- 禁止直接说出人物的情感（"他很难过""他很愤怒"）
- 禁止使用陈词滥调的比喻（"心如刀绞""泪如雨下"）
- 禁止以道理或总结结尾
- 禁止煽情渲染
- 禁止让叙述者变回上帝视角
- 禁止长篇对话（超过5轮就要用叙述打断）
- 禁止模糊的数字
- 禁止叙述越界（当前章只能知道已发生的事）"""

# ---- PRECHA 模板 ----
PRECHA_TEMPLATE = """## PRECHA
`上一章节的名字和文件链接`
prechaName {precha_name}
prechaLink {precha_link}

## PRECHA CONTENT
`用于记录上一章节的内容（时间地点人物 起因经过结果等等）`
时间：{precha_time}
地点：{precha_place}
人物：{precha_chars}
起：{precha_cause}
经：{precha_process}
结：{precha_result}
媒：{precha_media}

## CONTENT
"""

# ---- RAG 配置 ----
RAG_TOP_K = 5
RAG_THRESHOLD = 0.3

# ---- Flask 配置 ----
SECRET_KEY = "mybookapps-secret-key-2026"
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB 上传限制
UPLOAD_FOLDER = LIBRARIES_DIR
