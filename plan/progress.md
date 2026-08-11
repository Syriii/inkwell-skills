# Progress Log

## Session: 2026-08-11

### 三技能独立性与双宿主改造
- 将 `inkwell-capture`、`inkwell-search`、`inkwell-write` 明确为三个独立、自包含技能
- 移除兄弟技能引用、固定业务目录、隐式自动衔接和固定宿主路径
- 新增 Codex `agents/openai.yaml`，保留 Claude Code 独立安装布局
- 新增标准库验证器和契约测试，分别模拟三个技能在 Codex 与 Claude Code 中只安装自身
- 正式提交：`55b73d4`、`876efae`、`c498fce`、`ac0a5d1`

### `inkwell-capture` 煎蛋专用采集优化
- 使用 `https://jandan.net/t/6192383` 完成真实采集验证
- 新增 `scripts/forum/jandan.py` 与 `scripts/jandan_capture.py`
- L1 明确报告评论不完整，不再误报 `comment_count=1`
- 渲染层取得 10 条正式评论，排除 4 条热门重复，正文图片与 UI 图片精确分流
- 新增脱敏 fixture 与 6 项适配器回归测试；正式仓库 8 项独立性、双宿主与文档契约测试通过
- 正式提交：`f8168b2 feat(capture): add deterministic Jandan collector`

### 架构解释纠偏
- 用户再次强调三个技能必须各自独立运行
- 纠正将“同一技能的 Codex/Claude 兼容验证”表述为“跨宿主真实端到端测试”的误解
- 固化规则：宿主兼容与技能组合是正交维度；不再把三技能串联测试列为优化阶段
- 更新 README、CLAUDE、互操作约定、当前计划、发现记录和回归测试

---

## Session: 2026-07-16 (continued 2026-07-17)

### Phase 1: Collection Subsystem — Design
- **Status:** design review complete, awaiting final approval
- **Started:** 2026-07-16
- Actions taken:
  - Explored project context (empty repo)
  - Assessed scope: decomposed into 4 independent subsystems
  - Interviewed user on requirements (one question at a time per brainstorming skill)
  - Discussed architecture: hybrid skill + scripts, not standalone app
  - Designed project structure: .web-analysis.yaml + archived/ + discussions/ + drafts/ + published/
  - Designed archival format: Markdown + YAML frontmatter, date-based directories, subdirectory per item
  - Designed FAISS integration: auto-rebuild every 24h, background task, atomic replacement
  - Designed error fallback chains: web (3-tier), OCR (3-tier), image analysis (Claude vision)
  - Designed dedup strategy: source exact match + FAISS semantic similarity
  - Designed cross-subs linking: based_on frontmatter field
  - Selected all technologies: Python, trafilatura, PaddleOCR, Surya, KenLM, BGE-small-zh-v1.5, FAISS, sentence-transformers
  - Designed credential management: .env file, expired reminder
  - Designed model management: /Users/xiesh/Codes/models/, .env configurable
  - Reviewed design for defects: found 7 issues + 3 improvements, resolved
  - Set up planning-with-files structure (plan/)
  - Boundary review: content types, platforms, paywall, crawl delay, comment threshold, resume, L4
  - Second review (5 issues): tags/summary by Claude Code, update embedding threshold, forum domain learning, OCR quality fields, category/tags two-level system
  - Third review (6 issues): execution flow +Step 6, progress report URL/filename, templates/ removed, source field for non-URL, resume vs dedup mechanisms, Surya confirmed
  - Design spec complete: 11 sections, 8-step execution flow, 2-level category/tags, script-vs-Claude Code split, comprehensive boundaries
- Files createdified:
  - CLAUDE.md (created, updated multiple times)
  - docs/superpowers/specs/2026-07-16-collection-subs-design.md (created, updated with all fixes)
  - plan/task_plan.md (created)
  - plan/findings.md (created)
  - plan/progress.md (created)

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | All 3 skills implemented. Publish deferred. |
| Where am I going? | Ready to use: collect → discuss → create → publish (future) |
| What's the goal? | Build personal content pipeline as 4 independent on-demand Skills |
| What have I learned? | See findings.md + memory: architecture-four-independent-skills |
| What have I done? | Designed 3 skills (3-round review), implemented all 3 (21 files, 12 scripts, all tested) |

## Architecture rethink (2026-07-17)
Major shift this session — the "4 independent subsystems" framing was refined into a precise model:
- Four **平级独立** skills (collect / retrieval / discuss-create / publish), on-demand install, future GitHub project
- NOT layered (rejected "基础层/应用层" framing). Graded association instead: retrieval fully independent; collect optionally links retrieval (semantic dedup); discuss-create requires retrieval; publish standalone
- Skills don't call each other as hard deps — user orchestrates; data dirs are shared file conventions
- Retrieval = generic semantic index/search tool (knows documents+vectors, not tags/category). FAISS IndexFlatL2, persistent, incremental, under retrieval skill dir. Caller passes source dirs.
- Discussion + creation merged into one skill
- FAISS scale: personal use (100s-1000s vectors) → IndexFlatL2 exact & fast, no concern
- **Next:** ~~finish retrieval skill design~~ → all 4 skills designed; collection rework done; discuss-create designed (split→re-merged); publish deferred; ready for implementation

### Retrieval Skill Design (2026-07-17, continued after compact)
Decisions made this session:
1. **Pure/generic confirmed** — no tags/category listing; caller does grep/frontmatter
2. **Two-level index** — `doc.index` + `chunk.index`, separate FAISS files; usage boundaries: doc-level for dedup & related-articles, chunk-level for find-material/source; default rules + caller override (`doc`/`chunk`/`both`)
3. **Chunking = C (structure-first, length-fallback)** — heading-structured priority, ~500 char block cap, ~400 char + ~50 overlap for over-long sections & unstructured text
4. **Input contract** — caller concatenates `title+summary+tags+body` → passes to retrieval; retrieval never reads frontmatter, encodes whatever text given. Business fields NOT stored in index maps (maps only hold path/hash/text/offset). chunk_text stored in chunk map (return usable directly)
5. **5 API operations** — `index`, `search`, `dedup_check`, `remove`, `rebuild`
6. **Open: rebuild paradox** — rebuild needs to scan dirs and build text, but retrieval shouldn't read frontmatter. Solution TBD (text-builder callback? pre-built (path,text) pairs?)

### Session: 2026-07-20

### Retrieval Skill — design completed
All design decisions made and recorded. Design doc pending (will be written alongside implementation plan).

### Collection Skill — rework completed
Design doc (`2026-07-16-collection-subsystem-design.md`) fully updated:
- Removed all FAISS/indexer/retriever references; semantic dedup → optional call to retrieval Skill
- "子系统" → "Skill" throughout; architecture diagram updated to 5-skill model
- §7 FAISS section rewritten as "语义检索（检索 Skill）"
- Data directory, config, execution flow, dedup strategy all updated

### Discuss-Create Skill — designed, split then re-merged
- **Briefly split (2026-07-20)** into Discussion + Creation, then **re-merged within same session**
- Split rejected because: creation almost always builds on discussion; cross-discussion aggregation is natural within one skill
- **Final**: one Skill, two modes (讨论模式 / 创作模式)
- Discussion mode: dialog ↔ structured analysis, multi-round; Claude perceives rhythm; output summary + rounds
- Creation mode: 5-step (定方向→写提纲→出草稿→审阅→输出); version mgmt via embedding <0.85
- Shared `topics/{slug}/` with `discussion/` and `creation/` subdirectories
- Frontmatter types: `discussion`, `summary`, `outline`, `draft`, `article`
- Scripts: discussion_writer.py, references_builder.py, outline_writer.py, draft_writer.py
- Requires retrieval Skill (auto-inject ≥0.75)
- **Design doc**: `2026-07-20-discuss-create-skill-design.md` (merged)

### Architecture update
- 5 skills → 4 skills (Discuss-Create re-merged)
- Design complete for all 4 skills; publish deferred to future

### Collection design doc defects fixed
- §1.1 data directory: `discussions/` + `drafts/` → `topics/`
- §6.1 based_on examples: updated to new paths
- §6.2 data flow diagram: updated to topics/ structure

### Design doc final review & fixes (2026-07-20)
- All 3 design docs cross-reviewed for consistency (thresholds, frontmatter types, association tables, paths)
- **Collection doc**: 4 fixes — `discussions/`→`topics/`, added requirements.txt, clarified initialization dirs, expanded grep examples
- **Retrieval doc**: 4 fixes — `discussions`→`topics`, chunk size vs model limit note, added model availability check (§六), rebuild atomic replacement; renumbered sections (§六→§十)
- **Discuss-Create doc**: 2 fixes — added `category` to all frontmatter, added "安装时自动带检索 Skill"

### Second design review (2026-07-20)
Second cross-review of all 3 design docs. Found 8 issues, all fixed:

1. **检索缺少 compare 接口** — added `compare(text_a, text_b, strategy)` to searcher.py (§5.2), with `auto|direct|full` 三种策略，chunk+pooling 方案。Updated §3.3 注明分块复用，§8.1/§8.2 更新调用方式。Collection §3.1 和 Discuss-Create §4.2 同步更新。
2. **自动安装机制未定义** — Discuss-Create §7.1 写明 SKILL.md 启动首步检查+自动安装流程。
3. **tags 扫描范围过窄** — Collection §5.3 category 和 tags 都加上 `archived/` + `topics/`。
4. **采集列出非自有技术** — Collection §1.4 和 §十 移除 embedding/FAISS/sentence-transformers，改为标注"检索 Skill 管理"。
5. **Discuss-Create 缺初始化** — 新增 §1.1，覆盖检索检查、topics/ 创建、config.json 同步。
6. **"子项目"残留** — Collection §概述 改为"四个独立 Skill 之一"。
7. **KenLM 路径缺失** — Collection §1.4 目录树加入 `ocr/kenlm/`。
8. **round topic 语义模糊** — Round frontmatter `topic` → `round_title`，summary 保持 `topic`。

### Third design review (2026-07-20)
Final pass after all fixes. Found 3 minor issues, all fixed:
1. **Collection §7.1 表缺少 compare** — 关系表补充 `compare` 接口
2. **Discuss-Create §4.2 内联检索参数** — 移除策略细节（`<500字...`），改为只写 `strategy='auto'`，细节归检索 doc
3. **阈值符号不统一** — 0.95 的 `>` 改为 `≥`，全局统一用 `≥` 作触发边界

### Implementation phase — started 2026-07-20
All 3 design docs complete, cross-reviewed, and consistent. Implementation begins.
Order: Retrieval → Collection → Discuss-Create (Publish deferred)

### Retrieval Skill — implemented (2026-07-20)
- Created `.claude/skills/retrieval/` with full skill structure
- **SKILL.md**: workflow instructions covering index management, search, dedup, compare
- **indexer.py**: `index`, `rebuild`, `remove`, `status` — FAISS IndexFlatL2 + L2 normalization; chunking (structure-first, length-fallback); atomic rebuild with .new temp files
- **searcher.py**: `search` (doc/chunk/both granularity, scoping, excluding) + `compare` (auto/direct/full strategies, chunk+pooling for long text)
- **requirements.txt**: sentence-transformers>=2.7, faiss-cpu>=1.8, numpy>=1.26
- **references/embedding-models.md**: default BGE-small-zh-v1.5 + alternatives (bge-m3, bge-large, e5)
- All 4 operations tested and working (index, search, compare, rebuild)
- Bug fixed: _atomic_rebuild wrote maps to wrong paths (non-.new), get_embedding_dimension rename

### Collection Skill — implemented (2026-07-20)
- Created `.claude/skills/collect/` with full skill structure
- **SKILL.md**: 8-step execution flow with type detection, fallback chains, dedup, image download rules
- **archiver.py**: Archive writer — YYYYMMDD/{slug} dirs, YAML frontmatter + Markdown body, image download, slug generation (tested and working)
- **web_fetch.py** (L1): requests + trafilatura — metadata extraction, image detection, word count
- **web_fetch_full.py** (L2): Playwright rendering — headless Chromium, JS wait, cookie injection, graceful degradation when Playwright unavailable
- **forum_scraper.py**: V2EX + Tieba dedicated handlers + generic selector fallback, comment tree → unified Markdown
- **ocr_text.py**: PaddleOCR + KenLM quality evaluation, verdict (ok/degraded/poor), Surya/Claude vision fallbacks
- **requirements.txt**: trafilatura, requests, beautifulsoup4, lxml, playwright (optional), paddleocr+kenlm (optional)
- **references/**: frontmatter-schema.md (all 12 types), content-types.md (7 input types), error-handling.md (fallback chains + error codes)

### Discuss-Create Skill — implemented (2026-07-21)
- Created `.claude/skills/discuss-create/` with full skill structure
- **SKILL.md**: Two-mode orchestration (discussion + creation), startup auto-install retrieval, rhythm perception, 5-step creation workflow
- **discussion_writer.py**: write-round (rounds/NN-{角度}.md, type: discussion, round_title) + write-summary ({topic}讨论总结.md, type: summary, topic). Tested.
- **references_builder.py**: update (add/dedup wikilinks + excerpts) + show. Obsidian `[[path|label]]` format. Tested.
- **outline_writer.py**: write outline.md (type: outline, title). Tested.
- **draft_writer.py**: write (first draft / minor update) + archive-and-write (move current → drafts/vN.md, inject version field) + update-status (draft→review→article). Version numbering auto-increment. Tested all three commands.
- **references/frontmatter-schema.md**: discussion/creation type spec (discussion, summary, outline, draft, article)
- All 4 scripts tested end-to-end: round → summary → references → outline → draft → archive-and-write → update-status

### Future topics recorded
- Skill 触发自进化 (self-evolving skill triggers via community `claude-self-improving-skills` plugin)

### Inkwell Brand Rename (2026-07-21)
- Renamed 3 skills under **Inkwell** brand:
  - `.claude/skills/collect/` → `.claude/skills/clip/` (剪藏)
  - `.claude/skills/retrieval/` → `.claude/skills/thread/` (牵丝)
  - `.claude/skills/discuss-create/` → `.claude/skills/forge/` (熔裁)
- Updated all SKILL.md name fields, descriptions, titles, and cross-references
- Updated CLAUDE.md: project overview, structure diagram, brand description
- Updated plan/task_plan.md: all skill references, architecture table, phase labels
- Design docs retain historical filenames (dated specs)
- `.retrieval-index/` data dir name preserved (independent of skill rename)
- **Future roadmap**: tune, transcribe, digest, bridge, adapt, deck, send, cast

### 5-Question Reboot Check (updated)
| Question | Answer |
|----------|--------|
| Where am I? | Inkwell: clip/thread/forge implemented, post deferred |
| Where am I going? | Ready to use: clip → forge → post (future) |
| What's the goal? | Inkwell personal content pipeline: 4 independent Skills |
| What have I learned? | Brand naming: personal studio + serious OSS feel; Inkwell as writer's desk metaphor |
| What have I done? | Renamed all 3 skills to Inkwell brand; updated all cross-references |
