"""
MyBookApps 全局配置
"""
import os
import sys

# ---- 加载 .env 文件 ----
def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_load_env()

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

### 标点规范
- 少用分号，多用句号。短句比长句安全。
- 破折号控制：全文破折号密度不超过每500字2个。破折号用于真正需要强调的插入语，不能替代逗号、句号做随意停顿。

### 写作禁令
- 禁止直接说出人物的情感（"他很难过""他很愤怒"）
- 禁止使用陈词滥调的比喻（"心如刀绞""泪如雨下"）
- 禁止以道理或总结结尾
- 禁止煽情渲染
- 禁止让叙述者变回上帝视角
- 禁止长篇对话（超过5轮就要用叙述打断）
- 禁止模糊的数字
- 禁止滥用破折号（每500字不超过2个）
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
# 最终进提示词的条数。原来是 20，但实测 20 条里 15 条来自同一本书，
# 降到 12 并配合来源配额，多样性反而大幅提升。
RAG_TOP_K = 12
# 每条子查询召回的候选数（融合前）。
# 实测：候选池越深，来源越多样 —— top-60 只覆盖 4 个文件，top-300 覆盖 8 个，
# 而相似度只从 0.557 掉到 0.516（bge-m3 区间本来就窄，这点差距无意义）。
RAG_CANDIDATE_K = 200
# 来源配额 —— 这是修复「单文件垄断 top-k」的核心
RAG_MAX_PER_FILE = 2
RAG_MAX_PER_CATEGORY = 4
# bge-m3 的相似度是很弱的相关性信号（所有结果都挤在 0.49~0.64），
# 真正的排序信号是 RRF 名次。所以门限只当「滤掉明显无关」的安全网，
# 不承担排序职责 —— 别把它调紧，否则会把候选池饿死。
RAG_ABS_FLOOR = 0.40
RAG_REL_MARGIN = 0.15
# 是否用 flash 模型把用户提示拆成多条检索子查询
RAG_QUERY_EXPANSION = True
RAG_MAX_SUBQUERIES = 4
# 兼容旧调用点
RAG_THRESHOLD = 0.3

# ---- 资料库分类体系（library_categories 表的种子数据）----
# name: 规范分类名
# desc: 给 AI 看的判定说明 —— 分类准确率的关键
# aliases: 历史上散落的旧文件夹名，归并脚本据此合并
LIBRARY_TAXONOMY = {
    "知识库": [
        {"name": "行星与系外世界", "sort": 10,
         "desc": "系外行星、系外卫星、行星大气与环流、潮汐锁定、宜居带、行星地质与行星科学综论",
         "aliases": ["潮汐锁定", "系外行星", "系外卫星", "行星大气", "行星环流",
                     "行星科学", "外星世界", "天文物理"]},
        {"name": "宇宙与天体物理", "sort": 20,
         "desc": "恒星演化、星系、宇宙学、量子物理、高能物理、时空与信息传输理论",
         "aliases": ["宇宙探索", "量子物理", "宇宙计算", "随机传输"]},
        {"name": "地球与地质", "sort": 30,
         "desc": "地幔对流、板块运动、地球内部结构、古气候与地质年代",
         "aliases": ["地幔对流"]},
        {"name": "生命起源与演化", "sort": 40,
         "desc": "生命起源、地外生命可能性、生物物理、分子演化、硅基生命等替代生化路径",
         "aliases": ["宇宙生命", "生物物理", "硅基生命"]},
        {"name": "微生物与生态", "sort": 50,
         "desc": "微生物群落、珊瑚礁与海洋生态、共生关系、大气生物、生态系统动力学",
         "aliases": ["大堡礁微生物", "珊瑚礁微生物", "大气生物", "海洋生物"]},
        {"name": "神经与认知", "sort": 60,
         "desc": "神经生物学、光遗传与神经调控、意识与认知科学、感知机制",
         "aliases": ["光学神经调控", "神经生物学", "思维"]},
        {"name": "植物与农业", "sort": 70,
         "desc": "植物生理、太空种植与受控环境农业、作物育种、农业地质、香料与作物志",
         "aliases": ["太空种植", "植物", "农业地质", "香料参考"]},
        {"name": "法律与条约", "sort": 80,
         "desc": "外空条约、空间法、国内法律法规、伦理与治理规范",
         "aliases": ["外空条约", "法律法规"]},
        {"name": "工程与技术", "sort": 90,
         "desc": "航天工程、恒星工程、星际冬眠、材料与能源、AI 与计算系统",
         "aliases": ["恒星工程", "星际冬眠", "AI与计算"]},
        {"name": "未分类", "sort": 999,
         "desc": "暂时无法归入上述任何分类的科学资料",
         "aliases": []},
    ],
    "参考库": [
        {"name": "科幻小说", "sort": 10,
         "desc": "科幻长篇与短篇小说、赛博朋克、硬科幻等虚构叙事作品",
         "aliases": ["科幻小说", "盲视", "零伯爵"]},
        {"name": "历史纪实", "sort": 20,
         "desc": "战争史、朝代史、历史生活风俗等非虚构历史叙事",
         "aliases": ["战争历史", "清代历史", "红楼梦"]},
        {"name": "神话与民俗", "sort": 30,
         "desc": "神话志怪、妖怪民俗、地方传说",
         "aliases": ["山精神话"]},
        {"name": "报道与见闻", "sort": 40,
         "desc": "记者手记、旅行见闻、田野调查等第一人称纪实报道",
         "aliases": ["古巴见闻"]},
        {"name": "科普与社会", "sort": 50,
         "desc": "面向大众的科普读物、技术与社会评论、未来学与职场观察",
         "aliases": ["协同进化", "机器人职场", "古生物学"]},
        {"name": "其他文学", "sort": 60,
         "desc": "非科幻的文学作品、散文、诗歌",
         "aliases": []},
        {"name": "未分类", "sort": 999,
         "desc": "暂时无法归入上述任何分类的参考资料",
         "aliases": []},
    ],
    "风格库": [
        {"name": "个人作品", "sort": 10,
         "desc": "作者本人的写作样本，用于提取个人风格特征",
         "aliases": []},
        {"name": "风格样本", "sort": 20,
         "desc": "他人的风格参考样本、写作技巧与文体分析资料",
         "aliases": []},
        {"name": "未分类", "sort": 999,
         "desc": "暂时无法归入上述任何分类的风格资料",
         "aliases": []},
    ],
}

# 跨库纠正：这些旧文件夹被误放进了「知识库」，实际是叙事/科普散文，
# 会严重污染科学检索（《王树增战争系列》一本就占知识库 36%）。
CROSS_LIBRARY_FIXES = {
    # 旧 (library_type, folder_name) -> 新 (library_type, category_name)
    ("知识库", "战争历史"): ("参考库", "历史纪实"),
    ("知识库", "红楼梦"): ("参考库", "历史纪实"),
    ("知识库", "零伯爵"): ("参考库", "科幻小说"),
    ("知识库", "山精神话"): ("参考库", "神话与民俗"),
    ("知识库", "协同进化"): ("参考库", "科普与社会"),
}

# ---- Flask 配置 ----
SECRET_KEY = "mybookapps-secret-key-2026"
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB 上传限制
UPLOAD_FOLDER = LIBRARIES_DIR
