# AGENTS.md — Inkwell Skills

## 项目概述

Inkwell 是三个独立、可组合的 Codex 技能，分别提供**采集、搜索、写作**能力。

- `inkwell-capture/` — 网页采集、爬虫、截图 OCR、图片分析，归档为 Markdown
- `inkwell-search/` — 语义搜索、向量索引（FAISS），通用文档检索
- `inkwell-write/` — AI 辅助讨论 + 文章创作，自动关联历史素材

日常内容工作（采集、分析、创作）在 `~/writing/web-analysis/` 进行。使用过程中发现的 Skill 改进在此仓库同步和版本管理。

## 不可误读的架构约束

- “可组合”只表示用户可以显式传递普通文件，不表示自动调用、固定顺序或强制管线。
- 三个技能必须分别独立安装和运行；任何技能不得发现、安装、调用或要求另外两个技能。
- Codex/Claude 兼容描述同一个技能的宿主适配，与三技能是否组合无关。
- 不得把单技能双宿主验证称为“三技能端到端测试”，也不得将三技能串联列为默认验收或下一阶段。
- 只有用户明确要求上层组合工作流时才讨论文件级编排；单个技能的独立边界保持不变。

详细定义见 `docs/interop.md`。

## 目录结构

```
inkwell-skills/
├── README.md
├── AGENTS.md
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

日常开发在 `develop` 分支，版本稳定后合并到 `master` 并打 tag。

## 仓库

GitHub: https://github.com/Syriii/inkwell-skills
