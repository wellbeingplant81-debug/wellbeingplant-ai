from datetime import datetime
from pathlib import Path

from app.utils.atomic_write import atomic_write_json


def create_project(topic: str, channel: str):

    project_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    project_path = Path("output") / project_id

    (project_path / "images").mkdir(parents=True, exist_ok=True)
    (project_path / "audio").mkdir(parents=True, exist_ok=True)
    (project_path / "video").mkdir(parents=True, exist_ok=True)

    # Immutable project metadata - readable by any pipeline stage,
    # not just the step that first needs it.
    metadata = {
        "project_id": project_id,
        "topic": topic,
        "channel": channel,
    }

    atomic_write_json(
        str(project_path / "project.json"),
        metadata,
    )

    return {
        "id": project_id,
        "path": project_path
    }