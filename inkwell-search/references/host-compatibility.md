# 宿主兼容说明

inkwell-search 的核心能力完全由 Python 脚本提供，Codex 与 Claude Code 使用相同接口。

- `<skill-dir>`：当前 `inkwell-search/SKILL.md` 的父目录。
- `<project-root>`：包含 `.retrieval-index/` 的内容项目根。
- `<models-dir>`：从 `WEB_ANALYSIS_MODELS_DIR`、项目 `.env` 或 sentence-transformers 默认缓存解析。
- 从 `<project-root>` 执行命令，并对脚本使用已解析的绝对路径，避免工作目录漂移。
- 缺少 Python 包或模型时，先说明依赖、用途和体积，获得用户同意后再安装或下载。
- 索引和模型缓存是可重建的本地产物，不因宿主不同而写入不同业务格式。
