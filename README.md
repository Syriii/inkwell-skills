# Inkwell — Codex 与 Claude Code 独立技能集

Inkwell 包含三个彼此独立、自包含的内容技能。可以只安装其中一个，也可以同时安装多个；技能之间不会自动发现、安装或调用，只通过用户明确指定的普通文件自然组合。

“同时支持 Codex 与 Claude Code”是单个技能的宿主兼容能力，不是三技能联动模式。开发与验收始终以每个技能单独安装、单独完成自身任务为基本单位。

## 技能

| 技能 | 独立输入 | 输出 |
|------|----------|------|
| [**inkwell-capture**](./inkwell-capture/SKILL.md) | URL、本地文件、截图或媒体 | 结构化 Markdown 与本地资源 |
| [**inkwell-search**](./inkwell-search/SKILL.md) | 任意 Markdown 目录、查询或两段文本 | 本地向量索引、搜索或相似度结果 |
| [**inkwell-write**](./inkwell-write/SKILL.md) | 主题、文字、文件、链接或讨论记录 | 讨论、引用、提纲与版本化文章 |

详细边界见 [文件互操作约定](./docs/interop.md)。

## 安装

三个目录都是可单独安装的完整技能。

### Codex

复制需要的技能到 Codex 用户技能目录：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R inkwell-capture "${CODEX_HOME:-$HOME/.codex}/skills/"
```

### Claude Code

复制需要的技能到项目技能目录：

```bash
mkdir -p /path/to/project/.claude/skills
cp -R inkwell-capture /path/to/project/.claude/skills/
```

将 `inkwell-capture` 换成 `inkwell-search` 或 `inkwell-write` 即可独立安装其他技能；也可以按同样方式复制多个目录。

## 运行依赖与配置

- Python 依赖分别列在各技能的 `scripts/requirements.txt` 中；不要为未使用的技能安装依赖。
- `inkwell-capture` 首次使用时在内容项目内维护自己的归档配置。
- `inkwell-search` 在内容项目的 `.retrieval-index/config.json` 中记录索引配置和 `source_dirs`。
- `inkwell-write` 可从空白主题或用户材料直接开始，不要求知识库或索引。
- 任何包安装、联网、浏览器或外部服务操作都遵守当前宿主的权限策略。

## 开发验证

正式仓库可以脱离开发工作区独立验收：

```bash
python3 scripts/validate-skills.py
python3 -m unittest discover -s tests -v
```

验证器只使用 Python 标准库，检查结构、Codex 元数据、双宿主路径契约、Python 语法和三个技能之间的边界。

## License

MIT
