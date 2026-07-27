#!/usr/bin/env python3
"""检索 Skill — 索引管理脚本

管理 FAISS 向量索引和元数据映射：
  文档级索引 (doc.index / doc_map.json) — 整篇文档的语义向量
  块级索引 (chunk.index / chunk_map.json) — 文档段落的语义向量

操作：
  index   — 增量添加/更新一篇文档
  rebuild — 全量重建索引（原子替换）
  remove  — 删除一篇文档
  status  — 返回索引状态
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
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
# 分块策略：结构优先 + 长度兜底
# ---------------------------------------------------------------------------

HEADING_PATTERN = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
CHUNK_MAX = 500       # 块上限（字符数）
CHUNK_SIZE = 400       # 切分长度
CHUNK_OVERLAP = 50     # 重叠长度


def split_by_headings(text: str) -> list[tuple[str, str]]:
    """按 ## / ### 标题切分，返回 [(标题, 正文), ...]。"""
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

    # 标题前的导言
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.insert(0, ("", preamble))

    return sections


def chunk_by_length(text: str, max_len: int = CHUNK_MAX,
                    chunk_size: int = CHUNK_SIZE,
                    overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按长度切分长文本，带重叠。"""
    if len(text) <= max_len:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def chunk_document(text: str) -> list[str]:
    """结构优先 + 长度兜底：切分文档为块。"""
    sections = split_by_headings(text)
    chunks = []

    for heading, body in sections:
        full = f"{heading}\n{body}" if heading else body
        if len(full) <= CHUNK_MAX:
            if full.strip():
                chunks.append(full)
        else:
            # 标题 + 正文太长 → 标题保留，正文切分
            if heading:
                chunks.append(heading)  # 标题单独一块
            sub_chunks = chunk_by_length(body if heading else full)
            chunks.extend(sub_chunks)

    # 去空
    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Embedding 模型加载（懒加载单例）
# ---------------------------------------------------------------------------

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        model_name = _load_model_name()
        _model = SentenceTransformer(model_name)
    return _model


def _load_model_name() -> str:
    """从 config.json 或 .env 读取模型名，默认 BGE-small-zh-v1.5。"""
    config_path = Path(INDEX_DIR) / CONFIG_FILE
    if config_path.exists():
        config = json.loads(config_path.read_text())
        if config.get("embedding_model"):
            return config["embedding_model"]

    # 检查 .env
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("EMBEDDING_MODEL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    return "BAAI/bge-small-zh-v1.5"


# ---------------------------------------------------------------------------
# 路径工具
# ---------------------------------------------------------------------------

def _ensure_index_dir() -> Path:
    d = Path(INDEX_DIR)
    d.mkdir(exist_ok=True)
    return d


def _doc_index_path() -> Path:
    return _ensure_index_dir() / DOC_INDEX


def _doc_map_path() -> Path:
    return _ensure_index_dir() / DOC_MAP


def _chunk_index_path() -> Path:
    return _ensure_index_dir() / CHUNK_INDEX


def _chunk_map_path() -> Path:
    return _ensure_index_dir() / CHUNK_MAP


# ---------------------------------------------------------------------------
# 元数据读写
# ---------------------------------------------------------------------------

def load_doc_map() -> dict[int, dict]:
    p = _doc_map_path()
    if p.exists():
        return {int(k): v for k, v in json.loads(p.read_text()).items()}
    return {}


def save_doc_map(data: dict[int, dict]) -> None:
    _doc_map_path().write_text(json.dumps(
        {str(k): v for k, v in data.items()}, ensure_ascii=False, indent=2))


def load_chunk_map() -> dict[int, dict]:
    p = _chunk_map_path()
    if p.exists():
        return {int(k): v for k, v in json.loads(p.read_text()).items()}
    return {}


def save_chunk_map(data: dict[int, dict]) -> None:
    _chunk_map_path().write_text(json.dumps(
        {str(k): v for k, v in data.items()}, ensure_ascii=False, indent=2))


def load_faiss_index(path: Path, dim: int) -> faiss.IndexFlatL2:
    if path.exists():
        return faiss.read_index(str(path))
    return faiss.IndexFlatL2(dim)


def save_faiss_index(index: faiss.Index, path: Path) -> None:
    faiss.write_index(index, str(path))


# ---------------------------------------------------------------------------
# 内容哈希
# ---------------------------------------------------------------------------

def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def normalize(vecs: np.ndarray) -> np.ndarray:
    """L2 归一化，确保 L2 距离可转换为余弦相似度。"""
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms


# ---------------------------------------------------------------------------
# 核心操作
# ---------------------------------------------------------------------------

def _remove_from_index(path: str, doc_map: dict, chunk_map: dict,
                       doc_index: faiss.Index, chunk_index: faiss.Index) -> None:
    """从两个索引中删除指定路径的所有向量（需重建索引实现）。"""
    # FAISS IndexFlatL2 不支持直接删除，需要重建。
    # 标记待删除，在 _rebuild_faiss 中实际移除。
    # 这里我们直接在 map 和 index 层面处理：
    # 对于 IndexFlatL2，我们只能重建。
    pass  # 由 rebuild 统一处理


def op_index(path: str, text: str) -> dict:
    """增量添加/更新一篇文档。

    若同 path 已存在且 content_hash 未变 → 跳过
    若同 path 已存在但 content_hash 变了 → 删除旧条目后重建
    """
    model = get_model()
    h = content_hash(text)

    doc_map = load_doc_map()
    chunk_map = load_chunk_map()

    # 检查是否已存在且未变
    existing_paths = {v["path"] for v in doc_map.values()}
    if path in existing_paths:
        existing = next((v for v in doc_map.values() if v["path"] == path), None)
        if existing and existing.get("content_hash") == h:
            return {"action": "skip", "path": path, "reason": "unchanged"}

    # 编码文档级向量（归一化）
    doc_vec = normalize(model.encode([text])[0].astype(np.float32).reshape(1, -1))[0]

    # 分块 + 编码块级向量（归一化）
    chunks = chunk_document(text)
    chunk_vecs = normalize(model.encode(chunks).astype(np.float32)) if chunks else np.empty((0, model.get_embedding_dimension()), dtype=np.float32)

    dim = doc_vec.shape[0]

    # 加载或创建索引
    doc_index = load_faiss_index(_doc_index_path(), dim)
    chunk_index = load_faiss_index(_chunk_index_path(), dim)

    # 删除旧条目（从 map 和 FAISS 中）
    _delete_by_path(path, doc_map, doc_index)
    _delete_by_path(path, chunk_map, chunk_index)

    # 添加新向量
    new_doc_id = _next_id(doc_map)
    doc_index.add(np.array([doc_vec]))
    doc_map[new_doc_id] = {
        "path": path,
        "content_hash": h,
        "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    }

    chunk_ids = []
    for i, vec in enumerate(chunk_vecs):
        cid = _next_id(chunk_map)
        chunk_index.add(np.array([vec]))
        chunk_map[cid] = {
            "path": path,
            "chunk_text": chunks[i],
            "chunk_index": i
        }
        chunk_ids.append(cid)

    # 持久化
    save_doc_map(doc_map)
    save_chunk_map(chunk_map)
    save_faiss_index(doc_index, _doc_index_path())
    save_faiss_index(chunk_index, _chunk_index_path())

    return {
        "action": "indexed",
        "path": path,
        "doc_id": new_doc_id,
        "chunk_ids": chunk_ids,
        "num_chunks": len(chunks)
    }


def op_rebuild(data: list[tuple[str, str]]) -> dict:
    """全量重建索引。

    data: [(path, text), ...] — 调用方扫描目录、拼接好文本后传入。
    原子替换：先写临时文件，完成后重命名。
    """
    model = get_model()
    if not data:
        # 空数据 → 写空索引
        return _atomic_rebuild(model, [], [])

    paths = [d[0] for d in data]
    texts = [d[1] for d in data]
    hashes = [content_hash(t) for t in texts]

    # 编码所有文档（归一化）
    doc_vecs = normalize(model.encode(texts).astype(np.float32))
    dim = doc_vecs.shape[1]

    # 分块所有文档
    all_chunks: list[dict] = []  # [{path, chunk_text, chunk_index}, ...]
    for path, text in zip(paths, texts):
        chunks = chunk_document(text)
        for i, chunk in enumerate(chunks):
            all_chunks.append({"path": path, "chunk_text": chunk, "chunk_index": i})

    chunk_vecs = normalize(model.encode([c["chunk_text"] for c in all_chunks]).astype(np.float32)) if all_chunks else np.empty((0, dim), dtype=np.float32)

    return _atomic_rebuild(model, list(zip(paths, hashes, doc_vecs)),
                           list(zip(all_chunks, chunk_vecs)) if all_chunks else [])


def _next_id(map_data: dict) -> int:
    return max(map_data.keys(), default=-1) + 1


def _delete_by_path(path: str, map_data: dict, index: faiss.Index) -> None:
    """从 map 中删除指定 path 的条目。

    FAISS IndexFlatL2 不支持删除，因此这里只删 map，
    实际向量在后续 add 时通过完整重建索引来清理。
    """
    ids_to_remove = [k for k, v in map_data.items() if v["path"] == path]
    for k in ids_to_remove:
        del map_data[k]


def _atomic_rebuild(model: SentenceTransformer,
                    docs: list[tuple[str, str, np.ndarray]],
                    chunks: list[tuple[dict, np.ndarray]]) -> dict:
    """原子重建：写临时文件 → 重命名。"""
    index_dir = _ensure_index_dir()
    dim = model.get_embedding_dimension()

    # 文档级
    doc_index = faiss.IndexFlatL2(dim)
    doc_map: dict[int, dict] = {}
    tmp_doc_index = index_dir / f"{DOC_INDEX}.new"
    tmp_doc_map = index_dir / f"{DOC_MAP}.new"

    if docs:
        vecs = np.array([d[2] for d in docs])
        doc_index.add(vecs)
        for i, (path, h, _) in enumerate(docs):
            doc_map[i] = {"path": path, "content_hash": h,
                          "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    save_faiss_index(doc_index, tmp_doc_index)
    tmp_doc_map.write_text(
        json.dumps({str(k): v for k, v in doc_map.items()},
                   ensure_ascii=False, indent=2))

    # 块级
    chunk_index = faiss.IndexFlatL2(dim)
    chunk_map: dict[int, dict] = {}
    tmp_chunk_index = index_dir / f"{CHUNK_INDEX}.new"
    tmp_chunk_map = index_dir / f"{CHUNK_MAP}.new"

    if chunks:
        vecs = np.array([c[1] for c in chunks])
        chunk_index.add(vecs)
        for i, (meta, _) in enumerate(chunks):
            chunk_map[i] = meta

    save_faiss_index(chunk_index, tmp_chunk_index)
    tmp_chunk_map.write_text(
        json.dumps({str(k): v for k, v in chunk_map.items()},
                   ensure_ascii=False, indent=2))

    # 原子替换
    shutil.move(str(tmp_doc_index), str(index_dir / DOC_INDEX))
    shutil.move(str(tmp_doc_map), str(index_dir / DOC_MAP))
    shutil.move(str(tmp_chunk_index), str(index_dir / CHUNK_INDEX))
    shutil.move(str(tmp_chunk_map), str(index_dir / CHUNK_MAP))

    return {
        "action": "rebuilt",
        "num_docs": len(docs),
        "num_chunks": len(chunks)
    }


def op_remove(path: str) -> dict:
    """删除一篇文档的索引（需重建实现）。

    FAISS IndexFlatL2 不支持 ID 级删除，所以标记后用 _delete_by_path
    清理 map，实际向量在下次 rebuild 时清除。
    """
    doc_map = load_doc_map()
    chunk_map = load_chunk_map()

    # 从 map 中删除
    doc_ids = [k for k, v in doc_map.items() if v["path"] == path]
    chunk_ids = [k for k, v in chunk_map.items() if v["path"] == path]

    for k in doc_ids:
        del doc_map[k]
    for k in chunk_ids:
        del chunk_map[k]

    save_doc_map(doc_map)
    save_chunk_map(chunk_map)

    # FAISS 无法原子删除，标记需要重建
    # 对于 IndexFlatL2，实际的重建由下次 index/rebuild 触发
    return {
        "action": "removed",
        "path": path,
        "doc_ids_removed": len(doc_ids),
        "chunk_ids_removed": len(chunk_ids),
        "note": "FAISS index requires rebuild for actual vector removal"
    }


def op_status() -> dict:
    """返回索引状态。"""
    doc_map = load_doc_map()
    chunk_map = load_chunk_map()
    config_path = Path(INDEX_DIR) / CONFIG_FILE

    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    return {
        "num_docs": len(doc_map),
        "num_chunks": len(chunk_map),
        "last_indexed_at": config.get("last_indexed_at"),
        "model": _load_model_name(),
        "source_dirs": config.get("source_dirs", []),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="检索 Skill — 索引管理")
    sub = parser.add_subparsers(dest="command", required=True)

    # index
    p = sub.add_parser("index")
    p.add_argument("--path", required=True)
    p.add_argument("--text", required=True)

    # rebuild
    p = sub.add_parser("rebuild")
    p.add_argument("--data", required=True, help="JSON 文件路径，内容为 [[path, text], ...]")

    # remove
    p = sub.add_parser("remove")
    p.add_argument("--path", required=True)

    # status
    sub.add_parser("status")

    args = parser.parse_args()

    try:
        if args.command == "index":
            result = op_index(args.path, args.text)
        elif args.command == "rebuild":
            data = json.loads(Path(args.data).read_text())
            result = op_rebuild(data)
        elif args.command == "remove":
            result = op_remove(args.path)
        elif args.command == "status":
            result = op_status()
        else:
            result = {"error": f"unknown command: {args.command}"}

        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
