#!/usr/bin/env python3
"""采集 Skill — 论坛抓取

提取论坛帖子正文 + 评论树，输出一体式 Markdown。

支持的论坛：
  - NGA（bbs.nga.cn）
  - V2EX（www.v2ex.com）
  - 贴吧（tieba.baidu.com）
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
from datetime import datetime
from urllib.parse import urlparse

import requests
import trafilatura

# 自动读取 .env 中保存的 Cookie（当前脚本目录）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cookie_store import get_cookie_for_url  # noqa: E402


# ---------------------------------------------------------------------------
# 论坛识别
# ---------------------------------------------------------------------------

FORUM_HANDLERS = {
    "bbs.nga.cn": "_scrape_nga",
    "nga.cn": "_scrape_nga",
    "nga.178.com": "_scrape_nga",
    "www.v2ex.com": "_scrape_v2ex",
    "v2ex.com": "_scrape_v2ex",
    "tieba.baidu.com": "_scrape_tieba",
}


def detect_forum(url: str) -> str | None:
    """根据域名识别论坛类型。"""
    domain = urlparse(url).netloc.lower().replace("www.", "")
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
    import html as _html
    text = _html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _parse_relative_time(s: str) -> str:
    """尝试解析相对时间 → YYYY-MM-DD。"""
    from datetime import timedelta
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


def _parse_post_date(cell) -> str:
    """从 NGA 帖子单元格提取发布日期。"""
    text = cell.get_text(" ", strip=True) if hasattr(cell, 'get_text') else str(cell)
    m = re.search(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}', text)
    if m:
        return m.group(1)
    m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    return m.group(1) if m else ""


def _extract_tid_from_url(url: str) -> str:
    """从 NGA URL 提取 thread ID。"""
    m = re.search(r'tid=(\d+)', url)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# NGA 辅助函数
# ---------------------------------------------------------------------------

def _get_nga_author(post, user_map: dict) -> str:
    """从帖子的 td.c1 中提取作者 UID 并查用户名。"""
    c1 = post.select_one("td.c1")
    if not c1:
        return ""
    for a in c1.select("a[href*='uid=']"):
        m = re.search(r'uid=(\d+)', a.get('href', ''))
        if m:
            return user_map.get(m.group(1), f"UID:{m.group(1)}")
    return ""


def _parse_nga_user_map(html: str, existing: dict | None = None) -> dict:
    """从 NGA 页面内嵌 JSON 提取 UID → 用户名映射，可合并已有映射。"""
    user_map = existing.copy() if existing else {}
    for m in re.finditer(r'"(\d{5,})":\{[^}]+"username":"([^"]+)"', html):
        if m.group(1) not in user_map:
            user_map[m.group(1)] = m.group(2)
    return user_map


def _extract_nga_total_pages(html: str) -> int:
    """从 NGA 页面提取总页数。返回至少 1。"""
    # 方法 1: __PAGE JS 变量
    m = re.search(r'__PAGE\s*=\s*\{[^}]*?(?:totalPages|total|pages)\s*[:=]\s*(\d+)', html)
    if m:
        return int(m.group(1))
    # 方法 2: "共 N 页"
    m = re.search(r'共\s*(\d+)\s*页', html)
    if m:
        return int(m.group(1))
    # 方法 3: 页面链接中的最大 page=N
    pages = set()
    for m in re.finditer(r'[?&]page=(\d+)', html):
        pages.add(int(m.group(1)))
    if pages:
        return max(pages)
    return 1


def _extract_nga_images(text: str) -> list[str]:
    """从文本中提取 [img]...[/img] 标签内的图片 URL 并规范化去重。

    URL 规范化规则：
      - ./ 开头的相对路径 → https://img.nga.178.com/attachments/ + 去掉 ./ 前缀
      - http 开头的完整 URL → 保持原样
      - 其他相对路径 → https://img.nga.178.com/attachments/ + 路径
    """
    urls = []
    seen: set[str] = set()
    for m in re.finditer(r'\[img\](.*?)\[/img\]', text, re.IGNORECASE):
        url = m.group(1).strip()
        if not url:
            continue
        # URL 规范化
        if url.startswith('./'):
            url = 'https://img.nga.178.com/attachments/' + url[2:]
        elif not url.startswith('http'):
            url = 'https://img.nga.178.com/attachments/' + url
        # else: http 开头的保持原样
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _clean_nga_bbcode(text: str) -> str:
    """清理 NGA BBCode 标签，转换为 Markdown。

    处理顺序（从内到外，参考 references/nga-bbcode.md）：
      1. 表情 [s:...]          → 移除
      2. 回复引用 [pid]...[/pid] → 移除
      3. @提及 [@]...[/@]       → @name
      4. 用户提及 [uid]...[/uid]  → @name
      5. 图片 [img]...[/img]    → 移除（URL 已单独提取）
      6. 内联格式 (b/i/u/del/color/size) → 迭代转换
      7. 链接 [url]              → Markdown 链接
      8. 引用 [quote]            → Markdown > 引用
      9. 折叠 [collapse]         → HTML <details>
      10. 代码 [code]            → Markdown ``` 代码块
      11. 列表 [list]            → Markdown 列表
      12. 标题 [h1]/[h2]/[h3]    → Markdown #
      13. 末尾"改动"标记         → 移除
      14. 残留标签碎片            → 清理
    """
    # === 1. 表情标签 [s:ac:xx] [s:a2:xx] ===
    text = re.sub(r'\[s:[^\]]+\]', '', text)

    # === 2. [pid=xxx]Reply[/pid] → 移除 ===
    text = re.sub(r'\[pid=[^\]]+\]Reply\[/pid\]', '', text)

    # === 3-4. [@]name[/@] → @name / [uid=xxx]name[/uid] → @name ===
    text = re.sub(r'\[@\]([^\[\]]*?)\[/@\]', r'@\1', text)
    text = re.sub(r'\[uid=\d+\]([^\[\]]*?)\[/uid\]', r'@\1', text)

    # === 5. [img]...[/img] → 移除（图片已在 _extract_nga_images 中提取） ===
    text = re.sub(r'\[img\][^\[]*?\[/img\]', '', text, flags=re.IGNORECASE)

    # === 6. 内联格式：迭代转换，每次只处理不含子标签的最内层 ===
    for _ in range(20):
        old = text
        text = re.sub(r'\[b\]([^\[\]]*?)\[/b\]', r'**\1**', text)
        text = re.sub(r'\[i\]([^\[\]]*?)\[/i\]', r'*\1*', text)
        text = re.sub(r'\[u\]([^\[\]]*?)\[/u\]', r'<u>\1</u>', text)
        text = re.sub(r'\[del\]([^\[\]]*?)\[/del\]', r'~~\1~~', text)
        text = re.sub(r'\[color=[^\]]+\]([^\[\]]*?)\[/color\]', r'\1', text)
        text = re.sub(r'\[size=[^\]]+\]([^\[\]]*?)\[/size\]', r'\1', text)
        if text == old:
            break

    # === 7. 链接 [url=xxx]text[/url] / [url]xxx[/url] ===
    text = re.sub(
        r'\[url=([^\]]+?)\]([^\[\]]*?)\[/url\]',
        r'[\2](\1)', text,
    )
    text = re.sub(r'\[url\]([^\[\]]*?)\[/url\]', r'\1', text)

    # === 8. 引用 [quote] —— 迭代处理嵌套（Markdown 只支持单层 >） ===
    for _ in range(10):
        old = text
        text = re.sub(
            r'\[quote\]([^\[\]]*?)\[/quote\]',
            lambda m: '\n> ' + m.group(1).strip().replace('\n', '\n> ') + '\n',
            text,
        )
        if text == old:
            break

    # === 9. 折叠 [collapse=title] / [collapse] ===
    text = re.sub(
        r'\[collapse=([^\]]+)\](.*?)\[/collapse\]',
        r'<details><summary>\1</summary>\n\n\2\n\n</details>',
        text, flags=re.DOTALL,
    )
    text = re.sub(
        r'\[collapse\](.*?)\[/collapse\]',
        r'<details><summary>点击展开</summary>\n\n\1\n\n</details>',
        text, flags=re.DOTALL,
    )

    # === 10. [code] → Markdown 代码块 ===
    text = re.sub(
        r'\[code\](.*?)\[/code\]',
        r'\n```\n\1\n```\n',
        text, flags=re.DOTALL,
    )

    # === 11. [list][*]item1[*]item2[/list] → Markdown 列表 ===
    text = re.sub(r'\[list\]\s*', '', text)
    text = re.sub(r'\[\*\](?!\])', '- ', text)
    text = re.sub(r'\[/list\]', '', text)

    # === 12. [h1]/[h2]/[h3] → Markdown 标题 ===
    text = re.sub(
        r'\[h([1-3])\](.*?)\[/h\1\]',
        lambda m: '#' * int(m.group(1)) + ' ' + m.group(2).strip(),
        text, flags=re.DOTALL,
    )

    # === 13. 末尾"改动"编辑标记 ===
    text = re.sub(r'\s*改动\s*$', '', text.strip())

    # === 14. 残留清理：未匹配的标签碎片 ===
    text = re.sub(r'\[/[^\]]+\]', '', text)   # 孤立结束标签 [/xxx]
    text = re.sub(r'\[[^\]=]+(?:=[^\]]*)?\]', '', text)  # 孤立开始标签 [xxx=...]

    # 压缩多余空行和空格
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)

    return text.strip()


def _parse_nga_replies(post_tables, user_map: dict, op_uid: str,
                        page_num: int = 1, start_index: int = 1,
                        skip_op_initial: bool = False) -> list[dict]:
    """解析 NGA 回复列表。

    Args:
        post_tables: BeautifulSoup 选中的帖子表格列表
        user_map: UID → 用户名映射
        op_uid: 楼主的 UID
        page_num: 当前页码
        start_index: 起始序号
        skip_op_initial: 是否跳过第一个表格（非首页的 OP 摘要区域）

    Returns:
        回复字典列表
    """
    replies = []
    for idx, table in enumerate(post_tables):
        # 非首页时跳过第一个表格（可能是 OP 摘要）
        if skip_op_initial and idx == 0:
            if table.select_one("td.comment_c_2"):
                continue

        author = _get_nga_author(table, user_map)
        is_op = (op_uid and author and user_map.get(op_uid) == author)

        c2 = table.select_one("td.c2")
        if not c2:
            continue
        text = c2.get_text(" ", strip=True)

        # 提取图片（清理前）
        reply_images = _extract_nga_images(text)

        # 提取时间
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})', text)
        r_date = date_match.group(1) if date_match else ""
        r_time = date_match.group(2) if date_match else ""

        # 提取赞数
        support = ""
        sup_match = re.search(r'支持(\d+)', text)
        if sup_match:
            support = sup_match.group(1)

        # 清理：去时间戳、支持/反对、发送自、操作菜单、收藏、改动记录、签名档
        content = text
        content = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}', '', content, count=1)
        content = re.sub(r'支持\d*', '', content)
        content = re.sub(r'反对\d*', '', content)
        content = re.sub(r'发送自.*?(?:客户端)?', '', content)
        content = re.sub(r'收藏|操作菜单|举报|锁定', '', content)
        content = re.sub(r'\+\s*R\s*by.*?(?=\n|$)', '', content, flags=re.DOTALL)
        content = re.sub(r'改动\n在.*?(?:修改|$)', '', content, flags=re.DOTALL)
        content = re.sub(r'BBS\.NGA\.CN[\s\S]*$', '', content)
        content = re.sub(r'无法编辑/回复', '', content)
        content = _clean_text(content)
        content = _clean_nga_bbcode(content)

        if content.strip():
            replies.append({
                "author": author,
                "is_op": is_op,
                "date": r_date,
                "time": r_time,
                "support": support,
                "content": content.strip(),
                "page": page_num,
                "index": start_index + len(replies),
                "images": reply_images,
            })

    return replies


# ---------------------------------------------------------------------------
# NGA 专用处理器
# ---------------------------------------------------------------------------

def _scrape_nga(html: str, url: str, cookie: str | None = None,
                timeout: int = 30, max_pages: int | None = None) -> dict:
    """抓取 NGA 帖子（支持多页）。

    NGA 页面结构：
      - 内嵌 JSON 用户数据              → UID → 用户名映射
      - table.forumbox.postbox           → 帖子（第一页第一个是 OP，后续是回复）
      - OP 内 td.c1                      → OP 作者的 UID 链接
      - OP 内 td.c2                      → 正文内容
      - OP 内 td.comment_c_2             → 热点回复（仅第一页，格式：+ 时间 内容）
      - 回复 td.c1                       → 回复作者的 UID 链接
      - 回复 td.c2                       → 回复内容
    """
    import time
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    # --- 用户映射：从页面内嵌 JSON 提取 UID → 用户名 ---
    user_map = _parse_nga_user_map(html)

    # --- 标题 ---
    title = ""
    title_el = soup.find("title")
    if title_el:
        title = _clean_text(title_el.get_text())
        title = re.sub(r'\s*NGA玩家社区\s*$', '', title)

    # --- 所有帖子 ---
    post_tables = soup.select("table.forumbox.postbox")
    if not post_tables:
        return _scrape_nga_fallback(html, url, soup)

    # === OP ===
    op = post_tables[0]
    op_date = ""

    # OP 正文 → td.c2
    op_c2 = op.select_one("td.c2")
    op_raw = op_c2.get_text("\n", strip=True) if op_c2 else ""

    # 提取 OP 图片
    op_images = _extract_nga_images(op_raw)

    # 提取日期
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}', op_raw)
    if date_match:
        op_date = date_match.group(1)

    # 清理 OP 正文：去掉时间戳、热点回复区域、UID 行
    op_body = op_raw
    op_body = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}', '', op_body, count=1)
    # 截断在热点回复 UID 之前（op_raw 末尾会混入热评 UID）
    edit_pos = len(op_body)
    for marker in ['\n改动\n', '\n热点回复\n', '\nUID:', '\n+\n']:
        pos = op_body.find(marker)
        if pos > 0 and pos < edit_pos:
            edit_pos = pos
    op_body = op_body[:edit_pos].strip()
    op_body = _clean_text(op_body)
    op_body = _clean_nga_bbcode(op_body)

    # === 热点回复 → td.comment_c_2（仅第一页） ===
    hot_replies = []
    for cell in op.select("td.comment_c_2"):
        text = cell.get_text(" ", strip=True)
        text = re.sub(r'^\+\s*', '', text)
        date_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', text)
        hot_time = date_match.group(1) if date_match else ""
        hot_content = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s*', '', text).strip()
        hot_content = _clean_nga_bbcode(hot_content)
        if hot_content:
            hot_replies.append({"time": hot_time, "content": hot_content})

    # === OP 作者 UID 和用户名 ===
    op_uid = ""
    op_a_tags = post_tables[0].select_one("td.c1")
    if op_a_tags:
        op_a = op_a_tags.select("a[href*='uid=']")
        if op_a:
            op_uid_match = re.search(r'uid=(\d+)', op_a[0].get('href', ''))
            if op_uid_match:
                op_uid = op_uid_match.group(1)
    op_author = _get_nga_author(post_tables[0], user_map)

    # === 总页数 ===
    total_pages = _extract_nga_total_pages(html)

    # 限制最大页数
    pages_to_fetch = total_pages
    if max_pages is not None and max_pages > 0:
        pages_to_fetch = min(total_pages, max_pages)

    # 超大帖子提醒
    if total_pages >= 100:
        estimated = total_pages * 3  # 每页约 3 秒延迟
        print(
            f"⚠️  该帖子共 {total_pages} 页，预计耗时约 {estimated} 秒。"
            f"可用 --max-pages 限制采集页数。",
            file=sys.stderr,
        )
    elif pages_to_fetch > 1:
        print(f"📋 帖子共 {total_pages} 页，将采集 {pages_to_fetch} 页。", file=sys.stderr)

    # === 第一页回复 ===
    all_replies = []
    page1_replies = _parse_nga_replies(
        post_tables[1:], user_map, op_uid, page_num=1, start_index=1
    )
    all_replies.extend(page1_replies)

    # === 采集后续页面 ===
    tid = _extract_tid_from_url(url)
    crawl_delay = 3  # 默认 3 秒，与 .web-analysis.yaml 一致
    failed_pages = []  # 记录采集失败的页码

    for page_num in range(2, pages_to_fetch + 1):
        try:
            page_url = f"https://bbs.nga.cn/read.php?tid={tid}&page={page_num}"
            print(f"  📄 第 {page_num}/{pages_to_fetch} 页...", file=sys.stderr)

            page_html = _fetch_html(page_url, cookie, timeout)
            page_soup = BeautifulSoup(page_html, "lxml")

            # 合并用户映射（后续页面可能有新用户）
            user_map = _parse_nga_user_map(page_html, user_map)

            # 解析回复（跳过可能是 OP 摘要的第一个表格）
            page_post_tables = page_soup.select("table.forumbox.postbox")
            page_replies = _parse_nga_replies(
                page_post_tables, user_map, op_uid,
                page_num=page_num, start_index=len(all_replies) + 1,
                skip_op_initial=True,
            )
            all_replies.extend(page_replies)

            # 页间延迟
            if page_num < pages_to_fetch:
                time.sleep(crawl_delay)

        except Exception as e:
            failed_pages.append({"page": page_num, "error": str(e)})
            print(f"  ⚠️  第 {page_num} 页采集失败: {e}", file=sys.stderr)
            continue

    # === 汇总图片（去重：同一 URL 只保留首次出现的 source） ===
    images: list[dict] = []
    seen_urls: set[str] = set()
    # OP 图片
    for img_url in op_images:
        if img_url not in seen_urls:
            seen_urls.add(img_url)
            images.append({"url": img_url, "source": "op"})
    # 回复图片
    for r in all_replies:
        for img_url in r.get("images", []):
            if img_url not in seen_urls:
                seen_urls.add(img_url)
                images.append({
                    "url": img_url,
                    "source": f"reply_{r.get('index', '?')}",
                })

    # === 分配图片本地路径 & 嵌入 Markdown ===
    url_to_local: dict[str, str] = {}
    for i, img in enumerate(images, 1):
        ext = img['url'].rsplit('.', 1)[-1].split('?')[0]
        if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'):
            ext = 'jpg'
        path = f"images/{i:02d}.{ext}"
        img['path'] = path
        url_to_local[img['url']] = path

    # 嵌入 OP 图片
    for img_url in op_images:
        if img_url in url_to_local:
            op_body += f"\n\n![]({url_to_local[img_url]})"

    # 嵌入回复图片（仅嵌入到源回复，避免跨页重复）
    reply_image_map: dict[int, list[str]] = {}
    for img in images:
        src = img['source']
        if src.startswith('reply_'):
            idx = int(src.split('_')[1])
            reply_image_map.setdefault(idx, []).append(img['url'])

    for r in all_replies:
        r_idx = r.get('index')
        if r_idx in reply_image_map:
            for img_url in reply_image_map[r_idx]:
                if img_url in url_to_local:
                    r['content'] += f"\n\n![]({url_to_local[img_url]})"

    # === 构建输出 Markdown ===
    lines = [f"# {title}\n"]
    author_line = f"**楼主 @{op_author}**" if op_author else ""
    date_line = f" · {op_date}" if op_date else ""
    lines.append(f"{author_line}{date_line}\n")
    lines.append(f"> {op_body}\n")

    if hot_replies:
        lines.append("---\n## 🔥 热点回复\n")
        for i, hr in enumerate(hot_replies):
            lines.append(f"- **#{i+1}** · {hr['time']}：{hr['content']}\n")

    if all_replies:
        lines.append("---\n## 💬 回复\n")
        current_page = 1
        for i, r in enumerate(all_replies):
            # 页面分界标记
            if r.get('page', 1) != current_page:
                current_page = r.get('page', 1)
                lines.append(f"\n--- 第 {current_page} 页 ---\n")

            sup = f" · 赞 {r['support']}" if r.get('support') else ""
            op_tag = " **[楼主]**" if r.get('is_op') else ""
            author_str = (
                f"@{r['author']}{op_tag}" if r.get('author')
                else f"#{r.get('index', i + 1)}"
            )
            lines.append(
                f"**{author_str}** · {r.get('date', '')} {r.get('time', '')}{sup}\n"
            )
            lines.append(f"{r['content']}\n")

    body = '\n'.join(lines)
    word_count = len(re.findall(r'[一-鿿]', body))

    # 生成 slug
    slug = re.sub(r'[\\/:*?"<>|\[\]]', '', title).strip()[:60]

    return {
        "type": "forum",
        "source": url,
        "title": title,
        "author": "",
        "date": op_date,
        "body": body,
        "word_count": word_count,
        "comment_count": len(all_replies),
        "hot_reply_count": len(hot_replies),
        "total_pages": total_pages,
        "pages_collected": pages_to_fetch - len(failed_pages),
        "pages_failed": len(failed_pages),
        "failed_pages": failed_pages if failed_pages else None,
        "images": images,
        "slug": slug,
        "fetched_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _scrape_nga_fallback(html: str, url: str, soup=None, **kwargs) -> dict:
    """NGA 降级方案：trafilatura + 通用选择器。"""
    from bs4 import BeautifulSoup
    if soup is None:
        soup = BeautifulSoup(html, "lxml")

    body = trafilatura.extract(html, output_format="markdown", with_metadata=True)

    title = ""
    title_el = soup.find("title")
    if title_el:
        title = _clean_text(title_el.get_text())
        title = re.sub(r'\s*NGA玩家社区\s*$', '', title)

    # 通用评论提取
    comments = []
    for el in soup.select("[class*='post'], [class*='reply'], [id*='post']"):
        text = _clean_text(el.get_text())
        if len(text) > 20:
            comments.append({"author": "", "time": "", "content": text[:500]})

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
        "hot_reply_count": 0,
        "images": [],
    }


# ---------------------------------------------------------------------------
# V2EX
# ---------------------------------------------------------------------------

def _scrape_v2ex(html: str, url: str, **kwargs) -> dict:
    """抓取 V2EX 帖子。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("h1")
    title = _clean_text(title_el.text) if title_el else ""

    op_el = soup.select_one(".topic_content")
    op_text = _clean_text(op_el.text) if op_el else ""

    author_el = soup.select_one(".header small a")
    author = _clean_text(author_el.text) if author_el else ""

    time_el = soup.select_one(".header small span")
    op_time = _clean_text(time_el.text) if time_el else ""

    comments = []
    for cell in soup.select(".cell[id^='r_']"):
        user_el = cell.select_one("strong a")
        user = _clean_text(user_el.text) if user_el else "匿名"

        time_el2 = cell.select_one(".ago")
        t = _clean_text(time_el2.text) if time_el2 else ""

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

def _scrape_tieba(html: str, url: str, **kwargs) -> dict:
    """抓取百度贴吧帖子。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(".core_title_txt") or soup.select_one("h1")
    title = _clean_text(title_el.text) if title_el else ""

    floors = []
    for floor in soup.select(".l_post"):
        user_el = floor.select_one(".d_name a")
        user = _clean_text(user_el.text) if user_el else "匿名"

        content_els = floor.select(".d_post_content")
        content = ""
        for el in content_els:
            content += _clean_text(el.text) + "\n"

        time_el2 = floor.select_one(".tail-info:last-child")
        t = _clean_text(time_el2.text) if time_el2 else ""

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

    body = trafilatura.extract(html, output_format="markdown", with_metadata=True)

    soup = BeautifulSoup(html, "lxml")

    title = ""
    title_el = soup.select_one("h1, .title, .thread-title, [class*='topic-title']")
    if title_el:
        title = _clean_text(title_el.text)

    comments = []
    for sel in [".post", ".comment", ".reply", "[class*='post-']", "article"]:
        elements = soup.select(sel)
        if len(elements) > 50:
            print(f"⚠️  通用论坛评论 ({len(elements)}) 超过上限 (50)，已截断。", file=sys.stderr)
        for el in elements[:50]:
            user_el = el.select_one("[class*='user'], [class*='author'], a[href*='user']")
            user = _clean_text(user_el.text) if user_el else ""
            content_el = el.select_one("[class*='content'], [class*='body'], [class*='text']")
            content = _clean_text(content_el.text) if content_el else _clean_text(el.text)
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
# 输出构建
# ---------------------------------------------------------------------------

def _build_forum_body(title: str, op_author: str, op_content: str,
                      comments: list[dict]) -> str:
    """构建一体式论坛 Markdown（V2EX/贴吧 使用）。"""
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

def scrape(url: str, cookie: str | None = None, timeout: int = 30,
           max_pages: int | None = None) -> dict:
    """论坛抓取主入口。

    Args:
        url: 帖子 URL
        cookie: Cookie 字符串（None 则从 .env 自动读取）
        timeout: HTTP 请求超时秒数
        max_pages: 最大采集页数（None = 全部；仅 NGA 支持）
    """
    html = _fetch_html(url, cookie, timeout)

    handler_name = detect_forum(url)
    if handler_name:
        handler = globals().get(handler_name)
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
