---
name: inkwell-write
description: >
  Inkwell 熔裁技能。基于素材进行讨论分析或文章创作。一个 Skill，两种模式：
  讨论模式 — 分析材料、讨论话题、质疑观点、延伸思考，多轮对话+结构化分析；
  创作模式 — 写文章、写博客、写公众号、整理观点输出，五步流程产出。
  当用户想讨论某个话题、分析材料、或创作文章时触发。也适用于采集完成后
  说"讨论这篇"、"基于这些写一篇"。关联 inkwell-search，自动注入相关历史内容。
---

# inkwell-write — 熔裁

一个 Skill，两种模式。**先讨论再创作是常态**，也可直接进入创作模式。

## 启动检查

首次触发时执行：

1. **检查 inkwell-search**
   - 检查 `.claude/skills/inkwell-search/` 是否存在
   - 不存在 → 自动安装（静默，用户无感）
   - 确认 `.retrieval-index/config.json` 的 `source_dirs` 包含 `topics`，没有则追加

2. **检查 topics/ 目录**
   - 不存在 → `mkdir -p topics`

## 模式识别

| 用户说 | 进入 |
|--------|------|
| "讨论 XX"、"分析一下"、"怎么看" | **讨论模式** |
| "写一篇"、"写文章"、"出稿"、"基于这些写" | **创作模式** |
| 采集完成后说"讨论这篇" | **讨论模式**（衔接 inkwell-capture（采集完成后）） |
| "把这些讨论写成文章" | **创作模式**（跨讨论聚合） |

---

## 讨论模式

### 入口动作

每次讨论开始时自动调 inkwell-search：

```bash
python .claude/skills/inkwell-search/scripts/searcher.py search \
  --query "<主题>" --granularity both --top-k 10 --threshold 0.50
```

- ≥ 0.75 → **直接注入上下文**，段落落地到 references.md
- 0.50 ~ 0.75 → 列清单问用户要不要
- < 0.50 → 静默丢弃，报告"无密切相关内容"

> 阈值依据：基于 BGE-small-zh-v1.5 在 25 篇中文社会类内容上的实测校准。
> 0.50 以下为同一语言/大域但不相关内容（如"诬告案"搜索中出现"相亲市场"0.31）。

### 开局分析

搜索完成后、进入讨论前，Claude **必须先对注入素材做开局分析**，给用户一个可反应的起点：

1. **总结**：素材的核心论点或关键信息，一两句话
2. **启发**：有意思的视角、让人多想一步的细节、反直觉的点
3. **缺口**：素材没覆盖到的地方、没说清楚的矛盾、逻辑跳跃
4. **可聊方向**：2-3 个值得展开讨论的角度

输出开局分析后，再问用户选哪种模式进入讨论。

### 两种子模式

**对话讨论** — Claude 与用户来回对话，逐步深入。

**结构化分析** — 用户说"分析一下"/"总结这个角度" → 输出多角度/利弊/要点提炼。

### 轮次管理

Claude 感知节奏：

- **话题自然转向** → 问"要开新的一轮吗？"
  - 是 → 写入当前轮到 `rounds/NN-{角度}.md`，开新轮
  - 否 → 继续
- **讨论差不多了** → 问"继续深入还是先做总结？"
  - 继续 → 回到对话
  - 先到这里 → 生成 summary → `{topic}讨论总结.md`

### 写入

**每轮**：
```bash
python scripts/discussion_writer.py write-round \
  --dir "topics/{slug}/discussion" --round <N> \
  --title "<角度>" --category "<分类>" --tags "<标签>" \
  --based-on "<引用路径>" --content "<正文>"
```

**总结**：
```bash
python scripts/discussion_writer.py write-summary \
  --dir "topics/{slug}/discussion" --topic "<主题>" \
  --category "<分类>" --tags "<标签>" --rounds <N> \
  --based-on "<引用路径>" --content "<正文>"
```

### 引用维护

```bash
python scripts/references_builder.py update \
  --dir "topics/{slug}/discussion" \
  --add "<path>|<label>|> <excerpt>"
```

---

## 创作模式

### 五步流程（每步需用户确认）

#### Step 1: 定方向
1. 用户给主题或素材
2. 调 inkwell-search 自动注入相关素材（同讨论模式）
3. 讨论确定：文章角度、语气、篇幅、目标读者
4. 用户确认 ✓

#### Step 2: 写提纲
1. Claude 基于素材写提纲（一/二级标题）
2. 呈现 → 用户修改/确认 ✓
3. 写入：
```bash
python scripts/outline_writer.py write \
  --dir "topics/{slug}/creation" --title "<标题>" \
  --category "<分类>" --tags "<标签>" \
  --based-on "<引用路径>" --content "<提纲>"
```

#### Step 3: 出草稿
1. Claude 按提纲写全文（wikilink 引用：`[[path|label]]`）
2. 写入：
```bash
python scripts/draft_writer.py write \
  --dir "topics/{slug}/creation" --title "<标题>" \
  --category "<分类>" --tags "<标签>" \
  --status draft --word-count <N> \
  --based-on "<引用路径>" --content "<正文>"
```
3. 呈现给用户

#### Step 4: 审阅迭代
1. 用户反馈 → Claude 修改
2. 新旧版本比较：
```bash
python .claude/skills/inkwell-search/scripts/searcher.py compare \
  --text-a "<旧版>" --text-b "<新版>" --strategy auto
```
- ≥ 0.85 → 小改动，`draft_writer.py write` 原地更新
- < 0.85 → 大改动，`draft_writer.py archive-and-write` 存档后写新版
3. 反复迭代直到满意 ✓

#### Step 5: 输出
1. `draft_writer.py update-status --status article`
2. 呈现最终版本 + 历史版本清单

### 跨讨论创作

inkwell-search 拉所有相关素材，Claude 自动整合。产出落在当前 topic 下；跨多个 topic 由用户决定放置位置。

---

## 脚本规范

- CLI 参数输入，stdout JSON，stderr 错误
- 退出码 0 = 成功

## 目录结构

```
topics/{topic-slug}/
├── discussion/
│   ├── {topic}讨论总结.md     ← type: summary
│   ├── references.md
│   └── rounds/
│       └── NN-{角度}.md       ← type: discussion
└── creation/
    ├── outline.md             ← type: outline
    ├── article.md             ← type: draft / article
    ├── drafts/                ← 历史版本
    └── images/
```
