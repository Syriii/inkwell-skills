---
name: inkwell-capture
description: >
  Inkwell 剪藏技能。当用户发送链接、要求保存/存档/采集网页内容、收集论坛帖子、截图OCR时触发。
  即使用户没用「采集」这个词（如「帮我把这篇存下来」「这个页面归档一下」），
  只要意图是保存网页内容为 Markdown，就应该触发此技能。
  如果对话在讨论技能开发或代码问题，留在本技能；内容采集完成后可衔接 inkwell-write 讨论。
---

# inkwell-capture — 剪藏

接收用户提供的链接/文件，自动识别类型，**先评估再采集**，调用独立脚本处理，输出归档 Markdown 到 `archived/` 目录。

## 初始化

首次触发时检查项目初始化：

1. 检查 `.web-analysis.yaml` 是否存在
2. 不存在 → 创建目录结构 + 写入默认配置：
   ```
   mkdir -p archived topics published inbox
   ```
   写入 `.web-analysis.yaml`：
   ```yaml
   project_name: <目录名>
   crawl_delay: 3
   domain_delays: {}
   comment_limit: 500
   forum_domains: []
   inbox_cleanup: keep_dir
   publish:
     hugo_root: ""
     obsidian_root: ""
   ```
3. 询问 Hugo/Obsidian 路径（可跳过）
4. 检查 inkwell-search 是否已安装（可选，`ls .claude/skills/inkwell-search/`）
5. 创建 `总览.md`（Obsidian Dataview 仪表盘）：
   - 检查项目根目录是否存在 `总览.md`
   - 不存在 → 从 `.claude/skills/inkwell-capture/references/dashboard-template.md` 复制到 `总览.md`
   - 提醒用户：需要安装 Obsidian Dataview 插件，在阅读模式（`Cmd+E`）下使用

## 执行流程

### Step 1: 检查初始化
- `.web-analysis.yaml` 存在 → 继续
- 不存在 → 执行初始化

### Step 1.5: 检查 inkwell-search
- 检查 `.claude/skills/inkwell-search/` 是否存在
- 已安装 → 后续去重和索引走 inkwell-search
- 未安装 → 跳过语义去重和索引追加，精确去重仍生效

### Step 2: 识别输入类型

用户输入 → 判断类型：

| 输入 | 判断条件 | 处理 |
|------|---------|------|
| URL + 完全已知（域名+结构已沉淀规则） | 匹配「已沉淀的域名规则」中的 URL 模式 | 直接按规则执行，跳过评估 |
| URL + 已知域名但结构不确定 | 域名在规则中，但 URL 模式不匹配 | 进入 **Step 2.5 前置网页评估** |
| URL + 未知域名/疑似论坛 | 域名不在任何沉淀规则中 | 进入 **Step 2.5 前置网页评估** |
| .png/.jpg/.jpeg 截图 | 文件扩展名 | **阻塞询问**：图片类还是文字类？必须等回答再继续 |
| 图片类截图 | 用户选图片类 | 检查模型多模态支持 → **对话中分析** |
| 文字类截图 | 用户选文字类 | `ocr_text.py` |
| 用户要求处理媒体文件（无具体路径） | 用户说「帮我分析几张图」「处理这个视频」等 | 进入 **inbox 入口** 流程 |
| 不确定 | 以上都不是 | **阻塞询问**，必须等回答再继续 |

> **流程铁律**：任何需要用户确认/选择的问题，提出后**必须等待用户回答**才能继续。没有用户回答，绝对不能推进到下一步。
> **提问原则**：当采集过程中有多个待确认事项时，**逐个确认**，一次只问一个问题。带用户逐个解决完后再推进到下一步。不要一次性抛出多个问题让用户评估。
> **安装铁律**：任何 `brew install`、`pip install`、`apt` 等系统级或项目级安装命令，执行前**必须征得用户明确同意**。告知：(1) 要装什么、它是干什么的 (2) 为什么当前场景需要它 (3) 大概多大。禁止未经同意自动安装。

### inbox 入口（媒体文件中转）

当用户要处理图片、视频等媒体文件，但没有给出具体路径时，使用 `inbox/` 目录作为统一入口。

> **数据安全铁律**：inbox 中的源文件是用户的原始数据。归档未完成、源文件未确认保存到 `archived/` 之前，**绝对禁止**清理 inbox。丢失用户数据是不可接受的。

1. **确保 inbox 存在**：检查项目根目录是否有 `inbox/`，没有则创建
2. **告知用户**：「把文件放到 `inbox/` 目录，放好后告诉我。」**阻塞等待**用户确认
3. **扫描文件**：`ls inbox/` 列出所有文件，向用户确认：「检测到 N 个文件：[列表]。需要：(1) 提取文字/OCR (2) 视觉分析理解 (3) 两者都要？」
4. **逐文件处理**：
   - 图片 → `Read` 工具视觉分析，或 `ocr_text.py` 提取文字
   - 视频 → `Read` 工具逐帧分析（Claude 只能处理视频的关键帧，如需完整逐帧分析需用户提前用 ffmpeg 拆帧）
   - 混合时按文件类型自动匹配处理方式
5. **汇总结果**：呈现分析结果，询问是否需要归档为 Markdown
6. **归档（可选）**：如果用户要保存分析结果：
   - 写入 Markdown 到 `archived/YYYYMMDD/{slug}/{slug}.md`
   - **将 inbox 中的源文件复制到** `archived/YYYYMMDD/{slug}/images/`（而非移动——源文件仍需保留在 inbox 直到验证完成）
   - 确认 `archived/YYYYMMDD/{slug}/images/` 中文件完整且可读
7. **验证归档完整性**：确认以下条件全部满足后，才能进入清理步骤：
   - `archived/YYYYMMDD/{slug}/{slug}.md` 存在且内容完整
   - 源文件已复制到 `archived/YYYYMMDD/{slug}/images/`，数量、大小与 inbox 一致
   - 不满足时立即报告用户，**禁止继续**，**禁止清理 inbox**
8. **清理**：验证通过后，根据 `.web-analysis.yaml` 中 `inbox_cleanup` 配置：
   - `keep_dir`（默认）：`rm inbox/*` 只清文件，保留目录
   - `remove_dir`：`rm -rf inbox/` 删除整个目录
9. **不复盘档案**：如果用户选择不归档，询问是否仍要清理 inbox 中的源文件，**阻塞等待**用户确认后才能清理

后续新增媒体类型（PDF、音频等）也统一走 inbox 入口，无需修改流程。

### Step 2.5: 前置网页评估（模型驱动）

当页面结构不确定时：

1. **轻量抓取梗概**：先用 L1 抓取获取主要内容文本（不用全量渲染）
2. **模型分析结构**：基于抓取内容判断：
   - 内容类型：单篇文章 / 单个回答 / 整个问题（多回答） / 帖子+评论区 / 列表页 / 图片集 / 其他
   - 内容规模：大约字数、评论数预估
   - 一句话摘要：内容主题是什么
3. **给出建议方案**：根据分析结果，推荐最合适的采集方式（仅采正文 / 采正文+评论 / 全问题采集 / 等等）
4. **分步询问**：
   - 先报告分析结果：结构 + 规模 + 主题
   - 然后只问一个问题："建议[AA采集方案]。是否按此方案采集？"
   - 用户说"调整"或"讨论"时再展开
   - 不要把所有选项（方案/评论数/Cookie/图片）一次性全问
5. **沉淀规则**：讨论确定的最佳实践，更新到下方的「**已沉淀的域名规则**」中，下次同类 URL 自动套用，跳过评估

### 已沉淀的域名规则

以下规则经讨论确认，遇到匹配的 URL 模式时**直接按规则执行**，不再走 Step 2.5 评估。

#### 知乎 (zhihu.com)

**URL 模式识别**：

| URL 模式 | 含义 | 采集范围 |
|---------|------|---------|
| `/question/{id}/answer/{aid}` 或 `/answer/{id}` | 单个回答 | 仅该回答正文 + 评论区，目录名为模型总结的回答标题 |
| `/question/{id}` | 整个问题 | **询问用户**：全部回答 / 前 N 个高赞？是否含评论？ |

`/answer/{id}` 会自动重定向到 `/question/{qid}/answer/{aid}`，问题上下文永远可用。

**目录结构模板**：

1. **单回答** (`/answer/{id}`)：
```
archived/YYYYMMDD/{回答标题-slug}/
├── {回答标题-slug}.md          # 回答正文，frontmatter 含问题来源和作者
├── comments.md                 # 该回答评论区
└── images/                     # 该回答图片
```
- `回答标题-slug` 由模型根据回答内容总结生成，**必须为中文**（禁止拼音/英文）
- 作者名写入文档 frontmatter 而非目录名

2. **全问题** (`/question/{id}`)：
```
archived/YYYYMMDD/{问题名称-slug}/
├── {问题名称-slug}.md          # 问题概览（标题、描述、标签、数据）
├── {回答1标题-slug}/
│   ├── {回答1标题-slug}.md     # 回答正文，frontmatter 含作者
│   ├── comments.md
│   └── images/
├── {回答2标题-slug}/
│   └── ...
```
- `问题名称-slug` 从问题标题生成
- 每个回答的文件夹名由模型根据该回答内容总结，**必须为中文**
- 每个回答独立文件夹，正文、评论、图片隔离
- 评论区上限由 `comment_limit` 控制（默认 500 条），超过时先询问用户

### Cookie 获取指导

采集需要登录的站点时，不要只是说"请参考 cookie-guide.md"。应当：

1. **告知用户**需要哪个域名的 Cookie、为什么需要（看到什么错误）
2. **分步指导**：告诉用户具体操作步骤（打开浏览器 → F12 → Application → Cookies → 找到对应域名 → 复制关键字段）
3. **给出 pastebin/AirDrop 等便捷方式建议**

详细获取指南在 `references/cookie-guide.md` 中，但副 agent 返回错误时主会话应主动展示获取步骤，而非让用户自己去看文档。

### Step 3: 执行采集

根据用户意图选择执行方式：

| 场景 | 用户状态 | 执行方式 |
|------|---------|---------|
| **单链接，用户等着采完** | 用户明确要求采集，在等结果 | **inline** — 主会话直接跑脚本采集归档，有问题当场解决 |
| **讨论中提到链接，顺便采集** | 用户在讨论其他事，提了一嘴采集 | **subagent** — 后台采，不打断当前讨论 |
| **批量采集多个链接** | 用户给了多个链接要采集 | **subagents 并行** — 每个链接独立 subagent，同时跑 |
| **用户说"看看这个"** | 用户想先了解内容，不一定归档 | **inline 轻量预览** — 只抓取内容展示，不归档。确认要存再走采集流程 |

**核心判断标准**：用户是不是在等结果。等 → inline；在做事 → subagent。

#### Inline 采集

主会话直接执行：

1. 运行采集脚本（web_fetch.py / web_fetch_full.py / forum_scraper.py）
2. 去重检查
3. 图片下载
4. 生成字段
5. **规范审查**（Step 5.5 清单逐项检查）
6. 调用 archiver.py 写入
7. FAISS 索引追加
8. 呈现结果

过程中遇到问题（评论超限、Cookie 缺失）**直接在对话中确认**，不需要 subagent 来回倒手。

#### Subagent 采集

当用户在做别的事时，启动 subagent 后台执行。其余情况使用 inline。

#### Subagent Prompt 模板

Subagent 的完整指令见 `references/subagent-prompt.md`。使用时替换其中的 `{url}`, `{采集类型}`, `{inkwell-search 状态}` 等占位符，将完整内容作为 prompt 传入。

#### Subagent 配置

- **subagent_type**: 不指定，使用默认的 general-purpose agent
- **description**: 简短描述如 "采集 {url 或标题}"
- Cookie 处理：subagent 可以 Read .env 文件读取已存储的 Cookie
- Playwright：优先使用**本地 Python Playwright**（`web_fetch_full.py`）。如果本地 Chromium 安装失败（网络问题），降级使用 **MCP Playwright** 完成渲染。
- 图片分析和字段生成：subagent 具备 Claude 能力，可以直接完成
- **错误反馈**：任何失败（采集失败、安装失败、需要用户交互）都必须**返回明确的错误信息和建议方案**给主会话，禁止静默卡住。

### Step 4: 呈现结果

Subagent 完成后，将结果展示给用户。

- **成功** → 显示归档摘要
  - 如果用户之前明确要求讨论内容 → 自动衔接 inkwell-write
  - 如果用户目的不明确 → 询问"要讨论这篇内容吗？"，确认后再衔接
- **失败** → 显示错误信息和建议方案，**等待用户指示下一步**（不能跳过询问直接重试）
- **多个待确认事项** → **逐个确认**，一次只问一个问题。例如 subagent 返回了"需要 Cookie"和"评论超限"两个问题，先确认 Cookie，解决后再确认评论数。不要批量呈现。
- **批量采集** → 汇总所有 subagent 的结果，报告成功/失败数量
- **去重提示** → 如果 subagent 返回了去重警告，**让用户决定覆盖/跳过**，必须等待用户回答

```
✅ 已归档：[title]
   📁 archived/YYYYMMDD/{slug}/
   🏷 {category} | {tags}
   📝 {summary}

要讨论这篇吗？（衔接 inkwell-write）
```

### Step 5.5 规范审查（写入前必须逐项通过）

归档不是一次性操作——格式错误会在后续阅读、搜索、跨平台渲染时反复暴露。以下清单覆盖了最常见的坑，**调用 archiver.py 之前逐项过一遍，不通过不写入。**

| # | 检查项 | 规则 | 为什么 | 不通过示例 |
|---|--------|------|--------|-----------|
| 1 | **slug 语言** | 中文，禁止拼音/纯英文 | 拼音 slug 无法被搜索、不可读 | ❌ `jandan-ed-zhensuo` → ✅ `去三甲医院看ED的经历` |
| 2 | **slug 与 title** | 单篇内容 slug=title；知乎回答等复合场景可不同 | 单篇时区分两者无意义，反而增加维护负担 | — |
| 3 | **category** | 不为空，不为「未分类」，中文 | 英文 category 破坏 Dataview 分组一致性 | ❌ `lifestyle` → ✅ `生活` |
| 4 | **tags** | 中文为主，每标签 2-4 字，禁止纯英文 | 英文标签在 Obsidian 图谱中与其他中文标签脱节 | ❌ `[health, marriage]` → ✅ `[男性健康, 婚姻]` |
| 5 | **title** | 中文为主（英文缩写可接受），禁止纯英文 | Wave/Obsidian 按标题排序时，中英混杂排序混乱 | ❌ `My ED Clinic Visit` |
| 6 | **summary** | 1-2 句中文，禁止纯英文 | 搜索索引依赖 summary 的语义质量 | ❌ `A man visited ED clinic...` |
| 7 | **body 图片** | 无 `data:image/` URI 引用残留 | 破坏 Wave 等 Markdown 渲染器 | ❌ `![](data:image/svg+xml;utf8,<svg)` |
| 8 | **目录名** | 与 slug 一致 | 不一致时引用路径断裂 | — |

## 脚本接口约定

- CLI 参数接收输入
- stdout 输出 JSON
- stderr 输出错误
- 退出码 0 = 成功，非 0 = 失败

脚本输出（阶段一，纯机械数据）：
```json
{
  "type": "webpage",
  "source": "https://...",
  "date": "2025-03-01",
  "author": "",
  "body": "# 标题\n\n正文...",
  "word_count": 3500,
  "images": [{"url": "https://...", "path": "images/..."}]
}
```

Claude Code 补充后（阶段二）：
```json
{
  "type": "webpage",
  "source": "https://...",
  "date": "2025-03-01",
  "author": "",
  "body": "# 标题\n\n正文...",
  "word_count": 3500,
  "images": [{"url": "https://...", "path": "images/..."}],
  "title": "文章标题",
  "category": "科技",
  "tags": ["人工智能", "政策解读"],
  "summary": "一句话摘要..."
}
```

## 配置

`.web-analysis.yaml`：
```yaml
project_name: web-analysis
crawl_delay: 3
domain_delays:
  xiaohongshu.com: 5
comment_limit: 500
forum_domains: []
inbox_cleanup: keep_dir   # keep_dir | remove_dir — 处理完后只清文件还是删整个目录
publish:
  hugo_root: ""
  obsidian_root: ""
```

## 目录结构

```
{project}/
├── .web-analysis.yaml
├── inbox/                        ← 媒体文件中转入口
├── archived/YYYYMMDD/{slug}/
│   ├── {slug}.md
│   └── images/
└── .claude/skills/inkwell-capture/
    ├── SKILL.md
    ├── scripts/
    │   ├── web_fetch.py
    │   ├── web_fetch_full.py
    │   ├── forum_scraper.py
    │   ├── ocr_text.py
    │   ├── archiver.py
    │   └── requirements.txt
    └── references/
        ├── frontmatter-schema.md
        ├── content-types.md
        ├── error-handling.md
        └── dashboard-template.md
```

> **目录日期规则**：`YYYYMMDD` 是**采集日期**（当天你什么时候存的），不是文章发布日期。文章发布日期保存在 frontmatter 的 `date` 字段。
> 目录是你的操作日志——「哪天存了什么」，不是内容时间线。
