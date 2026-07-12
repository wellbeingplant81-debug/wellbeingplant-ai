"""
Sprint87 - Planner Consumer Integration v1.

Feature Flag(PlannerDialogueInput.enabled, Sprint86)에 따라 Planner가
쓸 context를 어떤 입력으로 만들지 정하는 통합 계층이다. 새 판단/생성
로직은 없다 - dialogue_input이 없거나 꺼져 있으면 기존
planner_context_builder.build_planner_context()를 그대로 쓰고, 켜져
있으면 그 결과에 dialogue 관련 필드(dialogue_script/topic_profile/
planner_hints)만 덧붙인다. 기존 Planner(asset_planner.py)와
planner_context_builder.py는 수정하지 않는다 - 여기서 호출만 한다.
"""

from app.services.planner_context_builder import build_planner_context


class PlannerConsumerIntegration:

    @staticmethod
    def build_planner_context(asset_plan, dialogue_input=None):

        context = build_planner_context(asset_plan)

        if dialogue_input is None or not dialogue_input.enabled:
            return context

        context = context or {}
        context["dialogue_script"] = dialogue_input.dialogue_script
        context["topic_profile"] = dialogue_input.topic_profile
        context["planner_hints"] = dialogue_input.planner_hints

        return context
