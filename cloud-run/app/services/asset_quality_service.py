import os

from app.services import regeneration_service

# 각 검사 항목이 실패했을 때 score에서 깎이는 점수. 서로 다른 소수
# 조합(21/25/20/19/15)을 사용해 "asset_exists만 실패 -> 79점(FAIL)",
# "prompt_match만 실패 -> 80점(PASS)" 같은 임계값 경계 케이스를 실제
# 규칙 조합만으로 재현할 수 있게 했습니다 (합계는 항상 100).
POINTS = {
    "asset_exists": 21,
    "semantic_match": 25,
    "prompt_match": 20,
    "aspect_ratio": 19,
    "forbidden_text": 15,
}

REASON_FOR_CHECK = {
    "asset_exists": "asset_missing",
    "semantic_match": "low_semantic_match",
    "prompt_match": "low_prompt_match",
    "aspect_ratio": "aspect_ratio_mismatch",
    "forbidden_text": "forbidden_text_detected",
}

PASS_THRESHOLD = 80

FORBIDDEN_TEXT_MARKERS = (
    "watermark",
    "sample",
    "placeholder",
    "shutterstock",
    "getty",
)


def _significant_words(text: str) -> set:
    return {word for word in text.lower().split() if len(word) >= 3}


def _shares_a_word(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return bool(_significant_words(a) & _significant_words(b))


def _check_asset_exists(asset: dict) -> bool:
    local_path = asset.get("local_path")
    return bool(local_path) and os.path.exists(local_path)


def _check_semantic_match(scene: dict, asset: dict) -> bool:
    narration = scene.get("narration", "")
    query = asset.get("metadata", {}).get("query", "")
    return _shares_a_word(narration, query)


def _check_prompt_match(scene: dict, asset: dict) -> bool:
    image_prompt = scene.get("image_prompt", "")
    query = asset.get("metadata", {}).get("query", "")
    return _shares_a_word(image_prompt, query)


def _check_aspect_ratio(asset: dict) -> bool:
    """
    AI 이미지는 image_service가 항상 목표 비율로 생성하므로 항상
    통과시킵니다. 스톡 자산은 width/height 메타데이터가 있을 때만
    세로(portrait) 비율 여부를 확인합니다 - 없으면(구버전 캐시 등)
    판단 근거가 없으므로 통과로 처리합니다.
    """

    if asset.get("source") == "ai_image":
        return True

    metadata = asset.get("metadata", {})
    width = metadata.get("width")
    height = metadata.get("height")

    if not width or not height:
        return True

    return height > width


def _check_forbidden_text(asset: dict) -> bool:
    metadata = asset.get("metadata", {})
    haystack = " ".join(
        str(value)
        for value in metadata.values()
        if isinstance(value, str)
    ).lower()

    return not any(marker in haystack for marker in FORBIDDEN_TEXT_MARKERS)


def score_asset(scene: dict, asset: dict) -> dict:
    """
    scene에 선택된 asset 하나의 품질을 0~100점 규칙 기반으로
    채점합니다. 순수 함수입니다 - 파일을 쓰거나 재생성을 트리거하지
    않습니다 (asset 파일 존재 여부 확인을 위한 읽기 전용 os.path.exists
    호출만 있음).

    반환값: {"score": int, "passed": bool, "reasons": list[str]}
    """

    checks = {
        "asset_exists": _check_asset_exists(asset),
        "semantic_match": _check_semantic_match(scene, asset),
        "prompt_match": _check_prompt_match(scene, asset),
        "aspect_ratio": _check_aspect_ratio(asset),
        "forbidden_text": _check_forbidden_text(asset),
    }

    score = 0
    reasons = []

    for key, ok in checks.items():
        if ok:
            score += POINTS[key]
        else:
            reasons.append(REASON_FOR_CHECK[key])

    return {
        "score": score,
        "passed": score >= PASS_THRESHOLD,
        "reasons": reasons,
    }


def evaluate_asset(scene: dict, asset: dict, project_path: str) -> dict:
    """
    score_asset()으로 채점한 뒤, PASS_THRESHOLD(80점) 미만이면 기존
    Sprint40 Auto Regeneration Engine(regeneration_service.run)을
    그대로 재사용해 재생성을 트리거합니다. 재생성 로직 자체는
    중복 구현하지 않고, score_asset()의 순수성을 지키기 위해
    부수효과(재생성 호출)는 이 wrapper에서만 발생시킵니다.
    """

    result = score_asset(scene, asset)

    if not result["passed"]:
        regeneration_service.run(project_path)

    return result
