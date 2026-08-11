---
name: inkwell-search
description: >
  Inkwell 牵丝技能。语义索引和搜索工具。当用户想对文档内容进行语义搜索、
  查找相关文档、检查内容相似度、建立或更新索引时触发。也适用于
  "帮我索引这些文件""搜索XX相关的内容""这篇文章跟已有的有没有重复"等场景。
  这是一个通用工具——只依赖文档路径和文本，不要求特定业务目录或元数据结构。
---

# inkwell-search — 牵丝

通用的语义索引和搜索工具。保持**纯粹**——只要求文档路径和文本；可以利用常见 Markdown 元数据，但不依赖特定业务目录或 schema。

## 独立能力边界

- **输入**：用户指定的文档目录、文本、查询或两段待比较内容。
- **输出**：本地向量索引、结构化搜索结果或相似度结果。
- **成功条件**：仅凭本技能脚本和自身配置即可完成建索引、搜索、比较与状态查询。
- **边界**：不修改源文档，不校验其他业务格式，不猜测默认内容目录。

## 运行时约定

- 将当前 `SKILL.md` 所在目录解析为 `<skill-dir>`，将当前项目根解析为 `<project-root>`；所有命令从 `<project-root>` 执行。
- 将模型缓存目录解析为 `<models-dir>`：优先读取项目环境配置，未配置时使用 sentence-transformers 默认缓存；不要硬编码用户名或机器路径。
- 本技能不依赖 Codex 或 Claude Code 的专属工具，两个宿主调用同一组 Python 脚本。
- 正常的索引、搜索、比较和状态查询直接执行下方已文档化的 CLI，不预先通读脚本源码；仅在命令失败、需要调试或用户要求修改实现时读取对应脚本。
- 只在切换模型或遇到宿主差异时读取对应参考文件，普通索引与搜索不加载无关参考。

## 首次使用

1. 检查项目根是否有 `.retrieval-index/config.json`
2. 不存在 → 询问用户要索引哪些目录，写入 config，然后执行首次索引
3. 存在 → 读 config，按需执行

## 索引管理

用户说"建索引""更新索引""索引状态""重建索引"时触发。

### 建索引 / 更新索引（标准入口：reindex.py）

```
python <skill-dir>/scripts/reindex.py [--dirs docs notes]
```

全量重建（原子替换，重建期间搜索仍用旧索引，零中断）：
- 扫描 `--dirs` 或 `config.json` 中 `source_dirs` 指定的全部 `.md`
- 对每个文件提取可索引文本（title + summary + tags + 正文）
- 调 indexer.py rebuild，重命名/删除的文件自动消失，新增文件自动纳入
- 完成后写回 `last_indexed_at`
- 没有 `--dirs` 且 config 未配置 `source_dirs` 时明确报错，不猜测业务目录

> 低层命令 `indexer.py index`（增量追加）保留给临时补索引，不作为常规维护路径——它无法清除重命名/删除文件的旧向量，会导致索引残留。

### 索引状态

```
python <skill-dir>/scripts/indexer.py status
```

返回：文档数、块数、上次更新时间、索引大小。

### 重建索引

```
python <skill-dir>/scripts/indexer.py rebuild --data <json_file>
```

- 全量重建前，先扫描所有源文件，拼接好 [(path, text), ...]
- 写入临时 JSON 文件
- 调 indexer.py rebuild，内部原子替换旧索引
- 重建期间搜索仍用旧索引，零中断

## 搜索

用户说"搜索XX""找XX相关的""有没有讲XX的"时触发。

### 语义搜索

```
python <skill-dir>/scripts/searcher.py search --query "<query>" [--granularity doc|chunk|both] [--top-k 5] [--threshold 0.75] [--exclude <paths>] [--scope <dirs>]
```

- 默认阈值 0.75（可在 config.json 调整）
- ≥0.75 的结果 → 展示内容（可注入上下文）
- <0.75 的结果 → 列清单让用户决定

### 高阈值相似内容检查

```
python <skill-dir>/scripts/searcher.py search --query "<text>" --granularity doc --top-k 1 --threshold 0.95
```

- 用于检查是否已有高度相似内容
- 阈值 0.95（高于搜索默认值）

### 文本比较

```
python <skill-dir>/scripts/searcher.py compare --text-a "<text>" --text-b "<text>" [--strategy auto]
```

- 直接比较两段文本的相似度，不走索引
- strategy: auto（默认，<~500 字直接 encode，≥~500 字 chunk+pooling）| direct（直接 encode）| full（chunk+pooling）
- 可用于重复检测、版本差异参考或任意两段文本的语义比较

## 配置

`.retrieval-index/config.json`：

```json
{
  "source_dirs": ["docs", "notes"],
  "embedding_model": "BAAI/bge-small-zh-v1.5",
  "search_threshold": 0.75,
  "last_indexed_at": null
}
```

## 排除与范围限定

搜索时支持：
- `--exclude paths` — 排除指定文件（本次不想考虑某些文章）
- `--scope dirs` — 限定搜索范围（如“只在 notes 里搜”）

## 模型

- 默认 `BAAI/bge-small-zh-v1.5`（~100MB，CPU 友好，中文优化）
- 优先使用 `<models-dir>/` 中的本地缓存；缓存缺失时 sentence-transformers 才自动下载
- 换模型：修改 config.json 或项目 `.env` 中的 `EMBEDDING_MODEL`，然后重建索引

## 故障排查

### 模型下载失败

检查网络连接，然后手动下载模型到 `<models-dir>/`，模型名称见 `.retrieval-index/config.json` 中的 `embedding_model` 字段。

### FAISS 索引损坏

删除 `.retrieval-index/` 下的 `.index` 文件，然后重建索引：

```
rm .retrieval-index/*.index
python <skill-dir>/scripts/indexer.py rebuild --data <json_file>
```

### 搜索结果为空

1. 检查 `search_threshold`（默认 0.75），尝试降低阈值 → 修改 `.retrieval-index/config.json` 中的 `search_threshold`
2. 确认索引不是空的 → `python <skill-dir>/scripts/indexer.py status` 查看文档数和块数

## 目录结构

```
{project}/
├── .retrieval-index/          ← 索引数据（本 Skill 管理）
│   ├── config.json
│   ├── doc.index / doc_map.json
│   └── chunk.index / chunk_map.json
└── <skill-dir>/            ← Skill 本身（实际位于宿主发现的技能目录）
    ├── SKILL.md
    ├── scripts/
    │   ├── indexer.py
    │   ├── searcher.py
    │   ├── reindex.py
    │   └── requirements.txt
    └── references/
        └── embedding-models.md
```
