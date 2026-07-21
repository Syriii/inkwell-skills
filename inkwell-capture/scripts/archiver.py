#!/usr/bin/env python3
"""采集 Skill — 统一归档写入

接收完整的采集数据（脚本输出 + Claude Code 理解字段），
创建目录结构并写入 archive.md。

用法：
  python archiver.py --json '<json>'
  echo '<json>' | python archiver.py --stdin

JSON 字段：
  type, source      — 必填
  body              — 必填，Markdown 正文
  title             — 必填，用于生成 slug 和 frontmatter
  category, tags    — Claude Code 生成的分类和标签
  summary           — Claude Code 生成的摘要
  date              — 原文发布日期，无可为空
  author, word_count — 可选
  images            — [{url, path}, ...]
  fetched_at        — 可选，默认当前时间
  slug              — 可选，手动指定 slug（不指定则从 title 生成）
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Slug 生成
# ---------------------------------------------------------------------------

def make_slug(title: str) -> str:
    """从标题生成目录名。

    中文标题直接使用原文字（清理非法字符），非中文标题使用英文 slug。
    注意：这是脚本兜底方案，理想情况下 slug 由 Claude Code 在工作流中生成。

    >>> make_slug("欧盟AI法案最终解读")
    '欧盟AI法案最终解读'
    >>> make_slug("How to Learn Python in 2024")
    'how-to-learn-python-in-2024'
    """
    slug = title.strip()

    has_chinese = bool(re.search(r'[一-鿿]', slug))
    if has_chinese:
        # 中文标题：直接使用，清理文件名非法字符
        slug = re.sub(r'[\\/:*?"<>|]', '', slug)
        slug = slug[:60].strip()
    else:
        # 非中文标题：提取英文单词
        tokens = re.findall(r'[a-zA-Z]{2,}|\d+', slug)
        if tokens:
            slug = '-'.join(t.lower() for t in tokens[:5])
        else:
            today = datetime.now().strftime("%m%d")
            import hashlib
            h = hashlib.md5(title.encode()).hexdigest()[:6]
            slug = f"article-{today}-{h}"
        slug = slug[:60].strip('-')
        if len(slug) < 5:
            today = datetime.now().strftime("%m%d")
            slug = f"{slug}-{today}"

    return slug or 'untitled'


# ---------------------------------------------------------------------------
# 图片下载
# ---------------------------------------------------------------------------

def download_images(images: list[dict], target_dir: Path) -> list[dict]:
    """下载图片到目标目录，返回更新后的 images 列表。

    跳过已存在的文件，下载失败的标记为 failed。
    """
    import requests

    target_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for img in images:
        url = img.get("url", "")
        path = img.get("path", "")

        if not url:
            downloaded.append(img)
            continue

        target_path = target_dir / Path(path).name if path else _filename_from_url(url)

        if target_path.exists():
            img["path"] = str(target_path.relative_to(target_path.parent.parent.parent))
            downloaded.append(img)
            continue

        try:
            resp = requests.get(url, timeout=30, stream=True)
            resp.raise_for_status()
            target_path.write_bytes(resp.content)
            img["path"] = f"images/{target_path.name}"
        except Exception as e:
            img["path"] = None
            img["download_error"] = str(e)

        downloaded.append(img)

    return downloaded


def _filename_from_url(url: str) -> str:
    """从 URL 提取文件名。"""
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)
    if not name or '.' not in name:
        name = 'image.png'
    return name


# ---------------------------------------------------------------------------
# Frontmatter 生成
# ---------------------------------------------------------------------------

def build_frontmatter(data: dict) -> str:
    """从采集数据生成 YAML frontmatter。"""
    lines = ["---"]

    # 日期
    date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    lines.append(f"date: {date}")

    # 必填字段
    lines.append(f"source: \"{_escape(data['source'])}\"")
    lines.append(f"type: {data.get('type', 'webpage')}")
    lines.append(f"category: {data.get('category', '未分类')}")

    # tags
    tags = data.get("tags", [])
    if tags:
        tag_str = ', '.join(tags)
        lines.append(f"tags: [{tag_str}]")
    else:
        lines.append("tags: []")

    # title
    lines.append(f"title: \"{_escape(data.get('title', ''))}\"")

    # summary
    summary = data.get("summary", "")
    if summary:
        lines.append(f"summary: \"{_escape(summary)}\"")

    # 可选字段
    if data.get("author"):
        lines.append(f"author: \"{_escape(data['author'])}\"")
    if data.get("word_count"):
        lines.append(f"word_count: {data['word_count']}")

    # 采集时间戳
    fetched_at = data.get("fetched_at") or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    lines.append(f"fetched_at: {fetched_at}")

    # 原始图片路径（截图类）
    if data.get("original_image"):
        lines.append(f"original_image: \"{data['original_image']}\"")

    lines.append("---")
    return '\n'.join(lines)


def _escape(s: str) -> str:
    """转义 YAML 字符串中的双引号。"""
    return s.replace('\\', '\\\\').replace('"', '\\"')


# ---------------------------------------------------------------------------
# 主操作
# ---------------------------------------------------------------------------

def archive(data: dict, project_root: Path | None = None) -> dict:
    """执行归档写入。

    Args:
        data: 完整的采集数据（包含 title, category, tags, summary 等）
        project_root: 项目根目录，默认当前目录

    Returns:
        { path, slug, article_path }
    """
    root = project_root or Path.cwd()

    # 确定日期和 slug
    fetched_at = data.get("fetched_at") or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    date_str = fetched_at[:10].replace('-', '')
    slug = data.get("slug") or make_slug(data.get("title", "untitled"))

    # 创建目录
    archive_dir = root / "archived" / date_str / slug
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 下载图片
    images = data.get("images", [])
    if images:
        images = download_images(images, archive_dir / "images")

    # 构建 frontmatter
    data_with_images = {**data, "images": images}
    frontmatter = build_frontmatter(data_with_images)

    # 构建正文
    body = data.get("body", "")
    content = f"{frontmatter}\n\n{body}\n"

    # 写入 article.md
    article_path = archive_dir / "article.md"
    article_path.write_text(content)

    # 报告
    rel_path = str(archive_dir.relative_to(root))
    return {
        "path": rel_path,
        "slug": slug,
        "article_path": str(article_path.relative_to(root)),
        "num_images": len([i for i in images if i.get("path")]),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="采集 Skill — 归档写入")
    parser.add_argument("--json", help="JSON 数据字符串")
    parser.add_argument("--stdin", action="store_true", help="从 stdin 读取 JSON")
    parser.add_argument("--project-root", default=None, help="项目根目录")

    args = parser.parse_args()

    try:
        if args.stdin:
            data = json.load(sys.stdin)
        elif args.json:
            data = json.loads(args.json)
        else:
            print("error: must provide --json or --stdin", file=sys.stderr)
            sys.exit(1)

        root = Path(args.project_root) if args.project_root else None
        result = archive(data, root)

        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    except json.JSONDecodeError as e:
        json.dump({"error": f"Invalid JSON: {e}"}, sys.stderr, ensure_ascii=False)
        sys.exit(1)
    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
