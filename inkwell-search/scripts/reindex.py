#!/usr/bin/env python3
"""重建索引 —— 采集后的标准索引维护入口。

扫描内容目录下全部 .md → 提取可索引文本（title + summary + tags + 正文）→
调 indexer.py rebuild 全量原子重建。保证索引与磁盘文件严格一致：
重命名/删除的文件自动消失，新增文件自动纳入。

用法（在项目根目录执行）：
    python .claude/skills/inkwell-search/scripts/reindex.py

可用 --dirs 覆盖默认内容目录（默认: archived discussions creations）。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_DIRS = ["archived", "discussions", "creations"]

# 项目根 = 最近的 .retrieval-index 所在目录（与 indexer.py 的 CWD 约定一致）
def find_project_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".retrieval-index").exists():
            return p
    return start


def extract_text(p: Path) -> str:
    """从归档文件提取可索引文本：title + summary + tags + 正文。"""
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
    dirs = args.dirs or cfg.get("source_dirs") or DEFAULT_DIRS
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
    # 模型已本地缓存（WEB_ANALYSIS_MODELS_DIR），HF_HUB_OFFLINE 避免联网检查卡死
    env = {**os.environ, "HF_HUB_OFFLINE": "1"}
    r = subprocess.run([sys.executable, str(indexer), "rebuild", "--data", tmp],
                       capture_output=True, text=True, cwd=root, env=env)
    os.unlink(tmp)
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

    # 数据质量校验：日期格式 + 正文纯净度（防仪表盘 dataviewjs 报错复发）
    # date/fetched_at 若被写成空格分隔（如 `2026-07-30 10:42`），Obsidian 的
    # js-yaml 会解析为字符串，dv.date() 无法处理 → 总览仪表盘报错。
    validator = Path(__file__).resolve().parent / "validate_frontmatter.py"
    vr = subprocess.run([sys.executable, str(validator)],
                        capture_output=True, text=True, cwd=root)
    if vr.stdout:
        print(vr.stdout, end="")
    if vr.returncode != 0:
        if vr.stderr:
            sys.stderr.write(vr.stderr)
        # 校验作为门禁：发现问题即返回非零，提醒先修复数据再继续
        sys.exit(vr.returncode)


if __name__ == "__main__":
    main()
