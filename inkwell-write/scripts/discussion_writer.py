#!/usr/bin/env python3
"""讨论创作 Skill — 讨论写入

写入讨论轮次和总结到 topics/{slug}/discussion/ 目录。

用法：
  python discussion_writer.py write-round --dir <dir> --round <N> --title <...> ...
  python discussion_writer.py write-summary --dir <dir> --topic <...> ...
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')


def _slugify(text: str) -> str:
    """简化中文文本为文件名片段。"""
    import re
    # 保留中英文字符和数字，空格→短横
    text = re.sub(r'[^\w一-鿿]', '-', text)
    text = re.sub(r'-{2,}', '-', text)
    return text.strip('-')[:40] or 'untitled'


def write_round(discussion_dir: str, round_num: int, title: str,
                content: str, category: str = "",
                tags: str = "", based_on: str = "") -> dict:
    """写入一轮讨论。

    Args:
        discussion_dir: topics/{slug}/discussion 目录
        round_num: 轮次编号
        title: 本轮讨论角度（用作 round_title 和文件名）
        content: Markdown 正文
        category: 分类
        tags: 逗号分隔的标签
        based_on: 逗号分隔的引用路径
    """
    d = Path(discussion_dir)
    rounds_dir = d / "rounds"
    _ensure_dir(rounds_dir)

    # 文件名: NN-{角度}.md
    filename = f"{round_num:02d}-{_slugify(title)}.md"
    filepath = rounds_dir / filename

    # 构建 frontmatter
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    based_list = [b.strip() for b in based_on.split(",") if b.strip()]

    fm = ["---"]
    fm.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
    fm.append(f"round: {round_num}")
    fm.append(f'round_title: "{_escape(title)}"')
    fm.append("type: discussion")
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
        "action": "round_written",
        "path": str(filepath),
        "round": round_num,
        "round_title": title,
    }


def write_summary(discussion_dir: str, topic: str, content: str,
                  category: str = "", tags: str = "",
                  rounds: int = 0, based_on: str = "") -> dict:
    """写入讨论总结。

    Args:
        discussion_dir: topics/{slug}/discussion 目录
        topic: 讨论主题
        content: 总结正文
        category: 分类
        tags: 逗号分隔的标签
        rounds: 总轮次数
        based_on: 逗号分隔的引用路径
    """
    d = Path(discussion_dir)
    _ensure_dir(d)

    filename = f"{topic}讨论总结.md"
    filepath = d / filename

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    based_list = [b.strip() for b in based_on.split(",") if b.strip()]

    fm = ["---"]
    fm.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
    fm.append(f'topic: "{_escape(topic)}"')
    fm.append("type: summary")
    if category:
        fm.append(f"category: {category}")
    if tag_list:
        fm.append(f"tags: [{', '.join(tag_list)}]")
    if based_list:
        fm.append("based_on:")
        for b in based_list:
            fm.append(f"  - {b}")
    if rounds > 0:
        fm.append(f"rounds: {rounds}")
    fm.append("---")

    frontmatter = '\n'.join(fm)
    filepath.write_text(f"{frontmatter}\n\n{content}\n")

    return {
        "action": "summary_written",
        "path": str(filepath),
        "topic": topic,
    }


def main():
    parser = argparse.ArgumentParser(description="讨论创作 Skill — 讨论写入")
    sub = parser.add_subparsers(dest="command", required=True)

    # write-round
    p = sub.add_parser("write-round")
    p.add_argument("--dir", required=True, help="topics/{slug}/discussion 目录")
    p.add_argument("--round", type=int, required=True, help="轮次编号")
    p.add_argument("--title", required=True, help="本轮角度")
    p.add_argument("--content", required=True, help="Markdown 正文")
    p.add_argument("--category", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--based-on", default="")

    # write-summary
    p = sub.add_parser("write-summary")
    p.add_argument("--dir", required=True)
    p.add_argument("--topic", required=True, help="讨论主题")
    p.add_argument("--content", required=True, help="总结正文")
    p.add_argument("--category", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--rounds", type=int, default=0)
    p.add_argument("--based-on", default="")

    args = parser.parse_args()

    try:
        if args.command == "write-round":
            result = write_round(args.dir, args.round, args.title,
                                 args.content, args.category,
                                 args.tags, args.based_on)
        elif args.command == "write-summary":
            result = write_summary(args.dir, args.topic, args.content,
                                   args.category, args.tags,
                                   args.rounds, args.based_on)
        else:
            result = {"error": f"unknown command: {args.command}"}

        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
        sys.exit(1 if "error" in result else 0)

    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
