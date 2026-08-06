"""
Sprint104 - 붙여넣은 대본을 읽는다 (Epic 54, Phase 3).

사용자가 ChatGPT / Claude / Gemini / DeepSeek 웹 채팅에서 만든 결과를
그대로 붙여넣으면, 지금 엔진이 쓰는 script 형태로 옮긴다.

AI를 부르지 않는다. 정규식과 json 파싱뿐이다.

모델별 파서를 네 개 만들지 않았다. 네 모델의 출력이 실제로 다른
지점은 코드 펜스 표기, 앞뒤에 붙는 설명 문장, JSON이냐 마크다운이냐
셋뿐이고 그것은 모델이 아니라 "그날 그 대화"의 성질이다. 모델 이름으로
분기하면 사용자가 어느 창에서 복사했는지를 우리가 알아야 하고, 같은
모델이 다른 모양을 내놓는 순간 틀린다.

읽는 순서는 확실한 것부터다.

    1. JSON        구조가 이미 있다. 가장 믿을 수 있다.
    2. 코드 펜스 안 JSON
    3. 본문 어딘가에 박힌 JSON 덩어리
    4. 마크다운 / 라벨 붙은 평문

반쯤 읽은 결과를 돌려주지 않는다. 필요한 것이 없으면 무엇이 왜
없는지 적어 예외를 던진다 - 사람이 그 문장을 보고 다시 붙여넣을 수
있어야 한다. 없는 narration을 지어내면 그 영상은 아무도 만들라고
하지 않은 영상이 된다.
"""

import json
import re
from typing import List, Optional

# scene 하나가 갖는 요소. script_service가 Writer에게 요구하는 것과
# 같은 목록이다 - 여기서 새로 정하지 않는다.
SCENE_ELEMENTS = (
    "subject", "action", "environment", "camera", "composition", "lighting",
)

# 같은 뜻으로 쓰이는 이름들. 모델마다, 사람마다 다르게 적는다.
_ALIASES = {
    "title": ("title", "제목", "타이틀"),
    "hook": ("hook", "훅", "후크", "도입"),
    "script": ("script", "본문", "대본", "body", "full_script", "전체대본"),
    "character": ("character", "인물", "캐릭터", "등장인물"),
    "scenes": ("scenes", "scene_list", "장면", "씬"),
    "narration": (
        "narration", "내레이션", "나레이션", "대사", "멘트", "voiceover", "vo",
    ),
    "image_prompt": (
        "image_prompt", "imageprompt", "prompt", "이미지프롬프트", "이미지",
        "image",
    ),
    "subject": ("subject", "인물", "대상", "피사체"),
    "action": ("action", "동작", "행동"),
    "environment": ("environment", "배경", "환경", "장소"),
    "camera": ("camera", "카메라", "샷"),
    "composition": ("composition", "구도"),
    "lighting": ("lighting", "조명", "빛"),
}

_SCENE_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\**\s*)?(?:scene|씬|장면)\s*[#]?\s*(\d+)",
    re.IGNORECASE,
)

# 라벨 줄. 앞에 붙는 장식을 전부 허용한다 - 마크다운 제목(##),
# 목록 기호(- *), 굵게(**)가 섞여 온다. "## 제목: ..."을 못 읽어서
# Gemini 출력이 통째로 실패했다(실측).
_LABEL_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[-*+]\s+)?(?:\*{1,2})?\s*([^:：*#]{1,20}?)\s*"
    r"(?:\*{1,2})?\s*[:：]\s*(.*)$"
)

_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n(.*?)```", re.DOTALL)


class ChatImportError(ValueError):
    """붙여넣은 것을 대본으로 읽을 수 없다.

    무엇이 왜 안 읽혔는지 메시지에 담는다 - 사람이 고쳐서 다시
    붙여넣을 수 있어야 한다."""


def _normalize_key(key: str) -> str:
    return re.sub(r"[\s_\-]", "", str(key)).strip().lower()


def _canonical(key: str) -> Optional[str]:
    normalized = _normalize_key(key)

    for canonical, aliases in _ALIASES.items():
        if normalized in {_normalize_key(a) for a in aliases}:
            return canonical

    return None


def _clean(text: str) -> str:
    """따옴표와 군더더기를 정리한다. 내용은 바꾸지 않는다."""

    if text is None:
        return ""

    value = str(text).strip()
    # 스마트 따옴표 - 채팅 화면에서 복사하면 자주 섞여 온다.
    value = value.replace("“", '"').replace("”", '"')
    value = value.replace("‘", "'").replace("’", "'")
    # 통째로 감싼 따옴표만 벗긴다.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()

    return re.sub(r"\*\*", "", value).strip()


# ---- JSON 경로 -------------------------------------------------------


def _candidate_json_blocks(raw: str) -> List[str]:
    """읽어 볼 만한 JSON 덩어리들. 확실한 것부터."""

    blocks = [raw.strip()]

    blocks.extend(match.strip() for match in _FENCE.findall(raw))

    # 앞뒤에 설명 문장이 붙은 경우. "다음은 대본입니다:" 같은 말이
    # 흔하다.
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        blocks.append(raw[start:end + 1])

    return blocks


def _loads(text: str):
    try:
        return json.loads(text)
    except Exception:
        pass

    # 후행 쉼표는 모델이 자주 남긴다.
    repaired = re.sub(r",(\s*[}\]])", r"\1", text)

    try:
        return json.loads(repaired)
    except Exception:
        return None


def _from_json(raw: str) -> Optional[dict]:
    for block in _candidate_json_blocks(raw):
        if not block or block[0] not in "{[":
            continue

        parsed = _loads(block)

        if isinstance(parsed, dict):
            return parsed
        # scene 배열만 붙여넣는 경우도 있다.
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return {"scenes": parsed}

    return None


def _map_keys(payload: dict) -> dict:
    """모델이 쓴 이름을 우리 이름으로 옮긴다. 모르는 키는 버린다."""

    mapped = {}

    for key, value in payload.items():
        canonical = _canonical(key)
        if canonical and canonical not in mapped:
            mapped[canonical] = value

    return mapped


def _scene_from_dict(payload: dict, index: int) -> dict:
    mapped = _map_keys(payload)

    scene = {"scene": index, "narration": _clean(mapped.get("narration", ""))}

    for element in SCENE_ELEMENTS:
        value = mapped.get(element)
        if value:
            scene[element] = _clean(value)

    prompt = mapped.get("image_prompt")
    if prompt:
        scene["image_prompt"] = _clean(prompt)

    return scene


# ---- 평문 / 마크다운 경로 ---------------------------------------------


def _split_scenes(raw: str):
    """scene 제목을 기준으로 자른다. 없으면 (머리글, []) 그대로."""

    lines = raw.splitlines()
    head, blocks, current = [], [], None

    for line in lines:
        match = _SCENE_HEADING.match(line)

        if match:
            if current is not None:
                blocks.append(current)
            current = {"number": int(match.group(1)), "lines": []}
            continue

        (current["lines"] if current is not None else head).append(line)

    if current is not None:
        blocks.append(current)

    return "\n".join(head), blocks


def _labels_in(lines: List[str]) -> dict:
    found = {}

    for line in lines:
        match = _LABEL_LINE.match(line)
        if not match:
            continue
        canonical = _canonical(match.group(1))
        if canonical and canonical not in found:
            found[canonical] = _clean(match.group(2))

    return found


def _from_text(raw: str) -> Optional[dict]:
    head, blocks = _split_scenes(raw)

    if not blocks:
        return None

    payload = {k: v for k, v in _labels_in(head.splitlines()).items() if v}
    scenes = []

    for index, block in enumerate(blocks, start=1):
        labels = _labels_in(block["lines"])

        if not labels.get("narration"):
            # 라벨이 없으면 그 scene의 첫 번째 실질적인 줄을 내레이션
            # 으로 본다 - 모델이 "Scene 1" 다음 줄에 대사만 적는
            # 경우가 흔하다.
            body = [
                _clean(line) for line in block["lines"]
                if _clean(line) and not _LABEL_LINE.match(line)
            ]
            if body:
                labels["narration"] = body[0]

        scene = {"scene": index, "narration": labels.get("narration", "")}

        for element in SCENE_ELEMENTS:
            if labels.get(element):
                scene[element] = labels[element]

        if labels.get("image_prompt"):
            scene["image_prompt"] = labels["image_prompt"]

        scenes.append(scene)

    payload["scenes"] = scenes

    return payload


# ---- 조립과 검증 ------------------------------------------------------


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ChatImportError(message)


def _build(payload: dict, default_title: str = "") -> dict:
    mapped = _map_keys(payload) if payload else {}

    raw_scenes = mapped.get("scenes")
    _require(
        isinstance(raw_scenes, list) and raw_scenes,
        "scene을 하나도 찾지 못했습니다. "
        "JSON의 \"scenes\" 배열이나 \"Scene 1\" 같은 제목이 있어야 합니다.",
    )

    scenes = []
    for index, item in enumerate(raw_scenes, start=1):
        if isinstance(item, dict):
            # 평문 경로는 이미 우리 모양이라 그대로 통과한다.
            scenes.append(
                item if "narration" in item and "scene" in item
                else _scene_from_dict(item, index)
            )
        elif isinstance(item, str):
            scenes.append({"scene": index, "narration": _clean(item)})

    # 번호는 다시 매긴다. 모델이 0부터 세거나 건너뛰는 일이 있고,
    # 엔진은 1부터 이어지는 번호를 전제한다.
    for index, scene in enumerate(scenes, start=1):
        scene["scene"] = index

    empty = [s["scene"] for s in scenes if not s.get("narration")]
    _require(
        not empty,
        f"내레이션이 비어 있는 scene이 있습니다: {empty}. "
        "각 scene에 읽을 문장이 있어야 음성과 자막을 만들 수 있습니다.",
    )

    # 제목이 없으면 호출자가 준 것을 쓴다. 지어내는 것이 아니다 -
    # 사용자가 이미 적은 주제이고, 그것 말고 우리가 아는 제목은 없다.
    title = _clean(mapped.get("title", "")) or _clean(default_title)
    _require(
        bool(title),
        "제목을 찾지 못했습니다. "
        "JSON의 \"title\"이나 \"제목: ...\" 줄이 있어야 합니다.",
    )

    body = _clean(mapped.get("script", ""))

    if not body:
        # 본문이 따로 없으면 내레이션을 이어 붙인다. script_service가
        # Writer에게 요구하는 것과 같은 정의다("narration 전체를
        # 이어붙인 내용") - 지어내는 것이 아니라 정의대로 만드는 것이다.
        body = " ".join(s["narration"] for s in scenes)

    return {
        "title": title,
        "hook": _clean(mapped.get("hook", "")),
        "script": body,
        "character": _clean(mapped.get("character", "")),
        "scenes": scenes,
    }


def parse_script(raw: str, default_title: str = "") -> dict:
    """
    붙여넣은 텍스트를 지금 엔진이 쓰는 script 형태로 옮긴다.

    붙여넣은 것에 제목이 없으면 default_title을 쓴다. 비어 있으면
    제목 없음으로 거절한다.

    읽지 못하면 ChatImportError를 던진다 - 반쯤 읽은 결과를 돌려주지
    않는다.
    """

    _require(
        bool(raw and raw.strip()),
        "붙여넣은 내용이 비어 있습니다.",
    )

    payload = _from_json(raw)

    if payload is None:
        payload = _from_text(raw)

    _require(
        payload is not None,
        "대본으로 읽을 수 있는 구조를 찾지 못했습니다. "
        "JSON을 그대로 붙여넣거나, \"제목:\"과 \"Scene 1\" 형태로 "
        "정리해서 붙여넣어 주십시오.",
    )

    script = _build(payload, default_title)

    # image_prompt는 요소에서 파생된다. 엔진이 쓰는 그 함수를 그대로
    # 쓴다 - 여기서 프롬프트를 조립하지 않는다.
    from app.services import scene_prompt_service

    script["scenes"] = scene_prompt_service.apply_prompt_elements(script["scenes"])

    return script
