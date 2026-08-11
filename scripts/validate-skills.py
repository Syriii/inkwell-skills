#!/usr/bin/env python3
"""Validate Inkwell skill structure, portability, and independence.

This validator intentionally uses only the Python standard library so a fresh
clone can run it before any skill-specific dependencies are installed.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


EXPECTED_SKILLS = (
    "inkwell-capture",
    "inkwell-search",
    "inkwell-write",
)

TEXT_RESOURCE_SUFFIXES = {
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

FORBIDDEN_CORE_PATTERNS = (
    (re.compile(r"\.claude/skills/"), "hard-coded Claude skill path"),
    (re.compile(r"/Users/[^/]+/"), "machine-specific absolute path"),
    (
        re.compile(r"\bbrowser_(?:navigate|evaluate|run_code_unsafe|take_screenshot)\b"),
        "host-specific browser tool name",
    ),
)

FORBIDDEN_DOMAIN_PATTERNS = {
    "inkwell-capture": (
        (re.compile(r"\.retrieval-index"), "retrieval-index coupling"),
        (re.compile(r"\bFAISS\b", re.IGNORECASE), "vector-index coupling"),
        (
            re.compile(r"(?<![A-Za-z])(?:discussions|creations)/"),
            "writing-directory coupling",
        ),
    ),
    "inkwell-search": (
        (re.compile(r"\.web-analysis"), "content-workspace coupling"),
        (re.compile(r"WEB_ANALYSIS_"), "content-workspace environment coupling"),
        (
            re.compile(r"(?<![A-Za-z])(?:archived|discussions|creations)/"),
            "fixed business directory coupling",
        ),
    ),
    "inkwell-write": (
        (re.compile(r"\.retrieval-index"), "retrieval-index coupling"),
        (re.compile(r"\bFAISS\b", re.IGNORECASE), "vector-index coupling"),
        (re.compile(r"(?<![A-Za-z])archived/"), "capture-directory coupling"),
        (re.compile(r"搜索注入"), "implicit search-injection coupling"),
    ),
}


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must start with YAML frontmatter")
    try:
        end = next(
            i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as exc:
        raise ValueError("SKILL.md frontmatter is not closed") from exc

    frontmatter_lines = lines[1:end]
    keys: dict[str, str] = {}
    active_key: str | None = None
    for line in frontmatter_lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if match:
            active_key = match.group(1)
            keys[active_key] = match.group(2).strip()
        elif active_key and line.startswith((" ", "\t")):
            keys[active_key] = f"{keys[active_key]} {line.strip()}".strip()
        elif line.strip():
            raise ValueError(f"unsupported frontmatter line: {line}")
    return keys, text


def local_reference_targets(text: str) -> set[str]:
    targets = set(re.findall(r"references/[A-Za-z0-9_./-]+\.md", text))
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = target.strip().split("#", 1)[0]
        if target and not re.match(r"^[a-z]+://", target) and target.endswith(".md"):
            targets.add(target)
    return targets


def validate_openai_yaml(path: Path, skill_name: str) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return ["missing agents/openai.yaml"]
    text = path.read_text(encoding="utf-8")
    for key in ("display_name", "short_description", "default_prompt"):
        if not re.search(rf'^\s{{2}}{key}:\s*".+"\s*$', text, re.MULTILINE):
            errors.append(f"agents/openai.yaml missing quoted interface.{key}")
    description_match = re.search(
        r'^\s{2}short_description:\s*"(.+)"\s*$', text, re.MULTILINE
    )
    if description_match and not 25 <= len(description_match.group(1)) <= 64:
        errors.append("agents/openai.yaml short_description must be 25-64 characters")
    prompt_line = next(
        (line for line in text.splitlines() if "default_prompt:" in line), ""
    )
    if f"${skill_name}" not in prompt_line:
        errors.append(f"agents/openai.yaml default_prompt must mention ${skill_name}")
    return errors


def validate_cross_skill_independence(skill_dir: Path) -> list[str]:
    """Reject direct or implicit knowledge of sibling Inkwell skills."""
    errors: list[str] = []
    forbidden_names = tuple(name for name in EXPECTED_SKILLS if name != skill_dir.name)
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() not in TEXT_RESOURCE_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for forbidden in forbidden_names:
            for match in re.finditer(re.escape(forbidden), text, re.IGNORECASE):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{path.relative_to(skill_dir)}:{line}: "
                    f"direct sibling-skill reference: {match.group(0)}"
                )
        for match in re.finditer(r"<search-skill-dir>", text, re.IGNORECASE):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(
                f"{path.relative_to(skill_dir)}:{line}: "
                f"cross-skill path placeholder: {match.group(0)}"
            )
        for pattern, reason in FORBIDDEN_DOMAIN_PATTERNS.get(skill_dir.name, ()):
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{path.relative_to(skill_dir)}:{line}: {reason}: {match.group(0)}"
                )
    return errors


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return ["missing SKILL.md"]

    try:
        frontmatter, text = parse_frontmatter(skill_file)
    except ValueError as exc:
        return [str(exc)]

    if set(frontmatter) != {"name", "description"}:
        errors.append(
            f"frontmatter keys must be name and description only: {sorted(frontmatter)}"
        )
    name = frontmatter.get("name", "").strip('"\' ')
    if name != skill_dir.name:
        errors.append(
            f"frontmatter name {name!r} does not match folder {skill_dir.name!r}"
        )
    if not frontmatter.get("description", "").strip(" >|\t"):
        errors.append("frontmatter description is empty")

    line_count = len(text.splitlines())
    if line_count > 500:
        errors.append(f"SKILL.md has {line_count} lines; keep it at or below 500")

    for pattern, reason in FORBIDDEN_CORE_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"SKILL.md:{line}: {reason}: {match.group(0)}")

    for target in sorted(local_reference_targets(text)):
        if not (skill_dir / target).is_file():
            errors.append(f"missing referenced file: {target}")

    errors.extend(
        validate_openai_yaml(skill_dir / "agents" / "openai.yaml", skill_dir.name)
    )
    errors.extend(validate_cross_skill_independence(skill_dir))

    for script in sorted((skill_dir / "scripts").rglob("*.py")):
        if "__pycache__" in script.parts:
            continue
        try:
            compile(script.read_text(encoding="utf-8"), str(script), "exec")
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{script.relative_to(skill_dir)} does not compile: {exc}")
    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=repo_root)
    parser.add_argument(
        "--skill",
        action="append",
        choices=EXPECTED_SKILLS,
        help="validate only the named skill; repeat to select more than one",
    )
    args = parser.parse_args()

    all_errors: list[str] = []
    selected_skills = tuple(args.skill) if args.skill else EXPECTED_SKILLS
    for name in selected_skills:
        skill_dir = args.root / name
        if not skill_dir.is_dir():
            all_errors.append(f"{name}: missing skill directory")
            continue
        errors = validate_skill(skill_dir)
        if errors:
            all_errors.extend(f"{name}: {error}" for error in errors)
        else:
            print(f"PASS {name}")

    if all_errors:
        for error in all_errors:
            print(f"FAIL {error}", file=sys.stderr)
        return 1
    print("All Inkwell skills passed structural and dual-host checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
