"""
向量知识库配置文件
可根据需要修改模型、分块参数、路径等
"""
import os

# ============================================================
# 路径配置
# ============================================================
MYBOOKAPPS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 三库源目录（都会被扫描索引）
# 每个元组: (目录路径, library_type 标签)
SOURCE_DIRS = [
    # 项目级知识库（原始 PDF）
    (os.path.join(MYBOOKAPPS_ROOT, "知识库"), "知识库"),
    # 用户上传的文件
    (os.path.join(MYBOOKAPPS_ROOT, "libraries", "知识库"), "知识库"),
    (os.path.join(MYBOOKAPPS_ROOT, "libraries", "参考库"), "参考库"),
    (os.path.join(MYBOOKAPPS_ROOT, "libraries", "风格库"), "风格库"),
]

# ChromaDB 向量数据库持久化目录
CHROMA_DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")

# 文件指纹缓存（用于增量更新检测）
FINGERPRINT_FILE = os.path.join(os.path.dirname(__file__), ".file_fingerprints.json")

# ============================================================
# 嵌入模型配置
# ============================================================
# 推荐模型（中文效果优秀，体积小）：
#   BAAI/bge-small-zh-v1.5   — 轻量 100MB，速度快
#   BAAI/bge-large-zh-v1.5  — 精度最高 1.3GB
#   shibing624/text2vec-base-chinese — 均衡 400MB
EMBEDDING_MODEL = os.path.join(os.path.dirname(__file__), "..", "model", "bge-m3")

# 使用 HF 镜像（国内网络必需）
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 设备选择：优先使用 CUDA GPU，不可用时自动回退 CPU
# RTX 3060 12GB 跑 bge 系列模型非常充裕
import torch
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ============================================================
# 文本分块配置
# ============================================================
# 每个 chunk 的目标字符数（中文约 500 字 ≈ 1 个段落组）
CHUNK_SIZE = 500
# 相邻 chunk 之间的重叠字符数（保持语义连续性）
CHUNK_OVERLAP = 80

# ============================================================
# 检索配置
# ============================================================
# 默认返回的 chunk 数量
DEFAULT_TOP_K = 20
# 相似度阈值（低于此值的结果将被过滤，范围 0-1）
SIMILARITY_THRESHOLD = 0.3

# ============================================================
# ChromaDB collection 名称
# ============================================================
COLLECTION_NAME = "sci_fi_knowledge"
