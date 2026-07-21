---
name: inkwell-search
description: >
  Inkwell search — 语义搜索、向量索引、内容相似度检测。当用户想搜索文档、
  查找相关内容、建立索引、检查内容重复时触发。基于 FAISS，通用工具——
  只知道"文档"和"向量"，不理解业务字段。
---

# inkwell-search

通用的语义索引和搜索工具。保持**纯粹**——知道"文档"和"向量"，不知道业务字段（tags、category、title 等）。

## 首次使用

1. 检查项目根是否有 `.retrieval-index/config.json`
2. 不存在 → 询问用户要索引哪些目录，写入 config，然后执行首次索引
3. 存在 → 读 config，按需执行

## 索引管理

用户说"建索引""更新索引""索引状态""重建索引"时触发。

### 建索引 / 更新索引

```
python scripts/indexer.py index --path <path> --text <encodable_text>
```

增量扫描逻辑：
- 遍历 config.json 中 `source_dirs` 的所有 .md 文件
- 对每个文件提取文本（title + 正文）
- 调 indexer.py 逐个增量索引
- content_hash 没变的文件自动跳过
- 源目录中已消失的文件自动从索引移除
- 完成后更新 `last_indexed_at`

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
  "source_dirs": ["archived", "topics"],
  "embedding_model": "BAAI/bge-small-zh-v1.5",
  "search_threshold": 0.75,
  "last_indexed_at": null
}
```

## 排除与范围限定

搜索时支持：
- `--exclude paths` — 排除指定文件（本次不想考虑某些文章）
- `--scope dirs` — 限定搜索范围（"只在 topics 里搜"）

## 模型

- 默认 `BAAI/bge-small-zh-v1.5`（~100MB，CPU 友好，中文优化）
- 首次运行时 sentence-transformers 自动下载到 `/Users/xiesh/Codes/models/`
- 换模型：修改 config.json 或项目 `.env` 中的 `EMBEDDING_MODEL`，然后重建索引

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
