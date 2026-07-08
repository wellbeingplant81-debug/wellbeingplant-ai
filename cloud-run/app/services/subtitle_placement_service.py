"""
Sprint57 - Smart Subtitle Placement v1.

기존 자막은 항상 화면 하단(final_video_service.py의 Alignment=2)에
고정되어 있어, 실제 E2E에서 사람 얼굴/피사체가 하단에 있는 이미지에
자막이 그대로 겹치는 문제가 있었다. 이 모듈은 scene 이미지 하나를
받아 화면 상단 25% / 하단 25% 영역의 "복잡도"(Laplacian 분산 - 값이
클수록 가장자리/디테일이 많다는 뜻)를 비교해서, 더 단순한(비어있는)
쪽에 자막을 배치하도록 "top"/"bottom" 중 하나를 고른다.

이번 Sprint에서는 얼굴 인식을 하지 않는다 - 단순 이미지 복잡도
비교만 한다. 이미지가 없거나 읽을 수 없으면 기존 동작과 동일한
DEFAULT_POSITION(하단)으로 안전하게 폴백한다 - 어떤 경우에도 예외를
던지지 않는다(subtitle 생성이 이 판단 하나 때문에 실패하면 안 된다).
"""

import os

import cv2

TOP_STRIP_RATIO = 0.25
BOTTOM_STRIP_RATIO = 0.25

POSITION_TOP = "top"
POSITION_BOTTOM = "bottom"

DEFAULT_POSITION = POSITION_BOTTOM


def _region_complexity(gray_region) -> float:
    return float(cv2.Laplacian(gray_region, cv2.CV_64F).var())


def choose_subtitle_position(image_path: str) -> str:
    """
    image_path의 상단/하단 25% 영역 중 더 단순한(복잡도가 낮은) 쪽에
    자막을 배치하기로 결정한다. 경로가 없거나, 파일이 없거나, 이미지를
    디코딩할 수 없으면 DEFAULT_POSITION을 반환한다.
    """

    if not image_path or not os.path.exists(image_path):
        return DEFAULT_POSITION

    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    if image is None or image.size == 0:
        return DEFAULT_POSITION

    height = image.shape[0]
    top_h = max(1, int(height * TOP_STRIP_RATIO))
    bottom_h = max(1, int(height * BOTTOM_STRIP_RATIO))

    top_region = image[:top_h, :]
    bottom_region = image[height - bottom_h:, :]

    top_complexity = _region_complexity(top_region)
    bottom_complexity = _region_complexity(bottom_region)

    if bottom_complexity > top_complexity:
        return POSITION_TOP

    return POSITION_BOTTOM
