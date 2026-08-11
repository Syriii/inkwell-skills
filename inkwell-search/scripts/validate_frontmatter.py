#!/usr/bin/env python3
"""frontmatter 数据质量校验 —— 每次采集/重建索引后的格式复查。

复刻 Obsidian 的解析边界（js-yaml）：date/fetched_at 必须能被 js-yaml 解析为
Date（裸日期 `YYYY-MM-DD` 或 ISO `YYYY-MM-DDT...`），**禁止空格分隔**——
`2026-07-30 10:42` 这种值 js-yaml 会当作字符串，dv.date() 无法解析，
导致总览仪表盘 dataviewjs 抛错。

同时检查正文是否混入了源站 frontmatter（嵌套 `---` 块），违反「归档纯净化」。

用法（在项目根目录执行）：
    python <skill-dir>/scripts/validate_frontmatter.py

退出码：0 = 全部合规；1 = 发现问题。
reindex.py 重建索引后自动调用，作为采集后的格式门禁。
"""

import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

DEFAULT_DIRS = ["archived", "discussions", "creations"]

# 合规的日期字符串：裸日期 或 ISO（带 T 分隔，秒可选，可带小数秒/时区）
ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?"
    r"(Z|[+-]\d{2}:\d{2})?)?$"
)

DATE_FIELDS = ["date", "fetched_at"]


def check_field(field: str, value) -> tuple[bool, str]:
    """检查单个日期字段。返回 (合规?, 原因)。"""
    if isinstance(value, (date, datetime)):
        # YAML 原生解析成日期对象 —— Obsidian/Dataview 都能正确处理
        return True, ""
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return False, "空值"
        if " " in v:
            return False, "含空格，非 ISO（js-yaml 解析为字符串，dv.date() 无法解析 → 仪表盘报错）"
        if ISO_RE.match(v):
            return True, ""
        return False, f"无法识别的日期格式: {v!r}"
    return False, f"类型异常: {type(value).__name__}"


def has_nested_frontmatter(text: str) -> bool:
    """正文中是否混入了第二个 frontmatter 块（源站元数据残留）。"""
    if not text.startswith("---"):
        return False
    body = text.split("---", 2)[2]
    # body 开头是 `---`，且随后紧跟 YAML 键值行 → 嵌套 frontmatter
    m = re.match(r"\s*---\s*\n(\w[\w -]*:\s*[^\n]*\n)+---", body)
    return bool(m)


def main() -> int:
    root = Path.cwd()
    problems: list[tuple[str, str, str]] = []  # (file, field, reason)
    total = 0
    for d in DEFAULT_DIRS:
        base = root / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            total += 1
            text = p.read_text(encoding="utf-8")

            # 嵌套 frontmatter 检查（纯净化）
            if has_nested_frontmatter(text):
                problems.append((str(p), "body", "正文嵌入第二个 frontmatter 块（源站元数据残留）"))

            # 日期字段检查
            if not text.startswith("---"):
                continue
            parts = text.split("---", 2)
            if len(parts) < 3:
                continue
            try:
                fm = yaml.safe_load(parts[1])
            except Exception as e:
                problems.append((str(p), "yaml", f"frontmatter 解析失败: {e}"))
                continue
            if not isinstance(fm, dict):
                continue
            for field in DATE_FIELDS:
                if field in fm:
                    ok, reason = check_field(field, fm[field])
                    if not ok:
                        problems.append((str(p), field, reason))

    if not problems:
        print(f"✓ frontmatter 校验通过（{total} 个文件，日期字段与正文纯净度均合规）")
        return 0

    print(f"✗ frontmatter 校验发现 {len(problems)} 处问题（共 {total} 个文件）:")
    for f, field, reason in problems:
        print(f"  [{field}] {f}")
        print(f"      {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
