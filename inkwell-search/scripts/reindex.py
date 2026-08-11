#!/usr/bin/env python3
"""重建索引 —— 通用文档目录的标准索引维护入口。

扫描内容目录下全部 .md → 提取可索引文本（title + summary + tags + 正文）→
调 indexer.py rebuild 全量原子重建。保证索引与磁盘文件严格一致：
重命名/删除的文件自动消失，新增文件自动纳入。

用法（在项目根目录执行）：
    python <skill-dir>/scripts/reindex.py

使用 --dirs 指定内容目录，或读取 config.json 的 source_dirs。
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# 项目根 = 最近的 .retrieval-index 所在目录（与 indexer.py 的 CWD 约定一致）
def find_project_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".retrieval-index").exists():
            return p
    return start


def extract_text(p: Path) -> str:
    """从 Markdown 提取可索引文本：常见元数据字段 + 正文。"""
    text = p.read_text(encoding="utf-8")
    fm, body = "", text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm, body = parts[1], parts[2]

    def grab(pattern: str) -> str:
        m = re.search(pattern, fm, re.M)
        if not m:
            return ""
        return (m.group(1) or m.group(2)).strip().strip("'\"")

    title = grab(r'^title:\s*(?:"([^"]+)"|([^\n]+))')
    summary = grab(r'^summary:\s*(?:"([^"]+)"|([^\n]+))')
    m = re.search(r'^tags:\s*\[(.*?)\]', fm, re.S)
    tags = m.group(1).strip() if m else ""

    parts = [title, summary, tags, body]
    return "\n".join(x for x in parts if x)


CONFIG_PATH = ".retrieval-index/config.json"


def load_config(root: Path) -> dict:
    p = root / CONFIG_PATH
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_config(root: Path, cfg: dict) -> None:
    (root / CONFIG_PATH).write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="*", default=None,
                    help="要扫描的内容目录（默认读 config.json 的 source_dirs）")
    args = ap.parse_args()

    root = find_project_root(Path.cwd())
    cfg = load_config(root)
    dirs = args.dirs or cfg.get("source_dirs") or []
    if not dirs:
        print(json.dumps({
            "error": "no source directories configured; pass --dirs or set source_dirs in .retrieval-index/config.json"
        }, ensure_ascii=False))
        sys.exit(2)
    data: list[list[str]] = []
    for d in dirs:
        base = root / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            rel = p.relative_to(root)
            data.append([str(rel), extract_text(p)])

    if not data:
        print(json.dumps({"error": "no markdown files found"}, ensure_ascii=False))
        sys.exit(1)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        tmp = f.name

    indexer = Path(__file__).resolve().parent / "indexer.py"
    try:
        r = subprocess.run(
            [sys.executable, str(indexer), "rebuild", "--data", tmp],
            capture_output=True,
            text=True,
            cwd=root,
        )
    finally:
        Path(tmp).unlink(missing_ok=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit(r.returncode)

    # 记录 source_dirs 与本次重建时间，供 status 展示
    import time
    cfg = load_config(root)
    cfg["source_dirs"] = dirs
    cfg["last_indexed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_config(root, cfg)

    print(r.stdout, end="")

if __name__ == "__main__":
    main()
