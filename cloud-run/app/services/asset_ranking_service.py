from app.services.asset_feedback_service import load_all
from app.services.asset_learning_engine import compute_bias
from app.services.asset_quality_scorer import score_asset


def select_best(candidates: list, is_hook_scene: bool = False):
    """
    candidate 리스트를 채점하여 가장 점수가 높은 후보 하나를
    반환합니다. candidates가 비어 있으면 None을 반환합니다 -
    AI Image 폴백 여부는 호출자(asset_integration_service.py)가
    판단합니다.

    Sprint31 - Learning Layer: 채점 전에 feedback 이력을 한 번만
    로드하여(candidate마다 파일을 다시 읽지 않음) 각 후보의 provider에
    해당하는 학습된 bias를 조회, score_asset()에 명시적으로 전달합니다.
    feedback 이력이 없으면 모든 bias가 0.0이라 Sprint30과 완전히
    동일하게 동작합니다.
    """

    if not candidates:
        return None

    records = load_all()

    scored = [
        (
            score_asset(
                candidate,
                is_hook_scene=is_hook_scene,
                learned_bias=compute_bias(records, candidate["source"]),
            ),
            candidate,
        )
        for candidate in candidates
    ]

    _best_score, best_candidate = max(scored, key=lambda pair: pair[0])

    return best_candidate
