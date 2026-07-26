# MyBookApps — 科幻写作助手

知识库驱动的 AI 辅助科幻创作平台。五个功能模块覆盖从资料管理到成文改写的完整写作流程。

## 设计思路

### 一、创作理念：AI 是工具，不是代笔

市面上大多数 AI 写作工具试图替代作者——输入一个标题，输出一篇文章。MyBookApps 反其道而行。

它面向的是一个**有自己声音的作者**。这位作者已经形成了成熟的写作风格（第一人称观察者视角、具体数字承载情感、自嘲式幽默、环形结构……），不需要 AI 替他思考，需要的是 AI 在他思考时递上正确的资料、在他卡住时给出符合他审美的建议、在他写完后用他自己的标准审视文本。

因此，平台的核心设计原则是：

- **作者始终在循环中**。AI 生成 → 作者审阅 → 同意/对话修改 → 才会进入下一环节。不存在"一键成书"。
- **知识库是作者的延伸书架**。不是搜互联网，而是搜你自己筛选过的论文、参考作品和风格样本。
- **风格是注入的，不是学习的**。不靠 few-shot 让模型猜你的风格，而是把完整的写作规范写进每一个 system prompt。

适用场景：科幻中长篇创作，需要对科学设定有严谨性要求、对叙事风格有明确坚持的作者。

### 二、架构哲学：三库分离 + 本地 RAG

**为什么三库分离？**

知识库、参考库、风格库——三种资料的性质截然不同，混在一起既不利于检索，也不利于 prompt 设计：

| 库 | 性质 | 在 prompt 中的角色 |
|---|------|------------------|
| 知识库 | 科学事实 | "请以以下科学知识为基础，确保设定科学合理" |
| 参考库 | 他人创意 | "以下创意供你参考叙事方式和构思角度" |
| 风格库 | 写作特征 | "请在行文中融入这些风格特征" |

如果混在一起，模型无法区分"这是需要遵循的事实"和"这是可以参考的文风"，prompt 的指令就会互相打架。三库分离让每个库在 prompt 中有明确的角色定位。

**为什么本地 RAG 而不是联网搜索？**

1. **隐私**：创作中的稿件、个人风格样本、筛选过的参考资料——这些不应该离开本地。
2. **可控**：知识库里是作者亲自筛选过的论文，而不是搜索引擎返回的 SEO 垃圾。RAG 检索到的是你信任的来源。
3. **速度**：BGE-M3 嵌入模型（4.3GB）跑在本机 RTX 3060 上，查询延迟 <100ms，迭代写作时不打断心流。
4. **离线**：不依赖外部 API 即可完成知识检索，只有 AI 生成环节才需要 DeepSeek。

技术选型：`ChromaDB` 持久化向量存储 → `BGE-M3` 本地嵌入 → `sentence-transformers` 加载模型。索引一次，查询无数次，增量更新只处理新文件。

### 三、PRECHA 系统：章节间的叙事锚点

长篇写作最大的技术挑战不是"写出一章"，而是**让第 7 章和第 3 章之间的人物、时间、伏笔保持一致**。

PRECHA 是一个结构化的章节交接协议，名字取自七个维度的首字母：

| 维度 | 含义 | 示例 |
|------|------|------|
| **P**rechaName | 上一章名称 | "CHA3 第一次塌方" |
| **R**echaLink | 文件链接 | CHA3.md |
| 时间（**E**） | 章节时间线 | Sol-147，进入木卫二轨道第 3 天 |
| 地点（**C**） | 场景位置 | 轨道站"海妖"号气闸舱 |
| 人物（**H**） | 出场角色 | 我、老周（工程师）、AI"中郎将" |
| 起（**A**） | 触发事件 | 收到地面指令，需出舱检修 |
| 经（**P**） | 关键经过 | 出舱时发现舱外有异常生物痕迹 |
| 结（**R**） | 章末状态 | 返回舱内，生物痕迹照片已传地面 |
| 媒（**M**） | 核心意象 | 黑暗中闪烁的蓝色荧光 |

每章生成时，系统自动将上一章的 PRECHA 信息注入 system prompt。AI 知道"故事进展到哪了、人物在哪、上一章结尾是什么情绪"，而不是从空白开始。作者审阅通过后，系统从正文中提取本章的 PRECHA，传递给下一章。

这本质上是一个**外置的叙事记忆系统**——用结构化数据弥补 LLM 在长文本中的注意力衰减。

### 四、写作风格注入：把风格写进 prompt，而不是让模型猜

作者的个人风格经过 6 篇作品（约 9.6 万字）的系统性分析，提炼为一份 **写作风格指南**（12 条禁令 + 13 条正例），包含：

- 叙事视角：第一人称观察者，永远向下修正自我评价
- 语言节奏：长句铺陈、短句截断，高雅与世俗瞬时切换
- 细节原则：具体数字 > 抽象形容词，"不说等了很久，说从一点半等到五点"
- 情感处理：不煽情，写动作和物件，让读者自己哭
- 幽默机制：自我解嘲，永远拿自己开刀
- 结构原则：环形结构，意象呼应而非过渡句
- 结尾法则：落在画面/动作上，不落在道理上

这份指南以 `WRITING_STYLE_GUIDE` 常量的形式注入到**每一个** system prompt 中——无论是生成创意、大纲、章节还是改写。这不是 few-shot 示例，而是作为硬性规范，要求模型的每次输出都照此自检。

为什么不做 fine-tuning？因为风格是活的——作者在成长，风格在演变。改一份指南比重新训练一个模型轻量得多。而且风格指南本身是可读的，作者可以随时修改某一条，所有后续生成立即生效。

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

上传 PDF / EPUB / DOCX / TXT / MD 文件到三个资料库，上传前可选择目标库。上传后 AI 自动建议子文件夹名。

- **知识库**：科学论文、科普资料 → RAG 检索时作为"科学事实依据"
- **参考库**：文学作品、他人创意 → RAG 检索时作为"叙事参考"
- **风格库**：风格独特的作品 → 上传后 AI 自动提取风格特征（叙事视角、语言节奏、情感处理等），RAG 检索时作为"风格启发"

支持拖拽上传、文件夹浏览、删除。

### 二、创意工坊 (`/ideas`)

1. 输入写作提示词
2. 系统三库联合检索：**知识库**搜科学事实 → **参考库**搜叙事参考 → **风格库**搜风格启发
3. 构建分层 prompt（领域知识 / 参考创意 / 风格启发各有明确角色）
4. DeepSeek 结合三库 + 写作风格指南生成完整科幻设定
5. 底部对话栏可继续追问修改，流式输出
6. 满意后保存到数据库，在历史列表中可查看和继续编辑

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
