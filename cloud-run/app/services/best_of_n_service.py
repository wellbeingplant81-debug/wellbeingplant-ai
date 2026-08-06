"""
Sprint74 - Best-of-N Asset Selection Engine.

파이프라인은 Imagen이 그린 첫 장을 그대로 썼다. 그 장이 나쁘면 렌더가
끝나고 Gemini 평가가 나온 뒤에야 알게 되고, 거기서부터 재생성 사이클이
돈다 - 이미지 한 장, 전체 평가 한 번, 그리고 영상 전체 재렌더.

Best-of-N은 그 판단을 렌더 앞으로 당긴다. 후보를 N장 뽑고, 그 자리에서
Gemini Vision에게 고르게 하고, 고른 것으로 scene을 확정한다. 재생성은
그러고도 안 될 때만 돈다.

이득의 근거: 축적된 평가 53건에서 ai_image scene의 점수는 평균 78.9,
표준편차 24.2였고 20%가 재생성 권고를 받았다. Best-of-N이 버는 것은
전적으로 그 분산이다. 다만 그 표본은 스프린트마다 설정이 다른 실행을
섞은 것이라, 분산의 얼마가 "같은 프롬프트의 후보 사이" 것인지는
구분되지 않는다. 실제로 뽑아 봐야 아는 수치다.

이 모듈의 판단 부분은 순수 함수다. 무엇을 몇 장 뽑을지, 무엇을 고를지는
Imagen도 Gemini도 부르지 않고 검증된다.
"""

import os

from google import genai
from google.genai import types
from PIL import Image

from app.models.candidate_selection import CandidateSelection
from app.prompts.candidate_selection import CANDIDATE_SELECTION_RUBRIC
from app.services import image_service


MODEL_NAME = "gemini-2.5-pro"

# Imagen을 먼저 시도하는 scene만 후보 배정 대상이다. visual_type="real"은
# Pexels가 먼저이고 거기서 성공하면 Imagen을 아예 부르지 않으므로,
# 후보를 미리 배정해 둘 이유가 없다. Pexels가 실패해 Imagen으로 넘어온
# 경우는 후보 1장으로 처리한다 - 그 시점에는 이미 폴백 상황이다.
IMAGEN_FIRST_VISUAL_TYPE = "ai"


client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def plan_candidates(scenes, default_n: int, budget: int) -> dict:
    """
    scene별 후보 장수를 미리 정한다. 순수 함수입니다.

    integrate_asset은 scene마다 스레드 3개로 병렬 실행된다. 거기서 공유
    카운터를 깎으면 경쟁 상태가 되고, 같은 입력이 실행마다 다른 결과를
    낸다. 그래서 배분은 팬아웃 이전에 여기서 끝낸다.

    예산은 후보 이미지의 총량이고, scene 번호 순서로 쓴다. 앞 scene이
    뒤 scene보다 중요하다는 근거가 있어서가 아니라, 순서가 정해져 있어야
    같은 입력이 같은 배분을 내기 때문이다. hook(scene 1)이 앞에 오는
    것은 부수적으로 맞는 방향이기도 하다.

    어떤 scene도 0장을 받지 않는다 - 예산이 바닥나도 그렇다. 예산은
    "후보를 더 뽑을지"를 정하는 것이지 "그릴지"를 정하는 것이 아니다.
    0장은 scene에 그림이 없다는 뜻이고, 그것은 예산 문제가 아니라
    파이프라인 고장이다.
    """

    plan = {}
    remaining = budget

    # 첫 장은 어느 scene이든 그려야 한다. 예산에서 빼기는 하되,
    # 모자란다고 거르지는 않는다.
    for scene in scenes:
        plan[scene["scene"]] = 1

        if scene.get("visual_type") == IMAGEN_FIRST_VISUAL_TYPE:
            remaining -= 1

    for scene in scenes:
        if scene.get("visual_type") != IMAGEN_FIRST_VISUAL_TYPE:
            continue

        extra = min(max(default_n - 1, 0), max(remaining, 0))
        plan[scene["scene"]] += extra
        remaining -= extra

    return plan


def _total(score) -> tuple:
    """정렬 키. 실격 여부가 점수보다 앞선다."""

    return (
        0 if score.unrequested_person else 1,
        score.prompt_fidelity + score.character_match + score.composition,
    )


def winning_index(selection, candidate_count: int = None) -> int:
    """
    어느 후보를 쓸지. 순수 함수입니다.

    Gemini가 적어 준 best_candidate를 그대로 믿지 않고 점수에서 다시
    고른다. 구조화된 숫자는 검증할 수 있지만 자유 서술은 그렇지 않고,
    둘이 어긋나는 경우가 실제로 있다.

    프롬프트가 요구하지 않은 사람이 들어간 후보는 다른 점수와 무관하게
    뒤로 밀린다 - Sprint73 실측에서 그런 그림 한 장이 영상 전체의
    character_consistency를 95에서 20으로 떨어뜨렸다. 다만 전부 실격
    이어도 하나는 고른다. 그림이 없을 수는 없고, 나머지는 재생성
    엔진이 맡는다.
    """

    scores = list(selection.candidates)

    if not scores:
        return 0

    best = max(scores, key=_total)
    index = best.candidate

    if candidate_count is None:
        candidate_count = len(scores)

    if not 0 <= index < candidate_count:
        return 0

    return index


def _candidate_paths(staging_path: str, count: int) -> list:
    return [f"{staging_path}.cand{index}" for index in range(count)]


def generate_candidates(image_prompt, staging_path, count, channel,
                        is_hook_scene, image_style,
                        elements=None) -> list:
    """
    후보를 뽑는다. 반환값은 실제로 만들어진 파일 경로들.

    count == 1이면 기존 generate_image를 그대로 부른다. 플래그가 꺼진
    상태에서 동작이 한 바이트도 달라지지 않아야 하고, 후보가 하나면
    고를 것도 없다.

    여러 장일 때는 Imagen에 한 번만 요청한다. N번 따로 부르면 왕복이
    N배가 되는데, Imagen은 한 요청에 여러 장을 돌려준다.
    """

    if count <= 1:
        return [
            image_service.generate_image(
                image_prompt,
                staging_path,
                channel=channel,
                is_hook_scene=is_hook_scene,
                image_style=image_style,
                elements=elements,
            )
        ]

    paths = image_service.generate_image_candidates(
        image_prompt,
        _candidate_paths(staging_path, count),
        channel=channel,
        is_hook_scene=is_hook_scene,
        image_style=image_style,
        elements=elements,
    )

    if not paths:
        raise Exception("Imagen이 후보 이미지를 하나도 생성하지 않았습니다.")

    return paths


def _ask_gemini(candidate_paths: list, scene: dict):
    """Gemini Vision에게 후보를 보여 주고 고르게 한다."""

    images = [Image.open(path) for path in candidate_paths]

    context = (
        f"프롬프트: {scene.get('image_prompt', '')}\n"
        f"후보 수: {len(candidate_paths)}"
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[CANDIDATE_SELECTION_RUBRIC, context] + images,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CandidateSelection,
        ),
    )

    if response.parsed is None:
        raise ValueError("Gemini가 후보 선택 응답을 돌려주지 않았습니다.")

    return response.parsed


def select_best(candidate_paths: list, scene: dict):
    """
    후보 중 하나를 고른다. 반환값: (index, selection or None).

    후보가 하나면 Gemini를 부르지 않는다 - 고를 것이 없는데 호출할
    이유가 없다.

    고르기가 실패하면 첫 후보를 쓴다. Best-of-N은 개선 장치이지 필수
    경로가 아니므로, Gemini가 죽었다고 영상을 버리지 않는다. 예전과
    똑같이 첫 장을 쓰면 된다.
    """

    if len(candidate_paths) <= 1:
        return 0, None

    try:
        selection = _ask_gemini(candidate_paths, scene)
    except Exception as exc:
        print(
            f"[BestOfN] scene {scene.get('scene')} 후보 선택 실패, "
            f"첫 후보를 사용합니다: {exc}"
        )
        return 0, None

    return winning_index(selection, len(candidate_paths)), selection


def discard_losers(candidate_paths: list, winner: int) -> None:
    """고르지 않은 후보를 지운다. 없으면 조용히 넘어간다."""

    for index, path in enumerate(candidate_paths):
        if index == winner:
            continue
        try:
            os.remove(path)
        except OSError:
            pass
