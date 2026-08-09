"""
Sprint178 - 어느 채팅창에 물어볼 것인가 (Epic 59, Phase 1).

무료 대본은 붙여넣기로 온다(chat_import, Sprint104). Sprint154가
"무엇을 물어야 하는가"를 만들어 줬는데, 그 요청문은 Gemini 하나만
보고 있었다. 다른 채팅창을 쓰는 사람은 그 글을 제 손으로 고쳐야 했다.

이 층이 하는 일은 하나다
------------------------
"어느 채팅창에 넣을 글인가"를 정하는 것.

부르지 않는다. 우리가 대신 물어봐 주는 순간 돈이 들고, 그러면 무료
모드가 아니다. 모델 클라이언트를 들이지도 않는다.

app/providers/claude_script_provider.py 와 다른 자리다
------------------------------------------------------
그쪽은 Claude API를 실제로 부르는 엔진의 자리다. 여기는 사람이 제
손으로 붙여넣을 글을 만드는 자리다. 이름이 비슷해 헷갈리기 쉬워
적어 둔다.

셋을 어떻게 다르게 대하는가
---------------------------
    gemini_chat   Sprint154 그대로. 한 글자도 바꾸지 않는다
    claude_chat   같은 엔진 템플릿 위에 "이 모양으로 내놓아라"를 얹는다
    manual        물어볼 채팅창이 없다. 요청문도 없다

둘째가 조심스럽다. 여기서 요청문을 새로 쓰면 규칙이 두 벌이 되고,
Claude로 만든 대본만 다른 모양이 된다 - 그 어긋남은 며칠 뒤 자막이나
이미지 단계에서 드러난다. 그래서 엔진 템플릿을 그대로 두고 뒤에만
붙인다.

아무것도 저장하지 않는다
------------------------
로그인 정보도, 키도, 대본도, 채팅 내용도 남기지 않는다. 이 층은
글자를 만들어 돌려줄 뿐이다.
"""

CLAUDE = "claude_chat"
GEMINI = "gemini_chat"
MANUAL = "manual"

PROVIDERS = (CLAUDE, GEMINI, MANUAL)

# 고르지 않으면 예전 그대로다. 묶어 보낸 프로그램에는 고르는 칸이
# 없는 예전 화면이 들어 있을 수 있다.
DEFAULT = GEMINI

LABELS = {
    CLAUDE: "Claude 채팅",
    GEMINI: "Gemini 채팅",
    MANUAL: "직접 입력",
}

# 그 채팅창의 이름. 안내 문장이 이것을 쓴다.
WINDOWS = {CLAUDE: "Claude", GEMINI: "Gemini"}

# Claude에게 덧붙이는 것. 엔진 템플릿을 덮지 않고 맨 뒤에 둔다.
#
# 왜 따로 적는가: 엔진 템플릿은 Gemini에게 오래 쓰여 온 글이라 그
# 모델이 알아서 내주는 모양이 있다. 다른 창에서는 그 모양이 보장되지
# 않으므로, 무엇을 내놓아야 파서가 읽는지 여기서 못 박는다.
CLAUDE_OUTPUT = """

===========================
답을 내놓는 모양
===========================

설명 없이 아래 JSON 하나만 내놓으십시오. 코드 펜스는 있어도 됩니다.

{
  "title": "영상 제목",
  "hook": "첫 3초에 붙잡는 한 문장",
  "script": "전체 대본",
  "character": "등장 인물 묘사(영상 내내 같은 사람이어야 합니다)",
  "scenes": [
    {
      "narration": "이 장면에서 읽을 문장",
      "image_prompt": "이 장면의 그림을 묘사하는 말",
      "voice_prompt": "이 문장을 어떤 목소리로 읽을지"
    }
  ]
}

scenes 는 위에서 정한 개수만큼 넣으십시오.
"""


def require(name: str) -> str:
    """
    아는 이름인가. 비어 있으면 예전 방식으로 본다.

    모르는 이름을 그냥 넘기면 사람은 요청문을 받아 들고 왜 이상한지
    모른다.
    """

    name = (name or "").strip() or DEFAULT

    if name not in PROVIDERS:
        raise ValueError(
            f"모르는 대본 생성 방식입니다: {name}. "
            f"고를 수 있는 것: {', '.join(PROVIDERS)}"
        )

    return name


def label(name: str) -> str:
    """사람이 화면에서 읽는 이름."""

    return LABELS[require(name)]


def _manual() -> dict:
    """
    직접 쓰는 사람에게는 물어볼 창이 없다.

    빈 요청문을 만들어 주지 않는다 - 만들어 주면 사람은 그것을
    어딘가에 붙여넣으려 한다.
    """

    from app.services import script_prompt_builder

    return {
        "provider": MANUAL,
        "prompt": None,
        "save_to": script_prompt_builder.SAVE_TO,
        "how_to_use": (
            "script.json 을 직접 작성하거나, 이미 가지고 있는 대본을 "
            "아래 칸에 붙여넣고 '가져오기'를 누르십시오."
        ),
    }


def build(provider: str = None, topic: str = "", target_duration: int = None,
          scene_count: int = None, style: str = "",
          audience: str = "") -> dict:
    """
    그 채팅창에 붙여넣을 요청문. 아무것도 부르지 않는다.

    돌려주는 것에는 어느 방식이었는지가 함께 들어 있다 - 화면이
    그것을 다시 계산하지 않아도 되게.
    """

    provider = require(provider)

    if provider == MANUAL:
        return _manual()

    from app.services import script_prompt_builder

    found = script_prompt_builder.build(
        topic,
        target_duration=target_duration,
        scene_count=scene_count,
        style=style,
        audience=audience,
        window=WINDOWS[provider],
    )

    if provider == CLAUDE:
        found["prompt"] = found["prompt"] + CLAUDE_OUTPUT

    found["provider"] = provider

    return found
