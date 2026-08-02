#!/usr/bin/env python3
"""Inkwell Capture — 共享工具函数

被 web_fetch.py、web_fetch_full.py、forum_scraper.py、archiver.py 等脚本引用。
提供 HTTP 请求、文本清理、日期标准化、YAML 转义等通用能力。
"""

import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# HTTP
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


def fetch_html(url: str, cookie: str | None = None, timeout: int = 30) -> str:
    """获取网页 HTML。

    Args:
        url: 目标 URL
        cookie: 可选的 Cookie 字符串
        timeout: 请求超时秒数

    Returns:
        HTML 文本

    Raises:
        requests.RequestException: 网络错误
    """
    import requests

    headers = HEADERS.copy()
    if cookie:
        headers["Cookie"] = cookie
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    enc = (resp.apparent_encoding or "utf-8").lower()
    if enc in ("gbk", "gb2312", "gb18030"):
        # GB18030 是 GBK/GB2312 的超集，可覆盖生僻字（如 叒/叕）。
        # requests 的 charset 检测对 GBK 系页面常误报为 gb2312，导致生僻字乱码。
        enc = "gb18030"
    resp.encoding = enc
    return resp.text


# ---------------------------------------------------------------------------
# 文本清理
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """清理 HTML 实体和多余空白。"""
    import html as _html

    text = _html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ---------------------------------------------------------------------------
# 日期处理
# ---------------------------------------------------------------------------

def normalize_date(s: str) -> str:
    """标准化日期格式 → YYYY-MM-DD。

    支持格式：
      - YYYY-MM-DD（已是标准格式，直接返回）
      - YYYY-MM-DDTHH:MM:SS / YYYY-MM-DD HH:MM:SS
      - YYYY年MM月DD日
      - Month DD, YYYY / DD Month YYYY（英文）
    """
    if not s or not isinstance(s, str):
        return ""

    # 已是标准格式
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s

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


def parse_relative_time(s: str) -> str:
    """解析相对时间 → YYYY-MM-DD。

    支持：N小时前 / N天前 / N分钟前 / YYYY-MM-DD
    """
    now = datetime.now()
    s = s.strip()

    m = re.match(r'(\d+)\s*小时前', s)
    if m:
        dt = now - timedelta(hours=int(m.group(1)))
        return dt.strftime("%Y-%m-%d")

    m = re.match(r'(\d+)\s*天前', s)
    if m:
        dt = now - timedelta(days=int(m.group(1)))
        return dt.strftime("%Y-%m-%d")

    m = re.match(r'(\d+)\s*分钟前', s)
    if m:
        return now.strftime("%Y-%m-%d")

    m = re.match(r'(\d{4}-\d{2}-\d{2})', s)
    if m:
        return m.group(1)

    return s


# ---------------------------------------------------------------------------
# URL 工具
# ---------------------------------------------------------------------------

def extract_domain(url: str) -> str:
    """从 URL 提取域名（不含 www 前缀）。"""
    parsed = urlparse(url)
    return parsed.hostname or ""


# ---------------------------------------------------------------------------
# YAML / Markdown
# ---------------------------------------------------------------------------

def escape_yaml(s: str) -> str:
    """Escape chars that could break YAML double-quoted strings.

    Chinese curly double quotes conflict with YAML delimiters
    in some parsers (e.g. Obsidian), so normalize to corner brackets.
    """
    s = s.replace(chr(0x201c), chr(0x300c)).replace(chr(0x201d), chr(0x300d))
    return s.replace(chr(92), chr(92)+chr(92)).replace(chr(34), chr(92)+chr(34))

def extract_title_from_body(body: str) -> str:
    """从 Markdown body 中提取第一个 # 标题作为 title 兜底。"""
    m = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# 论坛 Markdown 构建
# ---------------------------------------------------------------------------

def build_forum_body(title: str, op_author: str, op_content: str,
                     comments: list[dict]) -> str:
    """构建一体式论坛 Markdown（V2EX/贴吧/通用论坛 使用）。"""
    lines = [f"# {title}\n"]
    lines.append(f"**楼主 @{op_author}**\n")
    lines.append(f"> {op_content}\n")

    for i, c in enumerate(comments):
        lines.append("---\n")
        likes = f" · 👍 {c['likes']}" if c.get("likes") else ""
        lines.append(f"**@{c['author']}** · {c['time']}{likes}\n")
        lines.append(f"{c['content']}\n")

    return '\n'.join(lines)
