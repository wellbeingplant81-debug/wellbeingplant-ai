"""
Sprint86 - Planner Dialogue Adapter v1 (Consumer Interface).

DialogueScript(dialogue_generator.py)와 TopicProfile(topic_intelligence_
service.py)을 받아, 향후 Planner가 소비할 PlannerDialogueInput으로
감싸는 최소 인터페이스만 정의한다. 기존 Planner(scene_planner_service.py,
asset_planner.py)를 호출하거나 수정하지 않는다 - enabled는 항상
False로 고정되어 Feature Flag 기본 OFF를 유지한다.
"""

from dataclasses import dataclass


@dataclass
class PlannerDialogueInput:
    dialogue_script: object
    topic_profile: object
    planner_hints: dict
    enabled: bool = False


class PlannerDialogueAdapter:

    @staticmethod
    def build(dialogue_script, topic_profile) -> PlannerDialogueInput:

        return PlannerDialogueInput(
            dialogue_script=dialogue_script,
            topic_profile=topic_profile,
            planner_hints=topic_profile.planner_hints,
            enabled=False,
        )
