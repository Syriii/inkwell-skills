---
name: inkwell-capture
description: >
  Inkwell 剪藏技能。采集网页文章、论坛帖子、截图 OCR 和图片分析。
  **仅当用户明确要求采集、保存、剪藏、归档网页内容时触发**。
  如果对话上下文在讨论技能开发、采集策略或代码问题，留在本技能讨论，不跳转其他技能。
  用户给链接并明确要求讨论内容本身，采集完成后衔接 inkwell-write。
---

# inkwell-capture — 剪藏

接收用户提供的链接/文件，自动识别类型，**先评估再采集**，调用独立脚本处理，输出归档 Markdown 到 `archived/` 目录。

## 初始化

首次触发时检查项目初始化：

1. 检查 `.web-analysis.yaml` 是否存在
2. 不存在 → 创建目录结构 + 写入默认配置：
   ```
   mkdir -p archived topics published
   ```
   写入 `.web-analysis.yaml`：
   ```yaml
   project_name: <目录名>
   crawl_delay: 3
   domain_delays: {}
   comment_limit: 500
   forum_domains: []
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
| 不确定 | 以上都不是 | **阻塞询问**，必须等回答再继续 |

> **流程铁律**：任何需要用户确认/选择的问题，提出后**必须等待用户回答**才能继续。没有用户回答，绝对不能推进到下一步。
> **提问原则**：当采集过程中有多个待确认事项时，**逐个确认**，一次只问一个问题。带用户逐个解决完后再推进到下一步。不要一次性抛出多个问题让用户评估。

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
- `回答标题-slug` 由模型根据回答内容总结生成
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
- 每个回答的文件夹名由模型根据该回答内容总结
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
5. 调用 archiver.py 写入
6. FAISS 索引追加
7. 呈现结果

过程中遇到问题（评论超限、Cookie 缺失）**直接在对话中确认**，不需要 subagent 来回倒手。

#### Subagent 采集

当用户在做别的事时，启动 subagent 后台执行。其余情况使用 inline。

#### Subagent Prompt 模板

将以下内容作为 subagent 的 prompt，替换 `{url}`, `{采集类型}`, `{inkwell-search 状态}` 等占位符：

```
你是一个内容采集 agent。请按照以下流程采集并归档内容。

**❗ 重要规则**:
	1. 任何步骤失败都必须**立即返回明确的错误信息给主会话**，禁止静默卡住、禁止不返回结果。
	2. **禁止直接和用户交互**。遇到任何需要确认的问题（评论超限、Cookie 缺失、去重冲突、图片过多等），必须返回给主会话并**立即挂起**，等待主会话 resume 回传指令。永远不要反问用户，永远不要自己做决定。

**采集目标**: {url}
**采集类型**: {webpage / forum / image-ocr}
**Cookie 来源**: {从 .env 读取 / 无}
**工作目录**: {project_root}
**inkwell-search 状态**: {已安装 / 未安装}
**配置**: .web-analysis.yaml → crawl_delay={delay}, comment_limit={limit}

## 可用工具

Bash, Read, Write, Edit, Grep, Glob

## 执行流程

### 1. 执行采集脚本

根据采集类型选择脚本，在 {project_root} 目录下执行。

**普通网页 (webpage)**:
```
python .claude/skills/inkwell-capture/scripts/web_fetch.py "{url}"
```
失败时自动降级：
```
python .claude/skills/inkwell-capture/scripts/web_fetch_full.py "{url}"
```

**系统化降级与错误处理**：

| 失败场景 | 处理方式 |
|---------|---------|
| **403/401 需要登录** | 检查 .env 中有无该域名 Cookie → 已有则传入重试；无则返回错误给主会话，由主会话指导用户获取 Cookie（具体指导方式见主会话 Step 3 前的说明） |
| **网络超时/连接失败** | 重试一次，仍失败则返回明确错误，交给主会话询问用户是否继续重试或换方案 |
| **Cloudflare/人机验证** | 识别到验证页面 → 返回错误，建议使用 `--wait-for interaction` 让用户手动完成验证 |
| **页面内容为空（疑似反爬）** | 检测到空内容 → 返回错误，说明疑似反爬，提供手动复制方案 |
| **Playwright 未安装/浏览器下载失败** | 返回错误，说明"建议使用 MCP Playwright fallback"，交给主会话处理 |
| **网站改版/选择器失效** | 脚本解析失败 → 返回错误，提示需要更新选择器，建议手动提取 |
| **其他错误（内容过短）** | 自动降级到 web_fetch_full.py → 仍失败则返回错误 + 手动方案建议 |

**论坛帖子 (forum)**:
```
python .claude/skills/inkwell-capture/scripts/forum_scraper.py "{url}"
```
- 采集前先检测评论总数 → 如果预估评论数 > comment_limit → 返回给主会话，询问用户："检测到约 N 条评论，超过限制 {comment_limit}。是否：(1)继续采集（截断到限制）/ (2)提高评论限制 / (3)只采集主帖不采评论"

**截图 OCR (image-ocr)**: 使用 ocr_text.py 或直接在对话中分析图片内容。

脚本输出 JSON（stdout），包含 type, source, date, author, body, word_count, images 等字段。

### 2. 验证采集结果

检查脚本输出：
- body 为空或 word_count < 50 → 尝试降级脚本
- body 中存在 `data:` URI 图片引用（如 `![](data:image/svg+xml;utf8,<svg...)`）→ 用 regex 清除：`re.sub(r'!\[[^\]]*\]\(data:[^)]*\)\s*\n?', '', body)`。这是 lazy-load 占位符，会破坏 Markdown 渲染器。脚本已做自动清理，此检查作为兜底
- 所有脚本都失败 → 返回错误：`❌ 采集失败：[url]` + 原因 + 手动方案建议
- 论坛评论数 > comment_limit → 备注"评论数超阈值，已截断"

### 3. 去重检查

**精确匹配**：扫描 archived/ 中所有 .md 文件的 source 字段
```bash
grep -rl "source: {url}" archived/
```
- 匹配到 → 返回 "⚠️ 链接已于 YYYY-MM-DD 采集过 (archived/.../)。请主会话决定：覆盖 / 跳过？"
- 未匹配 → 继续

**语义去重**（仅 inkwell-search 已安装时）：
```bash
cd {project_root}
python inkwell-skills/inkwell-search/scripts/searcher.py search --granularity doc --top-k 1 --threshold 0.95 --query "{title + summary}"
```
- 相似度 ≥ 0.95 → 返回 "⚠️ 发现高度相似内容：[path]，相似度 {score}。请主会话决定是否仍然归档。"
- 语义去重不阻塞归档，仅作提示

### 4. 图片下载

如果脚本输出的 images 数组非空：
- 1-2 张 → 自动下载到 archived/YYYYMMDD/{slug}/images/
- 3+ 张 → 报告数量，不自动下载（由主会话决定）

### 5. 生成理解字段

**category 和 tags 是必填字段，必须基于 body 内容生成，不得留空。**

1. **title** — 文章标题（脚本已提取则优先使用）
2. **category** — 粗粒度分类。先扫描已有分类作为参考：
   ```bash
   grep -rh "^category:" archived/ topics/ 2>/dev/null | sort | uniq -c | sort -rn | head -20
   ```
   如无历史分类，从以下默认分类中选择最匹配的一个：**社会、科技、政治、经济、文化、教育、生活、娱乐、健康、体育**。
   论坛帖子注意：脚本输出的 body 中可能包含版块名（如 NGA 帖子顶部有版块路径），优先据此推断 category。
3. **tags** — 2-4字标签，至少 2 个，最多 5 个。先扫描已有标签作为参考：
   ```bash
   grep -rh "tags:" archived/ topics/ 2>/dev/null | tr ',' '\n' | sort | uniq -c | sort -rn | head -30
   ```
4. **summary** — 1-2 句中文内容摘要

**写入前校验**：调用 archiver.py 前，确认：
- category 不为空，且不为「未分类」
- tags 数组至少包含 2 个标签
- 如不满足 → 重新生成，不得跳过

### 6. 写入归档

组装完整 JSON（合并脚本输出 + 生成的字段）：
```json
{
  "type": "...",
  "source": "...",
  "date": "...",
  "author": "...",
  "body": "...",
  "word_count": N,
  "images": [...],
  "title": "...",
  "category": "...",
  "tags": ["...", "..."],
  "summary": "..."
}
```

调用 archiver.py：
```bash
cd {project_root}
python .claude/skills/inkwell-capture/scripts/archiver.py --json '<json>'
```

archiver.py 自动创建 archived/YYYYMMDD/{slug}/ 目录并写入 `{slug}.md`。

如果 inkwell-search 已安装，追加 FAISS 索引：
```bash
cd {project_root}
python inkwell-skills/inkwell-search/scripts/indexer.py index --path "web-analysis/archived/YYYYMMDD/{slug}/{slug}.md" --text "{title + summary + tags + body 前 500 字}"
```

### 7. 返回结果

采集完成，返回以下格式的摘要：

```
✅ 已归档：[title]
   📁 archived/YYYYMMDD/{slug}/
   🏷 {category} | {tags}
   📝 {summary}
   📝 字数: {word_count}

[有图片] 🖼 已下载 N 张图片
[有警告] ⚠️ 注意事项：...
```

失败时返回：
```
❌ 采集失败：[url]
   原因：{错误信息}
   建议：{降级方案}
```
```

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
  "tags": ["AI", "政策"],
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
publish:
  hugo_root: ""
  obsidian_root: ""
```

## 目录结构

```
{project}/
├── .web-analysis.yaml
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
