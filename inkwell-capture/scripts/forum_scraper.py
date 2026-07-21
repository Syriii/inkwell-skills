#!/usr/bin/env python3
"""采集 Skill — 论坛抓取

提取论坛帖子正文 + 评论树，输出一体式 Markdown。

支持的论坛：
  - V2EX（www.v2ex.com）
  - 贴吧（tieba.baidu.com）
  - 通用论坛（自动检测常见选择器）

用法：
  python forum_scraper.py --url "https://www.v2ex.com/t/123456"
  python forum_scraper.py --url "https://tieba.baidu.com/p/123456" --cookie "..."

输出 JSON：type=forum, source, title, author, date, body, word_count, comment_count
"""

import argparse
import json
import re
import sys
from datetime import datetime
from urllib.parse import urlparse

import requests
import trafilatura


# ---------------------------------------------------------------------------
# 论坛识别
# ---------------------------------------------------------------------------

FORUM_HANDLERS = {
    "www.v2ex.com": "_scrape_v2ex",
    "v2ex.com": "_scrape_v2ex",
    "tieba.baidu.com": "_scrape_tieba",
}


def detect_forum(url: str) -> str | None:
    """根据域名识别论坛类型。"""
    domain = urlparse(url).netloc.lower()
    for key, handler in FORUM_HANDLERS.items():
        if domain == key or domain.endswith("." + key):
            return handler
    return None


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _fetch_html(url: str, cookie: str | None = None, timeout: int = 30) -> str:
    """获取 HTML。"""
    headers = HEADERS.copy()
    if cookie:
        headers["Cookie"] = cookie
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def _clean_text(text: str) -> str:
    """清理 HTML 实体和多余空白。"""
    import html
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _parse_relative_time(s: str) -> str:
    """尝试解析相对时间 → YYYY-MM-DD。"""
    now = datetime.now()
    s = s.strip()

    # "3 小时前" / "2 天前" / "2024-03-15"
    m = re.match(r'(\d+)\s*小时前', s)
    if m:
        from datetime import timedelta
        dt = now - timedelta(hours=int(m.group(1)))
        return dt.strftime("%Y-%m-%d")

    m = re.match(r'(\d+)\s*天前', s)
    if m:
        from datetime import timedelta
        dt = now - timedelta(days=int(m.group(1)))
        return dt.strftime("%Y-%m-%d")

    m = re.match(r'(\d+)\s*分钟前', s)
    if m:
        return now.strftime("%Y-%m-%d")

    # 标准日期
    m = re.match(r'(\d{4}-\d{2}-\d{2})', s)
    if m:
        return m.group(1)

    return s


# ---------------------------------------------------------------------------
# V2EX
# ---------------------------------------------------------------------------

def _scrape_v2ex(html: str, url: str) -> dict:
    """抓取 V2EX 帖子。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    # 标题
    title_el = soup.select_one("h1")
    title = _clean_text(title_el.text) if title_el else ""

    # OP
    op_el = soup.select_one(".topic_content")
    op_text = _clean_text(op_el.text) if op_el else ""

    # OP 作者和时间
    author_el = soup.select_one(".header small a")
    author = _clean_text(author_el.text) if author_el else ""

    time_el = soup.select_one(".header small span")
    op_time = _clean_text(time_el.text) if time_el else ""

    # 评论
    comments = []
    for cell in soup.select(".cell[id^='r_']"):
        user_el = cell.select_one("strong a")
        user = _clean_text(user_el.text) if user_el else "匿名"

        time_el = cell.select_one(".ago")
        t = _clean_text(time_el.text) if time_el else ""

        likes_el = cell.select_one(".small.fade")
        likes = ""
        if likes_el:
            likes = _clean_text(likes_el.text)

        content_el = cell.select_one(".reply_content")
        content = _clean_text(content_el.text) if content_el else ""

        comments.append({
            "author": user,
            "time": _parse_relative_time(t),
            "likes": likes,
            "content": content,
        })

    body = _build_forum_body(title, author, op_text, comments)
    word_count = len(re.findall(r'[一-鿿]', body))

    return {
        "type": "forum",
        "source": url,
        "title": title,
        "author": author,
        "date": op_time,
        "body": body,
        "word_count": word_count,
        "comment_count": len(comments),
        "images": [],
    }


# ---------------------------------------------------------------------------
# 贴吧
# ---------------------------------------------------------------------------

def _scrape_tieba(html: str, url: str) -> dict:
    """抓取百度贴吧帖子。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    # 标题
    title_el = soup.select_one(".core_title_txt") or soup.select_one("h1")
    title = _clean_text(title_el.text) if title_el else ""

    # 楼层
    floors = []
    for floor in soup.select(".l_post"):
        user_el = floor.select_one(".d_name a")
        user = _clean_text(user_el.text) if user_el else "匿名"

        content_els = floor.select(".d_post_content")
        content = ""
        for el in content_els:
            content += _clean_text(el.text) + "\n"

        time_el = floor.select_one(".tail-info:last-child")
        t = _clean_text(time_el.text) if time_el else ""

        floors.append({
            "author": user,
            "time": t,
            "content": content.strip(),
        })

    if not floors:
        return {"error": "tieba_parse_failed", "message": "无法解析贴吧页面结构",
                "type": "forum", "source": url}

    op = floors[0]
    comments = floors[1:]

    body = _build_forum_body(title, op["author"], op["content"], comments)
    word_count = len(re.findall(r'[一-鿿]', body))

    return {
        "type": "forum",
        "source": url,
        "title": title,
        "author": op["author"],
        "date": op["time"],
        "body": body,
        "word_count": word_count,
        "comment_count": len(comments),
        "images": [],
    }


# ---------------------------------------------------------------------------
# 通用论坛（兜底）
# ---------------------------------------------------------------------------

def _scrape_generic(html: str, url: str) -> dict:
    """通用论坛抓取——用 trafilatura 提取正文 + 常见选择器提取评论。"""
    from bs4 import BeautifulSoup

    # trafilatura 提取正文
    body = trafilatura.extract(html, output_format="markdown", with_metadata=True)

    soup = BeautifulSoup(html, "lxml")

    # 尝试从常见选择器提取评论
    title = ""
    title_el = soup.select_one("h1, .title, .thread-title, [class*='topic-title']")
    if title_el:
        title = _clean_text(title_el.text)

    comments = []
    for sel in [".post", ".comment", ".reply", "[class*='post-']", "article"]:
        for el in soup.select(sel)[:50]:
            user_el = el.select_one("[class*='user'], [class*='author'], a[href*='user']")
            user = _clean_text(user_el.text) if user_el else ""
            content_el = el.select_one("[class*='content'], [class*='body'], [class*='text']")
            content = _clean_text(content_el.text) if content_el else _clean_text(el.text)
            if len(content) > 20:  # 过滤无效
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
# 输出构建
# ---------------------------------------------------------------------------

def _build_forum_body(title: str, op_author: str, op_content: str,
                      comments: list[dict]) -> str:
    """构建一体式论坛 Markdown。"""
    lines = [f"# {title}\n"]
    lines.append(f"**楼主 @{op_author}**\n")
    lines.append(f"> {op_content}\n")

    for i, c in enumerate(comments):
        lines.append("---\n")
        likes = f" · 👍 {c['likes']}" if c.get("likes") else ""
        lines.append(f"**@{c['author']}** · {c['time']}{likes}\n")
        lines.append(f"{c['content']}\n")

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def scrape(url: str, cookie: str | None = None, timeout: int = 30) -> dict:
    """论坛抓取主入口。"""
    html = _fetch_html(url, cookie, timeout)

    handler_name = detect_forum(url)
    if handler_name:
        handler = globals().get(handler_name)
        if handler:
            return handler(html, url)

    # 降级到通用抓取
    return _scrape_generic(html, url)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="采集 Skill — 论坛抓取")
    parser.add_argument("--url", required=True, help="论坛帖子 URL")
    parser.add_argument("--cookie", default=None, help="Cookie 字符串")
    parser.add_argument("--timeout", type=int, default=30)

    args = parser.parse_args()

    try:
        result = scrape(args.url, args.cookie, args.timeout)
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
