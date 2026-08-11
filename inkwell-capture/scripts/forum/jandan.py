#!/usr/bin/env python3
"""煎蛋帖子专用解析器（jandan.net/t/{id}）。

静态 HTML 用于保留主帖元数据和正文图片；渲染 HTML 用于提取动态评论。
只有同时带楼层号和评论 ID 的行才被视为正式评论，从而排除“热门吐槽”重复项。
"""

import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from lxml import html as lxml_html

from utils import clean_text


JANDAN_PATH_RE = re.compile(r"^/t/(\d+)/?$")


def source_id_from_url(url: str) -> str:
    """返回煎蛋 /t/ URL 中的帖子 ID；不匹配时返回空串。"""
    match = JANDAN_PATH_RE.match(urlparse(url).path)
    return match.group(1) if match else ""


def _text(element, separator: str = " ") -> str:
    if element is None:
        return ""
    return clean_text(separator.join(element.itertext()))


def _class(name: str) -> str:
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {name} ')"


def _first(element, xpath: str):
    matches = element.xpath(xpath)
    return matches[0] if matches else None


def _number(element) -> int:
    if element is None:
        return 0
    match = re.search(r"\d+", _text(element))
    return int(match.group()) if match else 0


def _image_url(element, base_url: str) -> str:
    for attribute in ("data-original", "data-src", "src"):
        value = (element.get(attribute) or "").strip()
        if value and not value.startswith("data:"):
            return urljoin(base_url, value)
    return ""


def _image_path(url: str, role: str, index: int, comment_id: str = "") -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{2,5}", suffix):
        suffix = ".jpg"
    if role == "post":
        name = "original" if index == 1 else f"original-{index}"
    else:
        safe_id = re.sub(r"\D", "", comment_id) or "unknown"
        name = f"comment-{safe_id}-{index}"
    return f"images/{name}{suffix}"


def _extract_post(document, url: str) -> dict:
    post = _first(document, f"//*[{_class('post')}]")
    if post is None:
        return {
            "title": "",
            "author": "",
            "published_at": "",
            "content": "",
            "oo": 0,
            "xx": 0,
            "images": [],
        }

    title_el = _first(post, f".//h1 | .//h2 | .//*[{_class('post-title')}]")
    if title_el is None:
        title_el = _first(document, "//title")
    title = _text(title_el)
    author_el = _first(post, f".//*[{_class('post-author')}]")
    author = _text(author_el)
    meta_el = _first(post, f".//*[{_class('post-meta')}]")
    meta = _text(meta_el)
    published_match = re.search(r"\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?", meta)
    published_at = published_match.group() if published_match else ""

    content_el = _first(post, f".//*[{_class('post-content')}]")
    content = _text(content_el, "\n")
    images = []
    if content_el is not None:
        for index, image in enumerate(content_el.xpath(".//img"), start=1):
            image_url = _image_url(image, url)
            if not image_url:
                continue
            images.append({
                "url": image_url,
                "path": _image_path(image_url, "post", index),
                "role": "post",
            })

    func = _first(post, f".//*[{_class('post-func')}]")
    if func is None:
        func = post
    return {
        "title": title,
        "author": author,
        "published_at": published_at,
        "content": content,
        "oo": _number(_first(func, f".//*[{_class('oo_number')}]")),
        "xx": _number(_first(func, f".//*[{_class('xx_number')}]")),
        "images": images,
    }


def _extract_comments(document, url: str) -> tuple[list[dict], int]:
    comments = []
    seen_ids = set()
    excluded_rows = 0

    for row in document.xpath(f"//*[{_class('comment-row')}]"):
        floor_el = _first(row, f".//*[{_class('floor')}]")
        id_el = _first(row, f".//*[{_class('comment-id')}]")
        if floor_el is None or id_el is None:
            excluded_rows += 1
            continue

        comment_id = _text(id_el)
        if not comment_id or comment_id in seen_ids:
            excluded_rows += 1
            continue
        seen_ids.add(comment_id)

        content_el = _first(row, f".//*[{_class('comment-content')}]")
        author_el = _first(row, f".//*[{_class('author-core')}] | .//*[{_class('author-verify')}]")
        time_el = _first(row, f".//*[{_class('create-time')}]")
        floor = _text(floor_el)
        author = _text(author_el) or "匿名"
        timestamp = _text(time_el)
        content = _text(content_el, "\n")

        images = []
        if content_el is not None:
            for index, image in enumerate(content_el.xpath(".//img"), start=1):
                image_url = _image_url(image, url)
                if not image_url:
                    continue
                images.append({
                    "url": image_url,
                    "path": _image_path(image_url, "comment", index, comment_id),
                    "role": "comment",
                    "comment_id": comment_id,
                })

        comments.append({
            "floor": floor,
            "id": comment_id,
            "author": author,
            "time": timestamp,
            "content": content,
            "oo": _number(_first(row, f".//*[{_class('oo_number')}]")),
            "xx": _number(_first(row, f".//*[{_class('xx_number')}]")),
            "images": images,
        })

    return comments, excluded_rows


def _build_body(post: dict, comments: list[dict]) -> str:
    lines = [f"# {post['title']}", ""]
    byline = f"**楼主 @{post['author'] or '匿名'}**"
    if post["published_at"]:
        byline += f" · {post['published_at']}"
    lines.extend([byline, f"OO {post['oo']} · XX {post['xx']}", ""])
    if post["content"]:
        lines.extend([post["content"], ""])
    for image in post["images"]:
        lines.extend([f"![主帖图片]({image['path']})", ""])

    for comment in comments:
        lines.extend(["---", ""])
        heading = f"**{comment['floor']} @{comment['author']}** · {comment['id']}"
        if comment["time"]:
            heading += f" · {comment['time']}"
        heading += f" · OO {comment['oo']} · XX {comment['xx']}"
        lines.extend([heading, "", comment["content"], ""])
        for image in comment["images"]:
            lines.extend([f"![评论图片]({image['path']})", ""])

    return "\n".join(lines).strip()


def scrape_jandan(html: str, url: str, *, rendered_html: str | None = None,
                   final_url: str | None = None, **kwargs) -> dict:
    """解析煎蛋 /t/ 页面并返回带完整性契约的标准化数据。"""
    requested_id = source_id_from_url(url)
    final_url = final_url or url
    final_id = source_id_from_url(final_url)
    if not requested_id:
        return {
            "error": "unsupported_jandan_url",
            "message": "煎蛋专用解析器仅支持 /t/{id}",
            "type": "forum",
            "source": url,
        }
    if final_id != requested_id:
        return {
            "error": "source_mismatch",
            "message": f"请求帖子 {requested_id}，最终页面为 {final_id or final_url}",
            "type": "forum",
            "source": url,
            "final_source": final_url,
            "source_id": requested_id,
            "source_verified": False,
        }

    static_document = lxml_html.fromstring(html)
    post = _extract_post(static_document, url)
    page_id_match = re.search(r"No\.\s*(\d+)", post["title"], re.IGNORECASE)
    if page_id_match and page_id_match.group(1) != requested_id:
        return {
            "error": "source_mismatch",
            "message": f"请求帖子 {requested_id}，页面标题指向 {page_id_match.group(1)}",
            "type": "forum",
            "source": url,
            "final_source": final_url,
            "source_id": requested_id,
            "source_verified": False,
        }

    comments = []
    excluded_rows = 0
    rendered = rendered_html is not None
    comments_complete = False
    if rendered:
        rendered_document = lxml_html.fromstring(rendered_html)
        rendered_post = _extract_post(rendered_document, url)
        if post["author"] and rendered_post["author"] and post["author"] != rendered_post["author"]:
            return {
                "error": "author_mismatch",
                "message": "静态页面与渲染页面作者不一致，拒绝合并",
                "type": "forum",
                "source": url,
                "source_id": requested_id,
                "source_verified": False,
            }
        comments, excluded_rows = _extract_comments(rendered_document, url)
        comments_complete = bool(comments)

    comment_images = [image for comment in comments for image in comment["images"]]
    images = post["images"] + comment_images
    post_complete = bool(post["title"] and post["author"] and (post["content"] or post["images"]))
    warnings = []
    if not post_complete:
        warnings.append("post_incomplete")
    if not rendered:
        warnings.append("comments_require_rendered_page")
    elif not comments_complete:
        warnings.append("no_formal_comments_detected")

    body = _build_body(post, comments)
    return {
        "type": "forum",
        "source": url,
        "final_source": final_url,
        "source_id": requested_id,
        "source_verified": True,
        "source_title": post["title"],
        "title": post["title"],
        "author": post["author"],
        "date": post["published_at"][:10],
        "published_at": post["published_at"],
        "body": body,
        "word_count": len(re.findall(r"[一-鿿]", body)),
        "oo": post["oo"],
        "xx": post["xx"],
        "images": images,
        "comments": comments,
        "comment_count": len(comments),
        "hot_or_duplicate_rows_excluded": excluded_rows,
        "completeness": {
            "source": True,
            "post": post_complete,
            "comments": comments_complete,
            "complete": post_complete and comments_complete,
        },
        "capture": {
            "level": "L2" if rendered else "L1",
            "needs_rendered_page": not comments_complete,
            "warnings": warnings,
        },
    }
