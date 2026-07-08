import json
import os

from app.services.duration_gate import generate_script_within_duration


def run(
    topic: str,
    project_path: str,
):

    # Sprint53-4 - Duration Gate: TTS를 부르기 전에 narration 예상
    # 길이가 43~47초 범위인지 먼저 확인하고, 벗어나면 Writer를 다시
    # 호출한다(최대 3회). Duration Optimizer(Sprint53-2)는 이 게이트를
    # 통과한 대본의 미세한 오차만 다듬는다.
    gate_outcome = generate_script_within_duration(topic=topic)

    result = gate_outcome["result"]
    data = result["data"]

    print("\n" + "=" * 80)
    print("STEP01 RESULT")
    print("=" * 80)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(
        f"Duration Gate: passed={gate_outcome['passed']} "
        f"attempts={gate_outcome['attempts']} "
        f"estimated_seconds={gate_outcome['estimated_seconds']:.2f}"
    )
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