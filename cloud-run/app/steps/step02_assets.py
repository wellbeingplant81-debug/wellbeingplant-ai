from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.asset_integration_service import integrate_asset
from app.services.asset_mode_config import get_ai_ratio_cap
from app.services.asset_priority_classifier import select_ai_priority_scenes
from app.services.upload_asset_strategy import AssetMode, UploadAssetStrategy
from app.services.visual_diversity_engine import assign_visual_profiles


MAX_WORKERS = 3


def collect_assets(
    scenes,
    project_path,
    channel="wellbeing",
    asset_plan=None,
    asset_strategy=None,
):
    """
    기존 step02_image.py의 병렬 처리 구조(ThreadPoolExecutor,
    max_workers=3)를 그대로 재사용합니다. scene마다 AssetSelector ->
    (필요시) 비디오 프레임 추출까지 마친 확장된 scene dict를
    돌려받아, 원래 scenes 순서(scene 번호 기준)로 정렬해 반환합니다.

    Sprint38 - Hybrid Asset Engine: scene 배치 전체를 대상으로
    ASSET_MODE의 ai_ratio_cap 이내에서 AI 우선 품질 게이트 대상 scene을
    한 번만 골라두고(select_ai_priority_scenes), 각 scene에
    prefer_ai로 전달합니다. 실제 AI 사용 여부는 여전히
    asset_integration_service.integrate_asset()의 Pexels 품질
    게이트가 최종 결정합니다.

    Sprint72-1 - Visual Diversity Engine: scene 배치 전체를 대상으로
    Camera Distance/Angle/Composition/Lighting Profile을 한 번만
    배정해두고(assign_visual_profiles), 각 scene에 visual_profile로
    전달합니다 - 이래야 scene마다 서로 다른 조합이 보장됩니다(scene을
    하나씩 독립적으로 처리하면 배치 전체 관점의 "이미 쓴 조합"을 알
    수 없습니다).

    Sprint77 - Asset Planner v1: asset_plan(pipeline.py가
    ENABLE_ASSET_PLANNER일 때만 asset_planner.plan_asset_strategy()로
    미리 계산해 넘기는, {scene_number: {"prefer_ai", "visual_profile"}}
    형태의 dict)이 주어지면 그 값을 그대로 쓰고, select_ai_priority_
    scenes()/assign_visual_profiles()를 다시 계산하지 않습니다.
    asset_plan이 없으면(기본값 None, 즉 Planner 미사용) 기존 계산
    경로를 그대로 실행합니다 - 완전히 하위 호환입니다.

    기존 step02_image.py는 삭제/수정하지 않고 그대로 유지합니다.

    Sprint96 - ProductionProfile asset_strategy Activation: asset_plan이
    없고 asset_strategy="upload"면 UploadAssetStrategy(Sprint88)로 scene별
    prefer_ai를 정합니다. 그 외(None/"default"/기타 값)는 기존
    select_ai_priority_scenes() 경로 그대로입니다.
    """

    if asset_plan:
        ai_priority_scenes = {
            scene_number
            for scene_number, strategy in asset_plan.items()
            if strategy.get("prefer_ai")
        }
        visual_profiles = {
            scene_number: strategy.get("visual_profile")
            for scene_number, strategy in asset_plan.items()
        }
    elif asset_strategy == "upload":
        # Sprint96 - ProductionProfile asset_strategy Activation:
        # asset_plan이 없고 asset_strategy가 "upload"면 scene마다
        # UploadAssetStrategy(Sprint88)로 prefer_ai를 정한다.
        # select_ai_priority_scenes()/get_ai_ratio_cap()은 쓰지 않는다.
        ai_priority_scenes = {
            scene["scene"]
            for scene in scenes
            if UploadAssetStrategy.select_asset_mode(scene, profile="upload") == AssetMode.AI
        }
        visual_profiles = assign_visual_profiles(scenes)
    else:
        ai_priority_scenes = select_ai_priority_scenes(
            scenes, get_ai_ratio_cap(),
        )
        visual_profiles = assign_visual_profiles(scenes)

    integrate_asset_kwargs = {}
    if asset_strategy == "upload":
        # Sprint96.1 Hotfix - asset_strategy="upload"일 때만
        # integrate_asset()에 전달한다(그 외에는 기존처럼 kwarg 자체를
        # 넘기지 않아 완전히 하위 호환).
        integrate_asset_kwargs["asset_strategy"] = asset_strategy

    futures = []
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        for scene in scenes:

            futures.append(
                executor.submit(
                    integrate_asset,
                    scene,
                    project_path,
                    channel,
                    prefer_ai=scene["scene"] in ai_priority_scenes,
                    visual_profile=visual_profiles.get(scene["scene"]),
                    **integrate_asset_kwargs,
                )
            )

        for future in as_completed(futures):
            results.append(future.result())

    return sorted(results, key=lambda enriched_scene: enriched_scene["scene"])
