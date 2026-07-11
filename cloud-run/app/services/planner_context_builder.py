"""
Sprint81 - Asset Planner Consumer Interface.

asset_planner.plan_asset_strategy()가 만드는 asset_plan(scene_number ->
SceneAssetStrategy dict)을, 향후 소비자(prompt enrichment 등)가 참조할
Context로 감싸는 순수 함수만 정의한다. 이번 Sprint는 인터페이스만
구축할 뿐 - Prompt 생성 코드 등 어떤 소비처와도 아직 연결하지 않는다.

Planner가 꺼져 있으면(asset_plan이 None/빈 dict) None을 반환한다 -
소비자는 이 None을 "Planner 정보 없음"으로 해석해 기존 동작(Planner
없이 생성)을 그대로 유지해야 한다.
"""


def build_planner_context(asset_plan: dict) -> dict:

    if not asset_plan:
        return None

    return {"scenes": asset_plan}
