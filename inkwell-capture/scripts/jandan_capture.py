#!/usr/bin/env python3
"""采集煎蛋 /t/{id} 主帖与动态评论，输出标准化 JSON。

默认先请求静态 HTML，再按需启动独立 Playwright 浏览器补齐评论。
使用 --no-render 可只做 L1；使用归档参数可将完整结果交给 archiver.py 写入。
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from archiver import archive  # noqa: E402
from cookie_store import get_cookie_for_url  # noqa: E402
from forum.jandan import scrape_jandan, source_id_from_url  # noqa: E402
from utils import HEADERS  # noqa: E402


def fetch_static(url: str, cookie: str | None, timeout: int) -> tuple[str, str]:
    headers = HEADERS.copy()
    if cookie:
        headers["Cookie"] = cookie
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        payload = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
        try:
            text = payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            text = payload.decode("gb18030", errors="replace")
        return text, response.geturl()


def render_html(url: str, cookie: str | None, timeout: int, wait_ms: int) -> tuple[str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "需要 Playwright 才能采集动态评论；安装依赖并执行 playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="zh-CN",
            )
            if cookie:
                cookies = []
                domain = urlparse(url).hostname or "jandan.net"
                for pair in cookie.split(";"):
                    if "=" not in pair:
                        continue
                    name, value = pair.strip().split("=", 1)
                    cookies.append({
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": domain,
                        "path": "/",
                    })
                if cookies:
                    context.add_cookies(cookies)

            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            try:
                page.wait_for_selector(".comment-row .floor", timeout=wait_ms)
            except Exception:
                page.wait_for_timeout(wait_ms)
            return page.content(), page.url
        finally:
            browser.close()


def find_duplicate(project_root: Path, source: str) -> str:
    marker = f'source: "{source}"'
    archive_root = project_root / "archived"
    if not archive_root.is_dir():
        return ""
    for path in archive_root.rglob("*.md"):
        try:
            if marker in path.read_text(encoding="utf-8"):
                return str(path.relative_to(project_root))
        except (OSError, UnicodeDecodeError):
            continue
    return ""


def capture(url: str, cookie: str | None = None, timeout: int = 60,
            wait_ms: int = 10000, render: bool = True,
            static_html: str | None = None,
            rendered_html: str | None = None) -> dict:
    if not source_id_from_url(url):
        return {
            "error": "unsupported_jandan_url",
            "message": "仅支持 https://jandan.net/t/{id}",
            "source": url,
        }

    if static_html is None:
        static_html, static_final_url = fetch_static(url, cookie, timeout)
    else:
        static_final_url = url

    if rendered_html is None and render:
        rendered_html, rendered_final_url = render_html(url, cookie, timeout, wait_ms)
    else:
        rendered_final_url = url

    final_url = rendered_final_url if rendered_html is not None else static_final_url
    return scrape_jandan(
        static_html,
        url,
        rendered_html=rendered_html,
        final_url=final_url,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="采集煎蛋 /t/ 帖子和动态评论")
    parser.add_argument("--url", required=True)
    parser.add_argument("--cookie", default=None)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--wait", type=int, default=10000, help="等待动态评论的毫秒数")
    parser.add_argument("--no-render", action="store_true", help="只采集静态主帖")
    parser.add_argument("--html-file", help=argparse.SUPPRESS)
    parser.add_argument("--rendered-html-file", help=argparse.SUPPRESS)
    parser.add_argument("--project-root", help="归档项目根目录；设置后必须同时提供语义字段")
    parser.add_argument("--title", help="归档使用的内容型中文标题")
    parser.add_argument("--category", help="归档分类")
    parser.add_argument("--tags", help="逗号分隔的中文标签")
    parser.add_argument("--summary", help="中文摘要")
    parser.add_argument("--slug", help="可选；默认与 title 一致")
    args = parser.parse_args()

    cookie = args.cookie or get_cookie_for_url(args.url)
    static_html = Path(args.html_file).read_text(encoding="utf-8") if args.html_file else None
    rendered_html = (
        Path(args.rendered_html_file).read_text(encoding="utf-8")
        if args.rendered_html_file else None
    )

    try:
        if args.project_root:
            missing = [name for name in ("title", "category", "tags", "summary")
                       if not getattr(args, name)]
            if missing:
                result = {
                    "error": "missing_archive_metadata",
                    "message": "归档模式缺少参数: " + ", ".join(missing),
                }
                json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
                print()
                return 2
            duplicate = find_duplicate(Path(args.project_root), args.url)
            if duplicate:
                result = {
                    "error": "duplicate_source",
                    "message": "该来源已归档；由用户决定跳过或覆盖",
                    "existing_article": duplicate,
                    "source": args.url,
                }
                json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
                print()
                return 2

        result = capture(
            args.url,
            cookie=cookie,
            timeout=args.timeout,
            wait_ms=args.wait,
            render=not args.no_render,
            static_html=static_html,
            rendered_html=rendered_html,
        )
        if "error" in result:
            json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
            print()
            return 1

        if args.project_root:
            if not result.get("completeness", {}).get("complete"):
                output = {
                    "error": "capture_incomplete",
                    "message": "主帖或评论尚未完整，拒绝归档",
                    "capture": result,
                }
                json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
                print()
                return 1
            archive_data = {
                **result,
                "title": args.title,
                "slug": args.slug or args.title,
                "category": args.category,
                "tags": [tag.strip() for tag in args.tags.split(",") if tag.strip()],
                "summary": args.summary,
            }
            archive_result = archive(archive_data, Path(args.project_root))
            if "error" in archive_result:
                json.dump(archive_result, sys.stdout, ensure_ascii=False, indent=2)
                print()
                return 1
            output = {"capture": result, "archive": archive_result}
        else:
            output = result

        json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    except (HTTPError, URLError, TimeoutError) as exc:
        json.dump({
            "error": "request_failed",
            "message": str(exc),
            "source": args.url,
        }, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 1
    except Exception as exc:
        json.dump({"error": "capture_failed", "message": str(exc)}, sys.stderr,
                  ensure_ascii=False, indent=2)
        print(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
