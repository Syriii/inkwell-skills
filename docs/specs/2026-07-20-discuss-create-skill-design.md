# 讨论创作 Skill 设计

## 概述

web-analysis 四个独立 Skill 之一：**讨论创作（Discuss-Create）**。一个 Skill，两种模式：**讨论模式**（多轮对话+结构化分析）和**创作模式**（五步流程产出文章）。**必须**关联检索 Skill。

先讨论再创作是常态，但也可直接进入创作模式。跨讨论聚合写文章时，Skill 通过检索自动拉取所有相关素材。

### 四个独立 Skill 的关系

| Skill | 独立运行 | 关联 |
|-------|:---:|------|
| 检索 Retrieval | ✅ 完全独立 | 不需要任何其他 Skill |
| 采集 Collect | ✅ 独立（无检索时每次当新内容） | **可选**关联检索（语义去重） |
| 讨论创作 Discuss-Create | ❌ 需检索 | **必须**装检索（auto-inject ≥0.75） |
| 发布 Publish | ✅ 完全独立 | 无关联 |

> 本文档为讨论创作 Skill 的设计。检索、采集 Skill 设计见独立文档。发布 Skill 远期设计。

---

## 一、项目结构

```
{project}/
├── archived/                        ← 采集归档（采集 Skill 管理）
├── topics/                          ← 讨论+创作，按主题聚合
│   └── {topic-slug}/
│       ├── discussion/              ← 讨论模式产出
│       │   ├── {topic}讨论总结.md   ← 最终总结（type: summary）
│       │   ├── references.md        ← 引用清单（wikilinks + 摘录）
│       │   └── rounds/
│       │       ├── 01-{角度}.md     ← 每轮讨论（type: discussion）
│       │       ├── 02-{角度}.md
│       │       └── ...
│       └── creation/                ← 创作模式产出
│           ├── outline.md           ← 提纲（type: outline）
│           ├── article.md           ← 主草稿（type: draft / article）
│           ├── drafts/              ← 历史迭代版本
│           │   ├── v1.md
│           │   └── v2.md
│           └── images/              ← 配图
└── published/                       ← 成品文章
```

- `{topic-slug}` 和文件名由 Claude Code 根据内容生成
- 同一 topic 可以只有讨论、只有创作、或两者都有
- 跨 topic 创作：创作模式通过检索 Skill 拉所有相关素材，不限本 topic

### 1.1 初始化

首次触发 Discuss-Create Skill 时自动执行：

1. **检查检索 Skill**：检测检索 Skill 是否已安装 → 未安装则自动安装（用户无感）
2. **检查 `topics/` 目录**：不存在则创建
3. **读取检索配置**：确认检索 Skill 的 `config.json` 中有 `source_dirs` 含 `topics/`，没有则追加

> 注：`topics/` 目录也可能由采集 Skill 初始化时创建，两者不冲突——先到先建。


---

## 二、Skill 结构

### 2.1 目录

```
discuss-create/
├── SKILL.md                      ← 触发描述 + 工作流指令（两种模式）
├── scripts/
│   ├── discussion_writer.py      ← 写入 rounds + summary（含 frontmatter）
│   ├── references_builder.py     ← 生成/更新 references.md（wikilinks + 摘录）
│   ├── outline_writer.py         ← 写入 outline.md（含 frontmatter）
│   └── draft_writer.py           ← 写入 article.md + drafts/ 历史版本管理
└── references/
    └── frontmatter-schema.md     ← frontmatter 规范
```

### 2.2 触发描述

```
基于素材进行讨论分析或文章创作。一个 Skill，两种模式：
- 讨论模式：分析材料、讨论话题、质疑观点、延伸思考，多轮对话+结构化分析
- 创作模式：写文章、写博客、写公众号、整理观点输出，五步流程产出

当用户想讨论某个话题、分析材料、或创作文章时触发。也适用于采集完成后
说"讨论这篇"、"基于这些写一篇"。关联检索 Skill，讨论和创作时自动注入
相关历史内容。
```

---

## 三、讨论模式

### 3.1 两种子模式，交替进行

**对话讨论**：Claude 与用户来回对话，逐步深入。

**结构化分析**：用户说"分析一下"/"总结这个角度" → Claude 输出多角度/利弊/要点提炼。

### 3.2 完整流程

```
触发入口（任一种）：
  → 用户说"讨论 XX"（主题驱动）
  → 用户提供素材 + "分析一下"/"怎么看"（素材驱动）
  → 采集 Skill Step 8 衔接（"要讨论这篇吗？"）
  → 浏览已有内容时触发讨论
    ↓
检索 Skill 拉素材
  → ≥0.75 直接注入上下文
  → <0.75 列清单问用户要不要
    ↓
对话讨论（子模式一）
    ↓
用户说"分析一下" → 结构化分析（子模式二）
    ↓
更新 references.md（wikilinks + 关键摘录）
    ↓
Claude 感知节奏：
  → 话题自然转向 → 问"要开新的一轮吗？"
    → 是 → 写入 rounds/，开新轮（回到对话讨论）
    → 否 → 继续当前轮
  → 讨论深度差不多了 → 问"要继续深入还是先做个总结？"
    → 继续 → 回来
    → 先到这里 → 生成 summary，写入 {topic}讨论总结.md
    ↓
完成（可选衔接创作模式）
```

---

## 四、创作模式

### 4.1 五步流程

每步需要用户确认，不自动跳过：

```
Step 1: 定方向
  → 用户给主题或素材（可基于已有讨论、也可独立起题）
  → 检索 Skill 自动注入相关素材（≥0.75 直接注入，<0.75 列清单）
  → Claude 与用户讨论确定文章角度、语气、篇幅、目标读者
  → 用户确认方向 ✓
    ↓
Step 2: 写提纲
  → Claude 基于素材和方向写出文章提纲（一级/二级标题结构）
  → 呈现给用户
  → 用户修改 / 确认 ✓
  → outline_writer.py 写入 creation/outline.md
    ↓
Step 3: 出草稿
  → Claude 按提纲写全文，引用素材（wikilink 格式）
  → draft_writer.py 写入 creation/article.md
  → 呈现给用户
    ↓
Step 4: 审阅迭代
  → 用户反馈（"这段删了""这里加数据""语气不对"）
  → Claude 修改
  → 新旧版本 embedding 比较（跟 drafts/ 最新版本比）：
      → 相似度 ≥ 0.85 → 小改动，原地更新 article.md
      → 相似度 < 0.85 → 大改动，当前 article.md → drafts/vN.md，再写入新版
  → 反复迭代直到用户满意 ✓
    ↓
Step 5: 输出
  → article.md frontmatter type: draft → article
  → 呈现最终版本
  → 可选：衔接发布 Skill
```

### 4.2 版本管理

调检索 Skill `compare`（strategy='auto'），跟 `drafts/` 中最新版本比较：
- 相似度 ≥ 0.85 → 小改动，原地更新 `article.md`，不存档
- 相似度 < 0.85 → 大改动，当前 `article.md` → `drafts/vN.md`（N 递增），再写入新版

```
creation/
├── article.md          ← 当前最新版本
├── drafts/
│   ├── v1.md           ← 第一版（大改后存档）
│   └── v2.md           ← 第二版（再次大改后存档）
```

### 4.3 跨讨论创作

创作可聚合多个 topic 的讨论和素材。检索 Skill 拉回所有相关内容的段落，Claude 在定方向和写提纲时自动整合。产出落在当前 topic 目录下；如果跨多个 topic，用户决定放在哪个 topic。

---

## 五、Frontmatter 规范

### 5.1 讨论轮次（type: `discussion`）

```yaml
---
date: 2026-07-20
round: 1
round_title: "监管框架与立法背景"
type: discussion
category: 科技
tags: [AI政策, 科技法规]
based_on:
  - archived/20260301/eu-ai-act/article.md
---
```

### 5.2 讨论总结（type: `summary`）

```yaml
---
date: 2026-07-20
topic: "欧盟AI法案讨论"
type: summary
category: 科技
tags: [AI政策, 科技法规, 欧盟]
based_on:
  - archived/20260301/eu-ai-act/article.md
rounds: 3
---
```

### 5.3 创作提纲（type: `outline`）

```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: outline
category: 科技
tags: [AI政策, 科技治理]
based_on:
  - topics/eu-ai-regulation/discussion/欧盟AI法案讨论总结.md
  - archived/20260301/eu-ai-act/article.md
---
```

### 5.4 创作草稿（type: `draft`）

```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: draft
category: 科技
status: draft              # draft | review
tags: [AI政策, 科技治理]
based_on:
  - topics/eu-ai-regulation/discussion/欧盟AI法案讨论总结.md
  - archived/20260301/eu-ai-act/article.md
word_count: 3500
---
```

### 5.5 创作成品（type: `article`）

```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: article
category: 科技
tags: [AI政策, 科技治理]
based_on:
  - topics/eu-ai-regulation/discussion/欧盟AI法案讨论总结.md
  - archived/20260301/eu-ai-act/article.md
word_count: 3500
---
```

### 5.6 历史版本（type: `draft`）

```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: draft
category: 科技
version: 1
tags: [AI政策, 科技治理]
based_on:
  - archived/20260301/eu-ai-act/article.md
word_count: 2800
---
```

### 5.7 完整 type 清单

| 文件 | type |
|------|------|
| discussion round | `discussion` |
| discussion summary | `summary` |
| creation outline | `outline` |
| creation draft | `draft` |
| creation final | `article` |
| 采集归档 | `webpage` / `forum` / `screenshot_ocr` / ... |

---

## 六、引用机制

讨论过程中自动维护引用清单，使用 Obsidian wikilink 格式：

```markdown
# 引用素材

## [[archived/20260301/eu-ai-act/article|欧盟AI法案全文解读]]
> 欧盟议会于2024年3月13日正式通过...
> 风险分级制度是该法案的核心...

## [[topics/tech-policy/discussion/科技政策讨论总结|科技政策讨论]]
> 关于分级监管的一个重要分歧是...
```

- wikilink 在 Obsidian 中可点击跳转
- 关键摘录来自检索 Skill 自动注入的段落
- 讨论过程中由 `references_builder.py` 自动更新

---

## 七、与其他 Skill 的关系

### 7.1 检索 Skill（必须，安装时自动带）

- Discuss-Create SKILL.md 启动首步：检查检索 Skill 是否存在（检索 scripts 目录或 `.retrieval-index/` 配置）
- 不存在 → 自动安装检索 Skill（静默，用户无感），然后继续执行
- 安装来源在 Skill 分发时确定，不在本文档硬编码

- 讨论开始、每轮切换、创作定方向和写提纲时自动调检索
- ≥0.75 阈值自动注入，<0.75 列清单
- 注入的段落落地到 references.md
- 创作版本管理调 `compare`（strategy='auto'），阈值 0.85

### 7.2 采集 Skill（可选）

- 采集完一篇内容 → "要讨论这篇吗？" → 触发讨论创作 Skill 的讨论模式
- 通过 `based_on` 引用 archived/ 中的原文

### 7.3 发布 Skill（可选，远期）

- 创作模式输出成品后可选衔接发布 Skill

---

## 八、技术选型

| 层 | 选择 | 理由 |
|----|------|------|
| 对话编排 | SKILL.md 工作流 | Claude Code 直接对话，两种模式灵活切换 |
| 讨论写入 | discussion_writer.py | 确保 frontmatter 格式、目录结构一致性 |
| 引用生成 | references_builder.py | 自动扫描讨论内容生成 wikilinks + 摘录 |
| 提纲写入 | outline_writer.py | 确保 frontmatter 格式一致性 |
| 草稿写入+版本管理 | draft_writer.py | 版本比较（embedding 相似度）、drafts/ 管理 |
| 检索 | 调检索 Skill | 不在讨论创作 Skill 内建索引逻辑 |
| 归档 | Markdown + YAML frontmatter | Obsidian 兼容，人类可读 |

---

## 九、边界与不做的事

- 讨论创作 Skill 不做内容采集（那是采集 Skill 的事）
- 讨论创作 Skill 不管理检索索引（那是检索 Skill 的事）
- 讨论创作 Skill 不做发布（那是发布 Skill 的事，远期设计）
- 讨论模式产出的是讨论记录，不是可发布的文章（那是创作模式的事）
- 可从任意素材直接进入创作模式，不需要先讨论
