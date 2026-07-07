"""
Sprint50 - AI Director v1.

Sprint43(asset_quality_service)/Sprint47(prompt_effectiveness_service)/
Sprint48(prompt_optimization_service)/Sprint49(prompt_learning_service)의
결과를 읽어, scene마다 accept/review/regenerate 권고만 계산하는 순수
규칙 기반 판단 엔진입니다. LLM 호출, DB, 파일 I/O가 전혀 없습니다.

Director는 절대 아래를 하지 않습니다:
- image_prompt/narration 수정
- scene 순서 변경
- asset 재생성 호출
- 다른 서비스 호출(다른 서비스의 "결과"만 입력으로 받습니다)
- 그 외 pipeline 출력 변경

각 입력(prompt_metrics/asset_quality_results/best_pattern/
optimized_scene_ids)은 전부 "있으면 읽고, 없으면 unknown으로 취급"
방식입니다 - Sprint43/48/49 중 무엇이 파이프라인에 연결되어 있지
않아도(Sprint50 시점 기준 asset_quality_service는 아직 파이프라인에
연결되어 있지 않음) 안전하게 동작합니다.
"""

from app.services import asset_quality_service

ACCEPT = "accept"
REVIEW = "review"
REGENERATE = "regenerate"

PROMPT_PASSED = "prompt_passed"
PROMPT_FAILED = "prompt_failed"
PROMPT_UNKNOWN = "prompt_unknown"

ASSET_QUALITY_PASSED = "asset_quality_passed"
ASSET_QUALITY_BORDERLINE = "asset_quality_borderline"
ASSET_QUALITY_FAILED = "asset_quality_failed"
ASSET_QUALITY_UNKNOWN = "asset_quality_unknown"

KNOWN_SUCCESSFUL_PATTERN = "known_successful_pattern"
PROMPT_WAS_OPTIMIZED = "prompt_was_optimized"

# asset_quality_service.PASS_THRESHOLD(80)보다 낮지만 이 여유폭 안이면
# "완전히 실패"가 아니라 "애매함(review)"으로 완화합니다.
ASSET_QUALITY_BORDERLINE_MARGIN = 15

NEUTRAL_CONFIDENCE_SCORE = 50  # 데이터가 없을 때 쓰는 중립(0.5) 점수
PATTERN_MATCH_BONUS = 0.1


def _prompt_status(prompt_metric: dict) -> str:
    if prompt_metric is None:
        return PROMPT_UNKNOWN
    return PROMPT_PASSED if prompt_metric.get("passed") else PROMPT_FAILED


def _asset_quality_status(asset_quality_result: dict) -> str:
    if asset_quality_result is None:
        return ASSET_QUALITY_UNKNOWN

    if asset_quality_result.get("passed"):
        return ASSET_QUALITY_PASSED

    score = asset_quality_result.get("score", 0)

    if score >= asset_quality_service.PASS_THRESHOLD - ASSET_QUALITY_BORDERLINE_MARGIN:
        return ASSET_QUALITY_BORDERLINE

    return ASSET_QUALITY_FAILED


def _matches_best_pattern(scene_plan_item: dict, best_pattern: dict) -> bool:

    if not scene_plan_item or not best_pattern:
        return False

    fields = ("camera", "visual_type", "purpose")

    if not all(best_pattern.get(field) for field in fields):
        return False

    return all(
        scene_plan_item.get(field) == best_pattern.get(field)
        for field in fields
    )


def _decide(prompt_status: str, asset_status: str) -> str:

    if prompt_status == PROMPT_FAILED or asset_status == ASSET_QUALITY_FAILED:
        return REGENERATE

    if prompt_status == PROMPT_PASSED and asset_status in (
        ASSET_QUALITY_PASSED, ASSET_QUALITY_UNKNOWN,
    ):
        return ACCEPT

    return REVIEW


def _calculate_confidence(
    prompt_metric: dict,
    asset_quality_result: dict,
    pattern_match: bool,
) -> float:
    """
    prompt_metric["score"]/asset_quality_result["score"]를 0~1로
    정규화해 평균 낸 뒤, known_successful_pattern이면 소폭 가산합니다.
    둘 다 없으면(완전히 정보 부족) 중립값 0.5를 씁니다. 항상 0.0~1.0
    범위로 clamp합니다.
    """

    prompt_score = (
        prompt_metric.get("score", NEUTRAL_CONFIDENCE_SCORE)
        if prompt_metric is not None else NEUTRAL_CONFIDENCE_SCORE
    )
    asset_score = (
        asset_quality_result.get("score", NEUTRAL_CONFIDENCE_SCORE)
        if asset_quality_result is not None else NEUTRAL_CONFIDENCE_SCORE
    )

    base = (prompt_score / 100 + asset_score / 100) / 2
    bonus = PATTERN_MATCH_BONUS if pattern_match else 0.0

    return round(min(1.0, max(0.0, base + bonus)), 4)


def evaluate_scene(
    prompt_metric: dict = None,
    asset_quality_result: dict = None,
    scene_plan_item: dict = None,
    best_pattern: dict = None,
    optimized: bool = False,
) -> dict:
    """
    scene 하나의 accept/review/regenerate 권고를 계산합니다. 순수
    함수입니다 - 입력을 변경하지 않고, 아무것도 호출하지 않습니다.

    반환값: {"decision": str, "confidence": float, "reasons": list[str]}
    """

    prompt_status = _prompt_status(prompt_metric)
    asset_status = _asset_quality_status(asset_quality_result)
    pattern_match = _matches_best_pattern(scene_plan_item, best_pattern)

    decision = _decide(prompt_status, asset_status)

    # 실패한 프롬프트라도 Sprint48 Optimization이 이미 손을 댔다면,
    # 완전 재생성보다는 review로 완화해 사람이 다시 볼 여지를 둡니다 -
    # Director는 Optimization이 실제로 문제를 고쳤는지 재평가할 수는
    # 없으므로(재평가 호출 금지), 한 단계만 완화합니다.
    if decision == REGENERATE and optimized and asset_status != ASSET_QUALITY_FAILED:
        decision = REVIEW

    reasons = [prompt_status, asset_status]

    if pattern_match:
        reasons.append(KNOWN_SUCCESSFUL_PATTERN)

    if optimized:
        reasons.append(PROMPT_WAS_OPTIMIZED)

    confidence = _calculate_confidence(prompt_metric, asset_quality_result, pattern_match)

    return {
        "decision": decision,
        "confidence": confidence,
        "reasons": reasons,
    }


def evaluate_scenes(
    scenes: list,
    scene_plan: list = None,
    prompt_metrics: list = None,
    asset_quality_results: list = None,
    best_pattern: dict = None,
    optimized_scene_ids: set = None,
) -> list:
    """
    scene 배치 전체에 evaluate_scene()을 적용하는 pipeline 연동용
    래퍼입니다. scene 번호로 scene_plan/prompt_metrics/
    asset_quality_results를 매칭합니다 (Sprint47~49 배치 함수들과
    동일한 매칭 방식). scene을 변경하거나 순서를 바꾸지 않습니다.

    반환값: [{"scene_id": int, "decision": str, "confidence": float,
              "reasons": list[str]}, ...] - scenes 순서를 그대로
    유지합니다.
    """

    plan_by_scene = {
        item["scene_id"]: item for item in (scene_plan or [])
    }
    metrics_by_scene = {
        entry["scene_id"]: entry for entry in (prompt_metrics or [])
    }
    asset_quality_by_scene = {
        entry["scene_id"]: entry for entry in (asset_quality_results or [])
    }
    optimized_scene_ids = optimized_scene_ids or set()

    results = []

    for scene in (scenes or []):

        scene_number = scene.get("scene")

        result = evaluate_scene(
            metrics_by_scene.get(scene_number),
            asset_quality_by_scene.get(scene_number),
            plan_by_scene.get(scene_number),
            best_pattern,
            scene_number in optimized_scene_ids,
        )

        results.append({"scene_id": scene_number, **result})

    return results
