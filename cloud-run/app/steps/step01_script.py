import json
import os

from app.services import provider_selection
from app.services.duration_gate import generate_script_within_duration


def _generate_script(topic: str, provider: str = None):
    """
    Sprint128 - 대본을 만드는 유일한 지점. 다른 Provider가 붙는다면
    여기 붙는다.

    current(=고르지 않음)는 None으로 오고 예전 경로를 그대로 탄다 -
    Writer, Duration Gate, Topic Fidelity, QA, Retry 전부.

    Sprint133 - "gemini"는 그 파이프라인 없이 모델을 직접 부르는
    쪽이다. 같은 gemini-2.5-pro를 부르더라도 거치는 것이 다르므로
    결과가 같지 않다. 둘을 같게 취급하면 지어내는 것이 된다.

    나머지 이름(claude·openai·deepseek)은 아직 비어 있어 거절한다.
    """

    provider_selection.require_wired("script", provider)

    if provider == provider_selection.GEMINI:
        # 늦게 부른다 - current로 만드는 사람이 이 모듈을 짊어질
        # 이유가 없다.
        from app.providers import gemini_script_provider

        return gemini_script_provider.script_outcome(topic)

    # Sprint53-4 - Duration Gate: TTS를 부르기 전에 narration 예상
    # 길이가 43~47초 범위인지 먼저 확인하고, 벗어나면 Writer를 다시
    # 호출한다(최대 3회). Duration Optimizer(Sprint53-2)는 이 게이트를
    # 통과한 대본의 미세한 오차만 다듬는다.
    return generate_script_within_duration(topic=topic)


def run(
    topic: str,
    project_path: str,
):

    # Sprint128 - 이 프로젝트가 어느 Provider로 만들기로 했는가.
    # 환경변수를 읽지 않는다 - project_path를 이미 받고 있으므로 그
    # 프로젝트의 결정을 읽는다. 스레드가 겹쳐도 서로 섞이지 않는다.
    #
    # 음성·이미지는 아래 서비스가 project_path를 받아서 거기서 읽었지만
    # (Sprint126·127), 대본은 그 아래로 project_path가 내려가지 않아
    # 읽는 자리가 여기다. 계약(인자 둘)은 그대로다.
    gate_outcome = _generate_script(
        topic, provider_selection.selected(project_path, "script"),
    )

    result = gate_outcome["result"]
    data = result["data"]

    print("\n" + "=" * 80)
    print("STEP01 RESULT")
    print("=" * 80)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    # Sprint133 - 어느 자리가 이 판정을 냈는가. 직접 호출 Provider는
    # 게이트를 거치지 않으므로 "Duration Gate"라고 적으면 로그가 사실이
    # 아닌 말을 한다. 기본값은 예전 그대로다.
    print(
        f"{gate_outcome.get('gate', 'Duration Gate')}: "
        f"passed={gate_outcome['passed']} "
        f"attempts={gate_outcome['attempts']} "
        f"estimated_seconds={gate_outcome['estimated_seconds']:.2f}"
    )

    # Sprint95 - 주제를 지켰는지. 게이트가 이미 판정한 결과를 그대로
    # 보여 준다 - 여기서 다시 계산하지 않는다.
    fidelity = gate_outcome.get("topic_fidelity") or {}
    print(
        f"Topic Fidelity: passed={fidelity.get('passed')} "
        f"title={fidelity.get('in_title')} "
        f"keywords={fidelity.get('keywords')}"
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