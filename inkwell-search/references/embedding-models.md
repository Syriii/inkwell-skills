# 支持的 Embedding 模型

## 默认模型

### BAAI/bge-small-zh-v1.5
- **大小**: ~100MB
- **向量维度**: 512
- **最大输入**: ~512 token
- **语言**: 中文优化，支持英文
- **性能**: CPU 友好，个人规模无压力
- **适用场景**: 默认推荐，所有 Skill 共用

## 备选模型

以下模型可通过修改 config.json 的 `embedding_model` 切换。

### BAAI/bge-m3
- **大小**: ~2.2GB
- **向量维度**: 1024
- **最大输入**: 8192 token
- **语言**: 多语言（中英等 100+ 语言）
- **性能**: CPU 可跑但较慢，建议 GPU
- **适用场景**: 长文本不需要 chunk+pooling，直接一次 encode

### BAAI/bge-large-zh-v1.5
- **大小**: ~1.3GB
- **向量维度**: 1024
- **最大输入**: ~512 token
- **语言**: 中文优化
- **性能**: CPU 较慢，精度高于 small

### intfloat/multilingual-e5-small
- **大小**: ~470MB
- **向量维度**: 384
- **最大输入**: ~512 token
- **语言**: 多语言
- **备注**: 使用时 query 需加 "query: " 前缀，文档需加 "passage: " 前缀

## 切换模型

1. 修改 `.retrieval-index/config.json` 中的 `embedding_model`
2. 或修改项目 `.env` 中的 `EMBEDDING_MODEL`
3. 重建索引：`python scripts/indexer.py rebuild --data <(构建好的数据)`

## 模型存放

所有模型缓存到 `<models-dir>/embedding/`，由 sentence-transformers 自动管理。
