"""
Sprint145 - 순서는 따로 적는다 (Epic 56, Phase 22).

Sprint144에서 Timeline 이동을 넣지 못한 이유가 둘이었다.

    video_builder는 asset을 script.json 목록 순서로 모으고 길이는
    build_timeline(scene 번호 정렬) 순서로 만들어 index로 짝짓는다.
    번호를 두고 순서만 바꾸면 3번 그림에 2번 길이가 붙는다.

    subtitle_service는 audio/scenes/scene*.wav를 세어 scene 수와
    맞지 않으면 멈춘다. script.json에서 빼도 wav는 남는다.

이번에 그 둘을 푼다. 다만 번호와 파일 이름은 건드리지 않는다.

    번호      한 번 준 것을 다시 쓰지 않는다
    파일      images/scene{N}.png · audio/scenes/scene{N}.wav 그대로
    순서      여기, timeline.json에 따로 적는다

순서를 script.json에 섞지 않는 이유
-----------------------------------
script.json은 "무엇을 말하는가"이고 timeline.json은 "어떤 차례로
보여 주는가"다. 둘을 한 파일에 두면 대본을 고칠 때마다 순서가 함께
흔들리고, 어느 쪽이 진실인지 알 수 없게 된다.

없으면 예전 그대로다
--------------------
timeline.json이 없는 프로젝트는 손대지 않은 프로젝트다. 그때는 받은
목록을 그대로 돌려준다 - 기존 Auto Pipeline은 아무것도 달라지지
않는다.

지우는 것은 표시만 한다
-----------------------
파일을 지우지 않는다. deleted에 번호를 적어 두고 렌더에서 빼기만
한다 - 되돌릴 수 있어야 하고, 지운 뒤에 마음이 바뀌는 일은 흔하다.
"""

import json
import os

TIMELINE_FILENAME = "timeline.json"

VERSION = 1


def _path(project_path: str) -> str:
    return os.path.join(project_path, TIMELINE_FILENAME)


def load(project_path: str) -> dict:
    """
    적어 둔 순서. 없으면 빈 것을 돌려준다.

    읽을 수 없는 파일 때문에 제작이 멈추지는 않는다 - 그때도 예전
    순서로 도는 것이 맞다.
    """

    try:
        with open(_path(project_path), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"order": [], "deleted": []}

    if not isinstance(data, dict):
        return {"order": [], "deleted": []}

    return {
        "order": [n for n in (data.get("order") or []) if isinstance(n, int)],
        "deleted": [
            n for n in (data.get("deleted") or []) if isinstance(n, int)
        ],
    }


def save(project_path: str, order=None, deleted=None) -> dict:
    """사람이 정한 차례를 적는다. 대본은 건드리지 않는다."""

    current = load(project_path)

    data = {
        "version": VERSION,
        "order": list(order) if order is not None else current["order"],
        "deleted": (
            list(deleted) if deleted is not None else current["deleted"]
        ),
    }

    with open(_path(project_path), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return data


def _numbers(scenes) -> list:
    return [scene.get("scene") for scene in scenes]


def for_render(project_path: str, scenes: list) -> list:
    """
    렌더가 볼 차례대로 늘어놓는다. scene 자체는 고치지 않는다.

    적어 둔 것이 없으면 받은 그대로다 - 예전 프로젝트가 달라지지
    않아야 한다.

    적어 둔 순서에 없는 번호는 뒤에 붙인다. 대본에 scene이 새로
    생겼는데 순서를 아직 적지 않은 경우이고, 그때 그 scene을 잃는
    것보다 뒤에 두는 편이 낫다.
    """

    if not scenes:
        return list(scenes)

    plan = load(project_path)

    if not plan["order"] and not plan["deleted"]:
        return list(scenes)

    deleted = set(plan["deleted"])
    alive = [s for s in scenes if s.get("scene") not in deleted]

    by_number = {s.get("scene"): s for s in alive}

    ordered = [
        by_number.pop(number)
        for number in plan["order"]
        if number in by_number
    ]

    # 순서에 적히지 않은 것은 원래 있던 차례대로 뒤에 붙인다.
    ordered.extend(s for s in alive if s.get("scene") in by_number)

    return ordered


def render_problems(project_path: str, scenes: list) -> list:
    """
    지금 렌더를 걸면 무엇이 걸리는가. 고쳐 주지 않고 말만 한다.

    렌더 도중에 멈추면 이미 몇 분을 쓴 뒤다. 그 전에 사람이 읽을 수
    있는 말로 알려 준다.
    """

    from app.services import audio_policy

    problems = []
    ordered = for_render(project_path, scenes)

    if not ordered:
        return ["보여 줄 Scene이 하나도 없습니다."]

    for scene in ordered:
        number = scene.get("scene")

        if not (scene.get("narration") or "").strip():
            problems.append(f"Scene {number} 대본이 없습니다")

        image = os.path.join(project_path, "images", f"scene{number}.png")
        if not os.path.exists(image):
            problems.append(f"Scene {number} 이미지가 없습니다")

        voice = os.path.join(
            project_path, "audio", "scenes",
            audio_policy.scene_audio_filename(number),
        )
        if not os.path.exists(voice):
            problems.append(f"Scene {number} 음성이 없습니다")

    return problems
