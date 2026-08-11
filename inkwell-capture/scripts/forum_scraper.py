#!/usr/bin/env python3
"""采集 Skill — 论坛抓取

提取论坛帖子正文 + 评论树，输出一体式 Markdown。

支持的论坛：
  - NGA（bbs.nga.cn）        → forum/nga.py
  - V2EX（www.v2ex.com）     → forum/v2ex.py
  - 贴吧（tieba.baidu.com）   → forum/tieba.py
  - 煎蛋（jandan.net）        → forum/jandan.py（L1 主帖；完整评论用 jandan_capture.py）
  - 通用论坛（自动检测常见选择器）

用法：
  python forum_scraper.py --url "https://bbs.nga.cn/read.php?tid=47189694"
  python forum_scraper.py --url "https://tieba.baidu.com/p/123456" --cookie "..."

输出 JSON：type=forum, source, title, author, date, body, word_count, comment_count
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse

import requests
import trafilatura

# 确保脚本目录在 import 路径中（用于 utils / forum / cookie_store）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forum import FORUM_HANDLERS  # noqa: E402

try:
    from cookie_store import get_cookie_for_url  # noqa: E402
except ImportError:
    def get_cookie_for_url(url: str) -> None:  # noqa: E402
        return None
from utils import clean_text, fetch_html  # noqa: E402


# ---------------------------------------------------------------------------
# 论坛识别
# ---------------------------------------------------------------------------

from typing import Callable


def detect_forum(url: str) -> Callable | None:
    """根据域名识别论坛类型，返回对应的处理器函数。"""
    domain = urlparse(url).netloc.lower().replace("www.", "")
    for key, handler in FORUM_HANDLERS.items():
        if domain == key or domain.endswith("." + key):
            return handler
    return None


# ---------------------------------------------------------------------------
# 通用论坛（兜底）
# ---------------------------------------------------------------------------

def _scrape_generic(html: str, url: str) -> dict:
    """通用论坛抓取——用 trafilatura 提取正文 + 常见选择器提取评论。

    注意：与 NGA/V2EX/Tieba 不同，通用抓取不调用 build_forum_body() 构建格式化
    Markdown。因为不知道论坛结构，body 字段保留 trafilatura 原文输出，
    这与其他 handler 的「OP blockquote + 评论 thread」格式不同。这是设计取舍，不是 bug。
    """
    from bs4 import BeautifulSoup

    body = trafilatura.extract(html, output_format="markdown", with_metadata=True)

    soup = BeautifulSoup(html, "lxml")

    title = ""
    title_el = soup.select_one("h1, .title, .thread-title, [class*='topic-title']")
    if title_el:
        title = clean_text(title_el.text)

    comments = []
    for sel in [".post", ".comment", ".reply", "[class*='post-']", "article"]:
        elements = soup.select(sel)
        if len(elements) > 50:
            print(f"⚠️  通用论坛评论 ({len(elements)}) 超过上限 (50)，已截断。", file=sys.stderr)
        for el in elements[:50]:
            user_el = el.select_one("[class*='user'], [class*='author'], a[href*='user']")
            user = clean_text(user_el.text) if user_el else ""
            content_el = el.select_one("[class*='content'], [class*='body'], [class*='text']")
            content = clean_text(content_el.text) if content_el else clean_text(el.text)
            if len(content) > 20:
                comments.append({"author": user, "time": "", "content": content[:500]})
        if comments:
            break

    word_count = len(re.findall(r'[一-鿿]', body or ""))

    return {
        "type": "forum",
        "source": url,
        "title": title,
        "author": "",
        "date": "",
        "body": body or "",
        "word_count": word_count,
        "comment_count": len(comments),
        "images": [],
    }


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def scrape(url: str, cookie: str | None = None, timeout: int = 30,
           max_pages: int | None = None) -> dict:
    """论坛抓取主入口。

    Args:
        url: 帖子 URL
        cookie: Cookie 字符串（None 则从 .env 自动读取）
        timeout: HTTP 请求超时秒数
        max_pages: 最大采集页数（None = 全部；仅 NGA 支持）
    """
    html = fetch_html(url, cookie, timeout)

    handler = detect_forum(url)
    if handler:
        return handler(html, url, cookie=cookie, timeout=timeout,
                       max_pages=max_pages)

    return _scrape_generic(html, url)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="采集 Skill — 论坛抓取")
    parser.add_argument("--url", required=True, help="论坛帖子 URL")
    parser.add_argument("--cookie", default=None, help="Cookie 字符串")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="最大采集页数（默认采集全部；仅 NGA 有效）",
    )

    args = parser.parse_args()

    # --cookie 未指定时，从 .env 自动读取
    cookie = args.cookie or get_cookie_for_url(args.url)

    try:
        result = scrape(args.url, cookie, args.timeout,
                        max_pages=args.max_pages)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
        sys.exit(1 if "error" in result else 0)
    except requests.RequestException as e:
        json.dump({
            "error": "request_failed",
            "message": str(e),
            "type": "forum",
            "source": args.url,
        }, sys.stdout, ensure_ascii=False, indent=2)
        print()
        sys.exit(1)
    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
