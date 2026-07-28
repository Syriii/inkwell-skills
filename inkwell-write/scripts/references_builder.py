#!/usr/bin/env python3
"""讨论创作 Skill — 引用管理

管理 references.md 文件，维护 Obsidian wikilink 格式的引用清单。

用法：
  python references_builder.py update --dir <dir> --add "<path>|<label>|<excerpt>"
  python references_builder.py update --dir <dir> --add-multi '<json_array>'
  python references_builder.py show --dir <dir>
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


REF_HEADER = "# 引用素材"


def _ensure_file(dir_path: str) -> Path:
    d = Path(dir_path)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "references.md"
    if not p.exists():
        p.write_text(f"{REF_HEADER}\n\n")
    return p


def _parse_ref_entry(entry: str) -> dict | None:
    """解析 "path|label|> excerpt" 格式的引用条目。"""
    parts = entry.split("|", 2)
    if len(parts) < 2:
        return None

    path = parts[0].strip()
    label = parts[1].strip()
    excerpt = parts[2].strip() if len(parts) > 2 else ""

    # 移除 excerpt 开头的 > 标记
    if excerpt.startswith(">"):
        excerpt = excerpt[1:].strip()

    return {"path": path, "label": label, "excerpt": excerpt}


def _format_ref(ref: dict) -> str:
    """格式化为 Obsidian wikilink 引用。"""
    lines = [f"## [[{ref['path']}|{ref['label']}]]"]
    if ref.get("excerpt"):
        lines.append(f"> {ref['excerpt']}")
    lines.append("")
    return '\n'.join(lines)


def _load_refs(filepath: Path) -> list[dict]:
    """从 references.md 解析已有引用。"""
    if not filepath.exists():
        return []

    content = filepath.read_text()
    refs = []
    # 匹配 ## [[path|label]] 格式
    pattern = r'##\s+\[\[([^\]]+)\|([^\]]+)\]\].*?\n(?:>\s*(.+?)\n)?'
    for m in re.finditer(pattern, content, re.MULTILINE):
        refs.append({
            "path": m.group(1).strip(),
            "label": m.group(2).strip(),
            "excerpt": m.group(3).strip() if m.group(3) else "",
        })
    return refs


def _save_refs(filepath: Path, refs: list[dict]) -> None:
    """保存引用到 references.md。"""
    lines = [REF_HEADER, ""]
    for ref in refs:
        lines.append(_format_ref(ref))
    filepath.write_text('\n'.join(lines))


def update_refs(dir_path: str, add: str | None = None,
                add_multi: str | None = None) -> dict:
    """添加/更新引用。同 path 覆盖已有条目。

    Args:
        dir_path: discussions/{slug} 目录
        add: 单条引用 "path|label|excerpt"
        add_multi: JSON 数组 '[["path","label","excerpt"], ...]'

    Returns:
        { action, added, updated, total }
    """
    filepath = _ensure_file(dir_path)
    existing = _load_refs(filepath)
    existing_paths = {r["path"]: i for i, r in enumerate(existing)}

    # 收集要添加的条目
    entries: list[str] = []
    if add:
        entries.append(add)
    if add_multi:
        multi = json.loads(add_multi)
        for item in multi:
            entries.append("|".join(item))

    added = 0
    updated = 0
    for entry in entries:
        ref = _parse_ref_entry(entry)
        if not ref:
            continue
        if ref["path"] in existing_paths:
            existing[existing_paths[ref["path"]]] = ref
            updated += 1
        else:
            existing.append(ref)
            added += 1

    _save_refs(filepath, existing)

    return {
        "action": "references_updated",
        "path": str(filepath),
        "added": added,
        "updated": updated,
        "total": len(existing),
    }


def show_refs(dir_path: str) -> dict:
    """列出所有引用。"""
    filepath = Path(dir_path) / "references.md"
    refs = _load_refs(filepath)
    return {
        "references": refs,
        "total": len(refs),
    }


def main():
    parser = argparse.ArgumentParser(description="讨论创作 Skill — 引用管理")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("update")
    p.add_argument("--dir", required=True)
    p.add_argument("--add", default=None)
    p.add_argument("--add-multi", default=None)

    p = sub.add_parser("show")
    p.add_argument("--dir", required=True)

    args = parser.parse_args()

    try:
        if args.command == "update":
            result = update_refs(args.dir, args.add, args.add_multi)
        elif args.command == "show":
            result = show_refs(args.dir)
        else:
            result = {"error": f"unknown command: {args.command}"}

        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
