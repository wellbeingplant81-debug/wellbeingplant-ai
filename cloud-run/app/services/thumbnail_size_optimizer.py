"""
Sprint D (2026-07-22) - YouTube Thumbnail Size Optimizer.

YouTube Thumbnail API는 2MB(2097152 bytes)를 넘는 파일을 거부한다
(실측: output/20260722_125103, thumbnail_error="Media larger than:
2097152", 실제 thumbnail.png=2.3MB). optimize_thumbnail_for_upload()는
업로드 "직전"에만 호출되는 순수 파일 최적화 함수 - 원본 thumbnail_path
자체는 절대 수정하지 않는다(보관/시각 검수 목적 유지, Sprint124/
Sprint A와 동일한 원칙). sibling 파일(_optimized.png/.jpg)만 새로
만든다.

2MB 이하면 아무 파일도 새로 만들지 않고 원본 경로를 그대로 반환한다.
2MB 초과 시에만, 육안 손실이 가장 적은 방법부터 시도해 가장 먼저 2MB
이하가 되는 단계에서 멈춘다:

1. PNG Lossless Optimize (Pillow optimize=True, 화질 손실 없음)
2. PNG Quantization (256색 팔레트 - 약간의 색 손실)
3. JPEG 변환 quality=95 -> 90 -> 85 -> 80 (단계적 하향)

모든 단계를 거쳐도 2MB를 넘으면(현실적으로 거의 없음) quality=80
결과를 그대로 반환한다(best-effort) - 무한정 더 낮추지 않는다.
"""

import os

from PIL import Image

MAX_THUMBNAIL_BYTES = 2097152
JPEG_QUALITY_STEPS = [95, 90, 85, 80]


def get_file_size_bytes(path: str) -> int:
    return os.path.getsize(path)


def _optimized_png_path(thumbnail_path: str) -> str:
    base, _ext = os.path.splitext(thumbnail_path)
    return base + "_optimized.png"


def _optimized_jpeg_path(thumbnail_path: str) -> str:
    base, _ext = os.path.splitext(thumbnail_path)
    return base + "_optimized.jpg"


def _save_png_lossless_optimized(source_path: str, output_path: str) -> None:
    with Image.open(source_path) as image:
        image.convert("RGB").save(output_path, format="PNG", optimize=True)


def _save_png_quantized(source_path: str, output_path: str) -> None:
    with Image.open(source_path) as image:
        quantized = image.convert("RGB").convert(
            "P", palette=Image.ADAPTIVE, colors=256
        )
        quantized.save(output_path, format="PNG", optimize=True)


def _save_jpeg(source_path: str, output_path: str, quality: int) -> None:
    with Image.open(source_path) as image:
        image.convert("RGB").save(output_path, format="JPEG", quality=quality)


def optimize_thumbnail_for_upload(thumbnail_path: str) -> str:

    if get_file_size_bytes(thumbnail_path) <= MAX_THUMBNAIL_BYTES:
        return thumbnail_path

    png_path = _optimized_png_path(thumbnail_path)
    _save_png_lossless_optimized(thumbnail_path, png_path)
    if get_file_size_bytes(png_path) <= MAX_THUMBNAIL_BYTES:
        return png_path

    _save_png_quantized(png_path, png_path)
    if get_file_size_bytes(png_path) <= MAX_THUMBNAIL_BYTES:
        return png_path

    jpeg_path = _optimized_jpeg_path(thumbnail_path)
    for quality in JPEG_QUALITY_STEPS:
        _save_jpeg(png_path, jpeg_path, quality)
        if get_file_size_bytes(jpeg_path) <= MAX_THUMBNAIL_BYTES:
            return jpeg_path

    return jpeg_path
