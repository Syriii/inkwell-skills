from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validate-skills.py"
SKILLS = ("inkwell-capture", "inkwell-search", "inkwell-write")
TRIGGER_TERMS = {
    "inkwell-capture": ("存档", "采集", "截图OCR"),
    "inkwell-search": ("语义搜索", "索引", "相似度"),
    "inkwell-write": ("讨论", "创作", "写文章"),
}


def run_validator(root: Path, skill: str | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(VALIDATOR), "--root", str(root)]
    if skill:
        command.extend(("--skill", skill))
    return subprocess.run(command, text=True, capture_output=True, check=False)


class SkillContractTests(unittest.TestCase):
    def copy_one_skill(self, temp_root: Path, skill: str) -> Path:
        destination = temp_root / skill
        shutil.copytree(
            REPO_ROOT / skill,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        return destination

    def test_repository_passes_its_own_validator(self) -> None:
        result = run_validator(REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_each_skill_validates_in_both_host_layouts_when_installed_alone(self) -> None:
        for skill in SKILLS:
            for host in ("codex", "claude"):
                with (
                    self.subTest(skill=skill, host=host),
                    tempfile.TemporaryDirectory() as temp_dir,
                ):
                    base = Path(temp_dir)
                    root = (
                        base / "codex-home" / "skills"
                        if host == "codex"
                        else base / "project" / ".claude" / "skills"
                    )
                    root.mkdir(parents=True)
                    self.copy_one_skill(root, skill)
                    result = run_validator(root, skill)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        sorted(path.name for path in root.iterdir()),
                        [skill],
                    )

    def test_trigger_descriptions_cover_independent_entry_points(self) -> None:
        for skill, terms in TRIGGER_TERMS.items():
            with self.subTest(skill=skill):
                text = (REPO_ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
                frontmatter = text.split("---", 2)[1]
                for term in terms:
                    self.assertIn(term, frontmatter)

    def test_direct_sibling_reference_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = self.copy_one_skill(root, "inkwell-capture")
            marker = skill_dir / "references" / "forbidden.md"
            marker.write_text("Call inkwell-search next.\n", encoding="utf-8")
            result = run_validator(root, "inkwell-capture")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("direct sibling-skill reference", result.stderr)

    def test_other_skills_business_directories_are_rejected(self) -> None:
        cases = {
            "inkwell-capture": "Read discussions/topic.md next.\n",
            "inkwell-search": "Default to archived/ when no path is given.\n",
            "inkwell-write": "Load archived/example.md automatically.\n",
        }
        for skill, forbidden_text in cases.items():
            with self.subTest(skill=skill), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                skill_dir = self.copy_one_skill(root, skill)
                marker = skill_dir / "references" / "forbidden.md"
                marker.write_text(forbidden_text, encoding="utf-8")
                result = run_validator(root, skill)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("coupling", result.stderr)

    def test_codex_prompt_must_name_the_exact_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = self.copy_one_skill(root, "inkwell-search")
            metadata = skill_dir / "agents" / "openai.yaml"
            text = metadata.read_text(encoding="utf-8")
            metadata.write_text(
                text.replace("$inkwell-search", "$some-other-skill"),
                encoding="utf-8",
            )
            result = run_validator(root, "inkwell-search")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "default_prompt must mention $inkwell-search",
                result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
