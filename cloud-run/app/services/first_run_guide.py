"""
Sprint183 - 처음 쓰는 사람의 여섯 걸음 (Epic 59, Phase 6).

Sprint180이 열 가지 상태를 만들었다. 그것은 우리에게 정확하지만,
처음 쓰는 사람에게는 낱말이 낯설다 - ASSET_REQUIRED가 무엇인지
모르는 사람에게 그 말은 아무것도 알려 주지 않는다.

그래서 여섯 걸음으로 다시 적는다.

    1. 프로그램 시작   켠 것이 첫 걸음이다
    2. 내 자료 연결    그림과 목소리가 든 폴더를 고른다
    3. 대본 준비       채팅창에서 받아 붙여넣는다
    4. 자료 확인       장면마다 그림과 목소리가 있는지 본다
    5. 제작 시작       영상을 만든다
    6. 결과 확인       나온 것을 본다

새로 판정하지 않는다
--------------------
어느 걸음까지 왔는지는 onboarding_state가 낸 답에서 나온다. 여기서
다시 세면 진행 표시와 안내 카드가 서로 다른 걸음을 가리킨다.

첫 걸음은 늘 끝나 있다
----------------------
이 화면을 보고 있다는 것이 그 증거다. 물어볼 것이 없다.

번호에 대하여
-------------
사양의 예문은 "자료 없음 → 1단계"라고 적었는데, 사양이 함께 준 목록은
'프로그램 시작'을 1번으로 둔다. 둘을 다 지킬 수는 없어서 목록을
따랐다 - 화면에 그려지는 여섯 줄과 번호가 어긋나면 사람이 헷갈린다.
그래서 자료가 없을 때는 2단계다.
"""

from app.services import onboarding_state

START = 1
WORKSPACE = 2
SCRIPT = 3
ASSETS = 4
RENDER = 5
RESULT = 6

# 걸음마다 무엇을 말할 것인가. 판정이 아니라 안내문이다.
STEPS = (
    (START, "프로그램 시작",
     "프로그램을 켜셨습니다. 여기서부터 시작합니다.",
     "이미 하셨습니다"),
    (WORKSPACE, "내 자료 연결",
     "그림과 목소리가 든 폴더를 고릅니다. 그 아래에 images 와 "
     "voices 폴더가 있어야 합니다.",
     "내 자료 폴더 선택"),
    (SCRIPT, "대본 준비",
     "Claude 또는 Gemini 채팅창에서 대본을 받아 붙여넣습니다. "
     "요청문은 화면이 만들어 드립니다.",
     "대본 붙여넣기"),
    (ASSETS, "자료 확인",
     "장면마다 쓸 그림과 목소리가 있는지 봅니다. 없으면 어느 "
     "장면인지 알려 드립니다.",
     "부족한 자료 보기"),
    (RENDER, "제작 시작",
     "막는 것이 없으면 영상을 만듭니다. 몇 분 걸립니다.",
     "영상 만들기"),
    (RESULT, "결과 확인",
     "만들어진 영상을 봅니다. 빠진 것이 있으면 어디인지 알려 드립니다.",
     "결과 보기"),
)


def _done(found: dict) -> dict:
    """
    어느 걸음까지 왔는가. onboarding_state가 낸 답에서만 나온다.

    파일이 있다는 것과 준비됐다는 것은 다르다 - 대본 파일이 있어도
    쓸 만하지 않으면 3걸음은 아직 끝나지 않았다.
    """

    step = {row["key"]: bool(row["done"])
            for row in (found.get("steps") or [])}

    state = found["state"]

    return {
        START: True,
        WORKSPACE: step.get("workspace", False),
        SCRIPT: (step.get("script", False)
                 and state != onboarding_state.SCRIPT_CHECK_REQUIRED),
        ASSETS: step.get("image", False) and step.get("voice", False),
        RENDER: step.get("video", False),
        RESULT: step.get("output", False),
    }


def _headline(current, found: dict) -> str:
    """
    사람이 읽는 한 줄.

    지금 몇 번째이고 무엇을 하면 되는지를 한 문장에 담는다. 상태
    이름(ASSET_REQUIRED 같은 것)은 쓰지 않는다 - 처음 쓰는 사람에게
    그 말은 아무것도 알려 주지 않는다.
    """

    if current is None:
        return "여섯 걸음을 모두 마치셨습니다. 결과를 확인해 보십시오."

    title, description = next(
        (row[1], row[2]) for row in STEPS if row[0] == current)

    return f"{current}단계입니다. {title} - {description}"


def build(store_path: str, project_path: str = None) -> dict:
    """
    처음 쓰는 사람에게 보여 줄 여섯 걸음. 읽기만 한다.

    상태는 onboarding_state가 낸 그대로다 - 여기서 다시 세면 진행
    표시와 안내 카드가 서로 다른 걸음을 가리킨다.
    """

    found = onboarding_state.build(store_path, project_path)
    done = _done(found)

    steps = [
        {"step": number, "title": title, "description": description,
         "action": action, "completed": done[number]}
        for number, title, description, action in STEPS
    ]

    current = next((row["step"] for row in steps if not row["completed"]),
                   None)

    return {
        "steps": steps,
        "current": current,
        "done": current is None,
        "headline": _headline(current, found),
        # 화면이 이어서 쓸 수 있게 상태도 함께 준다. 여기서 지은 것이
        # 아니라 onboarding_state가 낸 그대로다.
        "state": found["state"],
        "next_action": found["next_action"],
        "can_continue": found["can_continue"],
    }
