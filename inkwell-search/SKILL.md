---
name: inkwell-search
description: >
  Inkwell 牵丝技能。语义索引和搜索工具。当用户想对文档内容进行语义搜索、
  查找相关文档、检查内容相似度、建立或更新索引时触发。也适用于
  "帮我索引这些文件""搜索XX相关的内容""这篇文章跟已有的有没有重复"等场景。
  这是一个通用工具——只知道"文档"和"向量"，不理解任何业务字段。
---

# inkwell-search — 牵丝

通用的语义索引和搜索工具。保持**纯粹**——知道"文档"和"向量"，不知道业务字段（tags、category、title 等）。

## 首次使用

1. 检查项目根是否有 `.retrieval-index/config.json`
2. 不存在 → 询问用户要索引哪些目录，写入 config，然后执行首次索引
3. 存在 → 读 config，按需执行

## 索引管理

用户说"建索引""更新索引""索引状态""重建索引"时触发。

### 建索引 / 更新索引（标准入口：reindex.py）

```
python .claude/skills/inkwell-search/scripts/reindex.py [--dirs archived discussions creations]
```

全量重建（原子替换，重建期间搜索仍用旧索引，零中断）：
- 扫描 `config.json` 中 `source_dirs` 的全部 .md（缺失时默认 archived/discussions/creations）
- 对每个文件提取可索引文本（title + summary + tags + 正文）
- 调 indexer.py rebuild，重命名/删除的文件自动消失，新增文件自动纳入
- 完成后写回 `last_indexed_at`
- **每次采集后必须执行**（inkwell-capture Step 4 第 7 步已接入）
- **重建后自动跑 frontmatter 数据质量校验**（`validate_frontmatter.py`）：
  - `date`/`fetched_at` 必须是 YAML 日期或 ISO 格式，**禁止空格分隔**（如 `2026-07-30 10:42`）——这类值 Obsidian 的 js-yaml 解析为字符串，`dv.date()` 无法处理，会导致总览仪表盘 dataviewjs 抛错
  - 正文不得混入第二个 frontmatter 块（源站元数据残留，违反归档纯净化）
  - 校验失败 → reindex 返回非零，提醒先修复数据

> 低层命令 `indexer.py index`（增量追加）保留给临时补索引，**不作为采集后的标准路径**——它无法清除重命名/删除文件的旧向量，会导致索引残留。

### 单独校验

```
python .claude/skills/inkwell-search/scripts/validate_frontmatter.py
```

退出码 0 = 合规，1 = 发现问题。可在归档/验证后手动运行复查格式。

### 索引状态

```
python scripts/indexer.py status
```

返回：文档数、块数、上次更新时间、索引大小。

### 重建索引

```
python scripts/indexer.py rebuild --data <json_file>
```

- 全量重建前，先扫描所有源文件，拼接好 [(path, text), ...]
- 写入临时 JSON 文件
- 调 indexer.py rebuild，内部原子替换旧索引
- 重建期间搜索仍用旧索引，零中断

## 搜索

用户说"搜索XX""找XX相关的""有没有讲XX的"时触发。

### 语义搜索

```
python scripts/searcher.py search --query "<query>" [--granularity doc|chunk|both] [--top-k 5] [--threshold 0.75] [--exclude <paths>] [--scope <dirs>]
```

- 默认阈值 0.75（可在 config.json 调整）
- ≥0.75 的结果 → 展示内容（可注入上下文）
- <0.75 的结果 → 列清单让用户决定

### 去重检查

```
python scripts/searcher.py search --query "<text>" --granularity doc --top-k 1 --threshold 0.95
```

- 用于采集前检查是否已有高度相似内容
- 阈值 0.95（采集用，高于搜索默认值）

### 文本比较

```
python scripts/searcher.py compare --text-a "<text>" --text-b "<text>" [--strategy auto]
```

- 直接比较两段文本的相似度，不走索引
- strategy: auto（默认，<~500 字直接 encode，≥~500 字 chunk+pooling）| direct（直接 encode）| full（chunk+pooling）
- 用于采集更新判定（阈值 0.85）和创作版本管理（阈值 0.85）

## 配置

`.retrieval-index/config.json`：

```json
{
  "source_dirs": ["archived", "discussions", "creations"],
  "embedding_model": "BAAI/bge-small-zh-v1.5",
  "search_threshold": 0.75,
  "last_indexed_at": null
}
```

## 排除与范围限定

搜索时支持：
- `--exclude paths` — 排除指定文件（本次不想考虑某些文章）
- `--scope dirs` — 限定搜索范围（"只在 discussions 里搜"）

## 模型

- 默认 `BAAI/bge-small-zh-v1.5`（~100MB，CPU 友好，中文优化）
- 首次运行时 sentence-transformers 自动下载到 `/Users/xiesh/Codes/models/`
- 换模型：修改 config.json 或项目 `.env` 中的 `EMBEDDING_MODEL`，然后重建索引

## 故障排查

### 模型下载失败

检查网络连接，然后手动下载模型到 `/Users/xiesh/Codes/models/`，模型名称见 `.retrieval-index/config.json` 中的 `embedding_model` 字段。

### FAISS 索引损坏

删除 `.retrieval-index/` 下的 `.index` 文件，然后重建索引：

```
rm .retrieval-index/*.index
python scripts/indexer.py rebuild --data <json_file>
```

### 搜索结果为空

1. 检查 `search_threshold`（默认 0.75），尝试降低阈值 → 修改 `.retrieval-index/config.json` 中的 `search_threshold`
2. 确认索引不是空的 → `python scripts/indexer.py status` 查看文档数和块数

## 目录结构

```
{project}/
├── .retrieval-index/          ← 索引数据（本 Skill 管理）
│   ├── config.json
│   ├── doc.index / doc_map.json
│   └── chunk.index / chunk_map.json
└── .claude/skills/inkwell-search/    ← Skill 本身
    ├── SKILL.md
    ├── scripts/
    │   ├── indexer.py
    │   ├── searcher.py
    │   └── requirements.txt
    └── references/
        └── embedding-models.md
```
