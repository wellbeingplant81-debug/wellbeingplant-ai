WARM_SOFT_CLEAN_WELLNESS = "warm, soft, clean wellness aesthetic"
NATURAL_MORNING_LIGHT = "natural morning lighting"


def build_color_mood() -> str:
    """
    영상 전체에 통일해서 적용할 색감/분위기 서술어를 반환합니다.
    순수 함수입니다 (파일/네트워크 접근 없음, 항상 동일한 값 반환).
    """

    return f"{WARM_SOFT_CLEAN_WELLNESS}, {NATURAL_MORNING_LIGHT}"
