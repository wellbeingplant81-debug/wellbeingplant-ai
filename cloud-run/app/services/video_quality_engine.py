import statistics

from app.services.scene_flow_engine import analyze_flow
from app.services.subtitle_service import MAX_CHARS, split_subtitle

WEIGHTS = {
    "scene_continuity": 0.25,
    "visual_diversity": 0.20,
    "subtitle_readability": 0.20,
    "provider_consistency": 0.15,
    "flow_smoothness": 0.20,
}


def _subtitle_readability_score(scenes: list) -> float:
    """
    각 scene의 narration을 실제 subtitle_service.split_subtitle()로
    분할해, 결과 자막 조각 중 MAX_CHARS 이하인 비율을 readability로
    사용합니다 - 근사치가 아니라 실제 자막 생성 로직을 그대로
    재사용한 실측값입니다.
    """

    total = 0
    within_limit = 0

    for scene in scenes:

        for piece in split_subtitle(scene.get("narration", "")):
            total += 1
            if len(piece) <= MAX_CHARS:
                within_limit += 1

    return within_limit / total if total else 1.0


def _provider_consistency_score(scenes: list) -> float:
    """
    가장 많이 쓰인 provider가 전체에서 차지하는 비율을 일관성
    점수로 사용합니다 (예: 6개 scene 중 5개가 ai_image면 5/6).
    """

    providers = [scene.get("provider") for scene in scenes if scene.get("provider")]

    if not providers:
        return 0.0

    most_common_count = max(providers.count(p) for p in set(providers))

    return most_common_count / len(providers)


def _visual_diversity_score(scenes: list) -> float:
    """
    연속된 scene끼리 provider와 검색 키워드가 완전히 동일한 비율의
    역수를 시각적 다양성 근사치로 사용합니다. 실제 이미지 픽셀/구도
    분석은 하지 않습니다 - 사용 가능한 메타데이터 기반의 근사치임을
    명시합니다 (Sprint28 설계 문서의 "관련성 검증 없음" 열린 이슈와
    같은 종류의 한계).
    """

    sorted_scenes = sorted(scenes, key=lambda scene: scene["scene"])

    if len(sorted_scenes) < 2:
        return 1.0

    repeats = sum(
        1
        for a, b in zip(sorted_scenes, sorted_scenes[1:])
        if a.get("provider") == b.get("provider")
        and a.get("search_query") == b.get("search_query")
    )

    return 1 - (repeats / (len(sorted_scenes) - 1))


def _flow_smoothness_score(pairs: list) -> float:
    """
    인접 scene 쌍의 연속성 점수 표준편차가 작을수록(고르게
    이어질수록) 높은 점수를 줍니다. 평균(연속성)이 아니라 편차를
    보므로 scene_continuity와는 다른 신호입니다.
    """

    scores = [pair["continuity_score"] for pair in pairs]

    if len(scores) < 2:
        return 1.0

    return max(0.0, 1 - statistics.pstdev(scores))


def evaluate_video_quality(scenes: list) -> dict:
    """
    전체 영상 품질 점수를 5가지 요소의 가중 평균으로 계산합니다.
    순수 함수입니다 (파일/네트워크 접근 없음, scene 순서 변경 없음).

    반환값: {"overall_score": float, "components": {5개 요소별 점수}}
    """

    flow = analyze_flow(scenes)

    components = {
        "scene_continuity": flow["overall_flow_score"],
        "visual_diversity": _visual_diversity_score(scenes),
        "subtitle_readability": _subtitle_readability_score(scenes),
        "provider_consistency": _provider_consistency_score(scenes),
        "flow_smoothness": _flow_smoothness_score(flow["pairs"]),
    }

    overall_score = sum(
        components[key] * weight
        for key, weight in WEIGHTS.items()
    )

    return {
        "overall_score": overall_score,
        "components": components,
    }
