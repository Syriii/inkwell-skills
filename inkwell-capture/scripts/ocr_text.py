#!/usr/bin/env python3
"""采集 Skill — 文字截图 OCR

使用 PaddleOCR 或 Tesseract 识别截图中的文字，KenLM 评估文字质量。
长图优先使用 Tesseract 内存分段识别；质量差时保留原图并降级处理。

用法：
  python ocr_text.py --image "/path/to/screenshot.png"
  python ocr_text.py --image "screenshot.jpg" --lang ch

输出 JSON：
  type=screenshot_ocr, source, body, word_count,
  ocr_quality: { confidence, perplexity, verdict, strategy, safe_for_verbatim }
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# 中文字符需要的最小宽度（低于此值先放大再 OCR）
MIN_WIDTH_FOR_CHINESE = 1000
LONG_IMAGE_MIN_HEIGHT = 6000
LONG_IMAGE_MIN_ASPECT_RATIO = 6.0
LONG_IMAGE_MAX_SEGMENT_HEIGHT = 4096
LONG_IMAGE_MIN_SEGMENT_HEIGHT = 3000
LONG_IMAGE_OVERLAP = 160


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

    # 极长图片优先分段，避免整图 OCR 的资源峰值与版面丢失。
    image_size = _probe_image_size(path)
    if image_size and _is_long_image(image_size):
        result = _ocr_tesseract(path, lang, force_segment=True)
        if result is not None and "error" not in result:
            return result

    # 普通图片沿用 PaddleOCR → Tesseract 降级链。
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
            "  - Tesseract（推荐，轻量）:\n"
            "    macOS:  brew install tesseract tesseract-lang\n"
            "    Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-chi-sim\n"
            "    然后:   pip install pytesseract Pillow\n"
            "  - PaddleOCR（更高精度）: pip install paddlepaddle paddleocr\n"
            "详见 scripts/requirements.txt"
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


def _ocr_tesseract(path: Path, lang: str, force_segment: bool = False) -> dict | None:
    """Tesseract OCR 识别。不可用时返回 None。

    策略（针对中文）:
    1. 纯 chi_sim 模式先尝试 — 避免中英混合时英文引擎抢夺中文字符
    2. 图片宽度 < 1000px → 放大到 2x 再识别
    3. 多配置比较，选最高置信度的结果
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None  # tesseract / PIL 不可用

    img = Image.open(path)
    img = _prepare_image(img, Image)

    if force_segment or _is_long_image(img.size):
        return _ocr_tesseract_segmented(path, img, lang, pytesseract, Image)

    # 检查是否需要放大
    original_size = img.size
    if img.width < MIN_WIDTH_FOR_CHINESE and lang == "ch":
        scale = MIN_WIDTH_FOR_CHINESE / img.width
        new_size = (MIN_WIDTH_FOR_CHINESE, int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    candidates = _run_tesseract_candidates(img, lang, pytesseract, original_size)

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
    best = max(candidates, key=lambda c: c[3])

    body = best[1].strip()
    # 合并连续空行为单个空行
    body = re.sub(r'\n{3,}', '\n\n', body)

    confidence = best[2]

    return _build_result(path, body, confidence, engine="tesseract", engine_lang=best[0])


def _probe_image_size(path: Path) -> tuple[int, int] | None:
    """轻量读取图片尺寸；Pillow 不可用时保持原降级链。"""
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def _is_long_image(size: tuple[int, int]) -> bool:
    """判断图片是否需要分段 OCR。"""
    width, height = size
    if width <= 0 or height <= 0:
        return False
    return height >= LONG_IMAGE_MIN_HEIGHT or height / width >= LONG_IMAGE_MIN_ASPECT_RATIO


def _segment_boxes(size: tuple[int, int], segment_height: int | None = None,
                   overlap: int = LONG_IMAGE_OVERLAP) -> list[tuple[int, int, int, int]]:
    """生成覆盖整图且无间隙的纵向分段框。"""
    width, height = size
    if width <= 0 or height <= 0:
        return []

    target_height = segment_height or max(
        LONG_IMAGE_MIN_SEGMENT_HEIGHT,
        min(LONG_IMAGE_MAX_SEGMENT_HEIGHT, width * 4),
    )
    target_height = min(target_height, height)
    overlap = max(0, min(overlap, target_height - 1))

    boxes = []
    top = 0
    while top < height:
        bottom = min(top + target_height, height)
        boxes.append((0, top, width, bottom))
        if bottom == height:
            break
        top = bottom - overlap
    return boxes


def _prepare_image(img, image_module):
    """把 Pillow 图片规范化为适合 Tesseract 的 RGB 图片。"""
    if img.mode == "RGBA":
        background = image_module.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        return background
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def _resize_for_chinese(img, lang: str, image_module):
    if img.width >= MIN_WIDTH_FOR_CHINESE or lang != "ch":
        return img
    scale = MIN_WIDTH_FOR_CHINESE / img.width
    return img.resize(
        (MIN_WIDTH_FOR_CHINESE, int(img.height * scale)),
        image_module.Resampling.LANCZOS,
    )


def _tesseract_languages(lang: str) -> list[str]:
    if lang == "ch":
        return ["chi_sim", "chi_sim+eng", "eng"]
    return [_TESSERACT_LANG_MAP.get(lang, lang)]


def _run_tesseract_candidates(img, lang: str, pytesseract_module,
                               original_size: tuple[int, int],
                               languages: list[str] | None = None) -> list[tuple[str, str, float, float]]:
    """运行候选语言配置，返回 (语言, 文本, 置信度, 排序分数)。"""
    candidates = []
    for engine_lang in languages or _tesseract_languages(lang):
        try:
            text, confidence = _tesseract_text_with_confidence(
                img, engine_lang, pytesseract_module
            )
            score = _score_ocr_result(text, lang, original_size) + confidence * 10
            candidates.append((engine_lang, text, confidence, score))
        except Exception as exc:
            print(f"⚠️  Tesseract {engine_lang} 识别失败: {exc}", file=sys.stderr)
    return candidates


def _tesseract_text_with_confidence(img, engine_lang: str,
                                    pytesseract_module) -> tuple[str, float]:
    """优先读取 Tesseract token 置信度，失败时回退到字符串与启发式估计。"""
    try:
        data = pytesseract_module.image_to_data(
            img,
            lang=engine_lang,
            output_type=pytesseract_module.Output.DICT,
        )
        text, confidence = _text_and_confidence_from_data(data)
        if text.strip():
            return text, confidence
    except Exception:
        pass

    text = pytesseract_module.image_to_string(img, lang=engine_lang)
    return text, _estimate_tesseract_confidence(text, img.size)


def _text_and_confidence_from_data(data: dict) -> tuple[str, float]:
    """从 pytesseract image_to_data 结果恢复行文本与加权置信度。"""
    texts = data.get("text", [])
    count = len(texts)
    lines: list[str] = []
    current_key = None
    current_tokens: list[str] = []
    weighted_confidence = 0.0
    total_weight = 0

    for index in range(count):
        token = str(texts[index]).strip()
        key = tuple(
            data.get(field, [0] * count)[index]
            for field in ("block_num", "par_num", "line_num")
        )
        if current_key is not None and key != current_key and current_tokens:
            lines.append(" ".join(current_tokens))
            current_tokens = []
        current_key = key
        if not token:
            continue
        current_tokens.append(token)
        try:
            confidence = float(data.get("conf", [-1] * count)[index])
        except (TypeError, ValueError):
            confidence = -1
        if confidence >= 0:
            weight = max(len(re.sub(r"\s+", "", token)), 1)
            weighted_confidence += confidence * weight
            total_weight += weight

    if current_tokens:
        lines.append(" ".join(current_tokens))

    body = "\n".join(lines)
    confidence = weighted_confidence / total_weight / 100 if total_weight else 0.0
    return body, round(min(max(confidence, 0.0), 1.0), 4)


def _ocr_tesseract_segmented(path: Path, img, lang: str,
                              pytesseract_module, image_module) -> dict:
    """在内存中分段识别长图，不落地中间图片。"""
    boxes = _segment_boxes(img.size)
    segment_records = []
    successful_texts = []
    selected_language = None

    for index, box in enumerate(boxes):
        crop = _resize_for_chinese(img.crop(box), lang, image_module)
        languages = [selected_language] if selected_language else None
        candidates = _run_tesseract_candidates(crop, lang, pytesseract_module, crop.size, languages)
        best = max(candidates, key=lambda candidate: candidate[3]) if candidates else None
        body = best[1].strip() if best else ""
        confidence = best[2] if best and body else 0.0
        if best and body and selected_language is None:
            selected_language = best[0]
        if body:
            successful_texts.append(body)

        segment_records.append({
            "index": index,
            "y_start": box[1],
            "y_end": box[3],
            "confidence": round(confidence, 4),
            "word_count": len(re.findall(r'[一-鿿]', body)),
            "char_count": len(re.sub(r"\s+", "", body)),
            "verdict": _quality_verdict(confidence, None),
            "status": "ok" if body else "failed",
        })

    if not successful_texts:
        return {
            "error": "ocr_no_text",
            "message": "Tesseract 未在长图分段中检测到文字",
            "type": "screenshot_ocr",
            "source": str(path),
            "body": "",
            "word_count": 0,
        }

    body = _merge_segment_texts(successful_texts)
    confidence = _aggregate_segment_confidence(segment_records)
    failed_count = sum(record["status"] == "failed" for record in segment_records)
    warning = None
    if failed_count:
        warning = f"{failed_count} 个分段未识别出文字；结果必须结合原图复核"

    return _build_result(
        path,
        body,
        confidence,
        engine="tesseract",
        engine_lang=selected_language or "",
        strategy="segmented",
        segments=segment_records,
        force_degraded=failed_count > 0,
        warning=warning,
    )


def _normalize_overlap_line(line: str) -> str:
    return re.sub(r"\s+", "", line).strip()


def _merge_two_segment_texts(left: str, right: str, max_overlap_lines: int = 12) -> str:
    """仅去除完全可确认的重复行，模糊匹配不删除。"""
    left_lines = left.strip().splitlines()
    right_lines = right.strip().splitlines()
    max_overlap = min(max_overlap_lines, len(left_lines), len(right_lines))

    overlap = 0
    for count in range(max_overlap, 0, -1):
        left_tail = [_normalize_overlap_line(line) for line in left_lines[-count:]]
        right_head = [_normalize_overlap_line(line) for line in right_lines[:count]]
        if all(left_tail) and left_tail == right_head:
            overlap = count
            break

    return "\n".join(left_lines + right_lines[overlap:]).strip()


def _merge_segment_texts(texts: list[str]) -> str:
    merged = ""
    for text in texts:
        merged = text.strip() if not merged else _merge_two_segment_texts(merged, text)
    return re.sub(r'\n{3,}', '\n\n', merged).strip()


def _aggregate_segment_confidence(segments: list[dict]) -> float:
    """按识别字符数加权，并用分段成功率惩罚缺失区域。"""
    if not segments:
        return 0.0
    successful = [segment for segment in segments if segment.get("status") == "ok"]
    if not successful:
        return 0.0
    weights = [max(int(segment.get("char_count", 0)), 1) for segment in successful]
    weighted = sum(
        float(segment.get("confidence", 0.0)) * weight
        for segment, weight in zip(successful, weights)
    ) / sum(weights)
    coverage = len(successful) / len(segments)
    return round(weighted * coverage, 4)


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
        # total_chars > 0 已在上面保证，无需除零保护
        ascii_ratio = ascii_chars / total_chars
        chinese_ratio = chinese_chars / total_chars
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
                  engine: str = "paddleocr", engine_lang: str = "",
                  strategy: str = "whole_image", segments: list[dict] | None = None,
                  force_degraded: bool = False, warning: str | None = None) -> dict:
    """组装标准输出 JSON。"""
    kenlm_perplexity = _compute_perplexity(body)
    verdict = _quality_verdict(confidence, kenlm_perplexity)
    if force_degraded and verdict == "ok":
        verdict = "degraded"
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
            "strategy": strategy,
            "safe_for_verbatim": verdict == "ok",
        },
        "images": [{"url": str(path.absolute()), "path": f"images/{path.name}"}],
    }
    if engine_lang:
        result["ocr_quality"]["engine_lang"] = engine_lang
    if segments is not None:
        result["ocr_quality"]["segment_count"] = len(segments)
        result["ocr_segments"] = segments
    if warning:
        result["ocr_quality"]["warning"] = warning
    if verdict != "ok":
        result["ocr_quality"]["handling"] = "preserve_original_and_review"

    return result


def _compute_perplexity(text: str) -> float | None:
    """使用 KenLM 计算文本困惑度。"""
    try:
        import kenlm
    except ImportError:
        return None

    # 模型目录：优先环境变量 WEB_ANALYSIS_MODELS_DIR → ~/.web-analysis/models/
    # 详见项目 CLAUDE.md 的 Key Paths 说明
    models_dir = os.environ.get(
        "WEB_ANALYSIS_MODELS_DIR",
        str(Path.home() / ".web-analysis" / "models"),
    )
    model_paths = [
        Path(models_dir) / "ocr/kenlm/zh.binary",
        Path(models_dir) / "ocr/kenlm/zh.arpa",
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
