import time

from app.steps import step01_script
from app.steps import step02_image
from app.steps import step03_tts
from app.steps import step04_subtitle
from app.steps import step05_video
from app.steps import step06_thumbnail
from app.steps import step07_quality


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

    t0 = time.perf_counter()
    step02_image.run(
        data["scenes"],
        project_path,
        channel,
    )
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

    return data
