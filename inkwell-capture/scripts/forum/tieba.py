#!/usr/bin/env python3
"""百度贴吧论坛专用处理器（tieba.baidu.com）。"""

import re

from bs4 import BeautifulSoup

from utils import build_forum_body, clean_text, parse_relative_time


def scrape_tieba(html: str, url: str, **kwargs) -> dict:
    """抓取百度贴吧帖子。"""
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(".core_title_txt") or soup.select_one("h1")
    title = clean_text(title_el.text) if title_el else ""

    floors = []
    for floor in soup.select(".l_post"):
        user_el = floor.select_one(".d_name a")
        user = clean_text(user_el.text) if user_el else "匿名"

        content_els = floor.select(".d_post_content")
        content = ""
        for el in content_els:
            content += clean_text(el.text) + "\n"

        time_el2 = floor.select_one(".tail-info:last-child")
        t = parse_relative_time(clean_text(time_el2.text)) if time_el2 else ""

        floors.append({
            "author": user,
            "time": t,
            "content": content.strip(),
        })

    if not floors:
        return {
            "error": "tieba_parse_failed",
            "message": "无法解析贴吧页面结构",
            "type": "forum",
            "source": url,
        }

    op = floors[0]
    comments = floors[1:]

    body = build_forum_body(title, op["author"], op["content"], comments)
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
