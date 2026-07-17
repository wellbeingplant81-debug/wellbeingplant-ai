from concurrent.futures import ThreadPoolExecutor, as_completed

from app import config
from app.services import duration_estimator
from app.services import motion_contract
from app.services import scene_stability_policy
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
    render_profile=None,
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

    video_priority_scenes = set()
    contract_by_scene = {}
    stock_video_priority_active = False

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
        # (Motion Contract는 Hook/Conclusion처럼 scene 위치로 motion을
        # 결정할 때도 AI/Stock 소스 선택 자체는 건드리지 않으므로,
        # 이 축은 계속 UploadAssetStrategy.select_asset_mode()가 유일한
        # 판단처다 - 아래 video 판단과 달리 정책 중복/충돌이 없다.)
        ai_priority_scenes = {
            scene["scene"]
            for scene in scenes
            if UploadAssetStrategy.select_asset_mode(scene, profile="upload") == AssetMode.AI
        }
        visual_profiles = assign_visual_profiles(scenes)

        # Sprint100-2 - Motion Contract: scene 배치 전체를 대상으로 한
        # 번만 계산한다(scene 위치가 필요하므로 개별 scene만 봐선
        # hook/conclusion을 알 수 없다). config.ENABLE_MOTION_CONTRACT는
        # 순수 kill switch다 - 기본값 False라 이 블록 전체가 기본적으로
        # no-op이다.
        if config.ENABLE_MOTION_CONTRACT:
            # Sprint100-3 - Motion Contract Single Source of Truth:
            # 판정은 전부 motion_contract.py 안에서 끝난다. 여기서는
            # build_motion_contract()가 만든 결과를 index_by_scene_id()/
            # video_priority_scene_ids()로 조회 가능한 형태로 바꿔
            # 쓸 뿐, video/static/dynamic을 스스로 다시 판단하지 않는다.
            contract_list = motion_contract.build_motion_contract(
                scenes, profile="upload",
            )
            contract_by_scene = motion_contract.index_by_scene_id(contract_list)
            video_priority_scenes = motion_contract.video_priority_scene_ids(
                contract_list,
            )
        else:
            # Sprint100-3 - Motion Contract가 꺼져 있으면(kill switch
            # False) Sprint100-2 이전 동작을 100% 그대로 유지한다 -
            # UploadAssetStrategy.prefers_video()를 scene 전체에 대해
            # 직접 계산한다(Hook/Conclusion 오버라이드 없음).
            video_priority_scenes = {
                scene["scene"]
                for scene in scenes
                if UploadAssetStrategy.prefers_video(scene, profile="upload")
            }
    elif config.ENABLE_STOCK_VIDEO_PRIORITY and any(
        scene.get("visual_type") for scene in scenes
    ):
        # Sprint121 - Stock Video Priority. 이미 확정된
        # scene["visual_type"]만 신뢰한다 - UploadAssetStrategy.
        # select_asset_mode()(AI/Real 재분류 로직)는 절대 호출하지
        # 않는다(승인된 Visual Planning 보호). Stock Video 채택
        # 여부만 검증된 asset_strategy="upload" 스코어링/관련성 체크
        # 메커니즘(아래 use_upload_wiring)을 재사용해서 결정하고,
        # 적합한 후보가 없으면 그 메커니즘 자체의 기존 폴백으로
        # Stock Image/AI에 자연스럽게 떨어진다.
        ai_priority_scenes = {
            scene["scene"] for scene in scenes if scene.get("visual_type") == "ai"
        }
        visual_profiles = assign_visual_profiles(scenes)
        video_priority_scenes = {
            scene["scene"] for scene in scenes if scene.get("visual_type") == "real"
        }
        stock_video_priority_active = True
    else:
        ai_priority_scenes = select_ai_priority_scenes(
            scenes, get_ai_ratio_cap(),
        )
        visual_profiles = assign_visual_profiles(scenes)

    # Sprint121 - Stock Video Priority 전용 분기도 asset_strategy=
    # "upload"와 동일한 스코어링/관련성 체크 배선을 재사용한다(AI/Real
    # 분류는 위에서 이미 scene["visual_type"]로 고정됨). 호출자가
    # 명시적으로 넘긴 asset_strategy(Motion Contract 등 실제 upload
    # ProductionProfile 전용 로직)는 아래에서 원래 값 그대로만 참조해
    # 이 분기와 절대 섞이지 않는다.
    use_upload_wiring = asset_strategy == "upload" or stock_video_priority_active

    integrate_asset_kwargs = {}
    if use_upload_wiring:
        # Sprint96.1 Hotfix - asset_strategy="upload"일 때만
        # integrate_asset()에 전달한다(그 외에는 기존처럼 kwarg 자체를
        # 넘기지 않아 완전히 하위 호환).
        integrate_asset_kwargs["asset_strategy"] = "upload"

    if render_profile is not None:
        # Sprint122 - Longform Foundation: render_profile이 주어졌을
        # 때만 integrate_asset()에 전달한다 - 안 주면(기본값 None)
        # kwarg 자체가 추가되지 않아 기존 호출부와 완전히 하위 호환.
        integrate_asset_kwargs["render_profile"] = render_profile

    futures = []
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        for scene in scenes:

            per_scene_kwargs = dict(integrate_asset_kwargs)
            scene_for_integration = scene

            if use_upload_wiring:
                # Sprint100-3 - prefer_video는 scene마다 다르므로(공유
                # 딕셔너리인 integrate_asset_kwargs에는 넣을 수 없다)
                # 매 반복마다 계산해 넣는다.
                per_scene_kwargs["prefer_video"] = scene["scene"] in video_priority_scenes

                if asset_strategy == "upload":
                    # Sprint100-2 - Motion Contract 오케스트레이션만:
                    # 실제 upload ProductionProfile 경로에서만 동작한다
                    # (Sprint121 Stock Video Priority 분기는 여기 타지
                    # 않는다 - 기존 동작 변경 금지). 규칙 판단은
                    # motion_contract.py, max_assets 강제는
                    # asset_integration_service.integrate_asset()의
                    # 책임이다. 여기서는 (a) integrate_asset()이 실제로
                    # 캡을 적용할 수 있도록 max_assets 값만 kwarg로
                    # 넘기고, (b) QA Report가 읽을 수 있도록 scene
                    # 사본에 motion_contract 필드를 얹는다 -
                    # integrate_asset()이 enriched = dict(scene)으로
                    # 시작하므로 이 필드가 결과에 그대로 전달된다
                    # (integrate_asset() 시그니처는 건드리지 않음).
                    contract_entry = contract_by_scene.get(scene["scene"])
                    if contract_entry is not None:
                        per_scene_kwargs["max_assets"] = contract_entry["max_assets"]
                        scene_for_integration = dict(scene)
                        scene_for_integration["motion_contract"] = contract_entry

            if config.ENABLE_SCENE_ASSET_LIMIT and "max_assets" not in per_scene_kwargs:
                # Sprint121 - Scene Stability. Motion Contract가 이미
                # max_assets를 정한 경우(위 분기)는 덮어쓰지 않는다.
                # narration 예상 길이(TTS 이전 단계라 실제 audio 길이는
                # 아직 알 수 없음 - duration_estimator로 추정)를
                # scene_stability_policy에 넘겨 Scene 길이에 맞는 최대
                # asset 개수를 정한다. 실제로는 primary asset이 AI
                # 생성일 때만 영향을 준다(Stock scene은 원래도 asset
                # 1개 - 기존 Sprint62-4 불변식, 이 Sprint에서 건드리지
                # 않음).
                estimated_duration = duration_estimator.estimate_duration(
                    scene.get("narration", ""),
                )
                per_scene_kwargs["max_assets"] = (
                    scene_stability_policy.max_assets_for_duration(
                        estimated_duration,
                    )
                )

            futures.append(
                executor.submit(
                    integrate_asset,
                    scene_for_integration,
                    project_path,
                    channel,
                    prefer_ai=scene["scene"] in ai_priority_scenes,
                    visual_profile=visual_profiles.get(scene["scene"]),
                    **per_scene_kwargs,
                )
            )

        for future in as_completed(futures):
            results.append(future.result())

    return sorted(results, key=lambda enriched_scene: enriched_scene["scene"])
