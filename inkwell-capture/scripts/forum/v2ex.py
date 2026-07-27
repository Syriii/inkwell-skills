#!/usr/bin/env python3
"""V2EX 论坛专用处理器（www.v2ex.com）。"""

import re

from bs4 import BeautifulSoup

from utils import build_forum_body, clean_text, parse_relative_time


def scrape_v2ex(html: str, url: str, **kwargs) -> dict:
    """抓取 V2EX 帖子。"""
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("h1")
    title = clean_text(title_el.text) if title_el else ""

    op_el = soup.select_one(".topic_content")
    op_text = clean_text(op_el.text) if op_el else ""

    author_el = soup.select_one(".header small a")
    author = clean_text(author_el.text) if author_el else ""

    time_el = soup.select_one(".header small span")
    op_time = parse_relative_time(clean_text(time_el.text)) if time_el else ""

    comments = []
    for cell in soup.select(".cell[id^='r_']"):
        user_el = cell.select_one("strong a")
        user = clean_text(user_el.text) if user_el else "匿名"

        time_el2 = cell.select_one(".ago")
        t = clean_text(time_el2.text) if time_el2 else ""

        likes_el = cell.select_one(".small.fade")
        likes = ""
        if likes_el:
            likes = clean_text(likes_el.text)

        content_el = cell.select_one(".reply_content")
        content = clean_text(content_el.text) if content_el else ""

        comments.append({
            "author": user,
            "time": parse_relative_time(t),
            "likes": likes,
            "content": content,
        })

    body = build_forum_body(title, author, op_text, comments)
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
