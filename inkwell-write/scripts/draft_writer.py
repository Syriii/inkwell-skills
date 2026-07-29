#!/usr/bin/env python3
"""讨论创作 Skill — 草稿写入 + 版本管理

管理 creations/{article-slug}/{article-slug}.md 及 drafts/ 历史版本。

用法：
  python draft_writer.py write --dir <dir> --title <...> --content <...>
  python draft_writer.py archive-and-write --dir <dir> --title <...> --content <...>
  python draft_writer.py update-status --dir <dir> --status article
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def _escape(s: str) -> str:
    # Normalize Chinese curly double quotes to corner brackets
    # to avoid conflict with YAML string delimiters
    s = s.replace(chr(0x201c), chr(0x300c)).replace(chr(0x201d), chr(0x300d))
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
                       source_discussions: str = "",
                       extra: dict | None = None) -> str:
    """构建 YAML frontmatter。"""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    based_list = [b.strip() for b in based_on.split(",") if b.strip()]
    source_list = [s.strip() for s in source_discussions.split(",") if s.strip()]

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
    if source_list:
        fm.append("source_discussions:")
        for s in source_list:
            fm.append(f"  - {s}")
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


def _article_filepath(creation_dir: str) -> Path:
    """从目录路径推导文章文件名 creations/{slug}/{slug}.md。"""
    d = Path(creation_dir)
    slug = d.name
    return d / f"{slug}.md"


def _ensure_images_dir(creation_dir: str) -> Path:
    d = Path(creation_dir)
    img = d / "images"
    img.mkdir(parents=True, exist_ok=True)
    return img


def _draft_filepath(creation_dir: str) -> Path:
    """草稿路径 drafts/draft.md。"""
    return Path(creation_dir) / "drafts" / "draft.md"


def _resolve_write_path(creation_dir: str, status: str) -> Path:
    """根据 status 决定写入位置。

    draft → drafts/draft.md
    article → {slug}.md（终稿）
    """
    if status == "article":
        return _article_filepath(creation_dir)
    else:
        d = Path(creation_dir)
        d.mkdir(parents=True, exist_ok=True)
        drafts_dir = d / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        return _draft_filepath(creation_dir)


def write_draft(creation_dir: str, title: str, content: str,
                category: str = "", tags: str = "",
                based_on: str = "", word_count: int = 0,
                status: str = "draft",
                source_discussions: str = "") -> dict:
    """写入草稿（首次或小改动更新）。

    status=draft → drafts/draft.md
    status=article → {slug}.md（终稿）
    不做版本存档。版本存档由 archive-and-write 命令单独处理。

    Args:
        creation_dir: creations/{article-slug} 目录
        title: 文章标题
        content: 文章正文 Markdown
        source_discussions: 逗号分隔的讨论 slug 列表
    """
    filepath = _resolve_write_path(creation_dir, status)
    frontmatter = _build_frontmatter(
        title=title, frontmatter_type="article" if status == "article" else "draft",
        category=category, tags=tags, based_on=based_on,
        word_count=word_count, status=status,
        source_discussions=source_discussions,
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
                      status: str = "draft",
                      source_discussions: str = "") -> dict:
    """存档当前版本后写入新版。

    1. 当前草稿（drafts/draft.md）存在 → 移动到 drafts/vN.md
    2. 写入新版到 drafts/draft.md（status=draft）或 {slug}.md（status=article）
    """
    d = Path(creation_dir)
    d.mkdir(parents=True, exist_ok=True)
    drafts_dir = d / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    draft_path = _draft_filepath(creation_dir)
    article_path = _article_filepath(creation_dir)
    archived_version = None

    # Archive current draft if it exists
    if draft_path.exists():
        v = _next_version(drafts_dir)
        archived_path = drafts_dir / f"v{v}.md"

        old_content = draft_path.read_text()
        old_content = _inject_version(old_content, v)
        archived_path.write_text(old_content)

        archived_version = v

    # Write new version to correct location
    write_path = _resolve_write_path(creation_dir, status)
    frontmatter = _build_frontmatter(
        title=title, frontmatter_type="article" if status == "article" else "draft",
        category=category, tags=tags, based_on=based_on,
        word_count=word_count, status=status,
        source_discussions=source_discussions,
    )
    write_path.write_text(f"{frontmatter}\n\n{content}\n")

    return {
        "action": "archived_and_written",
        "path": str(write_path),
        "title": title,
        "archived_version": archived_version,
        "drafts_dir": str(drafts_dir),
    }


def _inject_version(markdown: str, version: int) -> str:
    """在 frontmatter 中注入 version 字段。"""
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
                result.insert(-1, f"version: {version}")
                injected = True
                in_fm = False
    return '\n'.join(result)


def update_status(creation_dir: str, new_status: str) -> dict:
    """更新文章 status 并移动到正确位置。

    draft → article: 将 drafts/draft.md 内容移至 {slug}.md，更新 status
    """
    draft_path = _draft_filepath(creation_dir)
    article_path = _article_filepath(creation_dir)

    # Determine source: prefer draft, fall back to article
    if draft_path.exists():
        source_path = draft_path
    elif article_path.exists():
        source_path = article_path
    else:
        return {"error": "article_not_found", "path": str(article_path)}

    content = source_path.read_text()
    content = re.sub(
        r'^status:\s*\w+$',
        f'status: {new_status}',
        content,
        flags=re.MULTILINE,
    )

    # When promoting to article, write to {slug}.md and remove draft
    if new_status == "article":
        article_path.write_text(content)
        if draft_path.exists():
            draft_path.unlink()
        target_path = article_path
    else:
        source_path.write_text(content)
        target_path = source_path

    return {
        "action": "status_updated",
        "path": str(target_path),
        "status": new_status,
    }


def main():
    parser = argparse.ArgumentParser(description="讨论创作 Skill — 草稿写入 + 版本管理")
    sub = parser.add_subparsers(dest="command", required=True)

    # write
    p = sub.add_parser("write")
    p.add_argument("--dir", required=True, help="creations/{article-slug} 目录")
    p.add_argument("--title", required=True, help="文章标题")
    p.add_argument("--content", required=True, help="文章正文 Markdown")
    p.add_argument("--category", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--based-on", default="", help="逗号分隔的素材引用路径")
    p.add_argument("--source-discussions", default="", help="逗号分隔的讨论 slug 列表")
    p.add_argument("--word-count", type=int, default=0)
    p.add_argument("--status", default="draft")

    # archive-and-write
    p = sub.add_parser("archive-and-write")
    p.add_argument("--dir", required=True, help="creations/{article-slug} 目录")
    p.add_argument("--title", required=True, help="文章标题")
    p.add_argument("--content", required=True, help="文章正文 Markdown")
    p.add_argument("--category", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--based-on", default="", help="逗号分隔的素材引用路径")
    p.add_argument("--source-discussions", default="", help="逗号分隔的讨论 slug 列表")
    p.add_argument("--word-count", type=int, default=0)
    p.add_argument("--status", default="draft")

    # update-status
    p = sub.add_parser("update-status")
    p.add_argument("--dir", required=True, help="creations/{article-slug} 目录")
    p.add_argument("--status", required=True, choices=["draft", "review", "article"])

    args = parser.parse_args()

    try:
        if args.command == "write":
            result = write_draft(args.dir, args.title, args.content,
                                 args.category, args.tags, args.based_on,
                                 args.word_count, args.status,
                                 args.source_discussions)
        elif args.command == "archive-and-write":
            result = archive_and_write(args.dir, args.title, args.content,
                                       args.category, args.tags, args.based_on,
                                       args.word_count, args.status,
                                       args.source_discussions)
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
