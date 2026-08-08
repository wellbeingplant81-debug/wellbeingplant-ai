"""
Sprint154 - Gemini 채팅에 붙여넣을 요청문을 만든다 (Epic 57, Phase 5).

무료 모드의 대본은 붙여넣기로 온다(chat_import, Sprint104). 그런데
"무엇을 물어봐야 쓸 만한 답이 오는가"는 사람이 알아서 해야 했다.
잘못 물으면 답이 와도 파서가 못 읽고, 그러면 무료 경로가 거기서
막힌다.

새로 쓰지 않는다
----------------
엔진이 Gemini API에 보내는 그 프롬프트를 그대로 준다.

    app/prompts/script_prompt.py       SCRIPT_PROMPT
    app/prompts/viral_script_prompt.py VIRAL_SCRIPT_PROMPT

여기서 따로 쓰면 두 개의 규칙이 생긴다. 무료로 만든 대본만 다른
모양이 되고, 그 차이는 며칠 뒤에 자막이나 이미지 단계에서 드러난다.

같은 것을 물으니 같은 모양이 오고, 같은 모양이니 chat_import가 이미
읽는다. Sprint153에서 파일 경로를 지어내면 안 됐던 것과 같은 이야기다.

무엇을 고를 수 있는가
---------------------
    주제        반드시 있어야 한다. 없으면 물어볼 것이 없다
    영상 길이    엔진의 기본값과 같다
    Scene 개수   엔진의 기본값과 같다
    스타일       적었을 때만 덧붙는다
    타겟         적었을 때만 덧붙는다

스타일과 타겟은 엔진 템플릿에 없는 칸이라 뒤에 덧붙인다. 안 적은
것은 지어내지 않는다 - "전 연령 대상" 같은 말을 멋대로 넣으면 그것은
사용자가 하지 않은 말이고, 대본이 그쪽으로 끌려간다.

우리가 대신 물어봐 주지 않는다
------------------------------
이 자리는 요청문을 만들 뿐이다. 부르는 순간 돈이 들고, 그러면 무료
모드가 아니다. 모델 클라이언트를 import조차 하지 않는다 -
script_service는 모듈을 들이는 것만으로 Vertex 클라이언트를 만든다.
"""

# 받은 답을 어디에 두면 되는가. workspace 아래의 자리다.
#
# local_library에 새 종류를 만들지 않는다 - 아직 아무도 이 폴더를
# 훑지 않고, 훑지도 않을 것을 종류로 올리면 개수 표시가 거짓말을 한다.
SAVE_TO = "scripts/script.txt"


def _engine_defaults():
    """
    엔진이 Writer에게 요구하는 값. 여기서 새로 정하지 않는다.

    다르면 무료로 만든 대본만 길이가 어긋나고, 그것은 Duration Gate가
    걸릴 때에야 드러난다.

    늦게 들인다 - script_service는 모듈을 들이는 것만으로 Vertex
    클라이언트를 만들기 때문이다. 시그니처만 보면 되므로 그 비용을
    치를 이유가 없다.
    """

    import inspect

    from app.services import duration_estimator, script_service

    signature = inspect.signature(script_service.generate_script)

    return (
        signature.parameters["scene_count"].default,
        int(duration_estimator.TARGET_DURATION_SECONDS),
    )


try:
    DEFAULT_SCENE_COUNT, DEFAULT_TARGET_DURATION = _engine_defaults()
except Exception:  # pragma: no cover - 엔진을 못 읽는 환경
    DEFAULT_SCENE_COUNT, DEFAULT_TARGET_DURATION = 6, 45


def _extra(style: str, audience: str) -> str:
    """
    엔진 템플릿에 없는 칸. 적었을 때만 붙는다.

    맨 뒤에 둔다 - 앞의 규칙을 덮지 않고, 이번 영상에만 해당하는
    조건이라는 것이 읽는 순서로 드러난다.
    """

    lines = []

    if style and style.strip():
        lines.append(f"말투와 스타일\n{style.strip()}")

    if audience and audience.strip():
        lines.append(f"보는 사람\n{audience.strip()}")

    if not lines:
        return ""

    return (
        "\n\n===========================\n"
        "이번 영상의 추가 조건\n"
        "===========================\n\n"
        + "\n\n".join(lines)
        + "\n\n위 조건은 앞의 규칙을 어기지 않는 선에서 지킨다.\n"
    )


def how_to_use() -> str:
    """받은 답을 어떻게 하면 되는가. 한 줄로."""

    return (
        "Gemini 채팅창에 위 요청문을 붙여넣고, 돌아온 답 전체를 그대로 "
        f"복사해 아래 '가져오기' 칸에 붙여넣으십시오. "
        f"파일로 남기려면 내 자료 폴더의 {SAVE_TO} 에 저장하십시오."
    )


def build(topic: str, target_duration: int = None, scene_count: int = None,
          style: str = "", audience: str = "") -> dict:
    """
    붙여넣을 요청문을 만든다. 아무것도 부르지 않는다.

    돌려주는 것에는 무엇으로 만들었는지가 함께 들어 있다 - 화면이
    그것을 다시 계산하지 않아도 되게.
    """

    topic = (topic or "").strip()

    if not topic:
        raise ValueError("주제를 적어 주십시오. 무엇에 대한 영상인지 "
                         "없으면 물어볼 것이 없습니다.")

    scene_count = int(scene_count or DEFAULT_SCENE_COUNT)
    target_duration = int(target_duration or DEFAULT_TARGET_DURATION)

    # 엔진이 고르는 그대로 고른다. 플래그가 바뀌면 여기도 함께 바뀐다.
    from app import config
    from app.prompts.script_prompt import SCRIPT_PROMPT
    from app.prompts.viral_script_prompt import VIRAL_SCRIPT_PROMPT

    template = VIRAL_SCRIPT_PROMPT if config.ENABLE_VIRAL_WRITER \
        else SCRIPT_PROMPT

    prompt = template.substitute(
        topic=topic,
        target_duration=target_duration,
        scene_count=scene_count,
    ).strip()

    # 인물 일관성 규칙도 엔진이 붙일 때 같이 붙는다. 한쪽만 붙으면
    # 무료로 만든 대본에서 인물이 scene마다 달라진다.
    if config.ENABLE_CHARACTER_CONSISTENCY:
        from app.prompts.character_consistency_rules import with_character_rules

        prompt = with_character_rules(prompt)

    return {
        "topic": topic,
        "target_duration": target_duration,
        "scene_count": scene_count,
        "style": (style or "").strip(),
        "audience": (audience or "").strip(),
        "prompt": prompt + _extra(style, audience),
        "save_to": SAVE_TO,
        "how_to_use": how_to_use(),
    }
