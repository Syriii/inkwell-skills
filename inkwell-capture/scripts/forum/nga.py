#!/usr/bin/env python3
"""NGA 论坛专用处理器（bbs.nga.cn / nga.178.com）。

NGA 页面结构：
  - 内嵌 JSON 用户数据              → UID → 用户名映射
  - table.forumbox.postbox           → 帖子（第一页第一个是 OP，后续是回复）
  - OP 内 td.c1                      → OP 作者的 UID 链接
  - OP 内 td.c2                      → 正文内容
  - OP 内 td.comment_c_2             → 热点回复（仅第一页，格式：+ 时间 内容）
  - 回复 td.c1                       → 回复作者的 UID 链接
  - 回复 td.c2                       → 回复内容
"""

import re
import sys
import time
from datetime import datetime

from bs4 import BeautifulSoup

from utils import clean_text, fetch_html


# ---------------------------------------------------------------------------
# 用户与元数据
# ---------------------------------------------------------------------------

def get_nga_author(post, user_map: dict) -> str:
    """从帖子的 td.c1 中提取作者 UID 并查用户名。"""
    c1 = post.select_one("td.c1")
    if not c1:
        return ""
    for a in c1.select("a[href*='uid=']"):
        m = re.search(r'uid=(\d+)', a.get('href', ''))
        if m:
            return user_map.get(m.group(1), f"UID:{m.group(1)}")
    return ""


def parse_nga_user_map(html: str, existing: dict | None = None) -> dict:
    """从 NGA 页面内嵌 JSON 提取 UID → 用户名映射，可合并已有映射。"""
    user_map = existing.copy() if existing else {}
    for m in re.finditer(r'"(\d{5,})":\{[^}]+"username":"([^"]+)"', html):
        if m.group(1) not in user_map:
            user_map[m.group(1)] = m.group(2)
    return user_map


def extract_nga_total_pages(html: str) -> int:
    """从 NGA 页面提取总页数。返回至少 1。"""
    # 方法 1: __PAGE JS 变量
    # NGA 格式: __PAGE = {0:'url',1:总页数,2:当前页,3:每页帖数}
    # 先匹配数字键格式 1:N，再匹配命名键格式 totalPages:N
    m = re.search(r'__PAGE\s*=\s*\{[^}]*?[,{]1\s*:\s*(\d+)', html)
    if not m:
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


def parse_post_date(cell) -> str:
    """从 NGA 帖子单元格提取发布日期。"""
    text = cell.get_text(" ", strip=True) if hasattr(cell, 'get_text') else str(cell)
    m = re.search(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}', text)
    if m:
        return m.group(1)
    m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    return m.group(1) if m else ""


def extract_tid_from_url(url: str) -> str:
    """从 NGA URL 提取 thread ID。"""
    m = re.search(r'tid=(\d+)', url)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# 图片提取
# ---------------------------------------------------------------------------

def extract_nga_images(text: str) -> list[str]:
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


# ---------------------------------------------------------------------------
# BBCode 清理
# ---------------------------------------------------------------------------

def clean_nga_bbcode(text: str) -> str:
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

    # === 5. [img]...[/img] → 移除（图片已在 extract_nga_images 中提取） ===
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


# ---------------------------------------------------------------------------
# 回复解析
# ---------------------------------------------------------------------------

def parse_nga_replies(post_tables, user_map: dict, op_uid: str,
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

        author = get_nga_author(table, user_map)
        is_op = (op_uid and author and user_map.get(op_uid) == author)

        c2 = table.select_one("td.c2")
        if not c2:
            continue
        text = c2.get_text(" ", strip=True)

        # 提取图片（清理前）
        reply_images = extract_nga_images(text)

        # 提取时间
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})', text)
        r_date = date_match.group(1) if date_match else ""
        r_time = date_match.group(2) if date_match else ""

        # 提取赞数（先提取后清理，避免正则冲突）
        support = ""
        sup_match = re.search(r'支持(\d+)', text)
        if sup_match:
            support = sup_match.group(1)

        # 清理：去时间戳、支持/反对计数、发送自、操作菜单、收藏、改动记录、签名档
        content = text
        content = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}', '', content, count=1)
        # 注意：仅移除 UI 中的「支持N」「反对N」计数标签（N≥1），
        # 避免误删用户正文中的「支持」一词（如「我支持这个观点」）
        content = re.sub(r'支持\d+', '', content)
        content = re.sub(r'反对\d+', '', content)
        content = re.sub(r'发送自.*?(?:客户端)?', '', content)
        content = re.sub(r'收藏|操作菜单|举报|锁定', '', content)
        content = re.sub(r'\+\s*R\s*by.*?(?=\n|$)', '', content, flags=re.DOTALL)
        content = re.sub(r'改动\n在.*?(?:修改|$)', '', content, flags=re.DOTALL)
        content = re.sub(r'BBS\.NGA\.CN[\s\S]*$', '', content)
        content = re.sub(r'无法编辑/回复', '', content)
        content = clean_text(content)
        content = clean_nga_bbcode(content)

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
# 主抓取逻辑
# ---------------------------------------------------------------------------

def scrape_nga(html: str, url: str, cookie: str | None = None,
               timeout: int = 30, max_pages: int | None = None, **kwargs) -> dict:
    """抓取 NGA 帖子（支持多页）。"""
    soup = BeautifulSoup(html, "lxml")

    # --- 用户映射：从页面内嵌 JSON 提取 UID → 用户名 ---
    user_map = parse_nga_user_map(html)

    # --- 标题 ---
    title = ""
    title_el = soup.find("title")
    if title_el:
        title = clean_text(title_el.get_text())
        title = re.sub(r'\s*NGA玩家社区\s*$', '', title)

    # --- 所有帖子 ---
    post_tables = soup.select("table.forumbox.postbox")
    if not post_tables:
        return scrape_nga_fallback(html, url, soup)

    # === OP ===
    op = post_tables[0]
    op_date = ""

    # OP 正文 → td.c2
    op_c2 = op.select_one("td.c2")
    op_raw = op_c2.get_text("\n", strip=True) if op_c2 else ""

    # 提取 OP 图片
    op_images = extract_nga_images(op_raw)

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
    op_body = clean_text(op_body)
    op_body = clean_nga_bbcode(op_body)

    # === 热点回复 → td.comment_c_2（仅第一页） ===
    hot_replies = []
    for cell in op.select("td.comment_c_2"):
        text = cell.get_text(" ", strip=True)
        text = re.sub(r'^\+\s*', '', text)
        date_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', text)
        hot_time = date_match.group(1) if date_match else ""
        hot_content = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s*', '', text).strip()
        hot_content = clean_nga_bbcode(hot_content)
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
    op_author = get_nga_author(post_tables[0], user_map)

    # === 总页数 ===
    total_pages = extract_nga_total_pages(html)

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
    page1_replies = parse_nga_replies(
        post_tables[1:], user_map, op_uid, page_num=1, start_index=1
    )
    all_replies.extend(page1_replies)

    # === 采集后续页面 ===
    tid = extract_tid_from_url(url)
    crawl_delay = 3  # 默认 3 秒，与 .web-analysis.yaml 一致
    failed_pages = []  # 记录采集失败的页码

    for page_num in range(2, pages_to_fetch + 1):
        try:
            page_url = f"https://bbs.nga.cn/read.php?tid={tid}&page={page_num}"
            print(f"  📄 第 {page_num}/{pages_to_fetch} 页...", file=sys.stderr)

            page_html = fetch_html(page_url, cookie, timeout)
            page_soup = BeautifulSoup(page_html, "lxml")

            # 合并用户映射（后续页面可能有新用户）
            user_map = parse_nga_user_map(page_html, user_map)

            # 解析回复（跳过可能是 OP 摘要的第一个表格）
            page_post_tables = page_soup.select("table.forumbox.postbox")
            page_replies = parse_nga_replies(
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

    # 生成 slug（中文标题直接使用，非中文标题警告）
    slug = re.sub(r'[\\/:*?"<>|\[\]]', '', title).strip()[:60]
    has_chinese = bool(re.search(r'[一-鿿]', slug))
    if not has_chinese:
        print(f"⚠️  标题不含中文字符，slug 可能不可读: '{slug}'", file=sys.stderr)

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


def scrape_nga_fallback(html: str, url: str, soup=None, **kwargs) -> dict:
    """NGA 降级方案：trafilatura + 通用选择器。"""
    import trafilatura

    if soup is None:
        soup = BeautifulSoup(html, "lxml")

    body = trafilatura.extract(html, output_format="markdown", with_metadata=True)

    title = ""
    title_el = soup.find("title")
    if title_el:
        title = clean_text(title_el.get_text())
        title = re.sub(r'\s*NGA玩家社区\s*$', '', title)

    # 通用评论提取
    comments = []
    for el in soup.select("[class*='post'], [class*='reply'], [id*='post']"):
        text = clean_text(el.get_text())
        if len(text) > 20:
            comments.append({"author": "", "time": "", "content": text[:500]})

    word_count = len(re.findall(r'[一-鿿]', body or ""))

    # 生成 slug（fallback 用 title，清洗非法字符）
    slug = re.sub(r'[\\/:*?"<>|\[\]]', '', title).strip()[:60] if title else "untitled"

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
        "total_pages": 1,
        "pages_collected": 1,
        "pages_failed": 0,
        "failed_pages": None,
        "slug": slug,
        "fetched_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
