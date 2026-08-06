"""
Sprint107 - 붙여넣은 대본으로 프로젝트를 만든다 (Epic 54, Phase 6).

Sprint105의 화면은 읽어서 보여주는 데서 끝났다. 여기서 그것을 실제
프로젝트로 만든다 - 그러면 기존 "영상 생성" 버튼이 그대로 그 프로젝트를
집어 들 수 있다.

새로 만드는 것은 없다. project_service.create_project()를 그대로
부르므로 타임스탬프 규칙도 폴더 구조도 예전과 같고, script.json은
Chat Import Provider가 이미 엔진 형식으로 만들어 둔 것을 그대로 쓴다 -
여기서 한 번 더 변환하지 않는다.

출처는 project.json에 적어 둔다. Resolver가 디스크 상태로 추측하지
않고 그것을 그대로 읽는다 - 프로젝트를 만든 쪽이 직접 남긴 것이
가장 확실한 근거다.
"""

import json
import os

from app.services import project_service
from app.steps.step01_script_resolve import SOURCE_FIELD, SOURCES


def _mark_source(project_path: str, source: str) -> None:
    """project.json에 출처를 더한다.

    create_project()를 고치지 않으려고 여기서 읽어 다시 쓴다 - 그
    함수는 모든 프로젝트가 쓰는 자리라, 붙여넣기 하나 때문에 시그니처를
    바꾸지 않는다.
    """

    path = os.path.join(project_path, "project.json")

    with open(path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    metadata[SOURCE_FIELD] = source

    from app.utils.atomic_write import atomic_write_json

    atomic_write_json(path, metadata)


def create_from_script(script: dict, topic: str, channel: str,
                       source: str) -> dict:
    """
    이미 읽어 둔 대본으로 프로젝트를 만든다.

    script는 Chat Import Provider가 돌려준 것 그대로다 - 여기서
    검증하지 않는다. 검증은 읽을 때 이미 했고, 파이프라인이 시작될 때
    Resolver가 한 번 더 한다.
    """

    if source not in SOURCES:
        raise ValueError(
            f"알 수 없는 대본 출처입니다: {source!r}. 사용 가능한 값: {list(SOURCES)}"
        )

    project = project_service.create_project(topic, channel)
    project_path = str(project["path"])

    with open(
        os.path.join(project_path, "script.json"), "w", encoding="utf-8",
    ) as f:
        json.dump(script, f, ensure_ascii=False, indent=4)

    _mark_source(project_path, source)

    return {
        "project_id": project["id"],
        "project_path": project_path,
        "source": source,
        "title": script.get("title", ""),
        "scene_count": len(script.get("scenes") or []),
    }
