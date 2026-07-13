import json
import os

from app.services.duration_gate import generate_script_within_duration


def run(
    topic: str,
    project_path: str,
    target_duration=None,
    min_acceptable=None,
    max_acceptable=None,
    tts_provider=None,
):

    # Sprint53-4 - Duration Gate: TTS를 부르기 전에 narration 예상
    # 길이가 43~47초 범위인지 먼저 확인하고, 벗어나면 Writer를 다시
    # 호출한다(최대 3회). Duration Optimizer(Sprint53-2)는 이 게이트를
    # 통과한 대본의 미세한 오차만 다듬는다.
    #
    # Sprint94 - ProductionProfile Duration Target Activation:
    # target_duration/min_acceptable/max_acceptable이 주어지면 그대로
    # generate_script_within_duration()에 전달해 목표를 override한다.
    # 주어지지 않으면(기본값 None) 지금까지처럼 인자를 생략해 기존
    # 45/43/47 기본값과 완전히 동일하게 동작한다.
    gate_kwargs = {}
    if target_duration is not None:
        gate_kwargs["target_duration"] = target_duration
    if min_acceptable is not None:
        gate_kwargs["min_acceptable"] = min_acceptable
    if max_acceptable is not None:
        gate_kwargs["max_acceptable"] = max_acceptable
    # Sprint97 - Provider-Aware Calibration: tts_provider가 주어지면
    # Duration Gate가 그 provider에 맞는 chars_per_second를 쓰도록
    # 전달한다. 주어지지 않으면(기본값 None) 지금까지처럼 인자를 아예
    # 생략해 기존 Chirp 계수 기본값과 완전히 동일하게 동작한다.
    if tts_provider is not None:
        gate_kwargs["tts_provider"] = tts_provider

    gate_outcome = generate_script_within_duration(topic=topic, **gate_kwargs)

    result = gate_outcome["result"]
    data = result["data"]

    print("\n" + "=" * 80)
    print("STEP01 RESULT")
    print("=" * 80)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    log_line = (
        f"Duration Gate: passed={gate_outcome['passed']} "
        f"attempts={gate_outcome['attempts']} "
        f"estimated_seconds={gate_outcome['estimated_seconds']:.2f}"
    )

    # Sprint69-2 - 3회 재시도 모두 실패해 폴백했을 때, 목표 대비 얼마나
    # 부족/초과했는지 QA 로그에 명확히 남긴다.
    if not gate_outcome["passed"]:
        log_line += f" shortfall_seconds={gate_outcome['shortfall_seconds']:.2f}"

    print(log_line)
    print("=" * 80)

    with open(
        os.path.join(
            project_path,
            "script.json",
        ),
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4,
        )

    return data