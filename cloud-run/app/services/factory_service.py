from app.pipeline.pipeline import run_pipeline
from app.services.project_service import create_project


def generate_short_video(
    topic: str,
    channel: str = "wellbeing",
):

    project = create_project()

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
    )

    return {
        "success": True,
        "project_id": project["id"],
        "title": data["title"],
        "channel": channel,
        "output": project_path,
    }