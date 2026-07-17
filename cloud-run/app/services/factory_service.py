import time

from app.pipeline.pipeline import run_pipeline
from app.services.project_service import create_project


def generate_short_video(
    topic: str,
    channel: str = "wellbeing",
    production_profile_name: str = None,
    render_profile_name: str = None,
):

    pipeline_start = time.perf_counter()

    t0 = time.perf_counter()
    project = create_project(topic, channel)
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
        production_profile_name=production_profile_name,
        render_profile_name=render_profile_name,
    )

    return {
        "success": True,
        "project_id": project["id"],
        "title": data["title"],
        "channel": channel,
        "output": project_path,
    }