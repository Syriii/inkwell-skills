import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ocr_text.py"
SPEC = importlib.util.spec_from_file_location("inkwell_capture_ocr_text", SCRIPT_PATH)
ocr_text = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ocr_text
SPEC.loader.exec_module(ocr_text)


class LongImageDetectionTests(unittest.TestCase):
    def test_detects_extreme_height_and_aspect_ratio(self):
        self.assertTrue(ocr_text._is_long_image((1024, 19017)))
        self.assertTrue(ocr_text._is_long_image((500, 3000)))
        self.assertFalse(ocr_text._is_long_image((1200, 4000)))

    def test_segment_boxes_cover_without_gaps(self):
        boxes = ocr_text._segment_boxes((1024, 19017), segment_height=4096, overlap=160)
        self.assertEqual(boxes[0], (0, 0, 1024, 4096))
        self.assertEqual(boxes[-1][3], 19017)
        self.assertGreater(len(boxes), 1)
        for previous, current in zip(boxes, boxes[1:]):
            self.assertEqual(previous[3] - current[1], 160)


class SegmentMergeTests(unittest.TestCase):
    def test_removes_only_exact_normalized_line_overlap(self):
        merged = ocr_text._merge_segment_texts([
            "第一行\n重复 行\n第三行",
            "重复行\n第三行\n第四行",
        ])
        self.assertEqual(merged, "第一行\n重复 行\n第三行\n第四行")

    def test_keeps_uncertain_overlap(self):
        merged = ocr_text._merge_segment_texts(["第一行\n相似文本", "相似文木\n第二行"])
        self.assertEqual(merged, "第一行\n相似文本\n相似文木\n第二行")


class QualityContractTests(unittest.TestCase):
    def test_failed_segment_penalizes_confidence(self):
        confidence = ocr_text._aggregate_segment_confidence([
            {"status": "ok", "confidence": 0.9, "char_count": 100},
            {"status": "failed", "confidence": 0.0, "char_count": 0},
        ])
        self.assertEqual(confidence, 0.45)

    def test_degraded_result_is_not_safe_for_verbatim(self):
        result = ocr_text._build_result(
            Path("long.jpg"),
            "识别文本",
            0.95,
            engine="tesseract",
            strategy="segmented",
            segments=[{"status": "failed"}],
            force_degraded=True,
            warning="存在失败分段",
        )
        quality = result["ocr_quality"]
        self.assertEqual(quality["verdict"], "degraded")
        self.assertFalse(quality["safe_for_verbatim"])
        self.assertEqual(quality["handling"], "preserve_original_and_review")
        self.assertEqual(quality["segment_count"], 1)
        self.assertEqual(result["images"][0]["path"], "images/long.jpg")


if __name__ == "__main__":
    unittest.main()
