# MyBookApps — 科幻写作助手

知识库驱动的 AI 辅助科幻创作平台。五个功能模块覆盖从资料管理到成文改写的完整写作流程。

## 吉祥物：墨仔（InkBot）

<img src="frontend/public/基础形象.png" width="160" align="right" alt="墨仔">

一只巴掌大的 3D 小机器人，App 的形象代言人。灵感来自老式打字机 + 小书架。

- **头**：圆球 + 圆角方形屏幕，用像素字符做表情
- **身体**：竖起来的精装书造型，书脊纹理 + 烫金边
- **手臂**：金属关节，左手磁吸钢笔头、右手小夹子
- **腿**：迷你坦克履带（Wall-E 风格）
- **颜色**：暖灰白 + 墨绿点缀 + 胸口金色电源灯

墨仔出现在 App 的各个角落——首页打招呼、加载时翻书、空状态摊手、成功后欢呼、出错时冒烟。

### 场景图鉴

| 图片 | 场景 | 触发时机 |
|------|------|---------|
| ![](frontend/public/首页%20Hero.png) | **首页 Hero** | Dashboard 顶部横幅 |
| ![](frontend/public/空状态.png) | **空状态** | 创意列表空、大纲列表空、资料库空、章节未生成 |
| ![](frontend/public/加载中.png) | **生成中** | 创意 / 大纲 / 章节流式生成时 |
| ![](frontend/public/搜索中.png) | **检索中** | RAG 知识库查询 |
| ![](frontend/public/创意完成.png) | **创意出炉** | 创意生成完毕 |
| ![](frontend/public/上传成功.png) | **上传成功** | 文件上传 + AI 分类完成 |
| ![](frontend/public/章节保存.png) | **章节保存** | 章节审批通过保存 |
| ![](frontend/public/错误.png) | **出错了** | API 调用失败 |
| ![](frontend/public/404.png) | **404** | 页面未找到 |

### 表情包

| 写完了 | 查到了 | 不是我 | 天哪 | 还行吧 | 无力吐槽 |
|--------|--------|--------|------|--------|---------|
| ![](frontend/public/表情包-写完了.png) | ![](frontend/public/表情包-查到了.png) | ![](frontend/public/表情包-不是我.png) | ![](frontend/public/表情包-天哪.png) | ![](frontend/public/表情包-还行吧.png) | ![](frontend/public/表情包-无力吐槽.png) |

表情包用于 Toast 通知弹窗：成功 → 写完了、信息 → 查到了、错误 → 出错了。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS |
| 路由 | react-router-dom v6 |
| 状态管理 | Zustand |
| Markdown | react-markdown + remark-gfm |
| 后端 | Flask + SQLAlchemy + SQLite |
| AI | DeepSeek v4-pro（Anthropic 兼容端点，SSE 流式） |
| RAG | ChromaDB + BGE-M3（复用已有 `knowledge_rag/`） |

## 快速启动

```bash
# 1. 安装依赖
cd mybookapps
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 2. 启动 Flask API（终端1）
python app.py
# → http://localhost:5000/api

# 3. 启动前端开发服务器（终端2）
cd frontend && npm run dev
# → http://localhost:5173（自动代理 /api → Flask）

# 4.（可选）构建知识库索引
cd .. && python knowledge_rag/build_index.py
```

生产模式：`cd frontend && npm run build`，Flask 会自动服务 `frontend/dist/` 下的静态文件。

## 功能模块

### 一、资料管理 (`/upload`)

上传 PDF / EPUB / DOCX / TXT / MD 文件到三个资料库：

- **知识库**：科学论文、科普资料（接入 RAG 检索）
- **参考库**：文学作品、参考文献
- **风格库**：个人写作样本、风格参考

上传后 DeepSeek 自动分析文件名和内容摘要，决定归入哪个库的哪个子文件夹（如 `大气生物/`、`法律法规/`）。支持拖拽上传、文件夹浏览、删除。

### 二、创意工坊 (`/ideas`)

1. 输入写作提示词（可选按知识库分类过滤）
2. 系统自动 RAG 检索 `知识库/` 中的相关科学资料
3. DeepSeek 结合知识库 + 写作风格指南生成完整科幻设定（标题、核心概念、世界观、角色、主题、开篇构想）
4. 底部对话栏可继续追问修改，流式输出
5. 满意后保存到数据库，可在历史列表中查看和继续编辑

### 三、大纲工坊 (`/outlines`)

- **从创意生成**：选择已保存的创意，自动 RAG 检索 → DeepSeek 生成 7-10 章大纲
- **从零开始**：直接写场景描述生成大纲
- 每章标题渲染为超链接 → 点击跳转写作工坊
- 对话栏修改 + 保存到数据库

### 四、写作工坊 (`/writing`)

核心写作引擎，三栏布局：

```
┌─────────────┬──────────────────┬──────────┐
│ 左侧：上下文  │  中间：章节编辑器   │ 右侧：对话 │
│ IDEA + 大纲  │  PRECHA 模板      │ AI 协作  │
│ 章节列表     │  Markdown 渲染    │ 流式聊天  │
│ 导航        │  生成/同意按钮     │          │
└─────────────┴──────────────────┴──────────┘
```

**PRECHA 章节链**：

- 每章生成时自动带上章的时间/地点/人物/起因/经过/结果/媒（核心意象）
- 第 N 章生成时注入第 N-1 章的 PRECHA 信息 → 保持叙事连续性
- 叙述者知识范围截止于当前章时间点，禁止"预知"未来章节

**操作流程**：

1. 选择大纲进入写作页
2. 点击"生成第一章"→ 流式输出 → 审阅
3. 点击"同意"保存 → 自动导航到下一章
4. 继续生成 → 审阅 → 同意，循环至终章
5. 随时可通过右侧对话栏与 AI 讨论修改当前章
6. 导出全书为 Markdown

### 五、改写工坊 (`/rewrite`)

1. 粘贴文章
2. 点击"分析文章"→ DeepSeek 从叙事视角、语言节奏、细节数字、情感处理、幽默运用、对话质量、结尾方式、写作禁令 8 个维度打分 + 给出优缺点和建议
3. 点击"开始改写"→ 流式输出改写后的全文
4. 支持额外要求（如"加强自嘲"、"缩短对话"）
5. 一键复制改写结果

## 数据库

SQLite 单文件 `data/mybookapps.db`，四张表：

| 表 | 用途 | 关键字段 |
|---|---|---|
| `ideas` | 创意设定 | title, content, chat_history(JSON), knowledge_context(JSON) |
| `outlines` | 故事大纲 | idea_id(FK), title, content, chat_history(JSON) |
| `chapters` | 章节 | outline_id(FK), chapter_number, precha_name/link/content, status(draft/completed) |
| `library_files` | 上传文件追踪 | library_type, folder_name, original_filename, stored_path |

## API 路由速查

所有 API 前缀 `/api`，SSE 流式响应 `text/event-stream`。

### 上传
```
POST   /api/upload              # 上传文件 → DeepSeek 分类
GET    /api/libraries            # 库结构 + 文件列表
DELETE /api/libraries/<id>       # 删除文件
```

### 创意
```
POST   /api/ideas/generate      # RAG + DeepSeek 生成（SSE）
POST   /api/ideas/chat/<id>     # 对话修改（SSE）
POST   /api/ideas/save           # 保存
GET    /api/ideas                # 列表
GET    /api/ideas/<id>           # 详情
DELETE /api/ideas/<id>           # 删除
```

### 大纲
```
POST   /api/outlines/generate   # 生成（SSE）
POST   /api/outlines/chat/<id>  # 对话修改（SSE）
POST   /api/outlines/save        # 保存
GET    /api/outlines             # 列表
GET    /api/outlines/<id>        # 详情
DELETE /api/outlines/<id>        # 删除
```

### 写作
```
POST   /api/writing/start        # 从大纲生成第一章（SSE）
POST   /api/writing/chapter      # 生成下一章（SSE）
POST   /api/writing/chat/<id>    # 对话修改当前章（SSE）
POST   /api/writing/save         # 保存章节
GET    /api/writing/chapters/<outline_id>  # 章节列表
POST   /api/writing/export/<outline_id>    # 导出全书 Markdown
```

### 改写
```
POST   /api/rewrite/analyze      # 8维度风格分析
POST   /api/rewrite/rewrite      # 改写（SSE）
```

## 数据流

```
创意生成：用户提示 → RAG(知识库) → +写作风格 → DeepSeek(SSE) → 对话修改 → SQLite

章节写作：IDEA + 大纲 + 前章PRECHA + RAG + 风格 → DeepSeek(SSE) → 审阅同意 → SQLite → 下一章

文件分类：文件 → 提取前500字 → DeepSeek(库类型?子文件夹?) → 存储 + SQLite
```

## 写作风格注入

所有生成调用均携带 `WRITING_STYLE_GUIDE`（从项目根 `CLAUDE.md` 提取），包含叙事视角、语言节奏、细节数字、情感处理、幽默、对话、结构、结尾、12条写作禁令等完整规范。

## 目录结构

```
mybookapps/
├── app.py                  # Flask 入口
├── app_config.py           # 配置（API密钥、路径、风格指南）
├── database.py             # ORM 模型
├── requirements.txt
├── services/               # 业务逻辑层
│   ├── deepseek_service.py # DeepSeek Anthropic 兼容客户端
│   ├── rag_service.py      # RAG 检索封装
│   ├── file_service.py     # 文件文本提取
│   └── library_service.py  # 库管理 + DeepSeek 分类
├── routes/                 # API 路由层
│   ├── api_upload.py
│   ├── api_ideas.py
│   ├── api_outlines.py
│   ├── api_writing.py
│   └── api_rewrite.py
├── frontend/               # React SPA
│   ├── public/             # 静态资源（墨仔图片等）
│   └── src/
│       ├── api/client.ts   # SSE + REST 客户端
│       ├── store/          # Zustand
│       ├── components/     # Layout/ChatWidget/StreamOutput/Toast
│       └── pages/          # 8个页面 + NotFound
├── imgs/                   # 墨仔原始图片（Gemini 生成）
├── libraries/              # 上传文件
│   ├── 知识库/
│   ├── 参考库/
│   └── 风格库/
└── data/mybookapps.db      # SQLite
```
