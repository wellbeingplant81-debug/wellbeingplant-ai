import time

from app.pipeline.pipeline import run_pipeline
from app.services.project_service import create_project, resolve_project_path


def generate_short_video(
    topic: str,
    channel: str = "wellbeing",
    project_id: str = None,
):
    """
    Sprint107 - project_id를 주면 그 프로젝트로 만든다.

    붙여넣은 대본으로 이미 만들어 둔 프로젝트가 있을 때 쓴다. 주지
    않으면(기본값) 예전과 똑같이 새 프로젝트를 만든다 - 기존 호출부는
    전혀 영향받지 않는다.

    새 Generate 경로를 만들지 않으려고 여기에 인자 하나를 더했다.
    화면의 버튼도, 그 버튼이 부르는 엔드포인트도 하나 그대로다.
    """

    pipeline_start = time.perf_counter()

    t0 = time.perf_counter()

    if project_id:
        project = {
            "id": project_id,
            "path": resolve_project_path(project_id),
        }
    else:
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
    )

    return {
        "success": True,
        "project_id": project["id"],
        "title": data["title"],
        "channel": channel,
        "output": project_path,
    }