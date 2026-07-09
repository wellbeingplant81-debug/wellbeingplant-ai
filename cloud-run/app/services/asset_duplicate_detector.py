"""
Sprint64-1 - Generated Asset Quality Layer 1단계: 생성된 이미지 asset
간 정확/근사 중복을 감지하는 구조.

Scene당 여러 asset(Sprint62-4: 최대 4개, 동일/유사 image_prompt가
아니라 서로 다른 subprompt로 생성됨 - Sprint62-5~63-4)이 실제로
픽셀 수준에서도 서로 다른지 검증한다. 이번 스프린트는 탐지 구조만
추가하며, asset_integration_service.py 등 기존 호출부는 전혀
수정하지 않는다(재생성 연동은 이후 스프린트 범위) - 순수 읽기 전용
함수로, 파일을 쓰거나 재생성을 트리거하지 않는다.
"""

import hashlib
import os

from PIL import Image

# Average Hash 크기. 8x8 그레이스케일 -> 64비트 해시.
HASH_SIZE = 8
HASH_BITS = HASH_SIZE * HASH_SIZE

# Hamming distance가 이 값 이하이면 "매우 유사"로 판정한다.
DEFAULT_HAMMING_THRESHOLD = 5


def _file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _average_hash(path: str) -> int:

    image = Image.open(path).convert("L").resize((HASH_SIZE, HASH_SIZE))
    pixels = list(image.getdata())
    average = sum(pixels) / len(pixels)

    bits = 0
    for pixel in pixels:
        bits = (bits << 1) | (1 if pixel >= average else 0)

    return bits


def _hamming_distance(hash_a: int, hash_b: int) -> int:
    return bin(hash_a ^ hash_b).count("1")


def _similarity(hamming_distance: int) -> float:
    return round(1 - (hamming_distance / HASH_BITS), 3)


def find_duplicate_assets(
    asset_paths: list,
    hamming_threshold: int = DEFAULT_HAMMING_THRESHOLD,
) -> list:
    """
    asset_paths 순서대로 각 asset을 그보다 앞선 asset들과 비교해
    정확/근사 중복을 찾습니다. 존재하지 않는 경로는 비교 대상에서
    조용히 제외됩니다(예외 발생 없음). 순수 읽기 전용 함수입니다.

    반환값: 중복으로 판정된 항목만 담은 리스트. 각 항목은
    {"index", "duplicate_of_index", "reason"("exact"|"near_duplicate"),
    "hamming_distance", "similarity"}. 한 asset이 여러 앞선 asset과
    동시에 겹치더라도 가장 먼저 발견된 중복 하나만 보고합니다.
    """

    valid_indices = [
        i for i, path in enumerate(asset_paths)
        if path and os.path.exists(path)
    ]

    file_hashes = {}
    avg_hashes = {}

    for i in valid_indices:
        file_hashes[i] = _file_hash(asset_paths[i])
        avg_hashes[i] = _average_hash(asset_paths[i])

    duplicates = []

    for position, i in enumerate(valid_indices):
        for j in valid_indices[:position]:

            if file_hashes[i] == file_hashes[j]:
                duplicates.append({
                    "index": i,
                    "duplicate_of_index": j,
                    "reason": "exact",
                    "hamming_distance": 0,
                    "similarity": 1.0,
                })
                break

            distance = _hamming_distance(avg_hashes[i], avg_hashes[j])

            if distance <= hamming_threshold:
                duplicates.append({
                    "index": i,
                    "duplicate_of_index": j,
                    "reason": "near_duplicate",
                    "hamming_distance": distance,
                    "similarity": _similarity(distance),
                })
                break

    return duplicates
