"""
Sprint241 - 무엇으로 만들지 사람이 정한다 (Media Source Policy).

왜 생겼나
---------
2026-08-01~18 사이 이미지 생성으로 약 20만원이 나갔고 결과도
만족스럽지 않았다. 지금 결제는 잠겨 있다.

그리고 잠긴 상태에서 배포된 EXE 가 이렇게 죽었다(실측).

    imagen-4.0-generate-001 -> 404 NOT_FOUND -> HTTP 500

"AI 이미지 안 씀" 이 **예외 경로**였기 때문이다. 스톡이 한 장 실패하면
곧바로 유료 모델로 넘어갔고, 그 모델에 닿지 못하자 제작 전체가 멈췄다.

이 파일이 뒤집는 것
-------------------
AI 를 쓰지 않는 것이 정상 경로다. 결제가 잠겨 있어도 내 자료와 무료
스톡만으로 영상이 끝까지 만들어져야 한다.

Provider 계층을 대체하지 않는다
-------------------------------
고르는 일은 provider_selection 이, 찾는 일은 provider_factory 와
local_stock 이, 만드는 일은 image_service 가 이미 한다. 이 파일은
그것들 위에 **허락 하나**를 얹을 뿐이다.

    무엇을 쓸 수 있는가   mine / stock / ai
    몇 장까지            상한
    금액은               모른다고 말한다

새 DB 를 만들지 않는다
----------------------
프로젝트가 고른 것은 project.json 에 적는다 - provider_selection 이
이미 그 파일에 산다. 전역 기본값은 %APPDATA%\\AI영상제작소 아래 json
한 장이다 - free_workspace · studio_upload 가 그렇게 산다.

금액을 지어내지 않는다
----------------------
Provider 가 단가를 말해 주지 않는다. stageSpec 의 estimated_cost 도
local_stock(0) 말고는 전부 null 이다. 모르면 모른다고 적는다 -
"대략 얼마" 라고 적어 두면 사람은 그 숫자를 믿고 결정한다.
"""

import json
import os

# ── 다섯 갈래 ──────────────────────────────────────────────────────
MODE_MINE_ONLY = "mine_only"
MODE_STOCK = "stock"
MODE_MINE_THEN_STOCK = "mine_then_stock"
MODE_MINE_STOCK_AI = "mine_stock_ai"
MODE_AI_FIRST = "ai_first"

MODES = (MODE_MINE_ONLY, MODE_STOCK, MODE_MINE_THEN_STOCK,
         MODE_MINE_STOCK_AI, MODE_AI_FIRST)

LABELS = {
    MODE_MINE_ONLY: "내 자료만",
    MODE_STOCK: "무료 스톡만",
    MODE_MINE_THEN_STOCK: "내 자료 먼저, 모자라면 무료 스톡",
    MODE_MINE_STOCK_AI: "내 자료 · 무료 스톡, 그래도 모자라면 AI",
    MODE_AI_FIRST: "AI 이미지 먼저",
}

# 결제가 잠겨 있다. 아무것도 고르지 않은 사람이 유료 모델을 부르는
# 일이 일어나면 안 된다.
DEFAULT_MODE = MODE_MINE_THEN_STOCK

_AI_MODES = (MODE_MINE_STOCK_AI, MODE_AI_FIRST)
_MINE_MODES = (MODE_MINE_ONLY, MODE_MINE_THEN_STOCK, MODE_MINE_STOCK_AI)
_STOCK_MODES = (MODE_STOCK, MODE_MINE_THEN_STOCK, MODE_MINE_STOCK_AI,
                MODE_AI_FIRST)

# ── 저장 자리 ──────────────────────────────────────────────────────
PROJECT_FIELD = "media_policy"
STORE_FILENAME = "media_policy.json"
VERSION = 1

# ── 상한 ───────────────────────────────────────────────────────────
#
# 재시도 때문에 무제한으로 불리면 안 된다. scene 하나에 한 장을
# 원칙으로 두고, 그 위에 절대 상한을 얹는다.
AI_IMAGE_HARD_LIMIT = 12
AI_CALL_HARD_LIMIT = 20

# ── Provider 상태 ──────────────────────────────────────────────────
AVAILABLE = "AVAILABLE"
NOT_CONFIGURED = "NOT_CONFIGURED"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
DISABLED = "DISABLED"

STATES = (AVAILABLE, NOT_CONFIGURED, NOT_IMPLEMENTED, DISABLED)

# 이름은 provider_selection 이 정한 것을 쓴다. 여기서 새로 짓지 않는다.
_AI_PROVIDERS = {
    "current": {"label": "현재 엔진 (Imagen)", "key": None},
    "flux": {"label": "FLUX", "key": "FLUX_API_KEY"},
    "gpt_image": {"label": "GPT Image", "key": "OPENAI_API_KEY"},
    "imagen": {"label": "Imagen", "key": None, "wired": False},
    "ideogram": {"label": "Ideogram", "key": None, "wired": False},
}


class AiNotAllowed(Exception):
    """
    이 프로젝트는 AI 이미지를 쓰지 않기로 했다.

    고장이 아니다. 부르는 쪽이 이것을 보고 스톡으로 이어 가거나,
    사람에게 그 사실을 알려야 한다.
    """


# ── 전역 기본값 ────────────────────────────────────────────────────
def default_store_path() -> str:
    from app import runtime_paths

    return os.path.join(runtime_paths.home(), STORE_FILENAME)


def _read_default() -> str:
    try:
        with open(default_store_path(), encoding="utf-8") as f:
            found = json.load(f)
    except Exception:
        # 설정 하나가 망가졌다고 제작이 멈출 이유는 없다. 다만 그때
        # 기본값은 **금지 쪽**이다 - 모르면 돈을 쓰지 않는다.
        return DEFAULT_MODE

    mode = found.get("mode") if isinstance(found, dict) else None

    return mode if mode in MODES else DEFAULT_MODE


def current_mode() -> str:
    """아무것도 고르지 않았을 때 따르는 것."""

    return _read_default()


def remember_default(mode: str) -> str:
    _require_mode(mode)

    where = default_store_path()
    folder = os.path.dirname(os.path.abspath(where))

    if folder:
        os.makedirs(folder, exist_ok=True)

    from app.utils.atomic_write import atomic_write_json

    atomic_write_json(where, {"version": VERSION, "mode": mode})

    return mode


# ── 프로젝트가 고른 것 ─────────────────────────────────────────────
def _require_mode(mode: str) -> None:
    if mode not in MODES:
        raise ValueError(
            f"그런 제작 방식이 없습니다: {mode!r}. "
            f"쓸 수 있는 것은 {', '.join(MODES)} 입니다.")


def _project_file(project_path: str) -> str:
    return os.path.join(project_path or "", "project.json")


def _load_project(project_path: str) -> dict:
    try:
        with open(_project_file(project_path), encoding="utf-8") as f:
            found = json.load(f)
    except Exception:
        return {}

    return found if isinstance(found, dict) else {}


def mode_for(project_path: str) -> str:
    """
    이 프로젝트가 따르는 방식. 고른 적이 없으면 전역 기본값이다.
    """

    mode = _load_project(project_path).get(PROJECT_FIELD)

    return mode if mode in MODES else current_mode()


def choose(project_path: str, mode: str) -> str:
    """
    이 프로젝트만 그렇게 한다.

    project.json 은 topic · channel · *_source 가 사는 곳이라 통째로
    덮어쓰면 안 된다 - provider_selection.save 가 지켜 온 그 규칙
    그대로, 읽어서 그 칸만 바꾸고 다시 쓴다.
    """

    _require_mode(mode)

    data = _load_project(project_path)
    data[PROJECT_FIELD] = mode

    os.makedirs(project_path, exist_ok=True)

    with open(_project_file(project_path), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return mode


# ── 무엇이 허락되는가 ──────────────────────────────────────────────
def ai_allowed(mode: str) -> bool:
    return mode in _AI_MODES


def stock_allowed(mode: str) -> bool:
    return mode in _STOCK_MODES


def mine_allowed(mode: str) -> bool:
    return mode in _MINE_MODES


def ai_is_the_point(mode: str) -> bool:
    """
    사람이 **AI 로 만들겠다고** 고른 것인가.

    몰래 바꾸지 않기 위해 필요하다. 보충용으로 AI 를 켠 사람에게는
    스톡으로 이어 주는 것이 맞지만, AI 로 만들겠다고 고른 사람에게
    조용히 스톡을 내주면 그것은 다른 영상이다.
    """

    return mode == MODE_AI_FIRST


def require_ai_allowed(mode: str) -> None:
    """막는 자리. 지나가면 None, 아니면 던진다."""

    if ai_allowed(mode):
        return None

    raise AiNotAllowed(
        f"이 프로젝트는 '{LABELS.get(mode, mode)}' 로 만들기로 했습니다 - "
        "AI 이미지 생성을 하지 않습니다. AI 로 만들려면 제작 방식을 "
        "바꾸십시오.")


# ── Provider 상태 ──────────────────────────────────────────────────
def provider_states(mode: str = None) -> dict:
    """
    지금 고를 수 있는 것이 무엇인가.

    없는 것을 있다고 하지 않는다. 그리고 AI 를 쓰지 않기로 한 모드
    에서는 전부 DISABLED 다 - 고를 수 있는 것처럼 보이면 사람은 눌러
    보고, 왜 안 되는지 모른 채 시간을 버린다.
    """

    mode = mode if mode in MODES else current_mode()
    off = not ai_allowed(mode)

    found = {}

    for name, spec in _AI_PROVIDERS.items():
        if off:
            state = DISABLED
        elif spec.get("wired") is False:
            state = NOT_IMPLEMENTED
        elif spec["key"] and not os.environ.get(spec["key"], "").strip():
            state = NOT_CONFIGURED
        else:
            state = AVAILABLE

        found[name] = {
            "label": spec["label"],
            "state": state,
            # 단가를 모른다. 지어내지 않는다.
            "cost": None,
            "needs": spec["key"] or "",
        }

    return found


# ── 무엇을 얼마나 쓸 것인가 ────────────────────────────────────────
def plan_for(mode: str, scene_count: int = 0) -> dict:
    """
    제작 전에 사람에게 보여 줄 것. 금액은 모른다고 적는다.

    scene 하나에 그림 한 장을 원칙으로 센다. 실제로 몇 장이 AI 로
    갈지는 스톡이 얼마나 찾아지느냐에 달렸으므로 **최대**다.
    """

    mode = mode if mode in MODES else current_mode()
    scenes = max(0, int(scene_count or 0))

    if ai_allowed(mode):
        images = min(scenes, AI_IMAGE_HARD_LIMIT)
        calls = min(scenes, AI_CALL_HARD_LIMIT)
    else:
        images = 0
        calls = 0

    return {
        "mode": mode,
        "label": LABELS.get(mode, mode),
        "scenes": scenes,
        "mine_allowed": mine_allowed(mode),
        "stock_allowed": stock_allowed(mode),
        "ai_allowed": ai_allowed(mode),
        "ai_max_images": images,
        "ai_max_calls": calls,
        # Provider 가 단가를 말해 주지 않는다.
        "estimated_cost": None,
        "cost_unknown": True,
    }
