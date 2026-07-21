---
name: clip
description: >
  Inkwell 剪藏技能。采集网页文章、论坛帖子、截图 OCR 和图片分析。
  当用户发送链接、截图、提及"采集""抓取""剪藏""归档""OCR"时触发。
  也适用于用户分享文章要讨论、保存参考材料、或需要从网页提取内容时。
---

# clip — 剪藏

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
4. 检查 thread 是否已安装（可选，`ls .claude/skills/thread/`）

## 执行流程

### Step 1: 检查初始化
- `.web-analysis.yaml` 存在 → 继续
- 不存在 → 执行初始化

### Step 1.5: 检查 thread
- 检查 `.claude/skills/thread/` 是否存在
- 已安装 → 后续去重和索引走 thread
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

### Step 3: 执行采集 + 降级

**网页抓取降级链（自动，不中断）：**
```
web_fetch.py (requests + trafilatura)
  ↓ 失败（状态码错误/超时/内容为空）
web_fetch_full.py (Playwright 渲染)
  ↓ 失败
告知用户降级方案：
  - 手动复制全文粘贴
  - 截全页滚动图 → OCR
  - 尝试 archive.org / Google Cache
```

**OCR 降级链（自动）：**
```
ocr_text.py (PaddleOCR)
  ↓ 质量差（置信度低 + KenLM 困惑度高）
告知用户可尝试 Surya 或手动处理
```

**批量采集时报告进度：**
- "第 N/M 个，正采集 [标题或链接]，已完成 ✓/✗"

**评论阈值检查：**
- 论坛/评论区回复数 > 500（config 中 comment_limit）→ 询问用户：全部保留 / 截断？

### Step 4: 内容去重检查

**精确匹配（始终生效）：**
- 扫描 `archived/` 中所有 article.md 的 frontmatter `source` 字段
- 同 URL → "这个链接已于 YYYY-MM-DD 采集过。更新 / 跳过？"
  - 更新 → 调 thread 的 `compare` 比较新旧内容（阈值 0.85）
    - ≥ 0.85 → 覆盖原 article.md，索引原地更新
    - < 0.85 → 建议新建归档，based_on 关联旧条目
  - 跳过 → 终止

**语义去重（thread 已安装时）：**
- 调 thread 的 `searcher.py search --granularity doc --top-k 1 --threshold 0.95`
- 相似度 ≥ 0.95 → "发现高度相似内容：[path]。关联 / 跳过？"
- 仅建议，用户决定

### Step 5: 图片采集

网页内发现图片时：
- 1-2 张 → 自动下载到 `images/`
- 3-20 张 → "发现 N 张图片，要下载吗？"
- 20+ 张 → "这篇有 N 张图片。都下载 / 只看正文 / 你来选？"

下载使用 `requests`，保存到 `archived/YYYYMMDD/{slug}/images/`。

### Step 6: 生成理解字段

Claude Code 阅读脚本输出的 body，生成：

1. **title** — 文章标题
2. **category** — 粗粒度分类，优先复用已有分类（grep `category:` 扫描 archived/ 和 topics/）
3. **tags** — 细粒度标签（2-4字为主），优先复用已有标签（grep `tags:` 扫描 archived/ 和 topics/）
4. **summary** — 1-2 句内容摘要

**确认策略**：批量采集默认自动确认，仅异常时提醒。

### Step 7: 写入归档

将脚本输出 + Claude Code 生成的字段合并为完整 JSON，传入 archiver.py：

```bash
python scripts/archiver.py --json '<json>'
```

archiver.py 负责：
- 根据采集日期创建 `archived/YYYYMMDD/{slug}/` 目录
- slug 由 Claude Code 从 title 生成
- 写入 `article.md`（YAML frontmatter + Markdown body）
- 下载图片到 `images/`

如果 thread 已安装，追加索引：
```bash
python ../thread/scripts/indexer.py index --path "<path>" --text "<title + summary + tags + body>"
```
（跨 skill 调用 thread 的索引脚本）

### Step 8: 呈现结果 → 衔接讨论创作

```
✅ 已归档：[title]
   📁 archived/YYYYMMDD/{slug}/
   🏷 {category} | {tags}
   📝 {summary}

要讨论这篇吗？（衔接 forge Skill）
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
└── .claude/skills/clip/
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
