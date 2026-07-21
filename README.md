# Inkwell 墨井 — Personal Content Pipeline

Inkwell 是一套 Claude Code 技能（Skills），构建个人内容处理的完整流水线。三个技能各自独立、可单独安装使用，组合起来覆盖从采集到创作的全流程。

> Inkwell means "ink well" (墨井) — where the ink is drawn before writing.

## 技能一览

| 技能 | 能做啥 | 单独用？ |
|------|--------|----------|
| [**clip**](./clip/SKILL.md) — 剪藏 | 抓网页、论坛帖子、截图 OCR、图片分析 → 归档为 Markdown | ✅ |
| [**thread**](./thread/SKILL.md) — 牵丝 | 语义索引和搜索（FAISS），只知道"文档+向量"的通用工具 | ✅ |
| [**forge**](./forge/SKILL.md) — 熔裁 | AI 辅助讨论 + 文章创作，自动关联历史内容 | ✅（会自动装 thread） |

```
clip (采集) → archived/
                ↓
thread (索引) → .retrieval-index/
                ↓
forge (讨论/创作) ← 自动检索相关内容
```

## 安装

每个技能是独立的，复制到任意项目的 `.claude/skills/<name>/` 即可使用：

```bash
# 安装全部技能到你的项目
cp -r clip forge thread /path/to/your-project/.claude/skills/

# 或者只安装其中一个
cp -r clip /path/to/your-project/.claude/skills/
```

## 依赖

- Python ≥ 3.12
- 各技能自己的 Python 依赖见 `<skill>/scripts/requirements.txt`
- 首次使用时，技能会自动检查环境

## 配置

技能在首次触发时会自动创建项目配置文件 `.web-analysis.yaml`。如需自定义：

- **嵌入模型**：在项目 `.env` 中设置 `EMBEDDING_MODEL`（默认 `BAAI/bge-small-zh-v1.5`）
- **模型目录**：在项目 `.env` 中设置 `WEB_ANALYSIS_MODELS_DIR`（默认 `~/.web-analysis/`）

## License

MIT
