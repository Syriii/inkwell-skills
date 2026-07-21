#!/usr/bin/env python3
"""讨论创作 Skill — 草稿写入 + 版本管理

管理 topics/{slug}/creation/article.md 及 drafts/ 历史版本。

用法：
  python draft_writer.py write --dir <dir> --title <...> --content <...>
  python draft_writer.py archive-and-write --dir <dir> --title <...> --content <...>
  python draft_writer.py update-status --dir <dir> --status article
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


def _escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')


def _next_version(drafts_dir: Path) -> int:
    """获取下一个版本号。"""
    if not drafts_dir.exists():
        return 1
    existing = list(drafts_dir.glob("v*.md"))
    nums = []
    for f in existing:
        m = re.match(r'v(\d+)\.md$', f.name)
        if m:
            nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


def _build_frontmatter(title: str, frontmatter_type: str,
                       category: str = "", tags: str = "",
                       based_on: str = "", word_count: int = 0,
                       status: str = "", version: int | None = None,
                       extra: dict | None = None) -> str:
    """构建 YAML frontmatter。"""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    based_list = [b.strip() for b in based_on.split(",") if b.strip()]

    fm = ["---"]
    fm.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
    fm.append(f'title: "{_escape(title)}"')
    fm.append(f"type: {frontmatter_type}")

    if category:
        fm.append(f"category: {category}")
    if status and frontmatter_type in ("draft", "article"):
        fm.append(f"status: {status}")
    if version is not None:
        fm.append(f"version: {version}")
    if tag_list:
        fm.append(f"tags: [{', '.join(tag_list)}]")
    if based_list:
        fm.append("based_on:")
        for b in based_list:
            fm.append(f"  - {b}")
    if word_count > 0:
        fm.append(f"word_count: {word_count}")
    if extra:
        for k, v in extra.items():
            fm.append(f"{k}: {v}")
    fm.append("---")

    return '\n'.join(fm)


def write_draft(creation_dir: str, title: str, content: str,
                category: str = "", tags: str = "",
                based_on: str = "", word_count: int = 0,
                status: str = "draft") -> dict:
    """写入草稿（首次或小改动更新）。

    直接覆盖 article.md，不做版本存档。
    版本存档由 archive-and-write 命令单独处理。
    """
    d = Path(creation_dir)
    d.mkdir(parents=True, exist_ok=True)

    filepath = d / "article.md"
    frontmatter = _build_frontmatter(
        title=title, frontmatter_type=status if status in ("draft", "article") else "draft",
        category=category, tags=tags, based_on=based_on,
        word_count=word_count, status=status,
    )

    filepath.write_text(f"{frontmatter}\n\n{content}\n")

    return {
        "action": "draft_written",
        "path": str(filepath),
        "title": title,
        "status": status,
    }


def archive_and_write(creation_dir: str, title: str, content: str,
                      category: str = "", tags: str = "",
                      based_on: str = "", word_count: int = 0,
                      status: str = "draft") -> dict:
    """存档当前版本后写入新版。

    1. 如果 article.md 存在 → 移动到 drafts/vN.md
    2. 写入新的 article.md
    """
    d = Path(creation_dir)
    d.mkdir(parents=True, exist_ok=True)
    drafts_dir = d / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    article_path = d / "article.md"
    archived_version = None

    if article_path.exists():
        v = _next_version(drafts_dir)
        archived_path = drafts_dir / f"v{v}.md"

        # 读取旧内容，给 version 字段打标
        old_content = article_path.read_text()
        # 在 frontmatter 中插入 version 字段
        old_content = _inject_version(old_content, v)
        archived_path.write_text(old_content)

        archived_version = v

    # 写入新版
    frontmatter = _build_frontmatter(
        title=title, frontmatter_type="draft",
        category=category, tags=tags, based_on=based_on,
        word_count=word_count, status=status,
    )
    article_path.write_text(f"{frontmatter}\n\n{content}\n")

    return {
        "action": "archived_and_written",
        "path": str(article_path),
        "title": title,
        "archived_version": archived_version,
        "drafts_dir": str(drafts_dir),
    }


def _inject_version(markdown: str, version: int) -> str:
    """在 frontmatter 中注入 version 字段。"""
    # 找到 frontmatter 的 --- 结束标记前插入 version
    lines = markdown.split('\n')
    result = []
    in_fm = False
    injected = False
    for line in lines:
        result.append(line)
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
            elif not injected:
                # 第二个 --- 前插入 version
                result.insert(-1, f"version: {version}")
                injected = True
                in_fm = False
    return '\n'.join(result)


def update_status(creation_dir: str, new_status: str) -> dict:
    """更新 article.md 的 status 字段。

    draft → review → article
    """
    d = Path(creation_dir)
    article_path = d / "article.md"

    if not article_path.exists():
        return {"error": "article_not_found", "path": str(article_path)}

    content = article_path.read_text()
    content = re.sub(
        r'^status:\s*\w+$',
        f'status: {new_status}',
        content,
        flags=re.MULTILINE,
    )

    article_path.write_text(content)

    return {
        "action": "status_updated",
        "path": str(article_path),
        "status": new_status,
    }


def main():
    parser = argparse.ArgumentParser(description="讨论创作 Skill — 草稿写入 + 版本管理")
    sub = parser.add_subparsers(dest="command", required=True)

    # write
    p = sub.add_parser("write")
    p.add_argument("--dir", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--content", required=True)
    p.add_argument("--category", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--based-on", default="")
    p.add_argument("--word-count", type=int, default=0)
    p.add_argument("--status", default="draft")

    # archive-and-write
    p = sub.add_parser("archive-and-write")
    p.add_argument("--dir", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--content", required=True)
    p.add_argument("--category", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--based-on", default="")
    p.add_argument("--word-count", type=int, default=0)
    p.add_argument("--status", default="draft")

    # update-status
    p = sub.add_parser("update-status")
    p.add_argument("--dir", required=True)
    p.add_argument("--status", required=True, choices=["draft", "review", "article"])

    args = parser.parse_args()

    try:
        if args.command == "write":
            result = write_draft(args.dir, args.title, args.content,
                                 args.category, args.tags, args.based_on,
                                 args.word_count, args.status)
        elif args.command == "archive-and-write":
            result = archive_and_write(args.dir, args.title, args.content,
                                       args.category, args.tags, args.based_on,
                                       args.word_count, args.status)
        elif args.command == "update-status":
            result = update_status(args.dir, args.status)
        else:
            result = {"error": f"unknown command: {args.command}"}

        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
