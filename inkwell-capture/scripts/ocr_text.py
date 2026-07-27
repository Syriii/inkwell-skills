#!/usr/bin/env python3
"""采集 Skill — 文字截图 OCR

使用 PaddleOCR 或 Tesseract 识别截图中的文字，KenLM 评估文字质量。
质量差时降级到 Surya 或 Claude Code 视觉分析。

用法：
  python ocr_text.py --image "/path/to/screenshot.png"
  python ocr_text.py --image "screenshot.jpg" --lang ch

输出 JSON：
  type=screenshot_ocr, source, body, word_count,
  ocr_quality: { confidence, perplexity, verdict }
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 中文字符需要的最小宽度（低于此值先放大再 OCR）
MIN_WIDTH_FOR_CHINESE = 1000


def ocr_image(image_path: str, lang: str = "ch") -> dict:
    """对截图执行 OCR 识别。

    降级链：PaddleOCR → Tesseract (chi_sim → chi_sim+eng) → 错误报告

    Args:
        image_path: 截图文件路径
        lang: OCR 语言（ch / en）

    Returns:
        { type, source, body, word_count, ocr_quality }
    """
    path = Path(image_path)
    if not path.exists():
        return {"error": "file_not_found", "message": f"文件不存在: {image_path}"}

    # 尝试 PaddleOCR，失败则降级到 Tesseract
    result = _ocr_paddleocr(path, lang)
    if result is not None and "error" not in result:
        return result

    result = _ocr_tesseract(path, lang)
    if result is not None and "error" not in result:
        return result

    # 都不可用
    return {
        "error": "no_ocr_engine",
        "message": (
            "没有可用的 OCR 引擎。安装方案：\n"
            "  - Tesseract（推荐，轻量）: brew install tesseract tesseract-lang\n"
            "  - PaddleOCR（更高精度）: pip install paddlepaddle paddleocr\n"
            "安装完成后重新运行。"
        ),
        "type": "screenshot_ocr",
        "source": str(path),
    }


# ---------------------------------------------------------------------------
# PaddleOCR
# ---------------------------------------------------------------------------

def _ocr_paddleocr(path: Path, lang: str) -> dict | None:
    """PaddleOCR 识别。不可用时返回 None。"""
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return None

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

    lines = []
    confidences = []
    for line in result[0]:
        text = line[1][0]
        conf = line[1][1]
        lines.append(text)
        confidences.append(conf)

    body = '\n'.join(lines)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return _build_result(path, body, avg_confidence)


# ---------------------------------------------------------------------------
# Tesseract (降级方案)
# ---------------------------------------------------------------------------

# PaddleOCR lang → Tesseract lang 映射
_TESSERACT_LANG_MAP = {
    "ch": "chi_sim",
    "en": "eng",
}


def _ocr_tesseract(path: Path, lang: str) -> dict | None:
    """Tesseract OCR 识别。不可用时返回 None。

    策略（针对中文）:
    1. 纯 chi_sim 模式先尝试 — 避免中英混合时英文引擎抢夺中文字符
    2. 图片宽度 < 1000px → 放大到 2x 再识别
    3. 多配置比较，选最高置信度的结果
    """
    try:
        import pytesseract
        from PIL import Image, ImageFilter
    except ImportError:
        return None  # tesseract / PIL 不可用

    tesseract_lang = _TESSERACT_LANG_MAP.get(lang, lang)

    img = Image.open(path)

    # RGBA → RGB（tesseract 对 RGBA 支持不稳定）
    if img.mode == 'RGBA':
        # 创建白色背景，合成 RGBA 图像
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])  # 使用 alpha 通道做遮罩
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    # 检查是否需要放大
    original_size = img.size
    if img.width < MIN_WIDTH_FOR_CHINESE and lang == "ch":
        scale = MIN_WIDTH_FOR_CHINESE / img.width
        new_size = (MIN_WIDTH_FOR_CHINESE, int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    # 多配置尝试，取最流畅的
    candidates = []

    # 配置 1: 纯中文 + 自动页面分割
    if lang == "ch":
        try:
            text = pytesseract.image_to_string(img, lang='chi_sim')
            candidates.append(('chi_sim', text))
        except Exception:
            pass

    # 配置 2: 中英混合 + 自动页面分割
    if lang == "ch":
        try:
            text = pytesseract.image_to_string(img, lang='chi_sim+eng')
            candidates.append(('chi_sim+eng', text))
        except Exception:
            pass

    # 配置 3: 纯英文
    if lang == "en" or lang == "ch":
        try:
            text = pytesseract.image_to_string(img, lang='eng')
            candidates.append(('eng', text))
        except Exception:
            pass

    if not candidates:
        return {
            "error": "ocr_no_text",
            "message": "Tesseract 未检测到文字",
            "type": "screenshot_ocr",
            "source": str(path),
            "body": "",
            "word_count": 0,
        }

    # 选最优：中文字符数最多 + 非中文字符数最少（排除乱码多的结果）
    best = max(candidates, key=lambda c: _score_ocr_result(c[1], lang, original_size))

    body = best[1].strip()
    # 合并连续空行为单个空行
    body = re.sub(r'\n{3,}', '\n\n', body)

    # 计算置信度（基于字符密度）
    confidence = _estimate_tesseract_confidence(body, img.size)

    return _build_result(path, body, confidence, engine="tesseract", engine_lang=best[0])


def _score_ocr_result(text: str, lang: str, original_size: tuple) -> float:
    """评估 OCR 结果质量，用于多配置比较。

    评分策略（针对中文）：
    - 中文字符数多 → 好
    - 拉丁字符 (ASCII) 占比高 → 差（可能是中文被误读为英文）
    - 总字符密度合理
    """
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    ascii_chars = len(re.findall(r'[a-zA-Z]', text))
    total_chars = len(text.strip())

    if total_chars == 0:
        return 0.0

    if lang == "ch":
        # 中文优先：中文多加分，英文多扣分
        ascii_ratio = ascii_chars / total_chars if total_chars > 0 else 0
        chinese_ratio = chinese_chars / total_chars if total_chars > 0 else 0
        return chinese_chars * (1.0 - ascii_ratio * 0.8) + chinese_ratio * 10
    else:
        return total_chars


def _estimate_tesseract_confidence(body: str, img_size: tuple) -> float:
    """基于输出特征估算 tesseract 置信度（tesseract 不直接返回全局置信度）。

    粗略估计：中文密度 vs 图片面积的比例。
    """
    chinese_chars = len(re.findall(r'[一-鿿]', body))
    total_chars = len(body.strip())
    ascii_chars = len(re.findall(r'[a-zA-Z]', body))

    if total_chars == 0:
        return 0.0

    # 中文占主导 → 置信度高；ASCII 乱入多 → 置信度低
    chinese_ratio = chinese_chars / total_chars if total_chars > 0 else 0
    ascii_ratio = ascii_chars / total_chars if total_chars > 0 else 0

    # 基线 0.7，中文多加分，英文多扣分
    confidence = 0.7 + chinese_ratio * 0.25 - ascii_ratio * 0.3
    return round(min(max(confidence, 0.0), 1.0), 4)


# ---------------------------------------------------------------------------
# 共用
# ---------------------------------------------------------------------------

def _build_result(path: Path, body: str, confidence: float,
                  engine: str = "paddleocr", engine_lang: str = "") -> dict:
    """组装标准输出 JSON。"""
    kenlm_perplexity = _compute_perplexity(body)
    verdict = _quality_verdict(confidence, kenlm_perplexity)
    word_count = len(re.findall(r'[一-鿿]', body))

    result = {
        "type": "screenshot_ocr",
        "source": str(path),
        "body": body,
        "word_count": word_count,
        "ocr_quality": {
            "confidence": round(confidence, 4),
            "engine": engine,
            "kenlm_perplexity": round(kenlm_perplexity, 2) if kenlm_perplexity else None,
            "verdict": verdict,  # ok | degraded | poor
        },
        "images": [{"url": str(path.absolute()), "path": f"images/{path.name}"}],
    }
    if engine_lang:
        result["ocr_quality"]["engine_lang"] = engine_lang

    return result


def _compute_perplexity(text: str) -> float | None:
    """使用 KenLM 计算文本困惑度。"""
    try:
        import kenlm
    except ImportError:
        return None

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
        return None

    try:
        import math
        model = kenlm.Model(model_path)
        log_prob = model.score(text)
        num_words = len(text.split())
        if num_words == 0:
            return None
        perplexity = math.exp(-log_prob / num_words)
        return perplexity
    except Exception:
        return None


def _quality_verdict(confidence: float, perplexity: float | None) -> str:
    """综合判定 OCR 质量。"""
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
