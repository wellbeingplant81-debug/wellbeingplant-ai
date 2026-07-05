import os

from app.services.scene_planner import create_scene_plan
from app.utils.atomic_write import atomic_write_json


def run(
    topic: str,
    project_path: str,
    target_duration: int = 45,
):

    scene_plan = create_scene_plan(
        topic=topic,
        target_duration=target_duration,
    )

    atomic_write_json(
        os.path.join(project_path, "scene_plan.json"),
        scene_plan,
    )

    return scene_plan
