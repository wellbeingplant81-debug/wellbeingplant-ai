import os
from datetime import datetime
from pathlib import Path

from app.utils.atomic_write import atomic_write_json


# 모든 프로젝트가 놓이는 루트. resolve_project_path()가 이 밖으로는
# 절대 나가지 않는다.
OUTPUT_ROOT = "output"


def resolve_project_path(project_id: str) -> str:
    """
    Sprint65 - HTTP로 들어온 project_id를 실제 프로젝트 경로로 바꾼다.

    라우터가 파일 경로를 그대로 받으면 요청 하나로 OUTPUT_ROOT 밖의
    아무 디렉터리나 가리킬 수 있다. 그래서 경로가 아니라 "프로젝트
    이름"만 받고, 그 이름에 경로 구분자나 상위 참조가 섞여 있으면
    해석을 시도조차 하지 않는다.

    형식이 잘못됐으면 ValueError, 형식은 맞지만 그런 프로젝트가 없으면
    FileNotFoundError를 던진다 - 라우터는 이 둘을 각각 400과 404로
    옮긴다.
    """

    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id가 비어 있습니다.")

    candidate = project_id.strip()

    if candidate in (".", ".."):
        raise ValueError(f"project_id가 올바르지 않습니다: {project_id!r}")

    if os.path.basename(candidate) != candidate:
        raise ValueError(
            f"project_id에 경로 구분자를 쓸 수 없습니다: {project_id!r}"
        )

    # os.path.basename은 Windows에서도 "/"를 구분자로 보지만, 드라이브
    # 문자(예: "C:")는 걸러내지 못하므로 따로 막는다.
    if os.path.splitdrive(candidate)[0] or "\\" in candidate or "/" in candidate:
        raise ValueError(
            f"project_id에 경로 구분자를 쓸 수 없습니다: {project_id!r}"
        )

    project_path = os.path.join(OUTPUT_ROOT, candidate)

    if not os.path.isdir(project_path):
        raise FileNotFoundError(
            f"프로젝트를 찾을 수 없습니다: {candidate}"
        )

    return project_path


def create_project(topic: str, channel: str):

    project_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    project_path = Path(OUTPUT_ROOT) / project_id

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