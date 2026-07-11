"""
Sprint82 - Topic Intelligence Engine v1.

주제(topic) 문자열을 규칙 기반 키워드 매칭만으로 최소 분류해
TopicProfile을 만든다. AI/GPT 호출 없음, Planner와 연결하지 않음 -
planner_hints는 항상 빈 dict다(이후 확장 자리만 마련).
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


DISEASE_KEYWORDS = ["당뇨", "고혈압", "치매"]
SYMPTOM_KEYWORDS = ["두통", "손발저림", "어지럼증"]
FOOD_KEYWORDS = ["브로콜리", "토마토", "마늘"]

DEFAULT_TARGET_AGE = "40-60"
DEFAULT_EVERGREEN = True
DEFAULT_CONVERSATION_STYLE = "expert_dialogue"


def _detect_content_type(topic: str) -> str:

    if any(keyword in topic for keyword in DISEASE_KEYWORDS):
        return "disease"

    if any(keyword in topic for keyword in SYMPTOM_KEYWORDS):
        return "symptom"

    if any(keyword in topic for keyword in FOOD_KEYWORDS):
        return "food"

    return "general"


class TopicIntelligenceService:

    @staticmethod
    def build_topic_profile(topic: str) -> TopicProfile:

        content_type = _detect_content_type(topic)

        return TopicProfile(
            topic=topic,
            content_type=content_type,
            medical_category=content_type,
            target_age=DEFAULT_TARGET_AGE,
            evergreen=DEFAULT_EVERGREEN,
            conversation_style=DEFAULT_CONVERSATION_STYLE,
            planner_hints={},
        )
