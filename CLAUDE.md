# CLAUDE.md — Inkwell Skills

## 项目概述

Inkwell 是三个独立、可组合的 Claude Code 技能，覆盖内容工作流：**采集 → 搜索 → 写作**。

- `inkwell-capture/` — 网页采集、爬虫、截图 OCR、图片分析，归档为 Markdown
- `inkwell-search/` — 语义搜索、向量索引（FAISS），通用文档检索
- `inkwell-write/` — AI 辅助讨论 + 文章创作，自动关联历史素材

日常内容工作（采集、分析、创作）在 `~/writing/web-analysis/` 进行。使用过程中发现的 Skill 改进在此仓库同步和版本管理。

## 目录结构

```
inkwell-skills/
├── README.md
├── CLAUDE.md
├── .gitignore
├── docs/
│   └── specs/                 ← Skill 设计文档
│       ├── 2026-07-16-collection-subsystem-design.md
│       ├── 2026-07-20-retrieval-skill-design.md
│       └── 2026-07-20-discuss-create-skill-design.md
├── plan/                      ← Skill 开发规划
│   ├── task_plan.md           ← 架构、阶段、决策
│   ├── findings.md            ← 技术选型、设计决策
│   └── progress.md            ← 开发进展日志
├── inkwell-capture/           ← clip (剪藏) Skill
│   ├── SKILL.md
│   ├── scripts/
│   └── references/
├── inkwell-search/            ← thread (牵丝) Skill
│   ├── SKILL.md
│   ├── scripts/
│   └── references/
└── inkwell-write/             ← forge (熔裁) Skill
    ├── SKILL.md
    ├── scripts/
    └── references/
```

## 分支策略

```
master   ← 稳定发布版本（只接受来自 develop 的合并）
  ↑
develop  ← 日常开发分支（所有改动先提交到这里）
```

- **`master`**：稳定版本，仅从 `develop` 合并，不直接提交。
- **`develop`**：日常开发分支，所有新功能、修复、重构都先提交到此分支。
- 当一个版本明确、稳定后，将 `develop` 合并到 `master` 并打 tag。

### 工作流程

```bash
# 日常开发在 develop 上
git checkout develop
git add ...
git commit -m "feat: ..."
git push origin develop

# 版本发布时合并到 master
git checkout master
git merge develop
git push origin master
git checkout develop  # 回到 develop 继续开发
```

## 仓库

GitHub: https://github.com/Syriii/inkwell-skills
