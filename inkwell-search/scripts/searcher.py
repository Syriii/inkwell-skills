#!/usr/bin/env python3
"""检索 Skill — 搜索脚本

提供语义搜索和文本比较功能：
  search  — 在索引中搜索最相似的文档/段落
  compare — 直接比较两段文本的相似度（不走索引）

策略说明：
  direct — 直接 encode（与 index 行为一致，apples-to-apples）
  full   — chunk → 分别 encode → mean pooling（全文覆盖，长文本用）
  auto   — < ~500 字走 direct；≥ ~500 字走 full（默认）
"""

import argparse
import json
import sys
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# 路径约定
# ---------------------------------------------------------------------------

INDEX_DIR = ".retrieval-index"
DOC_INDEX = "doc.index"
DOC_MAP = "doc_map.json"
CHUNK_INDEX = "chunk.index"
CHUNK_MAP = "chunk_map.json"
CONFIG_FILE = "config.json"

# ---------------------------------------------------------------------------
# 分块策略（与 indexer.py 保持一致）
# ---------------------------------------------------------------------------

CHUNK_MAX = 500
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

import re
HEADING_PATTERN = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


def split_by_headings(text: str) -> list[tuple[str, str]]:
    if not text.strip():
        return [("", text)]
    matches = list(HEADING_PATTERN.finditer(text))
    if not matches:
        return [("", text)]
    sections = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        heading = m.group(2).strip()
        body = text[start:end].strip()
        sections.append((heading, body))
    if matches[0].start() > 0:
        preamble = text[:matches[0].start()].strip()
        if preamble:
            sections.insert(0, ("", preamble))
    return sections


def chunk_by_length(text: str, max_len: int = CHUNK_MAX,
                    chunk_size: int = CHUNK_SIZE,
                    overlap: int = CHUNK_OVERLAP) -> list[str]:
    if len(text) <= max_len:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def chunk_document(text: str) -> list[str]:
    sections = split_by_headings(text)
    chunks = []
    for heading, body in sections:
        full = f"{heading}\n{body}" if heading else body
        if len(full) <= CHUNK_MAX:
            if full.strip():
                chunks.append(full)
        else:
            if heading:
                chunks.append(heading)
            sub_chunks = chunk_by_length(body if heading else full)
            chunks.extend(sub_chunks)
    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# 模型加载
# ---------------------------------------------------------------------------

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        model_name = _load_model_name()
        _model = SentenceTransformer(model_name)
    return _model


def _load_model_name() -> str:
    config_path = Path(INDEX_DIR) / CONFIG_FILE
    if config_path.exists():
        config = json.loads(config_path.read_text())
        if config.get("embedding_model"):
            return config["embedding_model"]
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("EMBEDDING_MODEL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "BAAI/bge-small-zh-v1.5"


def _load_default_threshold() -> float:
    config_path = Path(INDEX_DIR) / CONFIG_FILE
    if config_path.exists():
        config = json.loads(config_path.read_text())
        return config.get("search_threshold", 0.75)
    return 0.75


# ---------------------------------------------------------------------------
# 向量工具
# ---------------------------------------------------------------------------

def normalize(vecs: np.ndarray) -> np.ndarray:
    """L2 归一化，使 L2 距离可转换为余弦相似度。"""
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms


def l2_to_cosine(distances: np.ndarray) -> np.ndarray:
    """L2 距离 → 余弦相似度（假设向量已 L2 归一化）。

    d² = 2(1 - cos_sim) → cos_sim = 1 - d²/2
    """
    return 1.0 - (distances ** 2) / 2.0


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个向量的余弦相似度。"""
    a_norm = a / (np.linalg.norm(a) + 1e-10)
    b_norm = b / (np.linalg.norm(b) + 1e-10)
    return float(np.dot(a_norm, b_norm))


# ---------------------------------------------------------------------------
# 索引加载
# ---------------------------------------------------------------------------

def load_doc_map() -> dict[int, dict]:
    p = Path(INDEX_DIR) / DOC_MAP
    if p.exists():
        return {int(k): v for k, v in json.loads(p.read_text()).items()}
    return {}


def load_chunk_map() -> dict[int, dict]:
    p = Path(INDEX_DIR) / CHUNK_MAP
    if p.exists():
        return {int(k): v for k, v in json.loads(p.read_text()).items()}
    return {}


def load_faiss_index(path: Path) -> faiss.IndexFlatL2 | None:
    if path.exists():
        return faiss.read_index(str(path))
    return None


# ---------------------------------------------------------------------------
# 搜索
# ---------------------------------------------------------------------------

def op_search(query: str, granularity: str = "doc", top_k: int = 5,
              threshold: float | None = None,
              exclude_paths: list[str] | None = None,
              scope_dirs: list[str] | None = None) -> dict:
    """在索引中搜索最相似的内容。

    Args:
        query: 搜索文本
        granularity: doc | chunk | both
        top_k: 返回数量
        threshold: 相似度阈值，默认从 config 读取
        exclude_paths: 排除的路径列表
        scope_dirs: 限定搜索范围（目录前缀）

    Returns:
        { results: [...], granularity, threshold }
    """
    if threshold is None:
        threshold = _load_default_threshold()

    model = get_model()
    query_vec = model.encode([query])[0].astype(np.float32)

    results = []

    if granularity in ("doc", "both"):
        doc_results = _search_docs(model, query_vec, top_k, threshold,
                                   exclude_paths, scope_dirs)
        results.extend(doc_results)

    if granularity in ("chunk", "both"):
        chunk_results = _search_chunks(model, query_vec, top_k, threshold,
                                        exclude_paths, scope_dirs)
        results.extend(chunk_results)

    # 按分数降序
    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:top_k]

    return {
        "results": results,
        "granularity": granularity,
        "threshold": threshold,
        "query": query
    }


def _search_docs(model: SentenceTransformer, query_vec: np.ndarray,
                 top_k: int, threshold: float,
                 exclude_paths: list[str] | None,
                 scope_dirs: list[str] | None) -> list[dict]:
    index = load_faiss_index(Path(INDEX_DIR) / DOC_INDEX)
    doc_map = load_doc_map()
    if index is None or not doc_map:
        return []

    # FAISS 搜索
    query_norm = normalize(np.array([query_vec]))
    distances, ids = index.search(query_norm, min(top_k * 3, index.ntotal))
    scores = l2_to_cosine(distances[0])

    results = []
    for score, idx in zip(scores, ids[0]):
        if idx == -1 or idx not in doc_map:
            continue
        meta = doc_map[idx]
        if not _filter(meta["path"], exclude_paths, scope_dirs):
            continue
        if score >= threshold:
            results.append({
                "path": meta["path"],
                "score": round(float(score), 4),
                "granularity": "doc",
                "content_hash": meta.get("content_hash"),
                "indexed_at": meta.get("indexed_at")
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def _search_chunks(model: SentenceTransformer, query_vec: np.ndarray,
                   top_k: int, threshold: float,
                   exclude_paths: list[str] | None,
                   scope_dirs: list[str] | None) -> list[dict]:
    index = load_faiss_index(Path(INDEX_DIR) / CHUNK_INDEX)
    chunk_map = load_chunk_map()
    if index is None or not chunk_map:
        return []

    query_norm = normalize(np.array([query_vec]))
    distances, ids = index.search(query_norm, min(top_k * 3, index.ntotal))
    scores = l2_to_cosine(distances[0])

    results = []
    for score, idx in zip(scores, ids[0]):
        if idx == -1 or idx not in chunk_map:
            continue
        meta = chunk_map[idx]
        if not _filter(meta["path"], exclude_paths, scope_dirs):
            continue
        if score >= threshold:
            results.append({
                "path": meta["path"],
                "chunk_text": meta.get("chunk_text", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "score": round(float(score), 4),
                "granularity": "chunk"
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def _filter(path: str,
            exclude_paths: list[str] | None,
            scope_dirs: list[str] | None) -> bool:
    if exclude_paths:
        for ep in exclude_paths:
            if ep in path:
                return False
    if scope_dirs:
        for sd in scope_dirs:
            if path.startswith(sd):
                return True
        return False
    return True


# ---------------------------------------------------------------------------
# 文本比较
# ---------------------------------------------------------------------------

AUTO_THRESHOLD = 500  # 字符数阈值，< 此值走 direct，≥ 走 full


def op_compare(text_a: str, text_b: str, strategy: str = "auto") -> dict:
    """直接比较两段文本的相似度，不走索引。

    Args:
        text_a: 文本 A
        text_b: 文本 B
        strategy: auto | direct | full

    Returns:
        { score, strategy_used, chunks_a, chunks_b }
    """
    model = get_model()

    # 确定策略
    if strategy == "auto":
        if len(text_a) < AUTO_THRESHOLD and len(text_b) < AUTO_THRESHOLD:
            strategy_used = "direct"
        else:
            strategy_used = "full"
    else:
        strategy_used = strategy

    if strategy_used == "direct":
        vec_a = model.encode([text_a])[0]
        vec_b = model.encode([text_b])[0]
        score = cosine_similarity(vec_a, vec_b)
        return {
            "score": round(float(score), 4),
            "strategy_used": "direct",
            "chunks_a": 0,
            "chunks_b": 0
        }

    else:  # full — chunk + mean pooling
        chunks_a = chunk_document(text_a)
        chunks_b = chunk_document(text_b)

        if not chunks_a or not chunks_b:
            # 兜底：空文本走 direct
            vec_a = model.encode([text_a])[0]
            vec_b = model.encode([text_b])[0]
            score = cosine_similarity(vec_a, vec_b)
            return {
                "score": round(float(score), 4),
                "strategy_used": "direct",
                "chunks_a": len(chunks_a),
                "chunks_b": len(chunks_b)
            }

        vecs_a = model.encode(chunks_a)
        vecs_b = model.encode(chunks_b)

        # Mean pooling
        pooled_a = np.mean(vecs_a, axis=0)
        pooled_b = np.mean(vecs_b, axis=0)

        score = cosine_similarity(pooled_a, pooled_b)
        return {
            "score": round(float(score), 4),
            "strategy_used": "full",
            "chunks_a": len(chunks_a),
            "chunks_b": len(chunks_b)
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="检索 Skill — 搜索")
    sub = parser.add_subparsers(dest="command", required=True)

    # search
    p = sub.add_parser("search")
    p.add_argument("--query", required=True)
    p.add_argument("--granularity", default="doc", choices=["doc", "chunk", "both"])
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--threshold", type=float, default=None)
    p.add_argument("--exclude", nargs="*", default=None)
    p.add_argument("--scope", nargs="*", default=None)

    # compare
    p = sub.add_parser("compare")
    p.add_argument("--text-a", required=True)
    p.add_argument("--text-b", required=True)
    p.add_argument("--strategy", default="auto", choices=["auto", "direct", "full"])

    args = parser.parse_args()

    try:
        if args.command == "search":
            result = op_search(
                query=args.query,
                granularity=args.granularity,
                top_k=args.top_k,
                threshold=args.threshold,
                exclude_paths=args.exclude,
                scope_dirs=args.scope,
            )
        elif args.command == "compare":
            result = op_compare(
                text_a=args.text_a,
                text_b=args.text_b,
                strategy=args.strategy,
            )
        else:
            result = {"error": f"unknown command: {args.command}"}

        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
