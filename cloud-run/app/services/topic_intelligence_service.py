"""
Sprint82 - Topic Intelligence Engine v1.

주제(topic) 문자열을 규칙 기반 키워드 매칭만으로 최소 분류해
TopicProfile을 만든다. AI/GPT 호출 없음, Planner와 연결하지 않음 -
planner_hints는 항상 빈 dict다(이후 확장 자리만 마련).

Sprint83 - Medical Topic Classification v1. content_type과는 별도로,
의료 관련 세부 메타데이터(medical_domain/urgency/requires_medical_visual)
를 같은 방식(순수 키워드 매칭, AI 호출 없음)으로 추가한다.
"""

from dataclasses import dataclass


@dataclass
class TopicProfile:
    topic: str
    content_type: str
    medical_category: str
    target_age: str
    evergreen: bool
    conversation_style: str
    planner_hints: dict
    medical_domain: str
    urgency: str
    requires_medical_visual: bool
    conversation_depth: str
    asset_hints: dict
    dialogue_hints: dict


DISEASE_KEYWORDS = ["당뇨", "고혈압", "치매"]
SYMPTOM_KEYWORDS = ["두통", "손발저림", "어지럼증"]
FOOD_KEYWORDS = ["브로콜리", "토마토", "마늘"]

DEFAULT_TARGET_AGE = "40-60"
DEFAULT_EVERGREEN = True
DEFAULT_CONVERSATION_STYLE = "expert_dialogue"

DEFAULT_MEDICAL_DOMAIN = "general"
DEFAULT_URGENCY = "low"
DEFAULT_REQUIRES_MEDICAL_VISUAL = False
DEFAULT_CONVERSATION_DEPTH = "expert"

# Sprint83 - 키워드별 의료 메타데이터. 목록 순서대로 검사해 먼저
# 매칭되는 규칙 하나만 적용한다.
MEDICAL_DOMAIN_RULES = [
    (["당뇨"], {
        "medical_domain": "metabolism", "urgency": "high",
        "requires_medical_visual": True,
    }),
    (["고혈압"], {
        "medical_domain": "cardiovascular", "urgency": "high",
        "requires_medical_visual": True,
    }),
    (["치매"], {
        "medical_domain": "neurology", "urgency": "high",
        "requires_medical_visual": True,
    }),
    (["브로콜리", "토마토", "마늘"], {
        "medical_domain": "nutrition", "urgency": "low",
        "requires_medical_visual": False,
    }),
]


def _detect_content_type(topic: str) -> str:

    if any(keyword in topic for keyword in DISEASE_KEYWORDS):
        return "disease"

    if any(keyword in topic for keyword in SYMPTOM_KEYWORDS):
        return "symptom"

    if any(keyword in topic for keyword in FOOD_KEYWORDS):
        return "food"

    return "general"


def _detect_medical_metadata(topic: str) -> dict:

    for keywords, metadata in MEDICAL_DOMAIN_RULES:
        if any(keyword in topic for keyword in keywords):
            return metadata

    return {}


class TopicIntelligenceService:

    @staticmethod
    def build_topic_profile(topic: str) -> TopicProfile:

        content_type = _detect_content_type(topic)
        medical_metadata = _detect_medical_metadata(topic)

        return TopicProfile(
            topic=topic,
            content_type=content_type,
            medical_category=content_type,
            target_age=DEFAULT_TARGET_AGE,
            evergreen=DEFAULT_EVERGREEN,
            conversation_style=DEFAULT_CONVERSATION_STYLE,
            planner_hints={},
            medical_domain=medical_metadata.get(
                "medical_domain", DEFAULT_MEDICAL_DOMAIN,
            ),
            urgency=medical_metadata.get("urgency", DEFAULT_URGENCY),
            requires_medical_visual=medical_metadata.get(
                "requires_medical_visual", DEFAULT_REQUIRES_MEDICAL_VISUAL,
            ),
            conversation_depth=DEFAULT_CONVERSATION_DEPTH,
            asset_hints={},
            dialogue_hints={},
        )
