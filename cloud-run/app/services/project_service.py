import os
from datetime import datetime
from pathlib import Path

from app.utils.atomic_write import atomic_write_json


# 모든 프로젝트가 놓이는 루트. resolve_project_path()가 이 밖으로는
# 절대 나가지 않는다.
#
# Sprint169 - 실행 파일로 묶이면 코드 옆이 읽기 전용이 된다. 그때는
# 사용자 자리로 간다. 개발 중에는 예전 그대로 "output"이다 - 어제까지
# 만든 것이 사라진 것처럼 보이면 안 된다.
from app import runtime_paths

OUTPUT_ROOT = runtime_paths.output_root()


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

    # Sprint222 - 같은 초에 두 번 만들면 같은 이름이 나온다.
    #
    # 사람이 손으로 만들 때는 드러나지 않았다. 그런데 이제 화면이
    # 자료를 받으면서 프로젝트를 대신 만든다 - 파일을 고르고 곧바로
    # 폴더를 고르거나, 창이 둘이거나, 두 번 눌리면 같은 초에 두 번
    # 부른다. 그때 두 번째 프로젝트는 첫 번째와 **같은 폴더**가 되고,
    # 사람이 넣은 자료가 남의 프로젝트에 섞인다(실측: test_staging의
    # 기존_프로젝트에_넣으면_그_프로젝트로_간다가 이것으로 걸렸다).
    #
    # 이름의 앞부분은 그대로 둔다 - list_projects가 "이름이 타임스탬프라
    # 이름 역순이 곧 최신순"이라고 적어 두고 그 규칙으로 센다.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_id = stamp
    nth = 2

    while (Path(OUTPUT_ROOT) / project_id).exists():
        project_id = f"{stamp}_{nth}"
        nth += 1

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