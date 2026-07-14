import json
import os
import time

from app import config
from app.services import ai_director_service
from app.services import asset_planner
from app.steps import step01_script
from app.steps import step02_assets
from app.steps import step03_tts
from app.steps import step04_subtitle
from app.steps import step05_video
from app.steps import step06_thumbnail
from app.steps import step07_quality
from app.services import prompt_effectiveness_service
from app.services import prompt_enrichment_service
from app.services import prompt_learning_service
from app.services import production_profile_integration
from app.services import prompt_optimization_service
from app.services import regeneration_service
from app.services import scene_planner_service
from app.services import visual_consistency_engine


def _save_script(project_path, data):

    script_path = os.path.join(
        project_path,
        "script.json",
    )

    with open(
        script_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4,
        )


DURATION_TOLERANCE_SECONDS = 2


def run_pipeline(
    topic: str,
    project_path: str,
    channel: str,
    project_creation_time: float = 0.0,
    pipeline_start: float = None,
    production_profile_name: str = None,
):

    if pipeline_start is None:
        pipeline_start = time.perf_counter()

    timings = {
        "project_creation": project_creation_time,
    }

    # Sprint93/94 - ProductionProfile Activation: 기본적으로 꺼져 있고,
    # 켜져도 development profile(45초)이면 기존과 수치상 완전히
    # 동일하다. step01_script.run()보다 먼저 계산해야 duration_target이
    # Duration Gate에도 전달될 수 있다.
    step01_duration_kwargs = {}
    step02_asset_kwargs = {}
    step03_duration_kwargs = {}
    active_profile = None

    # Sprint100-2 - Explicit Profile Opt-In: 전역 플래그(config.
    # ENABLE_PRODUCTION_PROFILE, 기본 False)를 켜지 않고도, 호출자가
    # production_profile_name을 명시적으로 주면 그 요청 1건에 한해
    # profile을 활성화한다. 서버 프로세스 전체에 영향을 주는 전역
    # mutable state를 요청마다 뒤집는 것은 동시 요청 간 경쟁 상태를
    # 만들 수 있어 안전하지 않다 - 실제 활성화 스위치는 항상 이
    # 요청의 인자다. 아무도 opt-in하지 않으면(둘 다 기본값) 기존과
    # 완전히 동일하다.
    if config.ENABLE_PRODUCTION_PROFILE or production_profile_name is not None:
        try:
            active_profile = production_profile_integration.ProductionProfileIntegration.load_profile(
                profile_name=production_profile_name,
                enabled=True,
            )
            duration_target = active_profile["duration_target"]
            step01_duration_kwargs = {
                "target_duration": duration_target,
                "min_acceptable": duration_target - DURATION_TOLERANCE_SECONDS,
                "max_acceptable": duration_target + DURATION_TOLERANCE_SECONDS,
                # Sprint97 - Duration Gate가 provider별 chars_per_second
                # (duration_estimator.chars_per_second_for_provider)를
                # 쓸 수 있도록 tts_provider도 함께 전달한다.
                "tts_provider": active_profile["tts_provider"],
            }
            # Sprint95 - ProductionProfile tts_provider Activation: 값
            # 전달만 한다 - 내부 provider 라우팅 결과는 tts_provider.py의
            # 책임이다.
            step03_duration_kwargs = {
                "target_duration": duration_target,
                "tolerance": DURATION_TOLERANCE_SECONDS,
                "tts_provider": active_profile["tts_provider"],
            }
            # Sprint96 - ProductionProfile asset_strategy Activation: 값
            # 전달만 한다 - 내부 Asset 판정 로직은 step02_assets.py의
            # 책임이다.
            step02_asset_kwargs = {
                "asset_strategy": active_profile["asset_strategy"],
            }
        except Exception as exc:
            print(f"Production profile step failed: {exc}")

    t0 = time.perf_counter()
    data = step01_script.run(
        topic,
        project_path,
        **step01_duration_kwargs,
    )
    timings["script_generation"] = time.perf_counter() - t0

    if active_profile is not None:
        data["production_profile"] = active_profile

    if config.ENABLE_SCENE_PLANNER:
        try:
            data["scene_plan"] = scene_planner_service.plan_scenes(data)
        except Exception as exc:
            print(f"Scene planner step failed: {exc}")

    data["scenes"] = visual_consistency_engine.apply_visual_consistency(
        data["scenes"],
        channel,
    )

    pre_enrichment_scenes = data["scenes"]

    if config.ENABLE_PROMPT_ENRICHMENT and data.get("scene_plan"):
        try:
            data["scenes"] = prompt_enrichment_service.apply_prompt_enrichment(
                data["scenes"], data["scene_plan"],
            )
        except Exception as exc:
            print(f"Prompt enrichment step failed: {exc}")

    if config.ENABLE_PROMPT_EFFECTIVENESS:
        try:
            data["prompt_metrics"] = prompt_effectiveness_service.evaluate_scenes(
                pre_enrichment_scenes, data["scenes"], data.get("scene_plan"),
            )
        except Exception as exc:
            print(f"Prompt effectiveness step failed: {exc}")

    pre_optimization_scenes = data["scenes"]
    optimized_scene_ids = set()

    if config.ENABLE_PROMPT_OPTIMIZATION and data.get("prompt_metrics"):
        try:
            data["scenes"] = prompt_optimization_service.optimize_scenes(
                pre_enrichment_scenes,
                data["scenes"],
                data["prompt_metrics"],
                data.get("scene_plan"),
            )
            before_prompt_by_scene = {
                scene.get("scene"): scene.get("image_prompt")
                for scene in pre_optimization_scenes
            }
            optimized_scene_ids = {
                scene.get("scene")
                for scene in data["scenes"]
                if before_prompt_by_scene.get(scene.get("scene")) != scene.get("image_prompt")
            }
        except Exception as exc:
            print(f"Prompt optimization step failed: {exc}")

    if config.ENABLE_PROMPT_LEARNING and data.get("prompt_metrics"):
        try:
            prompt_learning_service.learn_from_scenes(
                data["scenes"], data.get("scene_plan"), data["prompt_metrics"],
            )
        except Exception as exc:
            print(f"Prompt learning step failed: {exc}")

    if config.ENABLE_AI_DIRECTOR:
        try:
            best_pattern = (
                prompt_learning_service.get_best_pattern()
                if config.ENABLE_PROMPT_LEARNING else None
            )
            data["director_decision"] = ai_director_service.evaluate_scenes(
                data["scenes"],
                data.get("scene_plan"),
                data.get("prompt_metrics"),
                data.get("asset_quality_results"),
                best_pattern,
                optimized_scene_ids,
            )
        except Exception as exc:
            print(f"AI director step failed: {exc}")

    # Sprint60 - Smart Visual Selection v1: 최종 image_prompt(enrichment/
    # optimization까지 다 반영된 뒤)를 기준으로 scene마다 real/ai를
    # 정한다. scene_plan(ENABLE_SCENE_PLANNER) 오버레이와 달리 항상
    # 실행된다 - asset 선택에 직접 쓰이는 필수 분기이기 때문이다.
    data["scenes"] = scene_planner_service.apply_visual_type(
        data["scenes"],
    )

    # Sprint77 - Asset Planner v1: 기본적으로 꺼져 있고, 켜져도
    # asset_plan은 step02_assets.collect_assets()가 이미 하던 계산을
    # 미리 한 번 해서 넘겨줄 뿐이라 오늘 시점 결과물은 바뀌지 않는다
    # (data.get("asset_plan")이 None이면 collect_assets()가 기존
    # 계산 경로로 그대로 폴백 - 완전히 하위 호환).
    if config.ENABLE_ASSET_PLANNER:
        try:
            data["asset_plan"] = asset_planner.plan_asset_strategy(data["scenes"])
        except Exception as exc:
            print(f"Asset planner step failed: {exc}")

    collect_assets_kwargs = dict(step02_asset_kwargs)
    if data.get("asset_plan"):
        collect_assets_kwargs["asset_plan"] = data["asset_plan"]

    t0 = time.perf_counter()
    data["scenes"] = step02_assets.collect_assets(
        data["scenes"],
        project_path,
        channel,
        **collect_assets_kwargs,
    )
    _save_script(project_path, data)
    timings["image_generation"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    step03_tts.run(
        data["scenes"],
        project_path,
        **step03_duration_kwargs,
    )
    timings["tts_generation"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    step04_subtitle.run(
        project_path,
    )
    timings["subtitle_generation"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    step05_video.run(
        project_path,
    )
    timings["video_rendering"] = time.perf_counter() - t0

    scene1 = data["scenes"][0]

    t0 = time.perf_counter()
    step06_thumbnail.run(
        data["title"],
        topic,
        project_path,
        channel,
        scene1["narration"],
        scene1["image_prompt"],
    )
    timings["thumbnail_generation"] = time.perf_counter() - t0

    try:
        step07_quality.run(
            project_path,
            data,
            timings,
            pipeline_start,
        )
    except Exception as exc:
        print(f"Quality evaluation step failed: {exc}")
    else:
        try:
            regeneration_service.run(project_path)
        except Exception as exc:
            print(f"Regeneration step failed: {exc}")

    return data
