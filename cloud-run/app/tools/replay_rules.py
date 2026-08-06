"""
Sprint82 - Replay 전용 규칙 목록.

**이것은 Production 순위 로직이 아니다.**

여기 있는 함수들은 "만약 이 규칙이었다면 무엇을 골랐을까"를 기록에
되돌려 보기 위한 가설이다. asset_relevance(실제 순위)나 asset_ranking_
service(실제 선택)는 이 모듈을 import하지 않으며, 그렇게 되면 안 된다.
테스트가 그것을 고정한다.

Sprint78 분석 때 scratchpad 스크립트에 있던 것을 옮겨 왔다. 화면에서
고를 수 있어야 하므로 저장소에 있어야 하지만, 위치와 이름으로 "아직
채택되지 않은 가설"임이 드러나야 한다.

두 규칙 모두 Sprint77 Observatory가 실측으로 지목한 것이다.

  부정 신호 - 선택된 후보의 alt가 "soda water in glass with bubbles and
  red straw"였고 Gemini는 "잔 안에 이상한 붉은 물체"를 지적했다.
  실격 사유가 우리가 이미 받아 놓은 텍스트에 있었는데 순위가 보지
  않았다.

  구도 어휘 - Gemini가 "요청된 flat lay 구도가 아니다"라고 한 scene의
  후보 풀에 "Top view of a nutritious breakfast bowl"이 있었다.
  camera/composition은 검색어에서 빼는 것이 맞지만(Pexels는 앵글로
  색인하지 않는다) 순위에서까지 빠져 있었다.
"""


BASELINE = "baseline"
NEGATIVE = "negative"
COMPOSITION = "composition"
COMBINED = "combined"


# scene이 요구하지 않았는데 alt에 있으면 감점할 어휘.
DISTRACTOR_TERMS = (
    "straw", "soda", "cocktail", "martini", "wine", "beer", "alcohol",
    "candy", "cookie", "artificial", "plastic", "toy", "abstract",
)

DISTRACTOR_PENALTY = 0.30

# 구도 어휘. scene이 요구한 구도가 alt에도 적혀 있으면 가점.
COMPOSITION_PHRASES = (
    ("top view", "top-down", "flat lay", "overhead", "from above"),
    ("close-up", "close up", "macro"),
    ("wide", "panoramic"),
)

COMPOSITION_BONUS = 0.25


def _text(candidate) -> str:
    return (
        f"{candidate.get('alt') or ''} {candidate.get('slug') or ''}"
    ).lower()


def _wanted(scene) -> str:
    return " ".join(scene.get("scene_terms") or []).lower()


def baseline(candidate, scene) -> float:
    """기록된 점수 그대로. 재생이 원본을 재현하는지 확인하는 기준선."""

    return candidate.get("ranking_score") or 0.0


def negative(candidate, scene) -> float:
    """scene이 요구하지 않은 사물/색이 alt에 있으면 감점."""

    score = baseline(candidate, scene)
    text = _text(candidate)
    terms = set(scene.get("scene_terms") or [])

    for term in DISTRACTOR_TERMS:
        if term in text and term not in terms:
            score -= DISTRACTOR_PENALTY

    return score


def composition(candidate, scene) -> float:
    """scene이 요구한 구도가 alt에도 적혀 있으면 가점."""

    score = baseline(candidate, scene)
    text = _text(candidate)
    wanted = _wanted(scene)

    for phrases in COMPOSITION_PHRASES:
        if any(phrase in wanted for phrase in phrases):
            if any(phrase in text for phrase in phrases):
                score += COMPOSITION_BONUS

    return score


def combined(candidate, scene) -> float:
    """둘 다 적용."""

    base = baseline(candidate, scene)

    return (
        base
        + (negative(candidate, scene) - base)
        + (composition(candidate, scene) - base)
    )


RULES = {
    BASELINE: {
        "key": BASELINE,
        "label": "Baseline (기록 재현)",
        "description": "기록된 점수 그대로. 변경이 0이어야 기록과 재생이 맞는다.",
        "scorer": baseline,
    },
    NEGATIVE: {
        "key": NEGATIVE,
        "label": "부정 신호",
        "description": "scene이 요구하지 않은 사물/색이 alt에 있으면 감점.",
        "scorer": negative,
    },
    COMPOSITION: {
        "key": COMPOSITION,
        "label": "구도 어휘",
        "description": "scene이 요구한 구도가 alt에도 적혀 있으면 가점.",
        "scorer": composition,
    },
    COMBINED: {
        "key": COMBINED,
        "label": "둘 다",
        "description": "부정 신호 + 구도 어휘.",
        "scorer": combined,
    },
}


def catalog() -> list:
    """화면이 보여 줄 규칙 목록. scorer는 뺀다."""

    return [
        {key: value for key, value in rule.items() if key != "scorer"}
        for rule in RULES.values()
    ]


def scorer_for(key: str):
    """규칙 이름으로 채점 함수를 얻는다. 모르는 이름은 거부한다."""

    rule = RULES.get(key)

    if rule is None:
        raise ValueError(
            f"알 수 없는 replay 규칙입니다: {key!r}. "
            f"사용 가능한 값: {sorted(RULES)}"
        )

    return rule["scorer"]
