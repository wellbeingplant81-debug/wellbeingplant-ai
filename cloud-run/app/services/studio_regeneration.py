"""
Sprint81 - Studio에서 재생성을 돌리는 orchestration 계층.

엔진 로직을 옮겨오지 않는다. 무엇을 재생성할지, 예산이 남았는지,
되돌릴지는 전부 regeneration_service와 regeneration_policy가 정한다.
여기서 하는 일은 세 가지뿐이다.

  1. 재생성 전 이미지를 스냅샷한다. Before/After를 보여 주려면 필요한데
     엔진의 백업은 사이클이 끝나면 사라진다 - 그게 맞다. 엔진의 백업은
     되돌리기용이지 보여 주기용이 아니고, 남겨 두면 프로젝트마다 쓰지도
     않는 사본이 쌓인다.

  2. regeneration_service.run()을 부른다.

  3. 엔진이 남긴 regeneration_log.json과 quality_report.json을 읽어
     화면이 쓸 모양으로 바꾼다.

비용에 대해 - 엔진은 재생성 루프가 끝난 뒤 영상을 한 번만 다시 만들고
한 번만 재평가한다(Sprint73에서 사이클마다 렌더하던 것을 걷어냈다).
scene을 하나씩 따로 재생성하면 그 렌더와 평가가 scene 수만큼 반복된다.
화면이 "실패 scene 전부"를 기본으로 두는 이유다.
"""

import os
import shutil

from app.services import regeneration_service


# 재생성 직전 이미지를 두는 곳. images/ 밖에 두는 이유는 그 안의
# scene*.png를 훑는 단계들이 이것을 scene으로 착각하지 않게 하기
# 위해서다.
BEFORE_DIRNAME = "studio_before"

REGENERATION_LOG_FILENAME = regeneration_service.REGENERATION_LOG_FILENAME


def _load(path: str):
    import json

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def before_dir(project_path: str) -> str:
    return os.path.join(project_path, BEFORE_DIRNAME)


def snapshot_before(project_path: str, scenes) -> list:
    """
    재생성 직전 이미지를 떠 둔다. 뜬 scene 번호를 반환한다.

    없는 scene을 지목해도 예외를 던지지 않는다 - 스냅샷 실패가 재생성을
    막을 이유는 없고, Before가 없으면 화면이 After만 보여 주면 된다.
    """

    directory = before_dir(project_path)
    os.makedirs(directory, exist_ok=True)

    taken = []

    for number in (scenes or []):
        source = os.path.join(
            project_path, "images", f"scene{number}.png",
        )

        if not os.path.exists(source):
            continue

        try:
            shutil.copy2(
                source, os.path.join(directory, f"scene{number}.png"),
            )
            taken.append(number)
        except OSError:
            continue

    return taken


def _failed_scene_numbers(project_path: str) -> list:
    report = _load(os.path.join(project_path, "quality_report.json")) or {}
    evaluation = report.get("ai_quality_evaluation") or {}

    return [
        scene.get("scene")
        for scene in evaluation.get("scenes", [])
        if scene.get("regenerate")
    ]


def regenerate(project_path: str, scenes=None):
    """
    재생성을 돌린다. scenes가 None이면 엔진이 대상을 스스로 정한다.

    엔진에 넘기기 전에 스냅샷을 뜨는 순서가 중요하다 - generate_image는
    원본 파일을 그대로 덮어쓰므로, 뒤에 뜨면 Before가 After가 된다.

    지목된 scene이 실제로 재생성될지는 여기서 판단하지 않는다. 통과한
    scene이나 재시도 한도에 도달한 scene은 정책이 걸러낸다.
    """

    targets = scenes if scenes is not None else _failed_scene_numbers(
        project_path,
    )

    snapshot_before(project_path, targets)

    return regeneration_service.run(project_path, only_scenes=scenes)


def regeneration_view(project_path: str) -> dict:
    """
    엔진이 남긴 결정을 화면이 읽을 모양으로. 순수 읽기입니다.

    scenes는 재생성이 실제로 일어난 scene만 담는다 - 한 번도 손대지
    않은 scene에 "재시도 0회"를 붙여 두면 화면이 시끄러워진다.
    """

    log = _load(os.path.join(project_path, REGENERATION_LOG_FILENAME))
    report = _load(os.path.join(project_path, "quality_report.json")) or {}

    rolled_back = sorted({
        number
        for cycle in ((log or {}).get("cycles") or [])
        for number in (cycle.get("rolled_back") or [])
    })

    scenes = {}

    for entry in report.get("regeneration") or []:
        state = entry.get("regeneration") or {}
        history = state.get("retry_history") or []

        scenes[entry.get("scene")] = {
            "retry_count": state.get("retry_count", 0),
            "final_status": state.get("final_status"),
            "history": history,
            "was_rolled_back": any(
                attempt.get("outcome") == "rolled_back"
                for attempt in history
            ),
        }

    if log is None:
        return {
            "has_run": False,
            "cycles": [],
            "scenes": scenes,
            "rolled_back_scenes": [],
            "stop_reason": None,
            "stop_explanation": None,
            "total_image_calls": 0,
            "max_image_calls": None,
            "budget_remaining": None,
            "rendered": False,
        }

    spent = log.get("total_image_calls", 0)
    budget = log.get("max_image_calls")

    return {
        "has_run": True,
        "cycles": log.get("cycles") or [],
        "scenes": scenes,
        "rolled_back_scenes": rolled_back,
        "stop_reason": log.get("stop_reason"),
        "stop_explanation": log.get("stop_explanation"),
        "total_image_calls": spent,
        "max_image_calls": budget,
        "budget_remaining": (
            None if budget is None else max(0, budget - spent)
        ),
        "rendered": bool(log.get("rendered")),
    }
