#!/usr/bin/env python3
"""讨论创作 Skill — 提纲写入

写入创作提纲到 creations/{article-slug}/outline.md。

用法：
  python outline_writer.py write --dir <dir> --title <...> --content-file <file>
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _add_content_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--content", help="提纲 Markdown（仅适合短单行内容）")
    group.add_argument(
        "--content-file",
        help="包含提纲 Markdown 的 UTF-8 文件；多行内容使用此参数",
    )


def _resolve_content(args: argparse.Namespace) -> str:
    if args.content_file:
        return Path(args.content_file).read_text(encoding="utf-8")
    return args.content


def _escape(s: str) -> str:
    # Normalize Chinese curly double quotes to corner brackets
    # to avoid conflict with YAML string delimiters
    s = s.replace(chr(0x201c), chr(0x300c)).replace(chr(0x201d), chr(0x300d))
    return s.replace('\\', '\\\\').replace('"', '\\"')


def write_outline(creation_dir: str, title: str, content: str,
                  category: str = "", tags: str = "",
                  based_on: str = "") -> dict:
    """写入提纲文件。

    Args:
        creation_dir: creations/{article-slug} 目录
        title: 文章标题
        content: 提纲 Markdown 正文
        category: 分类
        tags: 逗号分隔的标签
        based_on: 逗号分隔的引用路径
    """
    d = Path(creation_dir)
    d.mkdir(parents=True, exist_ok=True)

    filepath = d / "outline.md"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    based_list = [b.strip() for b in based_on.split(",") if b.strip()]

    fm = ["---"]
    fm.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
    fm.append(f'title: "{_escape(title)}"')
    fm.append("type: outline")
    if category:
        fm.append(f"category: {category}")
    if tag_list:
        fm.append(f"tags: [{', '.join(tag_list)}]")
    if based_list:
        fm.append("based_on:")
        for b in based_list:
            fm.append(f"  - {b}")
    fm.append("---")

    frontmatter = '\n'.join(fm)
    filepath.write_text(f"{frontmatter}\n\n{content}\n")

    return {
        "action": "outline_written",
        "path": str(filepath),
        "title": title,
    }


def main():
    parser = argparse.ArgumentParser(description="讨论创作 Skill — 提纲写入")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("write")
    p.add_argument("--dir", required=True, help="creations/{article-slug} 目录")
    p.add_argument("--title", required=True, help="文章标题")
    _add_content_arguments(p)
    p.add_argument("--category", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--based-on", default="")

    args = parser.parse_args()

    try:
        if args.command == "write":
            result = write_outline(args.dir, args.title, _resolve_content(args),
                                   args.category, args.tags, args.based_on)
        else:
            result = {"error": f"unknown command: {args.command}"}

        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
