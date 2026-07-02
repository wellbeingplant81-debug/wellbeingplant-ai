from datetime import datetime
from pathlib import Path


def create_project():

    project_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    project_path = Path("output") / project_id

    (project_path / "images").mkdir(parents=True, exist_ok=True)
    (project_path / "audio").mkdir(parents=True, exist_ok=True)
    (project_path / "video").mkdir(parents=True, exist_ok=True)

    return {
        "id": project_id,
        "path": project_path
    }