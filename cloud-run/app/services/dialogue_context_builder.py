"""
Sprint84 - Dialogue Context Builder v1 (Consumer Interface).

TopicProfile(topic_intelligence_service.py)을 받아, 향후 대사 생성
소비자가 참조할 DialogueContext로 감싸는 최소 인터페이스만 정의한다.
LLM 호출 없음, 실제 대사 생성 없음, Planner와 연결하지 않음 -
speakers는 아직 고정값이다.
"""

from dataclasses import dataclass

from app.services.topic_intelligence_service import TopicProfile


@dataclass
class DialogueContext:
    topic: str
    topic_profile: TopicProfile
    target_age: str
    conversation_style: str
    speakers: list
    asset_hints: dict


DEFAULT_SPEAKERS = [
    {"role": "professor"},
    {"role": "middle_aged_male"},
]


class DialogueContextBuilder:

    @staticmethod
    def build_dialogue_context(
        topic: str,
        topic_profile: TopicProfile,
    ) -> DialogueContext:

        return DialogueContext(
            topic=topic,
            topic_profile=topic_profile,
            target_age=topic_profile.target_age,
            conversation_style=topic_profile.conversation_style,
            speakers=list(DEFAULT_SPEAKERS),
            asset_hints=topic_profile.asset_hints,
        )
