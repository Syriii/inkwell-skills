# 采集 Skill 设计

## 概述

web-analysis 四个独立 Skill 之一：**采集（Collect）**。接收用户提供的链接/文件，自动识别类型，调用独立脚本处理，输出归档 Markdown 文件到项目目录。

### 四个独立 Skill 的关系

四个 Skill 平级独立，按需安装，存在分级关联（非层级依赖）：

| Skill | 独立运行 | 关联 |
|-------|:---:|------|
| 检索 Retrieval | ✅ 完全独立 | 不需要任何其他 Skill |
| 采集 Collect | ✅ 独立（无检索时每次当新内容） | **可选**关联检索（语义去重） |
| 讨论创作 Discuss-Create | ❌ 需检索 | **必须**装检索（auto-inject ≥0.75） |
| 发布 Publish | ✅ 完全独立 | 无关联 |

Skill 之间不互相调用；用户编排。数据目录（`archived/`、`topics/`）是共享的**文件约定**。`based_on` 是可选溯源标记。检索 Skill 独立管理语义索引（`.retrieval-index/`），不绑 web-analysis 业务字段。

> 本文档为采集 Skill 的设计。检索 Skill 设计见独立文档。

---

## 一、项目结构

### 1.1 数据目录（Project）

```
web-analysis/                          ← 项目根
├── .web-analysis.yaml                 ← 项目配置
├── archived/                          ← 采集归档
│   ├── YYYYMMDD/
│   │   └── {slug}/                    ← 每条采集 = 一个子目录
│   │       ├── article.md             ←   主文件（入口）
│   │       ├── images/                ←   下载的图片（按需）
│   │       ├── videos/                ←   下载的视频（未来）
│   │       └── attachments/           ←   其他文件（PDF 等，未来）
├── topics/                            ← 讨论+创作（讨论创作 Skill 管理）
├── published/                         ← 成品文章
```

**约定**：`article.md` 是每条采集的唯一入口，附件按类型分目录。有就有，没有就不建。

### 1.2 配置文件

`.web-analysis.yaml`，仅存储必要配置，其余使用内置默认值：

```yaml
project_name: web-analysis    # 自动取自目录名
crawl_delay: 3                # 全局默认，同域名采集间隔（秒）
domain_delays:                # 可选，按域名覆盖（值更保守时生效）
  xiaohongshu.com: 5
comment_limit: 500            # 回复数超过此值时询问用户是否截断
forum_domains: []             # 边用边积累，确认后自动加入
publish:
  hugo_root: ""               # 首次初始化时确认
  obsidian_root: ""           # 可选
```

### 1.3 凭证与模型配置

所有敏感信息和可变配置集中在 `.env` 文件（不入 git）：

```bash
# .env — 不入 git
# 凭证
ZHIHU_COOKIE="z_c0=xxx..."
FORUM_TOKEN="xxx"
WECHAT_MP_COOKIE="xxx"

# 模型
WEB_ANALYSIS_MODELS_DIR=/Users/xiesh/Codes/models
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

脚本启动时检查凭证：
- 有效 → 正常使用
- 过期 / 缺失 → 提醒用户在终端自行更新

### 1.4 模型管理

采集 Skill 使用以下模型，统一存放在 `/Users/xiesh/Codes/models/` 下：

```
/Users/xiesh/Codes/models/
├── ocr/
│   ├── PaddleOCR/             # PaddleOCR 模型（~500MB）
│   └── kenlm/                 # KenLM 语言模型（~30MB，OCR 质量评估用）
└── embedding/                 # 检索 Skill 管理，采集不直接加载
    └── bge-small-zh-v1.5/
```

- OCR 模型首次运行时自动下载，之后永久缓存
- Embedding 模型由检索 Skill 管理，采集不直接加载

### 1.5 依赖管理

Skill 启动时自动检查 Python 版本和必要包：

```
检查 Python ≥ 3.12 → 检查 requirements.txt 中的包 → 缺失时提示安装
```

检查是环境无关的——不依赖特定的包管理器（conda/venv/pip），只验证运行环境是否满足要求。

> 注：本地开发使用 conda 环境（见 CLAUDE.md），但 Skill 本身不依赖 conda。

### 1.6 初始化

首次触发采集 Skill 时自动执行：
1. 检查 `.web-analysis.yaml` 是否存在
2. 不存在 → 创建 `archived/`、`topics/`、`published/` 目录 + 写入默认配置
3. 仅询问 Hugo/Obsidian 路径（可跳过）

---

## 二、Skill 结构

### 2.1 目录

```
collect/
├── SKILL.md                  ← 触发描述 + 工作流指令
├── scripts/                  ← 独立脚本
│   ├── web_fetch.py          #   L1：requests + trafilatura
│   ├── web_fetch_full.py     #   L2：Playwright 渲染
│   ├── forum_scraper.py      #   论坛帖子 + 评论树
│   ├── ocr_text.py           #   文字截图 → PaddleOCR + KenLM 评估
│   ├── archiver.py           #   共享：统一归档写入
│   └── requirements.txt      #   trafilatura, playwright, paddleocr, etc.
└── references/               ← 按需加载
    ├── frontmatter-schema.md
    ├── content-types.md
    └── error-handling.md
```

### 2.2 触发描述

```
采集网页文章、论坛帖子、截图 OCR 和图片分析。当用户发送链接、截图、
提及"采集""抓取""归档""记录下来""分析这张图""OCR"时触发。也适用于
用户分享文章要讨论、保存参考材料、或需要从网页提取内容时。
```

### 2.3 执行流程

```
Step 1: 检查项目初始化（.web-analysis.yaml）
    ↓
Step 1.5: 检查检索 Skill 是否已安装（可选）
    → 已安装 → 后续去重和索引可走检索 Skill
    → 未安装 → 跳过语义去重和索引追加，精确去重仍生效
    ↓
Step 2: 识别输入类型
    → URL + 已知论坛域名（.web-analysis.yaml forum_domains）→ forum_scraper.py
    → URL + 普通网页 → web_fetch.py
    → 看起来像论坛但不在已知列表 → 询问用户确认 → 确认后自动加入 forum_domains
    → .png/.jpg 截图 → 阻塞询问：图片类还是文字类？
        → 图片类 → 检查模型多模态支持 → 对话中分析
        → 文字类 → ocr_text.py
    → 不确定 → 阻塞询问
    ↓
Step 3: 执行采集 + 降级（按降级链自动处理，不中断）
	    → 单条：采集完成后简要报告
	    → 批量：持续报告进度（当前第 N/M 个，正采集 {链接或文件名}，已完成 ✓/✗）
	    → 论坛/评论区回复数超过阈值（默认 500）→ 询问用户全部保留还是截断
    ↓
Step 4: 内容去重检查
    → source 精确匹配 → "这个链接已采集过，更新还是跳过？"
    → （检索 Skill 已安装时）语义相似度 > 0.95 → "发现高度相似内容，关联还是跳过？"
    → 不阻塞，仅提示
    ↓
Step 5: 图片采集（网页内发现图片时）
    → 1-2 张 → 自动下载到 images/
    → 3-20 张 → "发现 N 张图片，要下载吗？"
    → 20+ 张 → "这篇有 N 张图片，都下载 / 只看正文 / 你来选？"
    ↓
Step 6: Claude Code 生成理解字段
    → 读取脚本输出的 body，浏览已有 category 和 tags 列表
    → 生成 title、category、tags、summary，合并到脚本 JSON
    → 传给 archiver.py
    ↓
Step 7: archiver.py 写入归档 → （检索 Skill 已安装时）调检索 Skill 追加索引
    ↓
Step 8: 呈现结果（标题、分类、标签、摘要）→ 默认自动确认 → 仅异常时提醒 → 询问"要讨论这篇吗？"（衔接讨论创作 Skill）
```

---

## 三、去重策略

### 3.1 source 精确匹配

采集前检查 `source` 字段是否已存在：
- 同一 URL / 同一文件 hash → "这个来源已于 YYYY-MM-DD 采集过，更新内容还是跳过？"
- 选择更新 → 调检索 Skill `compare`（新旧文本直接比较，strategy='auto'）
    - 相似度 ≥ 0.85 → 变化不大，覆盖原 `article.md`，清空旧 `images/` 后重新下载，检索 Skill 索引原地更新
    - 相似度 < 0.85 → 变化较大，建议新建一条归档，通过 `based_on` 关联旧条目（保护已有引用的完整性）
- 跳过：终止本次采集

### 3.2 语义相似度（需检索 Skill）

- 相似度 ≥ 0.95 → "发现高度相似的内容：[path]。作为新归档 / 跳过？"
- 相似度 < 0.95 → 不提示，正常归档

两个检查都只做**建议**，最终由用户决定。未安装检索 Skill 时跳过高层次的语义检查，仅做 source 精确匹配。

---

## 四、错误降级策略

### 4.1 网页抓取（三级）

```
web_fetch.py (requests) → 成功 ✓
    ↓ 失败
web_fetch_full.py (Playwright) → 成功 ✓
    ↓ 失败
告知用户 + 备选方案：
  - 手动复制全文粘贴
  - 截全页滚动图 → OCR
  - 尝试 archive.org / Google Cache
```

### 4.2 图片处理

#### 文字类截图（OCR 链）

```
PaddleOCR → OCR 质量评估通过 → 继续
    ↓ 质量差 (置信度低 + KenLM 困惑度高)
Surya → 成功 ✓
    ↓ 失败
Claude Code 对话中直接看图提取文字
    ↓ 当前模型不支持多模态
告知用户："当前模型不支持图片分析，建议切换模型"
```

**OCR 质量评估**：PaddleOCR 置信度 + KenLM 困惑度双重信号。
- 两个信号都差 → 自动降级
- 单一信号异常 → 标记提醒但不降级

#### 图片类（照片/图表）

```
→ 检查 Claude Code 当前模型是否支持多模态
    → 支持 → 直接在对话中分析
    → 不支持 → "当前模型不支持图片分析，建议切换模型"
```

图片分析不经过脚本，由 SKILL.md 工作流处理。

---

## 五、归档格式

### 5.1 存储结构

```
archived/YYYYMMDD/{slug}/
    ├── article.md           ← 主文件
    ├── images/              ← 下载的配图 / 原始截图（按需）
    ├── videos/              ← 下载的视频（未来）
    └── attachments/         ← PDF 等附件（未来）
```

- 目录日期使用采集日期（`fetched_at`）
- 纯文字内容无附件时仅有 `article.md`

### 5.2 Frontmatter 规范

```yaml
---
date: 2025-03-01            # 原文发布日期，无可为空；为空时等于 fetched_at
source: "https://..."       # 必填，原始 URL / 文件名 / manual-{timestamp}（粘贴文本）
type: webpage               # 必填，开放枚举：webpage|forum|screenshot_ocr|screenshot_multimodal|pdf|chat_export|social_media|...，按需扩展
category: 科技              # 必填，粗粒度分类，一篇一个；Claude Code 生成，列表动态增长
tags: [AI政策, 开源, 芯片]   # 必填，细粒度标签，一篇多个；Claude Code 生成
title: "..."                # 必填，Claude Code 生成
summary: "..."              # 必填，Claude Code 生成 1-2 句
author: "..."               # 可选
word_count: 3500            # 可选
fetched_at: 2026-07-16T...  # 必填，采集时间戳
original_image: "images/original.png"  # 截图/图片类采集时记录原始文件路径
---
```

### 5.3 分类与标签

采用**两层结构**，均由 Claude Code 在 Skill 工作流中生成：

**分类（category）**——粗粒度，一篇一个，列表动态增长：
- 第一篇文章出现新领域时自动创建分类，不预设完整列表
- 示例：科技、社会、生活、游戏、创作、性别
- Claude Code 生成前浏览已有分类列表（扫描 `archived/` 和 `topics/`），优先复用；确需新建时才加

**标签（tags）**——细粒度，一篇多个：
- 2–4 字为主，最长不超过 8 字
- 相同概念用同一个标签名（如已有"开源"，不要再新建"开源软件"）
- 优先使用已有标签，避免为单篇文章创建一次性标签
- 来源自带的标签（小红书、知乎等）仅作参考，不直接采用；Claude Code 根据正文重新总结
- 生成前先浏览已有标签列表（通过 grep 扫描 `archived/` 和 `topics/` 的 frontmatter tags 字段）

**确认策略**：批量采集时默认自动确认，不逐个确认；仅在检测到重复、置信度低、采集失败等异常时提醒用户。

### 5.4 论坛内容格式

论坛帖子以一体式 Markdown 存储，正文 + 全部评论写入同一个 `article.md`：

```markdown
# 大家怎么看 Rust 的未来

**楼主 @张三** · 2026-07-15 14:30

> Rust 这几年发展很快...

---

**@李四** · 2026-07-15 15:20 · 👍 42

我觉得短期内不会...

> 引用 @王五: Rust 的学习曲线...

---

**@王五** · 2026-07-15 14:45

Rust 的学习曲线还是太陡了
```

---

## 六、跨 Skill 关联

### 6.1 based_on 字段

所有讨论、创作内容通过 frontmatter 的 `based_on` 字段显式关联上游。路径为相对于项目根目录的路径：

```yaml
# topics/ai-regulation/discussion/欧盟AI法案讨论总结.md
based_on:
  - archived/20260715/欧盟AI法案/article.md
  - archived/20260720/深度求索开源声明/article.md
tags: [AI政策, 开源]
```

```yaml
# topics/ai-governance/creation/article.md
based_on:
  - topics/ai-regulation/discussion/欧盟AI法案讨论总结.md
  - topics/sora-lawsuit/discussion/Sora版权讨论总结.md
  - archived/20260715/欧盟AI法案/article.md
tags: [AI政策, 开源, 版权]
```

### 6.2 数据流

```
archived/  ──引用→  topics/{slug}/discussion/  ──引用→  topics/{slug}/creation/  ──→  published/
                                                  ↑                                  基于草稿发布
                                  检索 Skill 语义检索（讨论创作刚需，采集可选）
```

### 6.3 三个约定

1. **引用不复制**：使用文件路径引用，不复制内容
2. **检索 Skill 共享**：检索 Skill 独立管理语义索引（`.retrieval-index/`），归档、讨论等所有内容统编入一个索引，由检索 Skill 统一管理
3. **标签贯穿**：从采集到发布全程保留

---

## 七、语义检索（检索 Skill）

语义索引和检索由独立的**检索 Skill** 统一管理，采集 Skill 可选用。

### 7.1 关系

| 检索 Skill | 采集 Skill |
|-----------|-----------|
| 管理 `.retrieval-index/`（doc.index + chunk.index） | 不管理索引，只调接口 |
| 提供 `index`、`search`、`compare`、`rebuild` | 归档后调 `index` 追加；采集前调 `search` 去重；更新时调 `compare` 比较 |
| 不知道 frontmatter、tags、category | 拼好文本传给检索：`title + summary + tags + 正文` |
| 默认搜索阈值 0.75 | 采集去重用更高阈值（0.85 更新判定 / 0.95 高度相似） |

### 7.2 采集对检索的使用

- **去重**：调检索 Skill `search`（文档级），传入待采集内容的拼接文本，拿到最相似文档 + 分数
- **追加**：归档后调检索 Skill `index`，传入 `(path, title+summary+tags+正文)`
- 未安装检索 Skill → 跳过上述两步，仅做 source 精确匹配

### 7.3 无检索时

采集 Skill 独立运行完全正常——每次采集当新内容处理，精确去重（URL/文件名）仍生效。缺失的只是语义去重和语义索引能力。详见检索 Skill 设计文档。

---

## 八、浏览与检索

### 8.1 首选：Obsidian

归档格式（Markdown + frontmatter + 标签）原生兼容 Obsidian：
- 标签面板：按标签聚合内容
- 图谱视图：基于标签和链接的关系图
- 全文搜索：Ctrl/Cmd + P
- 将项目目录作为 Obsidian Vault 打开即可

### 8.2 备选：命令行

```bash
rg "tags:.*AI政策" archived/ topics/   # 按标签搜（grep frontmatter）
rg "category: 科技" archived/ topics/   # 按分类搜
```
语义搜索通过检索 Skill 完成。

### 8.3 未来：轻量 Web 面板

作为可选增强，后期实现。

---

## 九、脚本接口约定

### 9.1 统一规范

- CLI 参数接收输入
- stdout 输出 JSON
- stderr 输出错误
- 退出码 0 = 成功，非 0 = 失败

### 9.2 脚本接口约定

**阶段一：采集脚本 → stdout（纯机械数据）**

脚本只负责提取，不做内容理解：

```json
{
  "type": "webpage",
  "source": "https://example.com/eu-ai-act",
  "date": "2025-03-01",
  "author": "张三",
  "body": "# 欧盟 AI 法案最终解读\n\n正文...",
  "word_count": 3500,
  "images": [
    {"url": "https://example.com/img/chart.png", "path": "images/chart.png"}
  ],
  "ocr_quality": {                        // 可选，仅 OCR 脚本输出
    "paddle_confidence": 0.87,
    "kenlm_perplexity": 45.2,
    "verdict": "ok"                      // ok | degraded | poor
  }
}
```

**阶段二：Claude Code 补充 → archiver.py 写入（完整归档）**

Claude Code 读完 body 后生成理解字段，合并写入：

```json
{
  // ...继承阶段一全部字段...,
  "title": "欧盟 AI 法案最终解读",        // Claude Code 生成
  "category": "科技",                    // Claude Code 生成
  "tags": ["AI政策", "科技法规", "欧盟"], // Claude Code 生成
  "summary": "欧盟议会正式通过 AI 法案..." // Claude Code 生成
}
```

**职责分界**：脚本负责采集（提取、下载、OCR），Claude Code 负责理解（标题、分类、标签、摘要）。

### 9.3 归档后目录示例

```
archived/20260716/eu-ai-act/
    ├── article.md
    └── images/
        └── chart.png
```

---

## 十、技术选型

| 层 | 选择 | 理由 |
|----|------|------|
| 语言 | Python | OCR/爬虫生态最强 |
| 正文提取 | `trafilatura` | 中文优化，支持论坛，结构化输出 |
| 爬虫 L1 | `requests` + `trafilatura` | 轻快，直接 HTTP |
| 爬虫 L2 | `playwright`（Python） | JS 渲染，环境已装 |
| OCR 主力 | `PaddleOCR` | 中文识别好 + 版面分析（~500MB） |
| OCR 降级 | `Surya` | 更强但需 PyTorch（~2GB） |
| OCR 质量评估 | PaddleOCR 置信度 + `KenLM` | 轻量统计，~30MB |
| 图片多模态 | Claude Code 视觉能力 | 不写脚本，SKILL.md 流程处理 |
| 语义检索 | 检索 Skill（可选安装） | Embedding + FAISS 由检索 Skill 管理，采集不内置 |
| 模型目录 | `/Users/xiesh/Codes/models/` | 统一管理 |
| 归档 | Markdown + YAML frontmatter | Obsidian 兼容，人类可读 |
| 凭证管理 | `.env` 文件 | 过期提醒手动更新 |

---

## 十一、边界与不做的事

### 11.1 内容类型边界

**全部支持输入**，处理方式因类型而异：

| 类型 | 采集方式 | 备注 |
|------|---------|------|
| 网页文章 | web_fetch / web_fetch_full | 正文不截断，全量保留 |
| 论坛帖子 | forum_scraper | 回复超阈值询问用户 |
| 截图（文字类） | OCR 链 | PaddleOCR → Surya → Claude vision |
| 截图（图片类） | Claude Code 视觉分析 | 不经过脚本 |
| PDF/报告 | OCR + 文本提取 | 按需处理 |
| 聊天记录导出 | 直接归档 | 用户提供文件 |
| 社交媒体单条 | 按平台适配 | 优先中文平台 |

### 11.2 平台边界

全部在范围内，**优先中文平台**（知乎、微信公众号、微博、V2EX、贴吧等），英文平台（Twitter/X、Reddit、HackerNews）后续适配。

### 11.3 付费墙/登录墙

- **登录态内容**：cookie 能解决的，通过 `.env` 注入，已覆盖
- **付费订阅内容**（知识星球、小报童、Medium Member）：不做
- **企业内部系统**：视为登录墙，cookie 能通就通

### 11.4 采集频率

- 同域名默认间隔 3 秒，可按域名覆盖
- 同时支持进度报告：批量采集时报告"第 N/M 个，正采集 [标题]，已完成 ✓/✗"

### 11.5 内容长度

- **正文**：不限长度，全量保留
- **论坛/评论区**：回复数超过阈值（默认 500）→ 询问用户全部保留还是截断

### 11.6 失败处理与断点续采

```
采集中断 → 保留已完成步骤的临时记录

重试时：
  → 轻量请求检查内容是否有变化（回复总数 / 楼层 ID / 最后时间）
  → 内容未变 → 跳过已完成步骤，从断点继续
  → 内容已变 → 全量重采（不拼旧数据）
  → 临时记录超过 1 小时 → 直接全量重采
```

### 11.7 反爬层级

| 层级 | 典型场景 | 当前 | 远期 |
|------|---------|:---:|:---:|
| L1-L3 | 静态页面、JS 渲染、简单频率限制 | ✅ 已覆盖 | — |
| 登录墙 | 知乎全文（cookie 注入） | ✅ .env 支持 | — |
| 浏览器指纹 | 小红书、部分论坛 | ⬜ | 可加 playwright-stealth |
| Cloudflare 盾 | 大量国外站点 | ❌ 降级手动 | 按需评估付费代理 |
| 验证码 | 微博登录、12306 | ❌ 不做 | 不值得 |

### 11.8 远期目标

- L4 反爬增强：playwright-stealth 指纹伪装、IP 轮转
- 自动定时采集（当用户需求明确后）
- 视频/音频内容提取转文字
- 企业系统（飞书、语雀）适配
