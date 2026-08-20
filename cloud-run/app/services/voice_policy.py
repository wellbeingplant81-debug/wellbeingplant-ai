"""
Sprint244 - 고르지 않은 유료 목소리는 부르지 않는다.

왜 이것이 필요했나
------------------
새 EXE 로 영상을 만들 때 나레이션이 Google 로 나갔다. 아무도 화면에서
Google 을 고른 적이 없다. .env 의 TTS_PROVIDER=google 한 줄이 그것을
정하고 있었다.

    scene_tts_service   프로젝트의 선택을 읽는다 -> 안 골랐으면 None
    tts_provider        provider or os.getenv("TTS_PROVIDER", "google")
    google_tts_provider 유료 호출

"고르지 않았다"가 "가장 비싼 것으로 간다"가 되어 있었다. 반대여야
한다.

왜 media_policy 를 늘리지 않았나
--------------------------------
그쪽은 그림의 축이다 - 내 자료 / 스톡 / AI 를 어떤 차례로 쓸지 다섯
가지로 나눈다. 목소리에는 스톡이 없고 차례라는 것도 없다. 물음이
하나뿐이다.

    돈을 써도 되는가

축이 다른 것을 한 모듈에 담으면 한쪽을 바꿀 때 다른 쪽이 조용히
따라 바뀐다. 이 저장소가 visual_type 하나로 라우팅과 스타일을 함께
지고 있다가 겪은 일이 그것이다(Sprint71).

대신 **상태 어휘는 가져다 쓴다**. 화면이 두 벌의 낱말을 배우게 하지
않는다.

관문은 어디에 있나
------------------
여기가 아니라 유료 Provider 자신의 문 앞이다.

    google_tts_provider.generate_voice
    elevenlabs_provider.generate_voice

tts_provider.generate_voice 에 두지 않는 이유는 무료인 local_voice 도
그 함수를 지나기 때문이다. Sprint241 이 _ai_result 에 관문을 세워
85 개를 깨뜨린 것과 같은 모양이 된다.
"""

import json
import os

# 상태 어휘는 그림 쪽이 이미 정해 두었다. 여기서 새로 짓지 않는다 -
# 화면이 같은 뜻의 낱말 두 벌을 배우게 하면 언젠가 갈라진다.
from app.services.media_policy import (  # noqa: F401
    AVAILABLE,
    DISABLED,
    NOT_CONFIGURED,
    NOT_IMPLEMENTED,
    STATES,
)

# 돈이 나가지 않는다. 사람이 녹음해 둔 것을 쓰거나, 아무것도 하지
# 않는다.
MODE_FREE_ONLY = "free_only"

# 사람이 화면에서 고른 그 하나만 쓴다. "유료 전부 열림"이 아니다.
MODE_PAID_OK = "paid_ok"

MODES = (MODE_FREE_ONLY, MODE_PAID_OK)

LABELS = {
    MODE_FREE_ONLY: "유료 음성 사용 안 함",
    MODE_PAID_OK: "고른 유료 음성만 사용",
}

# 가장 안전한 쪽이 기본값이다. 모르면 돈을 쓰지 않는다.
DEFAULT_MODE = MODE_FREE_ONLY

# project.json 의 한 칸. 새 저장소를 만들지 않는다 - provider_selection
# 이 이미 그 파일에 산다.
PROJECT_FIELD = "voice_policy"

# 전역 기본값. 프로젝트가 정하지 않았을 때만 본다.
STORE_FILENAME = "voice_policy.json"

GOOGLE = "google"
ELEVENLABS = "elevenlabs"

# 부르면 돈이 나가는 것들. provider_selection 은 반대편(무료)을 들고
# 있고, 두 쪽이 갈리지 않는 것은 시험이 잠근다.
PAID_PROVIDERS = (GOOGLE, ELEVENLABS)

PROVIDER_LABELS = {
    GOOGLE: "Google TTS",
    ELEVENLABS: "ElevenLabs",
    # 이름은 tts_provider 가 소유한다. 사람에게 보일 말만 여기 있다.
    "local_voice": "내 PC 음성",
}

# 그 Provider 를 쓰려면 환경에 있어야 하는 것. 없으면 NOT_CONFIGURED 다.
#
# Google 은 빈 칸이다. 열쇠를 환경변수 하나로 재지 않는다 - 그쪽은
# Imagen 과 같은 주변 자격증명으로 붙고, 그것이 있는지는 실제로 불러
# 보기 전에는 알 수 없다. GOOGLE_APPLICATION_CREDENTIALS 가 없다고
# NOT_CONFIGURED 라고 적으면 실제로는 되는 것을 안 된다고 말하게 된다
# (이 PC 에서 그 변수 없이 잘 돌았다).
#
# media_policy 도 현재 엔진에 같은 판단을 한다 - 키를 모르는 것은
# key=None 으로 두고 AVAILABLE 로 둔다.
PROVIDER_KEYS = {
    GOOGLE: "",
    ELEVENLABS: "ELEVENLABS_API_KEY",
}


class PaidVoiceNotAllowed(Exception):
    """
    이 프로젝트는 그 유료 목소리를 쓰지 않기로 했다.

    고장이 아니다. 부르는 쪽이 이것을 보고 사람에게 무엇을 고르면
    되는지 알려야 한다 - 조용히 다른 유료 Provider 로 넘어가면 그때
    부터 돈이 든다.
    """


# -- 전역 기본값 ----------------------------------------------------
def default_store_path() -> str:
    from app import runtime_paths

    return os.path.join(runtime_paths.home(), STORE_FILENAME)


def current_mode() -> str:
    """
    아무도 정하지 않았을 때 따르는 것.

    파일이 없거나 망가져 있으면 기본값이다. "읽을 수 없으니 일단
    열어 둔다" 는 예외를 만들지 않는다.
    """

    try:
        with open(default_store_path(), encoding="utf-8") as f:
            saved = json.load(f).get("mode")
    except Exception:
        return DEFAULT_MODE

    return saved if saved in MODES else DEFAULT_MODE


def remember_default(mode: str) -> str:
    """다음 프로젝트부터 이것으로 시작한다."""

    mode = require_mode(mode)

    path = default_store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump({"mode": mode}, f, ensure_ascii=False, indent=4)

    return mode


# -- 프로젝트의 결정 ------------------------------------------------
def require_mode(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(
            f"알 수 없는 음성 정책입니다: {mode!r}. "
            f"사용 가능한 값: {list(MODES)}"
        )

    return mode


def _project_file(project_path):
    from app.services import provider_selection

    return os.path.join(project_path, provider_selection.PROJECT_FILENAME)


def mode_for(project_path) -> str:
    """
    이 프로젝트가 정한 것. 정하지 않았으면 전역 기본값.

    적힌 값이 우리가 아는 것이 아니면 기본값으로 접는다 - 오타 하나가
    유료를 여는 일은 없어야 한다.
    """

    if not project_path:
        return current_mode()

    try:
        with open(_project_file(project_path), encoding="utf-8") as f:
            saved = json.load(f).get(PROJECT_FIELD)
    except Exception:
        return current_mode()

    return saved if saved in MODES else current_mode()


def choose(project_path, mode: str) -> str:
    """
    사람이 고른 것을 프로젝트에 적는다. 나머지 칸은 건드리지 않는다.

    project.json 에는 topic·channel·*_provider 가 함께 산다 - 통째로
    덮어쓰면 안 된다.
    """

    mode = require_mode(mode)

    path = _project_file(project_path)

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    if not isinstance(data, dict):
        data = {}

    data[PROJECT_FIELD] = mode

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return mode


def paid_allowed(mode: str) -> bool:
    return mode == MODE_PAID_OK


# -- 관문 -----------------------------------------------------------
def project_of(output_file):
    """
    적을 파일이 어느 프로젝트의 것인가.

    그림 쪽에도 같은 걸음이 있다. 합치지 않는다 - 그 모듈은 자기가
    Provider 계층을 알지 않는다는 것을 시험으로 잠가 두었고
    (test_image_provider_bridge), 여기서 부르는 provider_selection 을
    그쪽이 알게 되는 순간 그 잠금이 깨진다.

    열 줄을 두 번 적는 편이 계층을 무너뜨리는 것보다 싸다.
    """

    where = os.path.dirname(os.path.abspath(str(output_file or "")))

    for _ in range(10):
        if os.path.isfile(os.path.join(where, "project.json")):
            return where

        parent = os.path.dirname(where)

        if parent == where:
            break

        where = parent

    return None


def default_provider() -> str:
    """
    아무도 고르지 않았을 때 누가 만드는가.

    예전에는 TTS_PROVIDER 였고 그 기본값이 google 이었다. 즉 고르지
    않은 사람이 가장 비싼 길로 갔다.

    환경변수를 아예 무시하지는 않는다 - 돈이 들지 않는 것을 가리키면
    그대로 따른다. 유료를 가리키면 따르지 않는다. 유료를 고르는 자리는
    화면이지 .env 한 줄이 아니다.
    """

    from app.services import provider_selection

    wanted = (os.getenv("TTS_PROVIDER") or "").strip().lower()

    if wanted and not provider_selection.calls_api("voice", wanted):
        return wanted

    return provider_selection.LOCAL_VOICE


def require_allowed(output_file, provider: str) -> None:
    """
    돈이 나가기 직전의 마지막 문.

    두 가지를 본다.

        1. 이 프로젝트가 유료를 쓰기로 했는가
        2. 그 사람이 고른 것이 **바로 이것**인가

    둘째가 없으면 "유료 허용" 한 번이 모든 유료 Provider 를 여는 열쇠가
    된다. 그러면 Google 을 고른 사람이 ElevenLabs 요금을 받을 수 있다.
    """

    if provider not in PAID_PROVIDERS:
        return

    project = project_of(output_file)
    mode = mode_for(project)

    label = PROVIDER_LABELS.get(provider, provider)

    if not paid_allowed(mode):
        raise PaidVoiceNotAllowed(
            f"이 프로젝트는 유료 음성을 쓰지 않기로 되어 있어 "
            f"{label} 을(를) 부르지 않았습니다. 쓰시려면 화면에서 "
            f"{label} 을(를) 고르고 유료 음성을 허용해 주십시오."
        )

    from app.services import provider_selection

    chosen = provider_selection.selected(project, "voice") if project else None

    if chosen != provider:
        raise PaidVoiceNotAllowed(
            f"{label} 은(는) 이 프로젝트에서 고른 음성이 아니라 "
            f"부르지 않았습니다. 쓰시려면 화면에서 {label} 을(를) "
            f"고르십시오."
        )


# -- 화면에 보여 줄 것 ----------------------------------------------
def provider_states(mode: str = None, project_path=None) -> dict:
    """
    지금 고를 수 있는 것이 무엇인가.

    없는 것을 있다고 하지 않는다. 유료를 쓰지 않기로 한 모드에서는
    유료 쪽이 전부 DISABLED 다 - 고를 수 있는 것처럼 보이면 사람은
    눌러 보고 왜 안 되는지 모른 채 시간을 버린다.
    """

    from app.providers import tts_provider
    from app.services import provider_selection

    mode = mode if mode in MODES else current_mode()
    off = not paid_allowed(mode)

    found = {}

    for name in tts_provider.PROVIDERS:
        paid = provider_selection.calls_api("voice", name)
        key = PROVIDER_KEYS.get(name, "")

        if not paid:
            state = AVAILABLE
        elif off:
            state = DISABLED
        elif key and not os.environ.get(key, "").strip():
            state = NOT_CONFIGURED
        else:
            state = AVAILABLE

        found[name] = {
            "label": PROVIDER_LABELS.get(name, name),
            "state": state,
            "paid": paid,
            # 단가를 모른다. 지어내지 않는다.
            "cost": None,
            "needs": key if paid else "",
        }

    return found


def plan_for(mode: str, scene_count: int = 0, project_path=None) -> dict:
    """
    제작 전에 사람에게 보여 줄 것. 금액은 모른다고 적는다.

    scene 하나에 음성 하나다. 이쪽은 그림과 달리 스톡으로 대체되는
    일이 없어서 **최대**가 아니라 그 수 그대로다.
    """

    from app.services import provider_selection

    mode = mode if mode in MODES else current_mode()
    scenes = max(0, int(scene_count or 0))

    chosen = (provider_selection.selected(project_path, "voice")
              if project_path else None)

    if chosen is None:
        chosen = default_provider()

    paid = provider_selection.calls_api("voice", chosen)
    allowed = (not paid) or paid_allowed(mode)

    return {
        "mode": mode,
        "mode_label": LABELS[mode],
        "provider": chosen,
        "provider_label": PROVIDER_LABELS.get(chosen, chosen),
        "paid": paid,
        # 부를 수 없는 것은 0 번 부른다. 계획에 그대로 적는다.
        "voice_calls": scenes if allowed else 0,
        "paid_calls": scenes if (paid and allowed) else 0,
        "estimated_cost": None,
        "cost_unknown": True,
        "will_be_called": allowed,
    }
