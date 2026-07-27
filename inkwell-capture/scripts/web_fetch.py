#!/usr/bin/env python3
"""采集 Skill — L1 网页抓取（requests + trafilatura）

轻量级正文提取，适用于静态页面和不需要 JS 渲染的网页。
失败时降级到 L2（Playwright）。

用法：
  python web_fetch.py --url "https://example.com/article"
  python web_fetch.py --url "https://example.com" --cookie "name=value"

输出 JSON：
  type, source, date, author, title, body, word_count, images
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
import trafilatura
from trafilatura.metadata import extract_metadata

# 自动读取 .env 中保存的 Cookie（当前脚本目录）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cookie_store import get_cookie_for_url  # noqa: E402


def fetch(url: str, cookie: str | None = None, timeout: int = 30) -> dict:
    """L1 抓取：requests + trafilatura 提取正文和元数据。

    Args:
        url: 目标 URL
        cookie: 可选的 cookie 字符串，用于登录态内容
        timeout: 请求超时（秒）

    Returns:
        { type, source, date, author, body, word_count, images, title }
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if cookie:
        headers["Cookie"] = cookie

    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()

    html = resp.text

    # --- 正文提取 ---
    body = trafilatura.extract(
        html,
        output_format="markdown",
        with_metadata=True,
        include_comments=False,
        include_tables=True,
        include_images=True,
        include_formatting=True,
        favor_precision=True,
    )

    if not body:
        return {
            "error": "trafilatura_extraction_failed",
            "message": "无法从页面提取正文内容，可能需要 JS 渲染",
            "type": "webpage",
            "source": url,
            "body": "",
        }

    # --- 元数据 ---
    meta_raw = extract_metadata(html)
    if meta_raw is None:
        meta = {}
    elif isinstance(meta_raw, dict):
        meta = meta_raw
    else:
        meta = meta_raw.as_dict()

    title = meta.get("title") or ""
    date = meta.get("date") or ""
    author = meta.get("author") or ""

    # 日期标准化
    if date:
        try:
            date = _normalize_date(date)
        except Exception:
            pass

    # --- 图片提取 ---
    images = _extract_images(html, url)

    # --- 清理 body 中的 data: URI 图片占位符 ---
    # trafilatura include_images=True 会内联所有 img src，
    # 包括 lazy-load 的 SVG 占位符，导致 body 中出现无法渲染的
    # ![](data:image/svg+xml;utf8,<svg...) 引用。
    body = re.sub(r'!\[[^\]]*\]\(data:[^)]*\)\s*\n?', '', body)

    # --- 字数统计 ---
    word_count = len(re.findall(r'[一-鿿]', body))  # 中文字符

    return {
        "type": "webpage",
        "source": url,
        "date": date,
        "author": author,
        "title": title or _extract_title_from_body(body),
        "body": body.strip() if body else "",
        "word_count": word_count,
        "images": images,
    }


def _normalize_date(s: str) -> str:
    """尝试标准化日期格式 → YYYY-MM-DD。"""
    # 已标准
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s

    # 常见格式
    for fmt in [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y年%m月%d日",
        "%B %d, %Y",
        "%d %B %Y",
    ]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return s


def _extract_title_from_body(body: str) -> str:
    """从 Markdown body 中提取第一个 # 标题作为 title 兜底。"""
    m = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _extract_images(html: str, base_url: str) -> list[dict]:
    """从 HTML 中提取图片 URL 列表。"""
    # trafilatura 已经在 body 中内联了图片，这里提取原始 <img> 标签
    imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    seen = set()
    result = []
    for src in imgs[:30]:  # 最多 30 张
        src = src.strip()
        if not src or src.startswith("data:"):
            continue
        full_url = urljoin(base_url, src)
        if full_url in seen:
            continue
        seen.add(full_url)
        result.append({"url": full_url, "path": ""})
    if len(imgs) > 30:
        print(f"⚠️  图片数量 ({len(imgs)}) 超过上限 (30)，已截断。", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="L1 网页抓取 — requests + trafilatura")
    parser.add_argument("--url", required=True, help="目标 URL")
    parser.add_argument("--cookie", default=None, help="Cookie 字符串")
    parser.add_argument("--timeout", type=int, default=30, help="请求超时（秒）")

    args = parser.parse_args()

    # --cookie 未指定时，从 .env 自动读取
    cookie = args.cookie or get_cookie_for_url(args.url)

    try:
        result = fetch(args.url, cookie, args.timeout)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
        sys.exit(1 if "error" in result else 0)
    except requests.RequestException as e:
        json.dump({
            "error": "request_failed",
            "message": str(e),
            "type": "webpage",
            "source": args.url,
        }, sys.stdout, ensure_ascii=False, indent=2)
        print()
        sys.exit(1)
    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
