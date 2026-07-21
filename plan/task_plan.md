# Task Plan: web-analysis

## Goal
Build a personal content pipeline as **four independent, self-contained** Claude Code Skills under the **Inkwell** brand (clip/thread/forge/post), each installable on-demand into any project. Future: package as a GitHub project.

## Architecture (settled 2026-07-17)
Four **平级独立** skills — each complete and standalone, with graded association (NOT layered dependency):

| Skill | Independent | Association |
|-------|:---:|------|
| thread (牵丝) | ✅ fully | needs nothing |
| clip (剪藏) | ✅ (no thread →每次当新内容) | **optional** link to thread (semantic dedup) |
| forge (熔裁) | ❌ needs thread | **required** thread (auto-inject ≥0.75) |
| post (寄雁) | ✅ fully | none |

- forge briefly split then re-merged (2026-07-20). Split proved wrong — creation almost always builds on discussion; cross-discussion aggregation is natural within one skill. One skill, two modes (讨论模式/创作模式), shared `topics/{slug}/` directory.
- Skills don't call each other as dependencies; user orchestrates. Data dirs are shared **file conventions**, not dependencies. `based_on` is optional provenance.
- FAISS index data lives under `.retrieval-index/` at project root; persistent, incremental, `IndexFlatL2`.
- thread is a **generic** semantic index/search tool — knows only "documents" and "vectors", not web-analysis-specific fields.

## Current Phase
All 3 skills implemented (clip, thread, forge). Post Skill deferred to future. Brand: **Inkwell**.

## Phases

### clip (剪藏, formerly collect)
- [x] Requirements, brainstorming, design spec (4 review rounds)
- [x] Boundaries, tags/category two-level, script-vs-Claude split, source field, execution flow
- [x] **REWORK:** remove indexer.py/retriever.py (belong to thread skill); semantic dedup becomes optional call to thread; precise dedup (URL/filename) stays built-in
- [x] Design doc updated: all FAISS/indexer/retriever references removed or redirected to thread; "子系统" → "Skill" throughout
- **Status:** ✅ implemented

### thread (牵丝, formerly retrieval)
- [x] Core philosophy: pure/generic — vectors + documents only; no business fields
- [x] Two-level index: `doc.index` + `chunk.index`, separate FAISS files
- [x] Usage boundaries: default rules + caller override (`doc`/`chunk`/`both`)
- [x] Chunking: structure-first (heading), length-fallback (~500 char cap, ~400 + ~50 overlap)
- [x] Input contract: caller concatenates title+summary+tags+body → passes to retrieval; retrieval never reads frontmatter
- [x] Index metadata: doc map (path, content_hash, indexed_at); chunk map (path, chunk_text, chunk_index)
- [x] User-facing: only 2 capabilities — **索引管理** (index/update/rebuild/status) + **搜索** (semantic search, dedup check, 排除/范围限定)
- [x] Script-layer: `index`, `search`, `remove`(auto), `rebuild`, `compare`(text_a, text_b, strategy) — internal functions, not exposed to user
- [x] `compare`: 三种策略 auto|direct|full，auto 按长度自动选 direct 或 chunk+pooling
- [x] 删除=自动 (scan detects missing→auto-clean); 排除=搜索时临时过滤, not delete
- [x] Config: index data at `<project>/.retrieval-index/` (name matches skill, avoids conflict); one index per project; another project → another index
- [x] Source dirs persisted in `.retrieval-index/config.json`; first use prompts user to configure; later runs auto-read config
- [x] Skill file structure: `SKILL.md` (对话编排) + `scripts/indexer.py` (建/追加索引) + `scripts/searcher.py` (语义搜索) + `requirements.txt`
- [x] `rebuild`: accepts `[(path, text)]`, caller does dir-scan+text-building; retrieval stays pure
- [x] Search threshold: default 0.75 (cosine), adjustable via config
- [x] Above threshold → auto-inject content into context (@-like); below → list for user to pick
- [x] Design doc: `docs/superpowers/specs/2026-07-20-retrieval-skill-design.md`
- [x] **IMPLEMENTED**: SKILL.md + indexer.py + searcher.py + requirements.txt + embedding-models.md
- **Status:** ✅ complete

### forge (熔裁, formerly discuss-create)
- [x] Split then re-merged (2026-07-20). Split rejected: creation builds on discussion; cross-discussion aggregation natural within one skill
- [x] Two modes: **讨论模式** (dialog ↔ structured analysis, multi-round) + **创作模式** (定方向→写提纲→出草稿→审阅→输出)
- [x] Output structure: `topics/{slug}/discussion/` + `topics/{slug}/creation/` under same topic
- [x] Discussion output: `{topic}讨论总结.md` (type: summary) + `rounds/NN-{topic}.md` (type: discussion)
- [x] Creation output: `outline.md` (type: outline), `article.md` (type: draft→article), `drafts/`, `images/`
- [x] Version mgmt: embedding similarity <0.85 → save to drafts/ before update
- [x] References: wikilinks + key excerpts; references.md in discussion dir
- [x] Entry points: user "讨论XX", provides material+intent, clip result→forge bridge, browse content
- [x] Claude perceives discussion rhythm (new round / end)
- [x] Requires thread Skill (auto-inject ≥0.75); SKILL.md 启动自检+自动安装
- [x] Scripts: discussion_writer.py, references_builder.py, outline_writer.py, draft_writer.py
- [x] 初始化流程: 检查检索 Skill → 创建 topics/ → 同步 config.json source_dirs
- [x] Round frontmatter `round_title`（本轮角度），summary frontmatter `topic`（整体主题）
- [x] Design doc: `docs/superpowers/specs/2026-07-20-discuss-create-skill-design.md`
- **Status:** ✅ implemented

### post (寄雁, formerly publish)
- [ ] Requirements & design → **deferred to future**（首篇文章准备发布时再设计）

### Inkwell Brand — Rename (2026-07-21)
- [x] Renamed skills: collect→clip, retrieval→thread, discuss-create→forge
- [x] Updated all SKILL.md files, CLAUDE.md, plan files
- [ ] Update design docs
- **Status:** ✅ complete

## Key Questions
1. L4+ anti-crawl? → fallback manual copy/paste or full-page screenshot OCR
2. OCR quality eval? → PaddleOCR confidence + KenLM perplexity dual signals
3. Multimodal image analysis? → Claude Code vision directly, no script
4. Model dependencies? → `/Users/xiesh/Codes/models/`, `.env` configurable
5. ~~Does retrieval skill handle tags/category listing~~ → **RESOLVED: pure** (caller does grep/frontmatter)
6. Skill naming (dirs) — collect/retrieval/discuss-create/publish, exact names TBD
7. **How does `rebuild` scan dirs + build text without knowing frontmatter?** → caller provides "text builder" callback, or rebuild accepts list of (path, text) pairs?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Four independent平级 skills, on-demand install | Each usable standalone; user orchestrates; Inkwell brand; future GitHub project |
| thread as separate generic skill | FAISS logic in one place; clip optional, forge required |
| forge (discussion + creation merged) | Normal flow is discuss-then-create; even direct creation needs clarifying Qs |
| FAISS IndexFlatL2, persistent, under retrieval skill dir | Personal scale (100s-1000s), exact & fast; incremental add |
| Source dirs passed by caller | Retrieval stays generic, not bound to web-analysis dir names |
| Skill + scripts hybrid | Scripts for deterministic work, Skill for judgment/dialogue |
| Markdown + YAML frontmatter | Obsidian-compatible, human-readable |
| trafilatura / PaddleOCR→Surya→Claude vision / BGE-small-zh-v1.5 | Chinese-optimized tech choices |
| Precise dedup built into collect; semantic dedup optional via retrieval | Collect self-contained without retrieval |
