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
#
# Sprint227 - 이 창은 이제 **이 scene이 몇 초인지 모를 때만** 쓴다.
# 아래 motion_score를 볼 것.
USABLE_DURATION_SECONDS = (3, 30)

# 되풀이해야 겨우 덮는 영상. 덮기는 덮으므로 0은 아니고, 한 번에 덮는
# 것과 같지도 않다.
MOTION_LOOP_BONUS = MOTION_BONUS * 0.5

PERSON_WORDS = {
    "man", "men", "woman", "women", "person", "people", "boy", "girl",
    "male", "female", "lady", "guy", "couple", "family", "child",
    "children", "kid", "adult", "senior", "elderly", "model", "portrait",
    "hand", "hands", "face", "smiling", "selfie",
}


def _slug_of(url: str) -> str:
    """주소의 끝 조각을 말로. 확장자는 뗀다."""

    if not url:
        return ""

    parts = [part for part in str(url).split("?")[0].rstrip("/").split("/")
             if part]

    if not parts:
        return ""

    stem = parts[-1]

    if "." in stem:
        stem = stem.rsplit(".", 1)[0]

    return stem.replace("-", " ").replace("_", " ")


def _candidate_text(candidate: dict) -> str:
    """후보에 대해 우리가 아는 말 전부.

    alt는 Pexels 사진 응답의 설명이고, 슬러그는 url에 들어 있다. 비디오
    응답에는 alt가 없어 슬러그가 유일한 단서다.

    Sprint233 - 영상은 미리보기 그림의 파일 이름도 읽는다
    -----------------------------------------------------
    실측한 것(표본 75, 2026-08-19): 사진은 alt 13낱말 + 슬러그 7낱말쯤을
    들고 오는데 영상은 슬러그 6낱말이 전부였다. tags 칸이 응답에 있긴
    하지만 30개 중 30개가 비어 있었고, user.name 은 찍은 사람의 이름이라
    내용과 상관이 없다.

    남은 것이 미리보기 주소의 파일 이름이었다. 그 이름에 url 과 **다른**
    슬러그가 들어 있는 경우가 있다.

        url   .../video/a-woman-stretching-5510121/
        image .../videos/5510121/coaching-crossfit-training-fast-workout-
              at-home-fitness-5510121.jpeg

    75개 중 27개(36%)가 이렇게 새 낱말을 얻고 나머지는 pexels-photo 같은
    껍데기라 아무것도 늘지 않는다.

    영상에게 점수를 얹는 것이 아니다. 사진이 이미 두 자리에서 말을
    가져오는데 영상만 한 자리에서 가져오던 것을, 있는 자리를 마저 읽어
    같은 조건으로 맞추는 것이다.

    이 칸이 없는 후보(사진 · 옛 기록)는 예전과 한 글자도 다르지 않다.
    """

    alt = candidate.get("alt") or ""
    slug = _slug_of(candidate.get("source_url"))
    preview = _slug_of(candidate.get("preview_url"))

    return " ".join(part for part in (alt, slug, preview) if part).strip()


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


def needed_seconds(scene: dict):
    """
    이 scene을 채우려면 몇 초가 필요한가. 모르면 None.

    Sprint227 - 고를 때는 아직 소리가 없다
    --------------------------------------
    scene의 진짜 길이는 나레이션 오디오가 정한다(scene_timeline). 그런데
    자산을 고르는 것은 step02이고 소리는 step03에서 나온다 - 고르는
    시점에는 잴 것이 없다.

    그래서 대본으로 미리 센다. duration_estimator가 TTS를 부르지 않고
    글자 수와 문장 사이 쉼으로 예상 길이를 내는 그 함수이고, Duration
    Gate가 이미 그 값으로 대본을 되돌린다 - 새 기준을 만들지 않는다.

    나레이션이 없으면 None이다. 지어내지 않는다.
    """

    if not scene:
        return None

    narration = (scene.get("narration") or "").strip()

    if not narration:
        return None

    from app.services.duration_estimator import estimate_duration

    seconds = estimate_duration(narration)

    return seconds if seconds > 0 else None


def motion_score(candidate: dict, scene: dict = None) -> float:
    """
    이 영상이 이 scene을 채울 수 있는가. 사진은 해당 없음.

    Sprint227 - 길수록 좋은 것이 아니다
    -----------------------------------
    6초짜리와 20초짜리가 5초 scene을 채우는 데는 아무 차이가 없다 -
    둘 다 앞에서 잘라 쓰고 남는 것은 버린다. 그래서 "덮는다"에서 점수가
    멈춘다. 길이 자체에 점수를 주면 쓰지도 않을 15초를 이유로 더 맞는
    영상을 밀어낸다.

    판정을 여기서 새로 짜지 않는다
    ------------------------------
    그 영상이 실제로 어떻게 쓰일지는 footage.plan이 정한다(Sprint223).
    같은 함수에게 묻는다 - 여기서 따로 셈하면 점수와 실제 결과가 어느
    날 서로 다른 말을 한다.

        trim   이 scene을 한 번에 덮는다
        loop   되풀이해야 덮는다
        hold   마지막 프레임을 붙잡는다 = 사실상 정지 사진

    scene을 모르면 예전 그대로다 - 넓은 창(USABLE_DURATION_SECONDS)으로
    본다. 기존 호출부(인자 하나로 부르는 자리)가 그 길이다.
    """

    if "video" not in (candidate.get("source") or ""):
        return 0.0

    duration = candidate.get("duration")

    if not duration:
        return 0.0

    needed = needed_seconds(scene)

    if needed is None:
        low, high = USABLE_DURATION_SECONDS

        return MOTION_BONUS if low <= duration <= high else 0.0

    # 늦게 들인다 - 이 모듈은 순수 계산만 하는 자리이고, footage는
    # 영상을 여는 무거운 것을 들고 있다.
    from app.services import footage

    try:
        how = footage.plan(duration, needed)
    except ValueError:
        # 잴 수 없는 길이. 지어내지 않는다.
        return 0.0

    if how["mode"] == footage.TRIM:
        return MOTION_BONUS

    if how["mode"] == footage.LOOP:
        return MOTION_LOOP_BONUS

    return 0.0


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
        + motion_score(candidate, scene)
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
