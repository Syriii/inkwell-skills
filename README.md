# Inkwell — Claude Code Skills for Personal Content Pipeline

三个独立、可组合的 Claude Code 技能，覆盖完整的内容工作流：采集 → 搜索 → 写作。

## Skills

| 技能 | 功能 |
|------|------|
| [**inkwell-capture**](./inkwell-capture/SKILL.md) | 网页采集、爬虫、截图 OCR、图片分析 → 归档为 Markdown |
| [**inkwell-search**](./inkwell-search/SKILL.md) | 语义搜索、向量索引（FAISS），通用文档检索工具 |
| [**inkwell-write**](./inkwell-write/SKILL.md) | AI 辅助讨论 + 文章创作，自动关联历史素材 |

```
inkwell-capture (采集) → archived/
                            ↓
inkwell-search (搜索)   → .retrieval-index/
                            ↓
inkwell-write (写作)     ← 自动检索相关内容
```

## 安装

每个技能独立可用，复制到任意项目的 `.claude/skills/` 即可：

```bash
# 全部安装
cp -r inkwell-capture inkwell-search inkwell-write /path/to/project/.claude/skills/

# 按需安装
cp -r inkwell-capture /path/to/project/.claude/skills/
```

## 依赖

- Python ≥ 3.12
- 各技能的 Python 依赖见 `<skill>/scripts/requirements.txt`
- 首次使用时，技能会自动检查环境并创建配置文件

## 配置

首次触发时自动创建 `.web-analysis.yaml`。可选自定义：

- `EMBEDDING_MODEL` — 嵌入模型（默认 `BAAI/bge-small-zh-v1.5`）
- `WEB_ANALYSIS_MODELS_DIR` — 模型存放目录（默认 `~/.web-analysis/`）

在项目 `.env` 中设置即可。

## License

MIT
