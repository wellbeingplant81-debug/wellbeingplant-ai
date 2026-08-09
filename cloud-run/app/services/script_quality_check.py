"""
Sprint179 - 붙여넣기 전에 읽어 본다 (Epic 59, Phase 2).

채팅창이 내놓은 대본이 파서를 통과해도, 영상으로 만들다 보면 뒤에서
걸리는 것들이 있다. 그때는 이미 몇 분을 쓴 뒤이고, 그 자리의 문장은
사람이 읽어도 무엇을 고쳐야 하는지 알 수 없다.

그래서 붙여넣기 전에 한 번 본다.

고쳐 주지 않는다
----------------
읽고 말하기만 한다. 우리가 대신 고치면 사람은 무엇이 잘못됐는지
영영 모르고, 다음에도 같은 자리에서 걸린다. 다시 써 주지도 않고,
모델을 부르지도 않는다.

읽는 일은 여기서 하지 않는다
-----------------------------
app.production 은 studio 라우터만 들인다(test_production_architecture).
이 저장소는 그 선을 이미 한 번 넘었다 - Sprint166의 completion_report가
같은 자리에서 걸렸다.

그래서 라우터가 파서에게 읽혀 보고, 읽힌 대본(또는 못 읽었다는 문장)을
여기로 넘긴다. 판정만 여기서 한다.

기준을 여기서 지어내지 않는다
-----------------------------
    읽히는가        파서가 읽어 본 결과를 받는다
    길이            duration_optimizer가 정한 관문
    그림 낱말       local_stock_provider._keywords
    인물 묘사       config.ENABLE_CHARACTER_CONSISTENCY

여기서 다른 숫자를 정하면 "여기서는 됐다는데 저기서 걸린다"가 된다.
그것은 검사가 없는 것보다 나쁘다 - 사람이 검사를 믿지 않게 된다.

말은 둘뿐이다
-------------
준비됨 / 수정 필요.

자료 준비 쪽의 READY/REVIEW/BLOCKED와 다른 낱말을 쓴다. 저쪽은
"파일이 있는가"이고 여기는 "글이 쓸 만한가"다. 같은 낱말을 쓰면
화면에서 두 상태가 섞인다.

무엇은 말하지 않는가
--------------------
Scene 개수가 엔진 기본값과 다르다는 것은 말하지 않는다. 사람이 다른
개수를 달라고 했을 수 있고, 그것은 잘못이 아니다. 개수가 정말 문제가
되는 경우(하나도 없거나, 길이가 관문 밖)는 아래에서 따로 걸린다.
"""

READY = "ready"
NEEDS_WORK = "needs_work"

LABELS = {READY: "준비됨", NEEDS_WORK: "수정 필요"}


def _empty(found: dict, reason: str) -> dict:
    return {
        "state": NEEDS_WORK,
        "reasons": [reason],
        "scene_count": 0,
        "estimated_seconds": 0.0,
        "voice_prompt_scenes": 0,
        **found,
    }


def _structure(script: dict) -> list:
    """있어야 할 것이 있는가."""

    from app import config

    wanted = ["title", "hook", "script"]

    # 인물 묘사를 요구할지는 엔진이 정한다. 여기서 always로 정하면
    # 그 플래그를 끈 사람의 멀쩡한 대본이 오늘부터 막힌다.
    if config.ENABLE_CHARACTER_CONSISTENCY:
        wanted.append("character")

    return [
        f"{name} 이(가) 비어 있습니다. 채팅창에 다시 물어보십시오."
        for name in wanted
        if not (script.get(name) or "").strip()
    ]


def _scenes(scenes: list) -> list:
    """Scene 하나하나. 몇 번째인지 함께 말한다."""

    from app.providers import local_stock_provider

    found = []
    narrations = {}
    images = {}

    for scene in scenes:
        number = scene.get("scene")
        narration = (scene.get("narration") or "").strip()
        image = (scene.get("image_prompt") or "").strip()

        if not narration:
            found.append(f"Scene {number}: 읽을 문장이 없습니다.")
        else:
            narrations.setdefault(narration, []).append(number)

        if not image:
            found.append(f"Scene {number}: 그림 묘사가 없습니다.")
        else:
            images.setdefault(image, []).append(number)

            # 낱말을 하나도 못 뽑으면 내 자료에서 아무것도 못 고른다.
            # 고르는 규칙을 여기서 새로 만들지 않는다.
            if not local_stock_provider._keywords(image):
                found.append(
                    f"Scene {number}: 그림 묘사에서 찾을 낱말을 뽑을 수 "
                    "없습니다. 무엇이 보이는지 적어 주십시오."
                )

    for narration, numbers in narrations.items():
        if len(numbers) > 1:
            found.append(
                f"Scene {', '.join(str(n) for n in numbers)}: 같은 문장을 "
                "읽습니다."
            )

    for image, numbers in images.items():
        if len(numbers) > 1:
            found.append(
                f"Scene {', '.join(str(n) for n in numbers)}: 그림 묘사가 "
                "같아 한 파일이 여러 장면에 걸립니다."
            )

    return found


def _length(scenes: list) -> tuple:
    """
    영상 길이가 관문 안에 들어올 수 있는가. (초, 할 말들).

    엔진은 마지막 scene에 정적을 조금 붙이거나 조금 빠르게 읽어
    맞춘다. 그것으로도 안 되는 경우만 말한다 - 고칠 수 있는 것을
    문제라고 하면 사람이 검사를 믿지 않게 된다.
    """

    from app.services import duration_estimator, duration_optimizer

    seconds = [duration_estimator.estimate_duration(
        (scene.get("narration") or "")) for scene in scenes]

    total = sum(seconds)

    if not seconds:
        return total, []

    # 늘려도 못 채우는가. 엔진이 붙일 수 있는 정적은 한 번뿐이다.
    if total + duration_optimizer.MAX_PAUSE_SECONDS \
            < duration_optimizer.MIN_ACCEPTABLE_SECONDS:
        return total, [
            f"전체가 약 {total:.0f}초로 너무 짧습니다. 목표는 "
            f"{duration_optimizer.TARGET_DURATION_SECONDS:.0f}초입니다. "
            "문장을 더 넣어 달라고 하십시오."
        ]

    # 줄여도 못 맞추는가. 엔진은 마지막 scene만 빠르게 읽는다.
    last = seconds[-1]
    removable = last - (last / duration_optimizer.MAX_SPEAKING_RATE)

    if total - removable > duration_optimizer.MAX_ACCEPTABLE_SECONDS:
        return total, [
            f"전체가 약 {total:.0f}초로 너무 깁니다. 목표는 "
            f"{duration_optimizer.TARGET_DURATION_SECONDS:.0f}초입니다. "
            "문장을 줄여 달라고 하십시오."
        ]

    return total, []


def check(script: dict = None, refused: str = None) -> dict:
    """
    읽힌 대본을 살펴본다. 아무것도 고치지 않는다.

    script    파서가 읽어 낸 것. 못 읽었으면 None
    refused   파서가 못 읽겠다고 한 문장

    파서의 문장을 그대로 옮긴다 - 우리가 다시 쓰면 두 개의 설명이
    생기고, 사람은 어느 쪽을 믿어야 할지 모른다.

    돌려주는 것에는 무엇을 보았는지가 함께 들어 있다 - 화면이 그것을
    다시 세지 않아도 되게.
    """

    if refused:
        return _empty({}, refused)

    if not script:
        return _empty({}, "붙여넣은 것이 없습니다.")

    scenes = script.get("scenes") or []
    reasons = _structure(script)

    if not scenes:
        reasons.append("Scene 이 하나도 없습니다.")

    reasons += _scenes(scenes)

    total, told = _length(scenes)
    reasons += told

    return {
        "state": NEEDS_WORK if reasons else READY,
        "reasons": reasons,
        "scene_count": len(scenes),
        "estimated_seconds": round(total, 1),
        "voice_prompt_scenes": sum(
            1 for scene in scenes
            if (scene.get("voice_prompt") or "").strip()
        ),
    }
