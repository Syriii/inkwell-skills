# Inkwell 技能间互操作约定

四个技能通过以下方式协作：

## 目录约定

| 目录 | 读写技能 |
|------|---------|
| `archived/` | capture 写，search 索引，write 读取 |
| `topics/` | write 读写，search 索引 |
| `published/` | write 写 |
| `.retrieval-index/` | search 管理 |

## 技能间调用

- **capture → search**: 采集后追加 FAISS 索引
- **capture → write**: 采集完成后衔接讨论
- **write → search**: 讨论/创作前搜索相关素材

## 命名约定

| 本地 skill 名 | inkwell-skills 包名 |
|--------------|-------------------|
| clip | inkwell-capture |
| thread | inkwell-search |
| forge | inkwell-write |
| post | inkwell-publish |

## 路径引用

Skill 内部引用其他 skill 的脚本时使用相对路径：
```
.claude/skills/{skill-name}/scripts/{script}.py
```

项目相关路径使用 `{project_root}` 占位符，由执行时的工作目录确定。
