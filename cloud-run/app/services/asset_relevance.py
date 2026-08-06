"""
Sprint76 - 후보 자산의 순위.

지금까지 순위라는 것이 사실상 없었다. asset_quality_scorer.score_asset이
내는 값 중 후보마다 달라지는 것은 세로비율 가산점(0.05)뿐이라, 같은
provider에서 온 세로 사진 5장은 전부 같은 점수를 받고 max()가 그중 첫
번째를 골랐다. select_asset은 아예 results[0]을 썼다.

그리고 그것이 가장 큰 실패 원인과 맞물린다 - 축적된 스톡 scene 140건
중 80.7%가 재생성 권고를 받았고(AI scene은 17.1%), 사유가 기록된 113건
중 89건이 "검색 결과가 장면과 다름"이었다.

의미 정보가 없어서 순위를 못 매긴 것이 아니었다. Pexels 사진 응답에는
alt(사진 설명)가 있고 url에는 내용을 적은 슬러그가 들어 있는데,
provider가 두 필드를 모두 버리고 있었다. 추가 API 호출 없이 얻는
신호다.

여기 있는 것은 전부 순수 함수다. 네트워크도 파일도 건드리지 않는다.
"""

from app.services.search_query_builder import _words


# 각 신호의 무게. scene 일치가 압도적으로 중요하다 - 실패의 대부분이
# "장면과 다름"이기 때문이다. 나머지는 동점을 가르는 정도다.
RELEVANCE_WEIGHT = 1.0
PORTRAIT_BONUS = 0.15
MOTION_BONUS = 0.10

# 사물 scene에 사람이 들어오는 것은 Sprint73/75에서 반복해 무너진
# 자리다. 다른 신호로 상쇄되지 않도록 크게 깎는다.
HUMAN_PENALTY = 0.60

# 같은 사진이 두 scene에 들어가면 영상이 반복돼 보인다.
DUPLICATE_PENALTY = 0.50

# Shorts의 한 scene은 몇 초짜리다. 이 범위를 벗어난 영상은 쓸 구간이
# 없거나(너무 짧음) 대부분을 버린다(너무 김).
USABLE_DURATION_SECONDS = (3, 30)

PERSON_WORDS = {
    "man", "men", "woman", "women", "person", "people", "boy", "girl",
    "male", "female", "lady", "guy", "couple", "family", "child",
    "children", "kid", "adult", "senior", "elderly", "model", "portrait",
    "hand", "hands", "face", "smiling", "selfie",
}


def _candidate_text(candidate: dict) -> str:
    """후보에 대해 우리가 아는 말 전부.

    alt는 Pexels 사진 응답의 설명이고, 슬러그는 url에 들어 있다. 비디오
    응답에는 alt가 없어 슬러그가 유일한 단서다.
    """

    alt = candidate.get("alt") or ""
    url = candidate.get("source_url") or ""

    slug = ""
    if url:
        parts = [part for part in url.rstrip("/").split("/") if part]
        if parts:
            slug = parts[-1].replace("-", " ").replace("_", " ")

    return f"{alt} {slug}".strip()


def _scene_words(scene: dict) -> set:
    scene = scene or {}

    words = set()
    for element in ("subject", "action", "environment"):
        words.update(_words(scene.get(element)))

    if not words:
        words.update(_words(scene.get("image_prompt")))

    return words


def relevance_score(candidate: dict, scene: dict) -> float:
    """
    후보 설명이 scene을 얼마나 담고 있나. 0.0 ~ 1.0.

    scene 단어 중 몇 개가 후보 설명에 나타나는지를 본다. 후보 쪽 단어
    수로 나누지 않는 이유는, 설명이 긴 사진이 그것만으로 불리해질
    이유가 없기 때문이다.
    """

    wanted = _scene_words(scene)

    if not wanted:
        return 0.0

    found = set(_words(_candidate_text(candidate)))

    if not found:
        return 0.0

    return len(wanted & found) / len(wanted)


def human_penalty(candidate: dict, scene: dict) -> float:
    """
    사람을 요구하지 않은 scene에 사람이 들어왔는가.

    인물 scene이면 0이다 - 거기서는 사람이 나와야 한다. 다만 인물
    scene은 Character Consistency가 Imagen으로 돌리므로, 실제로 이
    함수가 의미를 갖는 것은 사물/풍경 scene이다.
    """

    if (scene or {}).get("character_scene"):
        return 0.0

    if PERSON_WORDS & _scene_words(scene):
        return 0.0

    if PERSON_WORDS & set(_words(_candidate_text(candidate))):
        return HUMAN_PENALTY

    return 0.0


def composition_score(candidate: dict) -> float:
    """세로 화면에 맞는가. 치수를 모르면 0."""

    width = candidate.get("width")
    height = candidate.get("height")

    if not width or not height:
        return 0.0

    return PORTRAIT_BONUS if height > width else 0.0


def motion_score(candidate: dict) -> float:
    """영상 후보의 길이가 쓸 만한가. 사진은 해당 없음."""

    if "video" not in (candidate.get("source") or ""):
        return 0.0

    duration = candidate.get("duration")

    if not duration:
        return 0.0

    low, high = USABLE_DURATION_SECONDS

    return MOTION_BONUS if low <= duration <= high else 0.0


def duplicate_penalty(candidate: dict, used) -> float:
    """이미 다른 scene이 쓴 자산인가."""

    if not used:
        return 0.0

    identity = candidate.get("source_url") or candidate.get("download_url")

    return DUPLICATE_PENALTY if identity and identity in used else 0.0


def score(candidate: dict, scene: dict, used=None) -> float:
    """후보 하나의 총점. 순수 함수입니다."""

    return (
        RELEVANCE_WEIGHT * relevance_score(candidate, scene)
        + composition_score(candidate)
        + motion_score(candidate)
        - human_penalty(candidate, scene)
        - duplicate_penalty(candidate, used)
    )


def rank(candidates: list, scene: dict, used=None) -> list:
    """
    점수가 높은 순서로 정렬한 새 리스트. 순수 함수입니다.

    동점이면 원래 순서를 지킨다(안정 정렬) - provider가 돌려준 순서에는
    그쪽의 관련도 판단이 담겨 있고, 우리가 가릴 근거가 없을 때 그것을
    뒤집을 이유가 없다.
    """

    return sorted(
        list(candidates or []),
        key=lambda candidate: score(candidate, scene, used),
        reverse=True,
    )
