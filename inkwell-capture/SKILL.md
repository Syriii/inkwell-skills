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
| URL + 完全已知（域名+结构已沉淀规则） | 匹配启发式规则 | 直接转下一步采集 |
| URL + 已知域名但结构不确定 | 域名已知，但 URL 结构可能对应多种采集方式 | 进入 **Step 2.5 前置网页评估** |
| URL + 未知域名/疑似论坛 | 看起来像论坛/问答但不在列表，或域名从未遇到 | 进入 **Step 2.5 前置网页评估** |
| .png/.jpg/.jpeg 截图 | 文件扩展名 | **阻塞询问**：图片类还是文字类？必须等回答再继续 |
| 图片类截图 | 用户选图片类 | 检查模型多模态支持 → **对话中分析** |
| 文字类截图 | 用户选文字类 | `ocr_text.py` |
| 不确定 | 以上都不是 | **阻塞询问**，必须等回答再继续 |

> **流程铁律**：任何需要用户确认/选择的问题，提出后**必须等待用户回答**才能继续。没有用户回答，绝对不能推进到下一步。

### Step 2.5: 前置网页评估（模型驱动）

当页面结构不确定时：

1. **轻量抓取梗概**：先用 L1 抓取获取主要内容文本（不用全量渲染）
2. **模型分析结构**：基于抓取内容判断：
   - 内容类型：单篇文章 / 单个回答 / 整个问题（多回答） / 帖子+评论区 / 列表页 / 图片集 / 其他
   - 内容规模：大约字数、评论数预估
   - 一句话摘要：内容主题是什么
3. **给出建议方案**：根据分析结果，推荐最合适的采集方式（仅采正文 / 采正文+评论 / 全问题采集 / 等等）
4. **询问用户确认**：
   > "分析结果：这是[XX结构]，预估[YY规模]，内容主题[ZZ]。建议[AA采集方案]。是否按建议采集？还是调整方案？还是先讨论？"
5. **沉淀规则**：讨论确定的最佳实践，更新启发式规则，下次同类 URL 自动套用，跳过评估

### Step 3: Dispatch 采集 Subagent

使用 Agent 工具启动一个 subagent，将实际的采集、处理、归档工作委托给它。这允许采集在后台并行执行，不影响主会话的讨论。

**单个链接：** 创建一个 subagent

**多个链接：** 为每个链接创建独立的 subagent 并行执行，或为一个 subagent 提供批量指令。并行 subagent 更快，但批量 subagent 可以共享去重和标签扫描结果。

#### Subagent Prompt 模板

将以下内容作为 subagent 的 prompt，替换 `{url}`, `{采集类型}`, `{inkwell-search 状态}` 等占位符：

```
你是一个内容采集 agent。请按照以下流程采集并归档内容。

**❗ 重要规则**: 任何步骤失败（采集失败、安装失败、网络超时）都必须**立即返回明确的错误信息给主会话**，禁止静默卡住、禁止不返回结果。

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
| **403/401 需要登录** | 检查 .env 中有无该域名 Cookie → 已有则传入重试；无则返回错误，提示用户需要登录，并指导参考 `.claude/skills/inkwell-capture/references/cookie-guide.md` 获取 Cookie |
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
