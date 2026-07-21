# 检索 Skill 设计

## 概述

web-analysis 四个独立 Skill 之一：**检索（Retrieval）**。通用的语义索引和搜索工具，知道"文档"和"向量"，不知道 web-analysis 的业务字段（tags、category 等）。**完全独立**，不需要任何其他 Skill。

被采集（可选）和讨论创作（必需）关联调用，也可独立用于任何项目的文档语义搜索。

### 四个独立 Skill 的关系

| Skill | 独立运行 | 关联 |
|-------|:---:|------|
| 检索 Retrieval | ✅ 完全独立 | 不需要任何其他 Skill |
| 采集 Collect | ✅ 独立（无检索时每次当新内容） | **可选**关联检索（语义去重） |
| 讨论创作 Discuss-Create | ❌ 需检索 | **必须**装检索（auto-inject ≥0.75） |
| 发布 Publish | ✅ 完全独立 | 无关联 |

> 本文档为检索 Skill 的设计。采集、讨论创作 Skill 设计见独立文档。发布 Skill 远期设计。

---

## 一、项目结构

```
{project}/
├── .retrieval-index/          ← 检索索引数据（项目根）
│   ├── config.json            ← 源目录配置
│   ├── doc.index              ← 文档级 FAISS 索引
│   ├── doc_map.json           ← 文档级 id → 元数据映射
│   ├── chunk.index            ← 块级 FAISS 索引
│   └── chunk_map.json         ← 块级 id → 元数据映射
├── archived/                  ← 采集归档
├── topics/                    ← 讨论+创作
└── published/                 ← 成品文章
```

- 一个项目一个索引，另一个项目另一个索引
- 目录名 `.retrieval-index/` 与 Skill 名称一致，避免与 FAISS 库名冲突

---

## 二、Skill 结构

### 2.1 目录

```
retrieval/
├── SKILL.md                  ← 触发描述 + 工作流指令
├── scripts/
│   ├── indexer.py            ← 建/追加索引（编码→写 FAISS）
│   ├── searcher.py           ← 语义搜索（编码 query→搜 FAISS→返回结果）
│   └── requirements.txt      ← sentence-transformers, faiss-cpu, numpy
└── references/
    └── embedding-models.md   ← 支持的 embedding 模型列表
```

### 2.2 触发描述

```
给文档建立语义索引和搜索。当用户想对内容进行语义搜索、查找相关文档、
检查内容相似度时触发。也适用于"帮我索引这些文件""更新索引""搜索XX相关的内容"
等场景。

这是一个通用工具——只知道"文档"和"向量"，不理解任何业务字段。
索引哪些目录由用户配置，首次使用时提示配置源目录。
```

---

## 三、核心设计

### 3.1 纯粹性

检索 Skill 保持**通用**——仅供向量索引和搜索，不识别业务字段：

- 不认识 `tags`、`category`、`title`、`summary` 等字段名
- 调用方（采集、讨论创作）拼接好待编码文本后传给检索
- 标签/分类列表查询 → 调用方自己 `grep` frontmatter
- 业务字段的存储归属在各归档文件和讨论创作产出中，不在检索索引里

### 3.2 两级索引

两个独立 FAISS 索引，服务不同场景：

| 索引 | 文件 | 一条向量 = | 回答的问题 | 典型场景 |
|------|------|------|------|------|
| 文档级 | `doc.index` | 一篇文档 | "这篇**整体**跟谁相关？" | 去重、找相关文章 |
| 块级 | `chunk.index` | 文档中的一段 | "**哪些段落**讲了这个？" | 找素材/出处 |

**默认规则 + 可覆盖**：

| 场景 | 默认走 | 
|------|------|
| 去重 | 文档级 |
| 找素材/出处 | 块级 |
| 找相关文章 | 文档级 |

每次搜索可传粒度参数（`doc`/`chunk`/`both`）覆盖默认。

### 3.3 分块策略（结构优先 + 长度兜底）

1. 优先按 Markdown 标题（`##`/`###`）边界切
2. 某节超过 ~500 字 → 节内按 ~400 字切，~50 字重叠
3. 无标题结构的纯文本 → 直接按 ~400 字/50 重叠切

参数实现时可调。**注意**：中文 BGE-small 输入长度 ~512 token（约 300-400 汉字），~500 字的块上限可能超模型限制，实现时需实测校准——可能需压到 ~400 字，或过长的块由 sentence-transformers 自动截断。

分块逻辑被 `searcher.py compare(strategy='full')` 复用——长文本比较时先用同一套分块算法切分，分别 encode 后 mean pooling 得到文档级向量。

### 3.4 输入契约

调用方向检索传 `(path, encodable_text)`：
- 采集调用时：`encodable_text = title + summary + tags + 正文`
- 讨论创作调用时同理，拼好传给检索

检索只管编码传入的文本，不管这文本是哪来的、怎么拼的。

### 3.5 索引元数据

FAISS 只存向量+整数 id，旁路映射存元数据：

**文档级映射** (`doc_map.json`)：`id → {path, content_hash, indexed_at}`

**块级映射** (`chunk_map.json`)：`id → {path, chunk_text, chunk_index}`
- 存 `chunk_text` 原文而非偏移量——个人规模空间便宜，检索返回即可用

**不存** tags、category、title、summary 等业务字段。

---

## 四、对外能力

用户面对检索 Skill，只需理解两件事：

### 4.1 索引管理

- "帮我把 archived 的内容建索引"
- "把这个文件加进去"
- "索引现在什么状态？"（多少文档、上次更新时间）
- "索引更新一下"（增量扫描，新增+清理消失的）
- "索引重建一下"（换了模型或觉得不准）

首次使用时提示用户配置源目录，写入 `config.json`。后续自动读取。

### 4.2 搜索

- "找跟 XX 相关的文章"
- "有没有讲 XX 的内容"
- "把知识库里最相关的 5 篇调出来"
- "这篇文章跟已有的有没有重复"
- "只在 topics 里搜"（范围限定）
- "这次不要搜 XX 那篇"（排除）

搜索默认阈值 **0.75**（余弦相似度），业界标准（BGE + FAISS + LangChain）。支持在 config 里调整。

≥0.75 的结果 → 自动返回内容（可注入上下文）；<0.75 的结果 → 列清单让用户决定。

---

## 五、脚本接口

### 5.1 indexer.py

```
输入：操作类型 + 参数
  index (path, encodable_text)     — 增量加一篇
  rebuild [(path, text), ...]      — 全量重建（调用方备好数据）
  remove path                      — 删除一篇（自动，扫描时发现文件消失）
  status                           — 返回索引状态

输出：JSON

行为：
  - 增量 index：已存在同 path 且 content_hash 没变 → 跳过；变了 → 更新
  - 全量 rebuild：先写入临时文件（`doc.index.new`），完成后原子替换旧索引。重建期间搜索仍用旧索引，零中断
  - remove：从两个索引删该文档的所有向量
```

### 5.2 searcher.py

```
输入：
  query             — 搜索文本
  granularity       — doc | chunk | both（默认按场景）
  top_k             — 返回数量
  threshold         — 相似度阈值（默认 0.75）
  exclude_paths     — 排除的路径列表（可选）
  scope_dirs        — 限定搜索范围（可选）

输出：
  doc 模式 → [(path, score), ...]
  chunk 模式 → [(path, chunk_text, chunk_index, score), ...]

compare(text_a, text_b, strategy='auto'):
  — 直接比较两段文本的相似度，不走索引
  strategy:
    auto   — < ~500 字走 direct；≥ ~500 字走 full（默认）
    direct — 直接 encode，与 index 行为对齐（apples-to-apples）
    full   — chunk → 分别 encode → mean pooling，全文覆盖
  输出：{ score, strategy_used, chunks_a, chunks_b }
```

---

## 六、模型管理

### 6.1 模型可用性检查

检索 Skill 启动时检查 embedding 模型是否可用：

```
检查模型文件是否存在（/Users/xiesh/Codes/models/embedding/bge-small-zh-v1.5/）
  → 存在 → 正常使用
  → 不存在 → sentence-transformers 首次运行时自动下载
  → 下载失败 → 提示用户检查网络或手动指定模型路径
```

换模型只需修改 `config.json` 或项目 `.env` 中的 `EMBEDDING_MODEL`。

## 七、配置

### 7.1 config.json

```json
{
  "source_dirs": [
    "archived",
    "topics"
  ],
  "embedding_model": "BAAI/bge-small-zh-v1.5",
  "search_threshold": 0.75,
  "last_indexed_at": "2026-07-20T10:30:00"
}
```

- `source_dirs`：首次使用时提示用户配置
- `embedding_model`：默认 BGE-small-zh-v1.5，可通过项目 `.env` 覆盖
- `search_threshold`：默认 0.75，支持按需调整

### 7.2 独立的项目使用

检索 Skill 安装到任意项目后：
1. 首次触发 → 检测无 `config.json` → 提示配置源目录
2. 用户指定目录后 → 写 config → 执行首次索引
3. 之后触发 → 读 config，按需增量或重建

---

## 八、与其他 Skill 的关系

### 8.1 采集 Skill（可选关联）

- 采集去重：调 `searcher.py`（granularity=doc, top_k=1），用 0.95 阈值判"高度相似"
- 采集更新判定：调 `searcher.py compare`（strategy='auto'），用 0.85 阈值判"内容变化大小"
- 采集追加：归档后调 `indexer.py index`，传入拼接好的文本
- 未安装 → 采集仅做 source 精确匹配

### 8.2 讨论创作 Skill（必需关联）

- 讨论和创作时自动调 `searcher.py` 拉相关素材
- ≥0.75 自动注入上下文 → 段落落地到 references.md
- <0.75 列清单让用户决定
- 创作版本管理：调 `searcher.py compare`（strategy='auto'），<0.85 → 存档旧版再写新版
- 安装讨论创作时自动带检索 Skill

---

## 九、技术选型

| 层 | 选择 | 理由 |
|----|------|------|
| 语言 | Python | FAISS/Embedding 生态最强 |
| 索引 | FAISS `IndexFlatL2` | 个人规模（100s-1000s），精确快速，文件即索引 |
| Embedding 模型 | `BAAI/bge-small-zh-v1.5`（默认，可换） | ~100MB，CPU 友好，中文优化 |
| Embedding 调用 | `sentence-transformers` | 一行 `model.encode()`，无需后台服务 |
| 分块 | 结构优先 + 长度兜底 | Markdown 标题天然语义边界，长度上限防截断 |
| 模型目录 | `/Users/xiesh/Codes/models/` | 统一管理，`.env` 可配 |

---

## 十、边界与不做的事

- 检索 Skill 不认识 `tags`、`category` 等业务字段
- 检索 Skill 不负责"列出所有标签/分类"（调用方 `grep` frontmatter）
- 检索 Skill 不管理归档目录结构（那是采集和讨论创作的事）
- 检索 Skill 不预设要索引哪些目录（首次使用时用户配置）
- 检索 Skill 不主动清理死链（增量扫描时文件消失自动从索引移除）
