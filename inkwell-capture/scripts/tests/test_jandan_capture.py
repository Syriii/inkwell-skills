#!/usr/bin/env python3
"""煎蛋专用采集器离线回归测试。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS_DIR))

from forum.jandan import scrape_jandan  # noqa: E402
from jandan_capture import find_duplicate  # noqa: E402


URL = "https://jandan.net/t/6192383"


class JandanParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.static_html = (FIXTURES_DIR / "jandan-6192383-static.html").read_text(encoding="utf-8")
        cls.rendered_html = (FIXTURES_DIR / "jandan-6192383-rendered.html").read_text(encoding="utf-8")

    def test_l1_reports_comments_as_incomplete_without_false_count(self):
        result = scrape_jandan(self.static_html, URL)
        self.assertEqual(result["comment_count"], 0)
        self.assertFalse(result["completeness"]["comments"])
        self.assertFalse(result["completeness"]["complete"])
        self.assertTrue(result["capture"]["needs_rendered_page"])

    def test_rendered_page_extracts_only_formal_comments(self):
        result = scrape_jandan(
            self.static_html,
            URL,
            rendered_html=self.rendered_html,
            final_url=URL,
        )
        self.assertEqual(result["comment_count"], 10)
        self.assertEqual(result["hot_or_duplicate_rows_excluded"], 4)
        self.assertEqual(result["comments"][0]["id"], "#14328519")
        self.assertEqual(result["comments"][-1]["floor"], "#10楼")
        self.assertTrue(result["completeness"]["complete"])
        self.assertFalse(result["capture"]["needs_rendered_page"])

    def test_images_are_limited_to_post_and_comment_content(self):
        result = scrape_jandan(self.static_html, URL, rendered_html=self.rendered_html)
        urls = [image["url"] for image in result["images"]]
        self.assertEqual(urls, ["https://img.example/main.jpg", "https://img.example/reply.png"])
        self.assertNotIn("https://cdn.example/ui-logo.png", urls)
        self.assertNotIn("https://cdn.example/avatar-1.png", urls)

    def test_redirect_to_another_post_is_rejected(self):
        result = scrape_jandan(
            self.static_html,
            URL,
            rendered_html=self.rendered_html,
            final_url="https://jandan.net/t/9999999",
        )
        self.assertEqual(result["error"], "source_mismatch")
        self.assertFalse(result["source_verified"])

    def test_duplicate_source_is_found_before_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            article = Path(temp_dir) / "archived/20260811/example/example.md"
            article.parent.mkdir(parents=True)
            article.write_text(f'---\nsource: "{URL}"\n---\n', encoding="utf-8")
            self.assertEqual(
                find_duplicate(Path(temp_dir), URL),
                "archived/20260811/example/example.md",
            )

    def test_offline_cli_returns_the_same_contract(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "jandan_capture.py"),
                "--url", URL,
                "--html-file", str(FIXTURES_DIR / "jandan-6192383-static.html"),
                "--rendered-html-file", str(FIXTURES_DIR / "jandan-6192383-rendered.html"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["source_id"], "6192383")
        self.assertEqual(result["comment_count"], 10)
        self.assertTrue(result["completeness"]["complete"])


if __name__ == "__main__":
    unittest.main()
