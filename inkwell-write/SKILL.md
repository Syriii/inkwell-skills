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
   - 确认 `.retrieval-index/config.json` 的 `source_dirs` 包含 `discussions`，没有则追加

2. **检查目录**
   - `discussions/` 不存在 → `mkdir -p discussions`
   - `creations/` 不存在 → `mkdir -p creations`

## 模式识别

| 用户说 | 进入 |
|--------|------|
| "讨论 XX"、"分析一下"、"怎么看" | **讨论模式** |
| "写一篇"、"写文章"、"出稿"、"基于这些写" | **创作模式** |
| 采集完成后说"讨论这篇" | **讨论模式**（衔接 inkwell-capture（采集完成后）） |
| "把这些讨论写成文章" | **创作模式**（跨讨论聚合） |

---

### Discussion Slug

每次讨论开始时，根据用户的话题生成中文 slug（如 `中医骨髓猪脑寒性之谜`），用于目录路径 `discussions/{slug}/`。规则：

- **中文**，简洁（≤20 字），概括讨论主题
- 如果是衔接 inkwell-capture 的已采集内容，用其归档目录名派生
- 如果是全新话题，从用户的第一句话提取

### Article Slug

每篇文章开始时，生成 article slug，用于目录路径 `creations/{article-slug}/`。规则同 discussion slug。

---

## 讨论模式

### 入口动作

每次讨论开始时自动调 inkwell-search：

```bash
python .claude/skills/inkwell-search/scripts/searcher.py search \
  --query "<主题>" --granularity both --top-k 10 --threshold 0.50
```

- ≥ 0.75 → **直接注入上下文**
- 0.50 ~ 0.75 → 列清单问用户要不要
- < 0.50 → 静默丢弃，报告"无密切相关内容"

> 阈值依据：基于 BGE-small-zh-v1.5 在 25 篇中文社会类内容上的实测校准。
> 0.50 以下为同一语言/大域但不相关内容（如"诬告案"搜索中出现"相亲市场"0.31）。

**搜索后自动建立 references.md**（素材库存清单）：

写入 `discussions/{slug}/references.md` 的素材：
- ≥ 0.75（直接注入）→ 自动写入
- 0.50 ~ 0.75 → 用户确认要的才写入，不要的不写
- 外部搜索（WebSearch/WebFetch）→ 只要讨论中用到，就追加写入

格式：
- 知乎问题目录 → 整目录引用（含所有回答，随时可取用）
- 单篇文章 → 文件路径 + 摘要
- 外部搜索 → URL + 关键信息摘要

```bash
python .claude/skills/inkwell-write/scripts/references_builder.py update \
  --dir "discussions/{slug}" \
  --add "<路径或URL>|<标签>|<摘要>"
```

**references.md 与 based_on 的区分**：
- `references.md` = 这个主题**所有可用**素材（库存清单），后续讨论随时查阅
- `based_on`（写入轮次时）= 本轮**实际引用**了的素材（出库记录）

### 开局分析

搜索完成后、进入讨论前，Claude **必须先对注入素材做开局分析**，给用户一个可反应的起点：

1. **总结**：素材的核心论点或关键信息，一两句话
2. **启发**：有意思的视角、让人多想一步的细节、反直觉的点
3. **缺口**：素材没覆盖到的地方、没说清楚的矛盾、逻辑跳跃
4. **可聊方向**：2-3 个值得展开讨论的角度

输出开局分析后，用户从可聊方向中选择一个开始讨论。**默认以对话讨论方式进入**——用户不需要显式选择模式。

### 两种子模式

两种子模式共用同一套轮次结构，仅交互风格不同：

**对话讨论**（默认）— Claude 与用户来回对话，逐步深入。大多数讨论走这个模式。

**结构化分析** — 用户明确说「分析一下」/「总结这个角度」时触发。Claude 一次性输出多角度/利弊/要点提炼。不需要多轮对话。

### 轮次节点

**开局分析给出的 2-3 个方向，就是预设的轮次节点。** 用户决定顺序——选哪个就从哪个开始，讨论按用户选择的节奏推进。每个方向聊出结论后写一轮，再切换（用户选下一个，或 Claude 建议剩余方向）。

| # | 触发条件 | 行为 |
|---|---------|------|
| 1 | 预设方向聊出明确结论，用户切换到下一个方向 | 写当前方向的轮次，开下一轮 |
| 2 | 讨论中产生新的预设外方向 | 作为新轮次追加到方向列表中 |
| 3 | 用户明确说「先记一下」/「写一轮」 | 立即写当前轮 |
| 4 | 用户回来续接（「继续讨论」） | 先补写上一轮（如果上次未写），再继续 |

触发后，**先和用户确认本轮标题**，确认后再写入。

### 轮次格式

每轮记录保留讨论的推进过程，不只是结论摘要：

```markdown
## 讨论脉络
- 起点：（本轮从哪里开始的）
- 关键转折：（哪个问题或发现改变了讨论方向）
- 收束：（本轮落脚点）

## 核心结论
- 结论1
- 结论2

## 未解决的问题
- 留给下一轮的

## 本轮关键引用
- [[具体文件|标签]] — 用来论证了什么
```

> 注意：`based_on` 只写本轮**实际引用**的素材，不是整个 references 清单。
> 引用格式优先用 Obsidian wikilink `[[path|label]]`；对于不支持 wikilink 的阅读器，同时保留纯路径版本在正文中。

### 续接讨论

用户离开后回来继续讨论时：

1. 扫描 `discussions/` 下所有子目录，**已有讨论记录 = `rounds/` 下有至少一个 `.md` 文件**
2. 加载 `references.md`（弹药清单）+ 最新一轮 `rounds/` + 总结（如有）
3. 呈现续接面板：
   ```
   📂 {slug}
   ├── 已进行 N 轮
   ├── 上次聊到：{最新轮标题 + 一句话}
   ├── 未解决问题：{从最新轮的「未解决的问题」提取}
   └── 可用素材：{references.md 条目数} 条
   
   继续上次讨论？
   ```
4. 用户确认 → 如果上次讨论未写轮，先补写；然后切回讨论模式

### 轮次结束

讨论差不多了 → 问「继续深入还是先做总结？」
- 继续 → 回到对话
- 先到这里 → 生成 summary → `{slug}讨论总结.md`

### 写入

所有脚本路径统一使用项目根目录的相对路径。

**每轮**：
```bash
python .claude/skills/inkwell-write/scripts/discussion_writer.py write-round \
  --dir "discussions/{slug}" --round <N> \
  --title "<角度>" --category "<分类>" --tags "<标签>" \
  --based-on "<引用路径>" --content "<正文>"
```

**总结**（合并了原 初步结果，同时承担讨论回顾 + 创作交接）：
```bash
python .claude/skills/inkwell-write/scripts/discussion_writer.py write-summary \
  --dir "discussions/{slug}" \
  --category "<分类>" --tags "<标签>" --rounds <N> \
  --based-on "<引用路径>" --content "<正文>"
```

> summary 的 slug 从 `--dir` 的 basename 自动推导，文件名 `{slug}讨论总结.md`。
> 总结内容应包含：核心结论、证据来源、叙事弧线、待查证项——既是讨论回顾也是创作交接文档。

### 引用维护

`references.md` 是讨论的素材库存清单，**搜索注入时自动建立**。讨论过程中发现新素材时手动追加：

```bash
python .claude/skills/inkwell-write/scripts/references_builder.py update \
  --dir "discussions/{slug}" \
  --add "<path或URL>|<label>|<摘要>"
```

支持格式：
- 本地文件：`archived/.../腹泻归寒炎症归热/腹泻归寒炎症归热.md|迦太基盐业：腹泻归寒|> 原文摘要`
- 外部 URL：`https://...|中医四气五味理论|> 从《神农本草经》到现代药理研究`
- 整目录：`archived/20260728/为什么中医里说骨髓.../|知乎全问题目录|> 20个高赞回答`

批量追加：
```bash
python .claude/skills/inkwell-write/scripts/references_builder.py update \
  --dir "discussions/{slug}" \
  --add-multi '[["path1","label1","> excerpt1"],["url2","label2","excerpt2"]]'
```

查看已收集的引用：
```bash
python .claude/skills/inkwell-write/scripts/references_builder.py show --dir "discussions/{slug}"
```

### 创作就绪判断

讨论达到以下四个条件时，Claude 应主动提示「可以创作了」：

| # | 条件 | 自检 |
|---|------|------|
| 1 | **主线问题闭环** | 「所以 XX 到底是什么？」能用一段话回答 |
| 2 | **修正已收敛** | 最近两轮在增量补充而非推翻重建 |
| 3 | **证据类型充足** | 至少覆盖 3 种不同来源（历史、数据、跨文化、生理机制、民间实践等） |
| 4 | **用户明确了创作主题** | 讨论覆盖很多角度，但文章只能写一个。用户决定了写什么、面向谁、传递什么 |

> 前三个条件满足后，Claude 可以问：「讨论比较充分了，有想写的角度吗？」
> 第四个条件必须由用户给出。没有明确主题时不自动推进到创作。

### 讨论升级为创作

用户说「把这些讨论写成文章」时：

1. **聚合素材**：加载所有轮次 + 总结（如有）+ `references.md`
2. **呈现交接面板**：
   ```
   📝 准备基于以下内容创作文章：
   ├── 已进行 N 轮讨论
   ├── 引用素材：M 条
   └── 轮次概览：
       · 01-标题（核心结论一句话）
       · 02-标题（核心结论一句话）
   
   以此为基础进入创作流程？
   ```
3. 用户确认 → 进入创作模式 Step 1（定方向），讨论素材作为上下文注入

> **讨论与创作是两条并行轨道。** 进入创作模式后，讨论轨道不关闭——关于文章角度、结构、取舍的讨论继续记录为轮次。创作轨道产出 outline → draft → article。两条轨道的引用链都指向同一个 `references.md`。

---

## 创作模式

### 入口（独立于讨论）

直接进入创作模式（不经讨论）时，同样执行：

1. 调 inkwell-search 搜索相关素材（同讨论模式的入口动作）
2. 建立 `references.md`
3. 做轻量版开局分析（总结 + 启发，不需四个方向）
4. 进入 Step 1：定方向

### 五步流程（每步需用户确认，产出步骤内含审查）

每个产出步骤（提纲、草稿、定稿）写入后，Claude 必须先执行一次**结构化审查**，再呈现给用户确认。审查不是自我批改——是逐条对照检查表，判断是否通过、是否需要修复。

#### Step 1: 定方向
1. 用户给主题或素材
2. 调 inkwell-search 自动注入相关素材（同讨论模式）
3. 讨论确定：文章角度、语气、篇幅、目标读者
4. **选文风**：从 `references/styles/` 中选择匹配的写作风格。根据文章 category 匹配风格的 `suitable_for` 字段。若无匹配风格，用默认对话感文风。选定后全文遵循该风格文件。
5. 用户确认 ✓

#### Step 2: 写提纲 → 审查 → 用户确认

1. Claude 基于素材写提纲（一/二级标题）
2. **审查提纲**（逐项通过后呈现给用户）：

| # | 检查项 | 通过标准 |
|---|--------|---------|
| 1 | **读者顺序** | 结构是否按读者自然关心的顺序展开（听过→哪来的→对不对→怎么用），而非学术框架 |
| 2 | **段段有目的** | 每一段在全文逻辑链中承担什么角色（破/转/用），去掉任何一段会不会断 |
| 3 | **逻辑闭合** | 开头提出的问题，结尾有没有回扣回答 |
| 4 | **字数适配** | 预估字数是否匹配目标平台（公众号科普观点文 1000-1500 字） |
| 5 | **遗漏检查** | 讨论中的关键论据有没有在提纲里丢了 |

3. 呈现审查结论 + 提纲 → 用户修改/确认 ✓
4. 写入：
```bash
python .claude/skills/inkwell-write/scripts/outline_writer.py write \
  --dir "creations/{article-slug}" --title "<标题>" \
  --category "<分类>" --tags "<标签>" \
  --based-on "<引用路径>" --content "<提纲>"
```

#### Step 3: 出草稿 → 审查 → 用户确认

1. Claude 按选定风格和提纲写全文
2. **审查草稿**（逐项通过后呈现给用户）：

| # | 检查项 | 通过标准 |
|---|--------|---------|
| 1 | **开头钩子** | 前 50-100 字是否让读者有理由继续读（场景共鸣、反直觉、提问） |
| 2 | **段段有血肉** | 每个论点有没有配例子/细节/数据——抽象结论要有可感知的支撑 |
| 3 | **语气全篇一致** | 不忽冷忽热——该讲道理的地方不突然煽情，该接地气的地方不突然学术腔 |
| 4 | **结尾回扣** | 是否回到开头的钩子或场景，让读者感到「看完了有变化」 |
| 5 | **无素材残留** | 是否为引用而引用的段落、不服务论点的知识展示——有就删 |

3. 呈现审查结论 + 草稿 → 用户确认 ✓
4. 写入（**每次写入自动生成新版本**：drafts/v1.md, v2.md, ...）：
```bash
python .claude/skills/inkwell-write/scripts/draft_writer.py write \
  --dir "creations/{article-slug}" --title "<标题>" \
  --category "<分类>" --tags "<标签>" \
  --status draft --word-count <N> \
  --based-on "<引用路径>" \
  --source-discussions "<讨论slug列表>" \
  --content "<正文>"
```

#### Step 4: 审阅迭代
1. 用户反馈 → Claude 修改
2. 每次修改后判断变更大小：
```bash
python .claude/skills/inkwell-search/scripts/searcher.py compare \
  --text-a "<旧版>" --text-b "<新版>" --strategy auto
```
- 变更大小仅用于**告知用户改了多少**，不决定写入方式
- 每次修改均通过 `draft_writer.py write` 写入，自动生成 vN+1

> 阈值 0.85 基于 BGE-small-zh-v1.5 在同类中文内容上的经验值。同一篇文章的微调通常在 0.85+，结构调整后通常降至 0.70-0.85。
3. 反复迭代直到满意 ✓

#### Step 5: 输出 → 审查 → 定稿

1. **审查定稿**（逐项通过后写入为终版）：

| # | 检查项 | 通过标准 |
|---|--------|---------|
| 1 | **标题准确** | 标题是否准确反映文章内容，没有标题党或文不对题 |
| 2 | **可读性** | 手机屏幕每段不超过 4 行，小标题层级清晰，关键句突出 |
| 3 | **完整性** | frontmatter 完整（title, category, tags, source_discussions, based_on），正文无残缺 |
| 4 | **引用合规** | 外部引用标注来源，禁写内容无残留 |

2. `draft_writer.py update-status --status article`（取最新编号草稿 → `{slug}.md`，旧草稿保留在 drafts/）
3. 呈现最终版本 + 历史版本清单

### 跨讨论创作

一篇文章可以聚合多个讨论的成果。在 Step 3 出草稿时，通过 `--source-discussions` 声明文章引用了哪些讨论的 slug。

inkwell-search 拉所有相关素材，Claude 自动整合。产出落在 `creations/{article-slug}/` 下；跨多个讨论时由用户决定 article slug。

### 产出状态查询

随时查询哪些讨论已产出文章、哪些还没有：

```bash
python .claude/skills/inkwell-write/scripts/discussion_writer.py status [--filter created|uncreated|all]
```

原理：扫描 `creations/` 下所有文章的 `source_discussions` 字段，与 `discussions/` 下所有有记录的讨论做差集。

---

## 脚本规范

- CLI 参数输入，stdout JSON，stderr 错误
- 退出码 0 = 成功

## 写作风格

文风作为独立文件管理在 `references/styles/`，可随时新增、修改，不影响 skill 本体。

每篇风格文件包含：
- `name`：风格名称
- `suitable_for`：适用 category 列表（用于 Step 1 自动匹配）
- 核心定位、开头/正文/结尾规范
- **AI 味检测清单**（草稿审查时对照检查）

当前可用风格：

| 风格 | 适用 | 说明 |
|------|------|------|
| [健康科普](references/styles/health-science.md) | 健康、医疗、饮食、生活常识 | 丁香医生/果壳风，"穿白大褂的朋友" |

审查草稿时，**额外对照风格文件的 AI 味检测清单**逐项检查。

## 目录结构

```
discussions/{slug}/
├── rounds/
│   └── NN-{角度}.md
├── references.md
└── {slug}讨论总结.md

creations/{article-slug}/
├── {article-slug}.md          ← 终稿（update-status → article 后生成）
├── outline.md
├── drafts/
│   ├── v1.md                  ← 初稿
│   ├── v2.md                  ← 修改后新版本
│   └── ...
└── images/
```

### 讨论与文章的关系

**文章声明自己来自哪些讨论**（article-centric）。一个讨论可以被多篇文章引用，一篇文章可以聚合多个讨论。

文章 frontmatter：
```yaml
source_discussions:
  - "中医骨髓猪脑寒性之谜"
  - "知乎食品谣言的社会传播"
```

`based_on` vs `source_discussions`：
- `based_on` = 引用了哪些**素材**（archived 文件、URL）
- `source_discussions` = 思想来自哪些**讨论**（discussion slug）
