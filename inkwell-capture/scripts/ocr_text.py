#!/usr/bin/env python3
"""采集 Skill — 文字截图 OCR

使用 PaddleOCR 识别截图中的文字，KenLM 评估文字质量。
质量差时降级到 Surya 或 Claude Code 视觉分析。

用法：
  python ocr_text.py --image "/path/to/screenshot.png"
  python ocr_text.py --image "screenshot.jpg" --lang ch

输出 JSON：
  type=screenshot_ocr, source, body, word_count,
  ocr_quality: { paddle_confidence, kenlm_perplexity, verdict }
"""

import argparse
import json
import re
import sys
from pathlib import Path


def ocr_image(image_path: str, lang: str = "ch") -> dict:
    """对截图执行 OCR 识别。

    降级链：PaddleOCR → (质量评估) → Surya 降级建议 → Claude 视觉兜底

    Args:
        image_path: 截图文件路径
        lang: OCR 语言（ch / en）

    Returns:
        { type, source, body, word_count, ocr_quality }
    """
    path = Path(image_path)
    if not path.exists():
        return {"error": "file_not_found", "message": f"文件不存在: {image_path}"}

    # --- PaddleOCR ---
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return {
            "error": "paddleocr_not_installed",
            "message": (
                "PaddleOCR 未安装。运行: pip install paddlepaddle paddleocr。"
                "降级方案：手动将截图传给 Claude Code 视觉分析，或安装 Surya。"
            ),
            "type": "screenshot_ocr",
            "source": str(path),
        }

    ocr = PaddleOCR(lang=lang, use_angle_cls=True)
    result = ocr.ocr(str(path), cls=True)

    if not result or not result[0]:
        return {
            "error": "ocr_no_text",
            "message": "OCR 未在截图中检测到文字",
            "type": "screenshot_ocr",
            "source": str(path),
            "body": "",
            "word_count": 0,
        }

    # 提取文字和置信度
    lines = []
    confidences = []
    for line in result[0]:
        text = line[1][0]
        conf = line[1][1]
        lines.append(text)
        confidences.append(conf)

    body = '\n'.join(lines)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    # --- KenLM 质量评估 ---
    kenlm_perplexity = _compute_perplexity(body)

    # --- 质量判定 ---
    verdict = _quality_verdict(avg_confidence, kenlm_perplexity)

    word_count = len(re.findall(r'[一-鿿]', body))

    return {
        "type": "screenshot_ocr",
        "source": str(path),
        "body": body,
        "word_count": word_count,
        "ocr_quality": {
            "paddle_confidence": round(avg_confidence, 4),
            "kenlm_perplexity": round(kenlm_perplexity, 2) if kenlm_perplexity else None,
            "verdict": verdict,  # ok | degraded | poor
        },
        "images": [{"url": str(path.absolute()), "path": f"images/{path.name}"}],
    }


def _compute_perplexity(text: str) -> float | None:
    """使用 KenLM 计算文本困惑度。

    困惑度低 → 文本流畅 → OCR 质量好
    困惑度高 → 文本混乱 → OCR 质量差
    """
    try:
        import kenlm
    except ImportError:
        return None  # KenLM 未安装，跳过

    # 查找 KenLM 模型
    model_paths = [
        Path("/Users/xiesh/Codes/models/ocr/kenlm/zh.binary"),
        Path("/Users/xiesh/Codes/models/ocr/kenlm/zh.arpa"),
    ]
    model_path = None
    for mp in model_paths:
        if mp.exists():
            model_path = str(mp)
            break

    if not model_path:
        return None  # 模型文件不存在

    try:
        model = kenlm.Model(model_path)
        # 计算整个文本的对数概率
        log_prob = model.score(text)
        # 近似困惑度：exp(-log_prob / num_words)
        num_words = len(text.split())
        if num_words == 0:
            return None
        import math
        perplexity = math.exp(-log_prob / num_words)
        return perplexity
    except Exception:
        return None


def _quality_verdict(confidence: float, perplexity: float | None) -> str:
    """综合判定 OCR 质量。

    - 两个信号都差 → poor（建议降级）
    - 单一信号异常 → degraded（标记但不强制降级）
    - 两个信号都好 → ok
    """
    conf_ok = confidence >= 0.80
    ppl_ok = perplexity is None or perplexity < 200

    if not conf_ok and not ppl_ok:
        return "poor"
    elif not conf_ok or not ppl_ok:
        return "degraded"
    else:
        return "ok"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="采集 Skill — 文字截图 OCR")
    parser.add_argument("--image", required=True, help="截图文件路径")
    parser.add_argument("--lang", default="ch", help="OCR 语言 (ch/en)")

    args = parser.parse_args()

    try:
        result = ocr_image(args.image, args.lang)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
        sys.exit(1 if "error" in result else 0)
    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr, ensure_ascii=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
