"""
Sprint108 - 만들기 전에 무엇이 나올지 알려 준다 (Epic 54, Phase 7).

붙여넣은 대본으로 영상을 만들면 몇 초짜리가 되는지, scene과 이미지는
몇 개인지, 비용은 얼마인지를 생성 버튼을 누르기 전에 계산한다.

PV-03에서 27.7초짜리가 나온 것이 계기다. 목표는 45초인데 그렇게 된
이유는 Duration Gate가 step01 안에 있고, 붙여넣은 대본은 그 게이트를
거치지 않기 때문이다. 그것은 Sprint106의 설계대로다 - 사용자가 준
대본을 우리가 고치지 않는다. 다만 누르기 전에 알 수는 있어야 한다.

그래서 여기서 하는 일은 재는 것뿐이다.

    고치지 않는다. 늘리지 않는다. 요약하지 않는다. 다시 만들지 않는다.

경고만 하고, 만드는 것은 사용자가 정한다. 짧은 영상이 필요한 날도
있고, 우리가 그 판단을 대신할 근거가 없다.

새 계산도 만들지 않는다. Duration Gate가 쓰는 그 estimator와 그
상수를 그대로 부른다 - 두 곳이 다른 값을 내면 화면이 통과라고 한
대본이 게이트에서 걸리는 날이 온다. 그래서 이 파일에는 숫자가 하나도
없다.
"""

from app.services import duration_estimator, duration_gate

PASS = "pass"
WARN = "warn"


def _seconds_for(narration: str) -> float:
    return duration_estimator.estimate_duration(narration or "")


def _duration(scenes: list) -> dict:
    # estimator는 scene["narration"]을 대괄호로 꺼낸다 - 없으면
    # KeyError다. Resolver는 그것을 미리 막지만(Sprint106) 여기는
    # 저장 전 미리보기라서 아직 검증을 통과하지 않은 대본도 들어온다.
    # 입력은 건드리지 않고 재기용 복사본만 만든다.
    measurable = [
        {"narration": scene.get("narration") or ""} for scene in scenes
    ]

    total = duration_estimator.estimate_script_duration(measurable)

    minimum = duration_gate.MIN_ACCEPTABLE_SECONDS
    maximum = duration_gate.MAX_ACCEPTABLE_SECONDS

    return {
        "seconds": round(total, 2),
        "min_seconds": minimum,
        "max_seconds": maximum,
        "verdict": PASS if minimum <= total <= maximum else WARN,
    }


def _warnings(duration: dict) -> list:
    if duration["verdict"] == PASS:
        return []

    seconds = duration["seconds"]
    minimum = duration["min_seconds"]
    maximum = duration["max_seconds"]

    if seconds < minimum:
        shape = "권장보다 짧습니다"
        advice = (
            f"쇼츠 권장 길이는 {minimum:.0f}~{maximum:.0f}초입니다. "
            "문장을 더 넣으면 길어집니다."
        )
    else:
        shape = "권장보다 깁니다"
        advice = (
            f"쇼츠 권장 길이는 {minimum:.0f}~{maximum:.0f}초입니다. "
            "문장을 줄이면 짧아집니다."
        )

    return [
        f"예상 {seconds:.1f}초 - {shape}. "
        f"영상 생성은 가능하지만 {advice}"
    ]


def forecast(script: dict, registry=None) -> dict:
    """
    이 대본으로 만들면 무엇이 나오는지. 순수 읽기입니다.

    script는 손대지 않는다 - 읽기만 하고 아무것도 쓰지 않는다.
    """

    scenes = (script or {}).get("scenes") or []

    duration = _duration(scenes)

    return {
        "duration": duration,
        "scene_count": len(scenes),
        # 지금 엔진은 scene마다 이미지 하나를 쓴다.
        "image_count": len(scenes),
        "tts_characters": sum(len(s.get("narration") or "") for s in scenes),
        "scenes": [
            {
                "scene": scene.get("scene", index),
                "seconds": round(_seconds_for(scene.get("narration")), 2),
                "characters": len(scene.get("narration") or ""),
            }
            for index, scene in enumerate(scenes, start=1)
        ],
        "cost": _cost(registry).as_dict(),
        "warnings": _warnings(duration),
    }


def _cost(registry=None):
    """
    이 대본으로 만들 때의 예상 비용.

    대본 단계는 0이다 - 붙여넣은 것이라 우리가 API를 부르지 않았다.
    나머지는 Provider가 답하는 대로 담는다. 모르면 모른다고 남는다.
    """

    from app.production import production_modes, source_modes, stages
    from app.production.production_plan import ProductionPlan, StageSelection
    from app.production.providers import bootstrap
    from app.production.registry import StageProviderRegistry

    if registry is None:
        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

    plan = ProductionPlan(mode=production_modes.ASSISTED)

    # 대본은 받아 온 것, 나머지는 지금 엔진이 만든다.
    plan.select(StageSelection(
        stages.SCRIPT, source_modes.IMPORT, payload="(붙여넣음)",
    ))

    for stage in (stages.IMAGE, stages.VOICE, stages.METADATA):
        provider = registry.select(
            stage,
            production_modes.policy_for(
                production_modes.AUTO_STANDARD).quality_preference,
            source_modes.GENERATE,
        )
        if provider is not None:
            plan.select(StageSelection(
                stage, source_modes.GENERATE, provider=provider.name,
            ))

    return plan.estimate_cost(registry=registry)
