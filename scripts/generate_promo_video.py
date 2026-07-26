"""
AI 科幻写作助手宣传视频生成器
输出 1080×1920 竖屏 MP4，适用于抖音/小红书/视频号
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moviepy import (
    ImageClip, TextClip, CompositeVideoClip, concatenate_videoclips,
    AudioFileClip, vfx
)
from PIL import Image
import numpy as np

# ---- 配置 ----
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(PROJECT_ROOT, "imgs", "系统运行展示")
PUBLIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "public")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 竖屏 1080×1920
W, H = 1080, 1920
FPS = 30
FONT = "C:/Windows/Fonts/msyh.ttc" if os.path.exists("C:/Windows/Fonts/msyh.ttc") else "C:/Windows/Fonts/arial.ttf"
DURATION_PER_IMAGE = 4  # 每张图展示秒数
CROSSFADE = 0.5  # 过渡秒数

# 截图和对应的标题
SCENES = [
    ("首页 Dashboard", "屏幕截图_26-7-2026_15355_localhost.jpeg", "🏠 首页 · 一目了然的写作工作台"),
    ("创意工坊", "屏幕截图_26-7-2026_155821_localhost.jpeg", "💡 创意工坊 · 三库检索，AI 生成科幻设定"),
    ("资料管理", "屏幕截图_26-7-2026_155842_localhost.jpeg", "📁 资料管理 · 上传自动分类、索引、摘要"),
    ("大纲工坊", "屏幕截图_26-7-2026_16015_localhost.jpeg", "📋 大纲工坊 · 自动生成 7-10 章章节目录"),
    ("写作工坊", "屏幕截图_26-7-2026_1610_localhost.jpeg", "✍️ 写作工坊 · PRECHA 章节链 + AI 协作"),
    ("改写工坊", "屏幕截图_26-7-2026_16246_localhost.jpeg", "🔧 改写工坊 · 8 维度风格分析 + 智能改写"),
    ("文件详情", "屏幕截图_26-7-2026_16335_localhost.jpeg", "🤖 AI 摘要 · 点文件即看，支持下载"),
    ("搜索功能", "屏幕截图_26-7-2026_16426_localhost.jpeg", "🔍 全文搜索 · 中英文关键词秒查"),
    ("PRECHA 章节", "屏幕截图_26-7-2026_16437_localhost.jpeg", "📝 章节写作 · 叙事锚点保持长篇连贯"),
]


def create_intro():
    """开场标题卡片"""
    # 深色渐变背景
    bg = Image.new("RGB", (W, H), (15, 17, 23))
    bg_path = os.path.join(OUTPUT_DIR, "_intro_bg.png")
    bg.save(bg_path)

    clip = ImageClip(bg_path, duration=3)

    # Logo + 标题
    logo_path = os.path.join(PUBLIC_DIR, "基础形象.png")
    if os.path.exists(logo_path):
        logo = ImageClip(logo_path, duration=3).resized(width=300).with_position(("center", 500))
    else:
        logo = None

    title = TextClip(
        text="MyBookApps",
        font_size=80, color="white", font=FONT,
        size=(W, 200), text_align="center",
    ).with_position(("center", 850)).with_duration(3)

    subtitle = TextClip(
        text="AI 驱动的科幻写作助手",
        font_size=36, color="#9ca0b0", font=FONT,
        size=(W, 60), text_align="center",
    ).with_position(("center", 950)).with_duration(3)

    tagline = TextClip(
        text="知识库 · 参考库 · 风格库 · 三库联合创作",
        font_size=28, color="#6366f1", font=FONT,
        size=(W, 50), text_align="center",
    ).with_position(("center", 1050)).with_duration(3)

    layers = [clip, title, subtitle, tagline]
    if logo:
        layers.append(logo)
    return CompositeVideoClip(layers, size=(W, H))


def create_outro():
    """结尾 CTA"""
    bg = Image.new("RGB", (W, H), (15, 17, 23))
    bg_path = os.path.join(OUTPUT_DIR, "_outro_bg.png")
    bg.save(bg_path)

    clip = ImageClip(bg_path, duration=3)

    qr = TextClip(
        text="⭐ GitHub: han1254-google/MyBookWriter",
        font_size=30, color="#e4e6ed", font=FONT,
        size=(W, 60), text_align="center",
    ).with_position(("center", 900)).with_duration(3)

    cta = TextClip(
        text="让 AI 成为你的笔，不是你的代笔",
        font_size=42, color="#6366f1", font=FONT,
        size=(W, 80), text_align="center",
    ).with_position(("center", 1000)).with_duration(3)

    return CompositeVideoClip([clip, qr, cta], size=(W, H))


def resize_to_fit(img_path, target_w, target_h):
    """等比缩放图片以适应目标尺寸，不足部分填黑色"""
    img = Image.open(img_path)
    iw, ih = img.size

    # 计算缩放比例
    scale = min(target_w / iw, target_h / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # 居中贴到黑色画布上
    canvas = Image.new("RGB", (target_w, target_h), (15, 17, 23))
    x, y = (target_w - new_w) // 2, (target_h - new_h) // 2
    canvas.paste(img, (x, y))
    return canvas


def create_scene_clip(label, img_file, caption):
    """创建单个场景：截图 + 底部标题"""
    img_path = os.path.join(IMG_DIR, img_file)
    if not os.path.exists(img_path):
        print(f"  [!] 缺失: {img_path}")
        return None

    # 缩放图片到 1080×1920 范围内
    resized = resize_to_fit(img_path, W, H - 240)  # 留底部 240px 给文字
    tmp_path = os.path.join(OUTPUT_DIR, f"_tmp_{label}.png")
    resized.save(tmp_path)

    img_clip = ImageClip(tmp_path, duration=DURATION_PER_IMAGE)

    # 底部半透明标题栏
    title_bar = TextClip(
        text=caption,
        font_size=32, color="#e4e6ed", font=FONT,
        size=(W - 60, 80), text_align="center",
        bg_color=(26, 29, 39, 200),
    ).with_position(("center", H - 160)).with_duration(DURATION_PER_IMAGE)

    # 顶部功能名标签
    label_clip = TextClip(
        text=label,
        font_size=24, color="#6366f1", font=FONT,
        size=(200, 44), text_align="center",
    ).with_position((40, 30)).with_duration(DURATION_PER_IMAGE)

    return CompositeVideoClip([img_clip, title_bar, label_clip], size=(W, H))


def generate():
    print("=" * 50)
    print("  🎬 MyBookApps 宣传视频生成器")
    print("=" * 50)

    clips = []

    # 1. 开场
    print("\n[1/3] 生成开场...")
    clips.append(create_intro())

    # 2. 功能展示
    print(f"[2/3] 生成 {len(SCENES)} 个功能场景...")
    for label, img_file, caption in SCENES:
        clip = create_scene_clip(label, img_file, caption)
        if clip:
            clips.append(clip)
            print(f"  ✓ {label}")

    # 3. 结尾
    print("[3/3] 生成结尾...")
    clips.append(create_outro())

    # ---- 合成 ----
    print(f"\n🎞 合成中... ({len(clips)} 段, 竖屏 {W}×{H})")
    video = concatenate_videoclips(clips, method="compose")

    output_path = os.path.join(OUTPUT_DIR, "MyBookApps_promo.mp4")
    video.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="4000k",
        preset="medium",
        threads=4,
    )

    # 清理临时文件
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith("_tmp") or f.startswith("_intro") or f.startswith("_outro"):
            os.remove(os.path.join(OUTPUT_DIR, f))

    duration = len(clips) * DURATION_PER_IMAGE + 6  # 含首尾各3秒
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\n✅ 完成！")
    print(f"   文件: {output_path}")
    print(f"   时长: {duration} 秒")
    print(f"   大小: {size_mb:.1f} MB")
    print(f"   格式: 1080×1920 MP4 (可直接上传抖音)")


if __name__ == "__main__":
    generate()
