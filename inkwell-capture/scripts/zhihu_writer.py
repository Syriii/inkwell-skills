#!/usr/bin/env python3
"""知乎全问题采集 — 归档写入器

把浏览器提取的知乎回答数据（JSON）写成「知乎采集模型」规定的多文件结构：
  archived/YYYYMMDD/{问题-slug}/
  ├── {问题-slug}.md          # 问题总览（frontmatter + wikilink 导航，唯一顶层入口）
  ├── 回答/                   # 回答正文（无 frontmatter，纯 Markdown）
  │   ├── {回答1-slug}.md
  │   ├── {回答2-slug}.md
  │   └── ...
  └── images/                 # 回答内嵌图片

用法（在项目根执行）：
  python .claude/skills/inkwell-capture/scripts/zhihu_writer.py \
      --qid 639844205 --title "问题标题" \
      --answers /tmp/zhihu_answers.json --meta /tmp/zhihu_meta.json \
      --category 文化 --tags 中医,食物 --desc "问题描述" \
      [--slugs /tmp/zhihu_slugs.json] [--top-n 20] [--date 2026-08-05] [--project-root .]

answers JSON 结构（浏览器提取）：
  {"title": "...", "answers": [
    {"rank": 1, "idx": 0, "votes": 133, "author": "pansz",
     "content": "回答正文（含 <img data-original=...> 占位）", "imgs": [...]},
    ...
  ]}

meta JSON 结构（浏览器提取）：
  {"nums": ["57 个回答"],
   "per": [{"idx": 0, "url": ".../answer/...", "date": "发布于2026-06-23 16:15"}]}

slugs JSON（可选）：
  {"639844205": {"1": "回答slug1", "2": "回答slug2", ...}}
  不提供时用 answers 里每条的 slug 字段，都没有则回退为 "回答{rank}"。
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

TOP_N = 20


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clean_title(t: str) -> str:
    """去掉知乎标题里的「(N 封私信)」前缀。"""
    return re.sub(r'^\(\d[\d\s]*封私信\)\s*', '', t).strip()


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        f.write(r.read())


def build_answer_file(a: dict, meta: dict, imgdir: Path, qid: str) -> str:
    """生成单个回答的 Markdown 正文，下载内嵌图片。"""
    content = a.get("content", "")

    # 内嵌图片：<img ... data-original="..."> → ![](images/xx)，并下载
    def repl(m):
        orig = m.group(1)
        fname = orig.split("?")[0].split("/")[-1]
        try:
            download(orig, imgdir / fname)
        except Exception as e:
            print(f"  ⚠️ 图片下载失败 {fname}: {e}", file=sys.stderr)
        return f"![](images/{fname})"

    content = re.sub(r'<img[^>]*data-original="([^"]+)"[^>]*?/?>', repl, content)
    content = re.sub(r'<[^>]+>', '', content)  # 清残留 HTML
    content = re.sub(r'\s+', ' ', content).strip()

    date = re.sub(r'^(编辑于|发布于)', '', (meta.get("date") or "")).strip() or "未知"
    url = meta.get("url") or f"https://www.zhihu.com/question/{qid}"
    return "\n".join([
        f"# {a.get('author', '匿名')}的回答", "",
        f"**{a.get('votes', 0)}人赞同** · [发布于{date}]({url})", "",
        content, "",
    ])


def main() -> None:
    ap = argparse.ArgumentParser(description="知乎全问题采集 — 归档写入器")
    ap.add_argument("--qid", required=True, help="问题 ID")
    ap.add_argument("--title", required=True, help="问题标题")
    ap.add_argument("--answers", required=True, help="浏览器提取的回答 JSON 路径")
    ap.add_argument("--meta", required=True, help="浏览器提取的元数据 JSON 路径")
    ap.add_argument("--category", default="社会", help="分类")
    ap.add_argument("--tags", default="", help="标签，逗号分隔")
    ap.add_argument("--desc", default="如题", help="问题描述")
    ap.add_argument("--slugs", default=None, help="slug 映射 JSON（可选）")
    ap.add_argument("--top-n", type=int, default=TOP_N, help="采前 N 高赞（默认 20）")
    ap.add_argument("--date", default=None, help="归档日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--project-root", default=".", help="项目根目录")
    args = ap.parse_args()

    root = Path(args.project_root)
    answers = load_json(Path(args.answers))["answers"]
    meta = load_json(Path(args.meta))
    metad = {m["idx"]: m for m in meta.get("per", [])}
    nums = (meta.get("nums") or [""])[0]

    # slug 解析：--slugs 优先，其次 answers 里的 slug 字段
    slug_map = {}
    if args.slugs:
        slug_map = {int(k): v for k, v in load_json(Path(args.slugs)).get(args.qid, {}).items()}

    title = clean_title(args.title)
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    date_str = date.replace("-", "")

    base = root / "archived" / date_str / title
    base.mkdir(parents=True, exist_ok=True)
    imgdir = base / "images"
    imgdir.mkdir(exist_ok=True)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    # 问题总览
    overview = [
        "---",
        f"date: {date}",
        f'source: "https://www.zhihu.com/question/{args.qid}"',
        "type: zhihu_question",
        f"category: {args.category}",
        f"tags: [{', '.join(tags)}]",
        f'title: "{title}"',
        f'summary: "知乎问题：{title}采集前{args.top_n}高赞回答。"',
        f"fetched_at: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}",
        "---",
        "",
        f"# {title}",
        "",
        f"[知乎原文](https://www.zhihu.com/question/{args.qid})",
        "",
        f"**{nums}**",
        "",
        f"> {args.desc}",
        "",
        "## 已采集回答",
        "",
    ]

    # 回答文件
    top = sorted(answers, key=lambda a: a.get("rank", 99))[: args.top_n]
    for a in top:
        rank = a["rank"]
        meta_i = metad.get(a.get("idx"), {})
        slug = slug_map.get(rank) or a.get("slug") or f"回答{rank}"
        body = build_answer_file(a, meta_i, imgdir, args.qid)
        (base / f"{slug}.md").write_text(body, encoding="utf-8")
        preview = re.sub(r'\s+', ' ', a.get("content", ""))[:60]
        overview.append(f"- [[{slug}]] — {a.get('author', '匿名')}：{preview}")

    (base / f"{title}.md").write_text("\n".join(overview), encoding="utf-8")

    print(json.dumps({
        "action": "zhihu_question_written",
        "path": str(base.relative_to(root)),
        "overview": f"{title}.md",
        "answers": len(top),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
