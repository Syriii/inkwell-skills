# Findings & Decisions

## Requirements
- Collect web pages, forums, screenshots, chat records via manual trigger
- Output archived Markdown with structured frontmatter
- FAISS semantic search across all archived content
- Mostly Chinese content, occasionally English
- Each subsystem independently usable
- Multiple unrelated discussions can combine for creative output
- Credentials in `.env`, models in `/Users/xiesh/Codes/models/`
- Natural language skill triggers, not just slash commands

## Research Findings
- trafilatura is the best Python library for Chinese web content extraction (supports forums, structured JSON output)
- PaddleOCR has best Chinese OCR quality among free options (~85-90%), with layout analysis
- KenLM provides lightweight (30MB) language model for OCR quality validation
- BGE-small-zh-v1.5 is the best balance of size (100MB) and Chinese embedding quality
- FAISS is the lightest vector index option (file-based, no server)
- EmbeddingGemma-300m via Ollama is good but requires background process — rejected
- Qwen3-Embedding-0.6B has best quality but needs GPU — overkill for this project

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Python for all scripts | Best ecosystem for FAISS, OCR, embedding, crawling |
| trafilatura over readability | Chinese optimization, forum support, maintained |
| PaddleOCR over Tesseract | Much better Chinese recognition, layout analysis |
| sentence-transformers over Ollama | No background process, pure Python |
| BGE-small-zh-v1.5 over m3e | Smaller (100MB vs 400MB), good enough quality |
| FAISS over ChromaDB/LanceDB | Simplest, file-as-index, no service |
| Claude Code vision over multimodal.py | No external API needed, simpler |
| `.env` for credentials | Standard, gitignored, familiar pattern |

## Resources
- Design spec: `docs/superpowers/specs/2026-07-16-collection-subsystem-design.md`
- CLAUDE.md: project overview & dev environment
- baoyu-skills: reference for skill structure patterns (baoyu-post-to-wechat, baoyu-wechat-summary)
- Model storage: `/Users/xiesh/Codes/models/`
- Conda env: `web-analysis` (Python 3.12)

## Boundary Decisions
| Boundary | Decision |
|----------|----------|
| Content types | All types supported; different processing paths per type |
| Platforms | All in scope; Chinese platforms prioritized |
| Paywall | Cookie-accessible only; paid subscriptions excluded |
| Crawl rate | Default 3s between same-domain requests; per-domain override |
| Comment length | Ask user when replies exceed threshold (default 500) |
| Resume/retry | Lightweight content-change check → resume if unchanged, full re-collect if changed |
| L4 anti-crawl | Not implemented; Cloudflare/captcha fall back to manual; added to future roadmap |

## Retrieval Skill Design Decisions
| Decision | Rationale |
|----------|-----------|
| Stays pure/generic — vectors + documents only | Reusable for any project; tag/category queries are web-analysis business concepts → caller does grep/frontmatter, not retrieval |
| Two indexes: `doc.index` (doc-level) + `chunk.index` (chunk-level) | Serve different scenes; dedup scans only doc-level, chunk rebuild doesn't touch doc; clean separation |
| Grade default rule + user override | Default: dedup→doc, find-material→chunk, find-related-article→doc. Caller may pass `doc`/`chunk`/`both` to override |
| Usage boundary: "which doc?" → doc-level; "which passage?" → chunk-level | Dedup & related-article are doc-vs-doc; find-material/source are passage-level |
| Chunking = structure-first, length-fallback (C) | Content mostly has heading structure (best semantic edges); over-long sections & unstructured OCR need length cap. BGE-small ~512 token limit forces a size ceiling anyway |
| Chunk params (tunable at impl): section-first, ~500 char/block cap; over-limit → split ~400 char + ~50 overlap; unstructured → 400/50 | Personal scale; tune after seeing real results |
| Index metadata sidecar (FAISS stores only vector+int id) | doc.index map: id→{path, content_hash, indexed_at}; chunk.index map: id→{path, chunk_text, chunk_index} |
| Store chunk_text (原文) in chunk map, not just offsets | Personal scale, space cheap; retrieval返回即可用, caller需引用段落直接拿 |
| title/summary/tags **assist retrieval** but retrieval stays pure | Caller (e.g. collect) concatenates `title+summary+tags+正文` into ONE encodable text and passes it to retrieval. Retrieval never reads frontmatter, doesn't know these field names — just encodes the text given. Doc-level vector benefits from summary (denser than truncated body); chunk-level uses chunk raw text only (no summary pollution) |
| Business fields NOT stored in index map | tags/category/summary live in archived files; retrieval map holds only generic fields (path/hash/text/offset); caller re-reads frontmatter by path |
| **Retrieval input contract** | Caller passes (path, encodable-text) to index; retrieval returns (path, score) for doc / (path, chunk_text, chunk_index, score) for chunk. Retrieval has zero business knowledge |
| Search similarity threshold: default 0.75 (cosine), adjustable via config | Industry standard for BGE/FAISS (LangChain, OpenAI embeddings); supports per-project tuning |
| Above threshold → auto-inject into context; below → list + user decides | Retrieval returns scores; caller handles the @-like auto-injection |

## Future Topics (远期优化)
| Topic | Notes |
|-------|-------|
| Skill 触发自进化 | 用户手动纠正未触发的调用后，自动优化 SKILL.md description；社区已有 `claude-self-improving-skills` 插件（基于 Hermes Agent 的自我进化能力），可作为基础。后续单独讨论 |


