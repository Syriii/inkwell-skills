#!/usr/bin/env python3
"""讨论创作 Skill — 讨论写入 + 产出状态查询

写入讨论轮次和总结到 discussions/{slug}/ 目录。

用法：
  python discussion_writer.py write-round --dir <dir> --round <N> --title <...> ...
  python discussion_writer.py write-summary --dir <dir> --content <...> ...
  python discussion_writer.py status [--filter created|uncreated|all]
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _escape(s: str) -> str:
    # Normalize Chinese curly double quotes to corner brackets
    # to avoid conflict with YAML string delimiters
    s = s.replace(chr(0x201c), chr(0x300c)).replace(chr(0x201d), chr(0x300d))
    return s.replace('\\', '\\\\').replace('"', '\\"')


def _slugify(text: str) -> str:
    """简化中文文本为文件名片段。"""
    # 保留中英文字符和数字，空格→短横
    text = re.sub(r'[^\w一-鿿]', '-', text)
    text = re.sub(r'-{2,}', '-', text)
    return text.strip('-')[:40] or 'untitled'


def write_round(discussion_dir: str, round_num: int, title: str,
                content: str, category: str = "",
                tags: str = "", based_on: str = "") -> dict:
    """写入一轮讨论。

    Args:
        discussion_dir: discussions/{slug} 目录
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


def write_summary(discussion_dir: str, content: str,
                  category: str = "", tags: str = "",
                  rounds: int = 0, based_on: str = "") -> dict:
    """写入讨论总结。

    合并了原 初步结果.md（findings）功能——总结文件同时承担
    讨论回顾和创作交接的职责。

    Args:
        discussion_dir: discussions/{slug} 目录，slug 从 basename 推导
        content: 总结正文（含讨论回顾 + 创作交接内容）
        category: 分类
        tags: 逗号分隔的标签
        rounds: 总轮次数
        based_on: 逗号分隔的引用路径
    """
    d = Path(discussion_dir)
    _ensure_dir(d)

    slug = d.name
    filename = f"{slug}讨论总结.md"
    filepath = d / filename

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    based_list = [b.strip() for b in based_on.split(",") if b.strip()]

    fm = ["---"]
    fm.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
    fm.append(f'slug: "{_escape(slug)}"')
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
        "slug": slug,
    }


# ---------------------------------------------------------------------------
# status — 讨论产出状态查询
# ---------------------------------------------------------------------------

def _parse_source_discussions(content: str) -> list[str]:
    """从文章 frontmatter 提取 source_discussions 列表。"""
    slugs = []
    in_source = False
    for line in content.split('\n'):
        if line.strip() == 'source_discussions:':
            in_source = True
            continue
        if in_source:
            if line.strip().startswith('- '):
                slug = line.strip()[2:].strip().strip('"')
                slugs.append(slug)
                continue
            elif line.strip() and not line.strip().startswith('-'):
                # 下一个 top-level frontmatter 字段
                in_source = False
        if in_source and line.strip() == '---':
            break
    return slugs


def _collect_discussion_slugs(project_root: Path) -> set[str]:
    """收集所有有讨论记录的 slug。

    判断标准：discussions/{slug}/rounds/ 下有至少一个 .md 文件。
    """
    discussions_dir = project_root / "discussions"
    if not discussions_dir.exists():
        return set()

    slugs = set()
    for slug_dir in discussions_dir.iterdir():
        if not slug_dir.is_dir():
            continue
        rounds_dir = slug_dir / "rounds"
        if rounds_dir.exists() and list(rounds_dir.glob("*.md")):
            slugs.add(slug_dir.name)
        # 也检查 summary 文件
        if list(slug_dir.glob("*讨论总结.md")):
            slugs.add(slug_dir.name)
    return slugs


def _collect_referenced_slugs(project_root: Path) -> dict[str, list[str]]:
    """扫描 creations/ 目录，收集每篇文章引用的讨论 slug。

    Returns:
        {discussion_slug: [article_path, ...]}
    """
    creations_dir = project_root / "creations"
    if not creations_dir.exists():
        return {}

    refs: dict[str, list[str]] = {}
    for article_dir in creations_dir.iterdir():
        if not article_dir.is_dir():
            continue
        article_file = article_dir / f"{article_dir.name}.md"
        if not article_file.exists():
            # 也检查 drafts/
            for draft in (article_dir / "drafts").glob("*.md") if (article_dir / "drafts").exists() else []:
                content = draft.read_text()
                for slug in _parse_source_discussions(content):
                    refs.setdefault(slug, []).append(str(draft))
        else:
            content = article_file.read_text()
            for slug in _parse_source_discussions(content):
                refs.setdefault(slug, []).append(str(article_file))

    return refs


def status(project_root: str = ".", filter_mode: str = "all") -> dict:
    """查询讨论产出状态。

    Args:
        project_root: 项目根目录
        filter_mode: created | uncreated | all

    Returns:
        { discussions: [...], created_count, uncreated_count, total }
    """
    root = Path(project_root)
    all_slugs = _collect_discussion_slugs(root)
    refs = _collect_referenced_slugs(root)
    referenced_slugs = set(refs.keys())

    results = []
    for slug in sorted(all_slugs):
        has_output = slug in referenced_slugs
        articles = refs.get(slug, [])
        results.append({
            "slug": slug,
            "created": has_output,
            "article_count": len(articles),
            "articles": articles,
        })

    created = [r for r in results if r["created"]]
    uncreated = [r for r in results if not r["created"]]

    if filter_mode == "created":
        filtered = created
    elif filter_mode == "uncreated":
        filtered = uncreated
    else:
        filtered = results

    return {
        "discussions": filtered,
        "created_count": len(created),
        "uncreated_count": len(uncreated),
        "total": len(results),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="讨论创作 Skill — 讨论写入 + 产出状态查询")
    sub = parser.add_subparsers(dest="command", required=True)

    # write-round
    p = sub.add_parser("write-round")
    p.add_argument("--dir", required=True, help="discussions/{slug} 目录")
    p.add_argument("--round", type=int, required=True, help="轮次编号")
    p.add_argument("--title", required=True, help="本轮角度")
    p.add_argument("--content", required=True, help="Markdown 正文")
    p.add_argument("--category", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--based-on", default="")

    # write-summary
    p = sub.add_parser("write-summary")
    p.add_argument("--dir", required=True, help="discussions/{slug} 目录，slug 从 basename 推导")
    p.add_argument("--content", required=True, help="总结正文（含讨论回顾 + 创作交接）")
    p.add_argument("--category", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--rounds", type=int, default=0)
    p.add_argument("--based-on", default="")

    # status
    p = sub.add_parser("status")
    p.add_argument("--filter", default="all", choices=["created", "uncreated", "all"],
                   help="筛选：已创作 | 未创作 | 全部（默认）")
    p.add_argument("--project-root", default=".",
                   help="项目根目录（默认当前目录）")

    args = parser.parse_args()

    try:
        if args.command == "write-round":
            result = write_round(args.dir, args.round, args.title,
                                 args.content, args.category,
                                 args.tags, args.based_on)
        elif args.command == "write-summary":
            result = write_summary(args.dir, args.content,
                                   args.category, args.tags,
                                   args.rounds, args.based_on)
        elif args.command == "status":
            result = status(args.project_root, args.filter)
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
