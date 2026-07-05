import time

from app.pipeline.pipeline import run_pipeline
from app.services.project_service import create_project


def generate_short_video(
    topic: str,
    channel: str = "wellbeing",
):

    pipeline_start = time.perf_counter()

    t0 = time.perf_counter()
    project = create_project()
    project_creation_time = time.perf_counter() - t0

    project_path = str(
        project["path"]
    )

    print(
        f"Project : {project_path}"
    )

    data = run_pipeline(
        topic=topic,
        project_path=project_path,
        channel=channel,
        project_creation_time=project_creation_time,
        pipeline_start=pipeline_start,
    )

    return {
        "success": True,
        "project_id": project["id"],
        "title": data["title"],
        "channel": channel,
        "output": project_path,
    }