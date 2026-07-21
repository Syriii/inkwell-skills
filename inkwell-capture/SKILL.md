---
name: inkwell-capture
description: >
  Inkwell capture — 网页采集、爬虫、截图 OCR、图片分析。
  当用户发送链接、截图、提及"采集""抓取""爬虫""归档""OCR""保存网页"时触发。
---

# inkwell-capture

接收用户提供的链接/文件，自动识别类型，调用独立脚本处理，输出归档 Markdown 到 `archived/` 目录。

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

| 输入 | 判断条件 | 处理脚本 |
|------|---------|---------|
| URL + 已知论坛域名 | domain 在 forum_domains 列表中 | `forum_scraper.py` |
| URL + 普通网页 | 非论坛域名 | `web_fetch.py`（L1） |
| URL + 疑似论坛 | 看起来像论坛但不在列表 | **询问用户确认** → 确认后加入 forum_domains |
| .png/.jpg/.jpeg 截图 | 文件扩展名 | **阻塞询问**：图片类还是文字类？ |
| 图片类截图 | 用户选图片类 | 检查模型多模态支持 → **对话中分析** |
| 文字类截图 | 用户选文字类 | `ocr_text.py` |
| 不确定 | 以上都不是 | **阻塞询问** |

### Step 3: Dispatch 采集 Subagent

使用 Agent 工具启动一个 subagent，将实际的采集、处理、归档工作委托给它。这允许采集在后台并行执行，不影响主会话的讨论。

**单个链接：** 创建一个 subagent

**多个链接：** 为每个链接创建独立的 subagent 并行执行，或为一个 subagent 提供批量指令。并行 subagent 更快，但批量 subagent 可以共享去重和标签扫描结果。

#### Subagent Prompt 模板

将以下内容作为 subagent 的 prompt，替换 `{url}`, `{采集类型}`, `{inkwell-search 状态}` 等占位符：

```
你是一个内容采集 agent。请按照以下流程采集并归档内容。

**采集目标**: {url}
**采集类型**: {webpage / forum / image-ocr}
**Cookie 来源**: {从 .env 读取 / 无}
**工作目录**: /Users/xiesh/writing/web-analysis
**inkwell-search 状态**: {已安装 / 未安装}
**配置**: .web-analysis.yaml → crawl_delay={delay}, comment_limit={limit}

## 可用工具

Bash, Read, Write, Edit, Grep, Glob

## 执行流程

### 1. 执行采集脚本

根据采集类型选择脚本，在 /Users/xiesh/writing/web-analysis 目录下执行。

**普通网页 (webpage)**:
```
conda run -n web-analysis python .claude/skills/inkwell-capture/scripts/web_fetch.py "{url}"
```
失败时自动降级：
```
conda run -n web-analysis python .claude/skills/inkwell-capture/scripts/web_fetch_full.py "{url}"
```
降级链：403/401 → 检查 .env 中的域名 Cookie，通过 --cookie 参数传入 → 仍失败则返回错误。其他错误（超时/内容为空）→ 自动降级到 web_fetch_full.py → 仍失败则返回手动方案建议。

**论坛帖子 (forum)**:
```
conda run -n web-analysis python .claude/skills/inkwell-capture/scripts/forum_scraper.py "{url}"
```

**截图 OCR (image-ocr)**: 使用 ocr_text.py 或直接在对话中分析图片内容。

脚本输出 JSON（stdout），包含 type, source, date, author, body, word_count, images 等字段。

### 2. 验证采集结果

检查脚本输出：
- body 为空或 word_count < 50 → 尝试降级脚本
- 所有脚本都失败 → 返回错误：`❌ 采集失败：[url]` + 原因 + 手动方案建议
- 论坛评论数 > comment_limit → 备注"评论数超阈值，已截断"

### 3. 去重检查

**精确匹配**：扫描 archived/ 中所有 article.md 的 source 字段
```bash
grep -rl "source: {url}" archived/ --include="article.md"
```
- 匹配到 → 返回 "⚠️ 链接已于 YYYY-MM-DD 采集过 (archived/.../)。请主会话决定：覆盖 / 跳过？"
- 未匹配 → 继续

**语义去重**（仅 inkwell-search 已安装时）：
```bash
cd /Users/xiesh/writing
conda run -n web-analysis python inkwell-skills/inkwell-search/scripts/searcher.py search --granularity doc --top-k 1 --threshold 0.95 --query "{title + summary}"
```
- 相似度 ≥ 0.95 → 返回 "⚠️ 发现高度相似内容：[path]，相似度 {score}。请主会话决定是否仍然归档。"
- 语义去重不阻塞归档，仅作提示

### 4. 图片下载

如果脚本输出的 images 数组非空：
- 1-2 张 → 自动下载到 archived/YYYYMMDD/{slug}/images/
- 3+ 张 → 报告数量，不自动下载（由主会话决定）

### 5. 生成理解字段

基于脚本输出的 body 内容，生成：

1. **title** — 文章标题（脚本已提取则优先使用）
2. **category** — 粗粒度分类，扫描已有分类作为参考：
   ```bash
   grep -h "^category:" archived/**/article.md topics/**/*.md 2>/dev/null | sort | uniq -c | sort -rn | head -20
   ```
3. **tags** — 2-4字标签，3-5 个，扫描已有标签作为参考：
   ```bash
   grep -h "tags:" archived/**/article.md topics/**/*.md 2>/dev/null | tr ',' '\n' | sort | uniq -c | sort -rn | head -30
   ```
4. **summary** — 1-2 句中文内容摘要

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
cd /Users/xiesh/writing/web-analysis
conda run -n web-analysis python .claude/skills/inkwell-capture/scripts/archiver.py --json '<json>'
```

archiver.py 自动创建 archived/YYYYMMDD/{slug}/ 目录并写入 article.md。

如果 inkwell-search 已安装，追加 FAISS 索引：
```bash
cd /Users/xiesh/writing
conda run -n web-analysis python inkwell-skills/inkwell-search/scripts/indexer.py index --path "web-analysis/archived/YYYYMMDD/{slug}/article.md" --text "{title + summary + tags + body 前 500 字}"
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
- Playwright：subagent 使用本地的 Playwright（web_fetch_full.py），不需要 MCP browser
- 图片分析和字段生成：subagent 具备 Claude 能力，可以直接完成

### Step 4: 呈现结果

Subagent 完成后，将结果展示给用户。

- **成功** → 显示归档摘要，询问"要讨论这篇吗？（衔接 inkwell-write）"
- **失败** → 显示错误信息和建议方案，询问是否手动处理
- **批量采集** → 汇总所有 subagent 的结果，报告成功/失败数量
- **去重提示** → 如果 subagent 返回了去重警告，让用户决定覆盖/跳过

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
│   ├── article.md
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
        └── error-handling.md
```
