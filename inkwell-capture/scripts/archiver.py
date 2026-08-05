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
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# 确保脚本目录在 import 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import escape_yaml  # noqa: E402

try:
    from cookie_store import get_cookie_for_url  # noqa: E402
except ImportError:
    def get_cookie_for_url(url: str) -> None:  # noqa: E402
        return None

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
        slug = re.sub(r'[\\/:*?"<>|\[\]]', '', slug)
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

def download_images(images: list[dict], target_dir: Path,
                    source_url: str | None = None) -> list[dict]:
    """下载图片到目标目录，返回更新后的 images 列表。

    已存在文件跳过，下载失败的标记为 failed。

    Args:
        images: 图片字典列表 [{url, path, ...}]
        target_dir: 下载目标目录
        source_url: 来源 URL（用于根据域名查找 Cookie，如 NGA 反盗链）
    """
    import requests

    target_dir.mkdir(parents=True, exist_ok=True)

    # 按域名查 Cookie（如 NGA img.nga.178.com 需要 Cookie 否则返回 567）
    cookie = get_cookie_for_url(source_url) if source_url else None

    downloaded = []
    for img in images:
        url = img.get("url", "")
        if not url:
            downloaded.append(img)
            continue

        # 已有本地路径且文件已存在 → 跳过
        existing_path = img.get("path", "")
        if existing_path:
            full_path = target_dir.parent / existing_path
            if full_path.exists():
                downloaded.append(img)
                continue

        # 确定文件名：优先用脚本分配的 path，没有再从 URL 提取
        filename = os.path.basename(img.get("path", "")) or _filename_from_url(url)
        dest = target_dir / filename

        # 避免重名
        counter = 1
        stem, ext = os.path.splitext(filename)
        while dest.exists():
            dest = target_dir / f"{stem}_{counter}{ext}"
            counter += 1

        # 下载：requests 优先，失败自动降级 curl（绕过 WAF 的 TLS 指纹风控，如 NGA 图片 CDN 返回 567）
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": url,
        }
        if cookie:
            headers["Cookie"] = cookie
        ok = False
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            dest.write_bytes(r.content)
            ok = True
        except Exception:
            ok = _curl_download(url, dest, source_url, cookie)
        if ok:
            img["path"] = f"images/{dest.name}"
        else:
            img["path"] = ""
            img["download_error"] = "requests 与 curl 均下载失败（可能仍被 WAF 拦截）"

        downloaded.append(img)

    return downloaded


def _curl_download(url: str, dest: Path, source_url: str | None,
                   cookie: str | None) -> bool:
    """requests 被 WAF 拦截（如 NGA 图片 CDN 的 TLS 指纹风控，HTTP 567）时，
    用 curl 重试——curl 使用真实浏览器 TLS 指纹，通常能绕过。

    Returns:
        True 表示下载成功且文件非空
    """
    import subprocess
    cmd = ["curl", "-s", "-L", "--fail", "--max-time", "60", "-o", str(dest)]
    cmd += ["-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"]
    if source_url:
        cmd += ["-H", f"Referer: {source_url}"]
    if cookie:
        cmd += ["-H", f"Cookie: {cookie}"]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=90)
        if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            return True
    except Exception:
        pass
    dest.unlink(missing_ok=True)
    return False


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
    lines.append(f"source: \"{escape_yaml(data['source'])}\"")
    lines.append(f"type: {data.get('type', 'webpage')}")
    category = data.get('category', '')
    if not category:
        print("⚠️ 警告：category 为空，已使用默认值「未分类」", file=sys.stderr)
        category = '未分类'
    elif category == '未分类':
        print("⚠️ 警告：category 为「未分类」，请确认是否需要手动分类", file=sys.stderr)
    lines.append(f"category: {category}")

    # tags
    tags = data.get("tags", [])
    if tags:
        tag_str = ', '.join(tags)
        lines.append(f"tags: [{tag_str}]")
    else:
        print("⚠️ 警告：tags 为空，请补充标签", file=sys.stderr)
        lines.append("tags: []")

    # title
    lines.append(f"title: \"{escape_yaml(data.get('title', ''))}\"")

    # summary
    summary = data.get("summary", "")
    if summary:
        lines.append(f"summary: \"{escape_yaml(summary)}\"")

    # 可选字段
    if data.get("author"):
        lines.append(f"author: \"{escape_yaml(data['author'])}\"")
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

    # 校验必填字段
    required = ["source", "body", "title"]
    for field in required:
        if field not in data or not data[field]:
            return {"error": "missing_required_field",
                    "message": f"缺少必填字段: {field}"}

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
        images = download_images(images, archive_dir / "images",
                                 source_url=data.get("source"))

    # 构建 frontmatter
    data_with_images = {**data, "images": images}
    frontmatter = build_frontmatter(data_with_images)

    # 构建正文
    body = data.get("body", "")
    content = f"{frontmatter}\n\n{body}\n"

    # 写入 {slug}.md（原子写入：先写临时文件，再 rename，防止中途崩溃损坏文件）
    md_name = f"{slug}.md"
    article_path = archive_dir / md_name
    tmp_path = archive_dir / f".{md_name}.tmp"
    try:
        tmp_path.write_text(content)
        tmp_path.replace(article_path)  # os.replace = 同文件系统原子操作
    except OSError:
        # 跨文件系统 fallback：非原子但不会丢数据
        import shutil
        shutil.move(str(tmp_path), str(article_path))
    finally:
        # 清理可能残留的 .tmp 文件（如 write_text 成功但 replace 失败）
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

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
    parser.add_argument("--json-file", help="从文件读取 JSON（避免 shell 转义问题）")
    parser.add_argument("--project-root", default=None, help="项目根目录")

    args = parser.parse_args()

    try:
        if args.json_file:
            with open(args.json_file, encoding='utf-8') as f:
                data = json.load(f)
        elif args.stdin:
            data = json.load(sys.stdin)
        elif args.json:
            data = json.loads(args.json)
        else:
            print("error: must provide --json, --stdin, or --json-file", file=sys.stderr)
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
