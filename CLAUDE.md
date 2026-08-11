# CLAUDE.md — Inkwell Skills

## 项目概述

Inkwell 是同时支持 Codex 与 Claude Code 的三个独立、自包含技能：

- `inkwell-capture/` — 获取、清洗并归档 URL、文件、截图或媒体。
- `inkwell-search/` — 为用户指定的 Markdown 目录建立语义索引并搜索或比较文本。
- `inkwell-write/` — 从主题或任意用户材料开展讨论、提纲规划和版本化创作。

它们不是必须串联的管线。任何技能目录都不得发现、安装、调用或要求另一个 Inkwell 技能，也不得假设另一个技能的业务目录存在。组合只能由用户或上层工作流通过普通文件和明确路径完成。

## 架构解释护栏

- **技能独立性**：描述三个技能之间的关系。每个技能必须独立安装、独立运行、独立达到成功条件。
- **宿主兼容性**：描述同一个技能可以运行在 Codex 或 Claude Code。它与技能组合是两个正交维度。
- “Codex/Claude 单技能安装测试”不得简称为“三技能端到端测试”或“跨宿主工作流”。
- 不得把三个技能串联运行列为默认验收、下一阶段或独立性证明。只有用户明确要求设计上层工作流时，才讨论基于普通文件的显式组合；这不会改变技能本身的独立架构。

## 目录结构

```text
inkwell-skills/
├── README.md
├── CLAUDE.md
├── docs/interop.md
├── scripts/validate-skills.py
├── tests/test_skill_contracts.py
├── inkwell-capture/
├── inkwell-search/
└── inkwell-write/
```

每个技能目录包含自己的 `SKILL.md`、`agents/openai.yaml` 和所需的 `scripts/`、`references/`。不要新增跨技能共享运行目录。

## 开发规则

1. 保持每个 `SKILL.md` 的 frontmatter 只有 `name` 和 `description`。
2. 路径以当前技能目录和内容项目根为运行时变量，不硬编码 `.claude/skills`、`.codex/skills`、用户名或机器路径。
3. 技能目录内禁止出现其他 Inkwell 技能名、路径占位符或对方业务目录。
4. 新增脚本必须实际运行；修改后至少执行：

   ```bash
   python3 scripts/validate-skills.py
   python3 -m unittest discover -s tests -v
   ```

5. 三个技能必须分别在“只安装自身”的 Codex 与 Claude Code 目录形态下通过验证；不得创建要求三个技能同时存在的技能契约测试。
6. 提交前运行 `git diff --check`，不要提交 `__pycache__`、模型、索引或内容项目产物。

## 分支策略

- `develop`：日常开发与验证通过的本地提交。
- `master`：稳定发布版本，只接受来自 `develop` 的合并。
- 未经用户明确要求不 push。

## 仓库

GitHub: https://github.com/Syriii/inkwell-skills
