import json
import os
import time

from app import config
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


def run_pipeline(
    topic: str,
    project_path: str,
    channel: str,
    project_creation_time: float = 0.0,
    pipeline_start: float = None,
):

    if pipeline_start is None:
        pipeline_start = time.perf_counter()

    timings = {
        "project_creation": project_creation_time,
    }

    t0 = time.perf_counter()
    data = step01_script.run(
        topic,
        project_path,
    )
    timings["script_generation"] = time.perf_counter() - t0

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

    if config.ENABLE_PROMPT_OPTIMIZATION and data.get("prompt_metrics"):
        try:
            data["scenes"] = prompt_optimization_service.optimize_scenes(
                pre_enrichment_scenes,
                data["scenes"],
                data["prompt_metrics"],
                data.get("scene_plan"),
            )
        except Exception as exc:
            print(f"Prompt optimization step failed: {exc}")

    if config.ENABLE_PROMPT_LEARNING and data.get("prompt_metrics"):
        try:
            prompt_learning_service.learn_from_scenes(
                data["scenes"], data.get("scene_plan"), data["prompt_metrics"],
            )
        except Exception as exc:
            print(f"Prompt learning step failed: {exc}")

    t0 = time.perf_counter()
    data["scenes"] = step02_assets.collect_assets(
        data["scenes"],
        project_path,
        channel,
    )
    _save_script(project_path, data)
    timings["image_generation"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    step03_tts.run(
        data["scenes"],
        project_path,
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
