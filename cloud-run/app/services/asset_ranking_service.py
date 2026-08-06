from app.services import asset_relevance
from app.services.asset_feedback_service import load_all
from app.services.asset_learning_engine import compute_bias
from app.services.asset_quality_scorer import score_asset


def select_best_with_score(candidates: list, is_hook_scene: bool = False,
                           scene: dict = None, used=None):
    """
    select_best()와 동일하게 채점하되, 최고 점수 후보와 그 점수를 함께
    반환합니다 (candidates가 비어 있으면 (None, None)). Sprint38 Hybrid
    Asset Engine이 "이 후보가 충분히 고품질인지"를 임계값과 비교해야
    해서 점수 자체가 필요할 때 사용합니다.

    Sprint76 - scene을 주면 의미 점수를 더한다.

    그 전까지 score_asset이 내는 값 중 후보마다 달라지는 것은 세로비율
    가산점뿐이었다. 같은 provider에서 온 세로 사진 5장은 전부 같은
    점수를 받았고 max()가 그중 첫 번째를 골랐다 - 순위라는 것이 사실상
    없었다. 축적된 스톡 scene 140건 중 80.7%가 재생성 권고를 받았고,
    사유가 기록된 113건 중 89건이 "검색 결과가 장면과 다름"이었다.

    scene이 없는 호출부는 예전과 완전히 동일하게 동작한다.
    """

    if not candidates:
        return None, None

    records = load_all()

    scored = [
        (
            score_asset(
                candidate,
                is_hook_scene=is_hook_scene,
                learned_bias=compute_bias(records, candidate["source"]),
            )
            + (
                asset_relevance.score(candidate, scene, used)
                if scene else 0.0
            ),
            candidate,
        )
        for candidate in candidates
    ]

    # 동점이면 앞선 후보가 이긴다. max()는 첫 최대값을 돌려주므로
    # provider가 준 순서가 유지된다 - 우리가 가릴 근거가 없을 때 그쪽
    # 판단을 뒤집을 이유가 없다.
    best_score, best_candidate = max(scored, key=lambda pair: pair[0])

    return best_candidate, best_score


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

    best_candidate, _ = select_best_with_score(candidates, is_hook_scene=is_hook_scene)

    return best_candidate
