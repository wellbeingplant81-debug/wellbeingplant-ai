"""
Sprint75 - Prompt Composer.

슬롯을 받아 Imagen에 보낼 (positive, negative) 한 쌍을 만든다. 순수
함수뿐이라 API를 부르지 않고 검증된다.

기존 방식은 채널 스타일 블록 하나를 scene 문장 앞에 통째로 이어붙이는
것이었다. 그 블록 안에 스타일, 인물 품질, 조명, 카메라, 구도, 부정어가
전부 섞여 있었고, scene이 정한 값과 정면으로 싸웠다. 여기서는 슬롯마다
값이 하나씩만 들어간다.
"""

from dataclasses import dataclass

from app.prompts import prompt_elements as slots


# 긍정 슬롯에서 발견되는 부정 표현. 여기 걸리면 버리지 않고
# negative로 옮긴다 - 의도 자체는 맞고 자리만 틀린 것이므로.
_NEGATION_PREFIXES = ("no ", "not ", "without ")


@dataclass(frozen=True)
class ComposedPrompt:
    positive: str
    negative: str


def _as_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    return ", ".join(part.strip() for part in value if part and part.strip())


def _split_negations(text: str):
    """긍정 슬롯에 섞인 부정 표현을 떼어낸다.

    반환값: (남은 긍정 텍스트, 옮겨야 할 부정어 목록)
    """

    keep, moved = [], []

    for part in text.split(","):
        stripped = part.strip()

        if not stripped:
            continue

        lowered = stripped.lower()

        for prefix in _NEGATION_PREFIXES:
            if lowered.startswith(prefix):
                moved.append(stripped[len(prefix):].strip())
                break
        else:
            keep.append(stripped)

    return ", ".join(keep), moved


def compose(elements: dict) -> ComposedPrompt:
    """
    슬롯에서 최종 프롬프트를 만든다. 순수 함수입니다.

    비어 있는 슬롯은 라벨째 빠진다 - "Camera:"만 덩그러니 남으면 모델이
    빈 지시를 해석하려 든다.

    모르는 슬롯 이름은 조용히 무시하지 않고 거부한다. Sprint71에서
    'real'/'ai'를 스타일 이름으로 넘기던 실수가 조용한 기본값 처리
    뒤에 숨어 있었다.
    """

    unknown = set(elements) - set(slots.ELEMENTS)

    if unknown:
        raise ValueError(
            f"알 수 없는 프롬프트 슬롯: {sorted(unknown)}. "
            f"사용 가능한 슬롯: {sorted(slots.ELEMENTS)}"
        )

    if not _as_text(elements.get(slots.SUBJECT)):
        raise ValueError(
            "subject 슬롯이 비어 있습니다. 피사체 없는 이미지 프롬프트는 "
            "만들지 않습니다."
        )

    lines = []
    negatives = [_as_text(elements.get(slots.NEGATIVE))]

    for slot in slots.POSITIVE_ORDER:
        text = _as_text(elements.get(slot))

        if not text:
            continue

        text, moved = _split_negations(text)
        negatives.extend(moved)

        if text:
            lines.append(f"{slots.LABELS[slot]}: {text}")

    return ComposedPrompt(
        positive="\n".join(lines),
        negative=", ".join(part for part in negatives if part),
    )


def merge(profile: dict, scene: dict) -> dict:
    """
    프로필 기본값과 scene의 값을 합친다. 순수 함수입니다.

    scene이 이긴다. 이것이 이 Epic의 핵심 계약이다 - 카메라를 두 곳에서
    쓰던 것이 Sprint74에서 후보 두 장이 똑같이 'wide shot'을 구현하지
    못한 원인이었다. 프로필은 scene이 비워 둔 슬롯만 채운다.

    부정어만 예외로 양쪽을 합친다. 부정은 "이것도 저것도 나오면 안
    된다"이므로 덮어쓸 이유가 없다.
    """

    merged = dict(profile)

    for slot, value in scene.items():
        if slot == slots.NEGATIVE:
            continue

        if _as_text(value):
            merged[slot] = value

    negatives = [
        _as_text(profile.get(slots.NEGATIVE)),
        _as_text(scene.get(slots.NEGATIVE)),
    ]
    combined = ", ".join(part for part in negatives if part)

    if combined:
        merged[slots.NEGATIVE] = combined

    return merged
