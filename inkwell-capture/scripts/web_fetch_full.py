#!/usr/bin/env python3
"""采集 Skill — L2 网页抓取（Playwright 渲染）

JavaScript 渲染页面的正文提取，作为 L1（web_fetch.py）的降级方案。
启动 headless Chromium，等待页面加载完成后提取内容。

用法：
  python web_fetch_full.py --url "https://spa-site.com/article"
  python web_fetch_full.py --url "https://..." --cookie "name=value" --wait 3000

输出 JSON：与 web_fetch.py 相同格式
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from urllib.parse import urljoin

# 自动读取 .env 中保存的 Cookie（当前脚本目录）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cookie_store import get_cookie_for_url  # noqa: E402


def fetch_full(url: str, cookie: str | None = None,
               wait_ms: int = 3000, timeout: int = 60) -> dict:
    """L2 抓取：Playwright 渲染 + trafilatura 提取。

    由于 Playwright 在一些环境中需要安装浏览器，
    脚本在 import 时可能失败——调用方应捕获并降级到手动方案。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "error": "playwright_not_installed",
            "message": "Playwright 未安装。运行: pip install playwright && playwright install chromium",
            "type": "webpage",
            "source": url,
        }

    try:
        import trafilatura
        from trafilatura.metadata import extract_metadata
    except ImportError:
        return {
            "error": "trafilatura_not_installed",
            "message": "trafilatura 未安装。运行: pip install trafilatura",
            "type": "webpage",
            "source": url,
        }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )

        if cookie:
            # cookie 格式: "name1=value1; name2=value2"
            cookies = []
            for pair in cookie.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    name, value = pair.split("=", 1)
                    cookies.append({
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": _extract_domain(url),
                        "path": "/",
                    })
            context.add_cookies(cookies)

        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            # 等待额外时间让动态内容加载
            page.wait_for_timeout(wait_ms)

            html = page.content()
            title = page.title()

            # 提取所有图片
            images = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('img[src]'))
                    .map(img => img.src)
                    .filter(src => !src.startsWith('data:'))
                    .slice(0, 30);
            }""")

        except Exception as e:
            browser.close()
            return {
                "error": "playwright_navigation_failed",
                "message": str(e),
                "type": "webpage",
                "source": url,
            }

        browser.close()

    # --- 正文提取 ---
    body = trafilatura.extract(
        html,
        output_format="markdown",
        with_metadata=True,
        include_comments=False,
        include_tables=True,
        include_images=True,
    )

    if not body:
        return {
            "error": "trafilatura_extraction_failed",
            "message": "即使在 JS 渲染后也无法提取正文",
            "type": "webpage",
            "source": url,
            "body": "",
        }

    # --- 元数据 ---
    try:
        meta_raw = extract_metadata(html, default_date=False)
        if meta_raw is None:
            meta = {}
        elif isinstance(meta_raw, dict):
            meta = meta_raw
        else:
            # trafilatura >= 2.0 returns Document object
            meta = {k: v for k, v in meta_raw.__dict__.items() if v}
    except TypeError:
        try:
            meta_raw = extract_metadata(html)
            if meta_raw is None:
                meta = {}
            elif isinstance(meta_raw, dict):
                meta = meta_raw
            else:
                meta = {k: v for k, v in meta_raw.__dict__.items() if v}
        except Exception:
            meta = {}
    date = meta.get("date") or ""
    author = meta.get("author") or ""

    if date:
        try:
            date = _normalize_date(date)
        except Exception:
            pass

    # --- 图片 ---
    image_list = []
    seen = set()
    for src in (images or []):
        if src in seen:
            continue
        seen.add(src)
        image_list.append({"url": urljoin(url, src), "path": ""})

    word_count = len(re.findall(r'[一-鿿]', body))

    return {
        "type": "webpage",
        "source": url,
        "date": date,
        "author": author,
        "title": title or meta.get("title", ""),
        "body": body.strip() if body else "",
        "word_count": word_count,
        "images": image_list,
    }


def _normalize_date(s: str) -> str:
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y年%m月%d日"]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _extract_domain(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return parsed.hostname or ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="L2 网页抓取 — Playwright 渲染")
    parser.add_argument("--url", required=True, help="目标 URL")
    parser.add_argument("--cookie", default=None, help="Cookie 字符串")
    parser.add_argument("--wait", type=int, default=3000, help="页面加载后额外等待（毫秒）")
    parser.add_argument("--timeout", type=int, default=60, help="导航超时（秒）")

    args = parser.parse_args()

    # --cookie 未指定时，从 .env 自动读取
    cookie = args.cookie or get_cookie_for_url(args.url)

    try:
        result = fetch_full(args.url, cookie, args.wait, args.timeout)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
        sys.exit(1 if "error" in result else 0)
    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
