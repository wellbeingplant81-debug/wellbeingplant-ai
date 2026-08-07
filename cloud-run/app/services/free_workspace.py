"""
Sprint152 - 내 자료 폴더 하나로 끝낸다 (Epic 57, Phase 3).

Sprint150이 그림을, Sprint151이 소리를 내 PC에서 가져오게 만들었다.
그런데 실제로 쓰려면 프로젝트마다 폴더를 다시 훑어야 했고, 무엇이
모자란지는 렌더를 눌러 봐야 알았다.

여기서 두 가지를 더한다.

    1. 폴더를 한 번 정하면 기억한다        remember / remembered
    2. Scene마다 무엇이 준비됐는지 말한다   preparation

Provider를 다시 만들지 않는다
-----------------------------
"이 scene에 쓸 그림이 있는가"를 여기서 따로 판정하지 않는다.
local_stock_provider.find와 local_voice_provider.find를 그대로 부른다.

여기서 따로 판정하면 화면이 "있다"고 한 것을 Provider가 못 찾는 날이
온다 - 같은 질문에 두 개의 답이 생기기 때문이다. 실제로 고르는 쪽이
답하게 두고, 우리는 그 답을 옮기기만 한다.

"만들 수 있다"와 "이미 만들었다"는 다른 말이다
----------------------------------------------
    made        이미 그 파일이 프로젝트에 있다
    workspace   내 자료에 있어서 만들 수 있다
    None        없다

둘을 "준비됨" 하나로 뭉치면 사람은 어느 쪽인지 모른 채 렌더를 누른다.
그래서 from에 어느 쪽인지 적는다.

폴더 이름
---------
사양은 voices/이고 Sprint150·151이 만든 것은 voice/다. 둘 다 받는다 -
그 결정은 local_library.ALIASES가 들고 있고 여기서 다시 정하지 않는다.
"""

import json
import os

from app.services import audio_policy, local_library

STORE_FILENAME = "free_workspace.json"

VERSION = 1

# 화면이 쓰는 이름. local_library의 종류를 그대로 따른다.
KINDS = local_library.KINDS


class WorkspaceError(ValueError):
    """그 폴더를 쓸 수 없다.

    무엇이 왜 안 되는지 적는다 - 사람이 고쳐서 다시 고를 수 있어야
    한다."""


def default_store_path() -> str:
    """
    정해 둔 폴더를 적는 곳. 프로젝트 디렉터리 밖이다.

    승인 기록(studio_upload.default_store_path)이 사는 그 자리를 쓴다 -
    사용자 한 사람의 결정이 사는 곳을 두 군데 만들지 않는다.
    """

    from app.pipeline.pipeline import DATASET_ROOT

    return os.path.join(
        os.path.dirname(DATASET_ROOT), ".workflow", STORE_FILENAME,
    )


def remembered(store_path: str) -> dict:
    """
    정해 둔 폴더. 정한 적이 없으면 root가 None이다.

    깨져 있으면 없는 것으로 읽는다 - 기억 하나가 망가졌다고 화면
    전체가 죽을 이유는 없다.
    """

    try:
        with open(store_path, encoding="utf-8") as f:
            found = json.load(f)
    except Exception:
        return {"version": VERSION, "root": None}

    if not isinstance(found, dict) or not isinstance(found.get("root"), str):
        return {"version": VERSION, "root": None}

    return {"version": VERSION, "root": found["root"]}


def remember(store_path: str, root: str) -> dict:
    """
    이 폴더를 쓰겠다고 적어 둔다.

    없는 곳은 받지 않는다 - 적어 두면 나중에 조용히 빈 목록이 되고,
    사람은 자기가 폴더를 잘못 골랐다는 것을 모른 채 "자료가 없다"는
    말만 보게 된다.
    """

    root = (root or "").strip()

    if not root:
        raise WorkspaceError("폴더를 고르지 않았습니다.")

    if not os.path.isdir(root):
        raise WorkspaceError(f"그런 폴더가 없습니다: {root}")

    directory = os.path.dirname(store_path)

    if directory:
        os.makedirs(directory, exist_ok=True)

    from app.utils.atomic_write import atomic_write_json

    atomic_write_json(store_path, {"version": VERSION, "root": root})

    return {"version": VERSION, "root": root}


def forget(store_path: str) -> dict:
    """정해 둔 것을 지운다. 폴더와 파일은 건드리지 않는다."""

    try:
        os.remove(store_path)
    except OSError:
        pass

    return {"version": VERSION, "root": None}


def inventory(root: str) -> dict:
    """
    그 폴더에 종류마다 몇 개 있는가.

    없는 폴더는 전부 0이다 - 예외를 던지지 않는다. 화면이 "아직
    아무것도 없다"를 그릴 수 있어야 한다.
    """

    if not root or not os.path.isdir(root):
        return {kind: 0 for kind in KINDS}

    return local_library.counts(local_library.scan(root))


def _made_image(project_path: str, number) -> bool:
    """이미 만들어진 그림. 엔진이 쓰는 그 이름이다."""

    return os.path.exists(
        os.path.join(project_path, "images", f"scene{number}.png")
    )


def _made_voice(project_path: str, number) -> bool:
    """이미 만들어진 음성. 이름은 audio_policy가 정한다."""

    return os.path.exists(os.path.join(
        project_path, "audio", "scenes",
        audio_policy.scene_audio_filename(number),
    ))


def _image_status(project_path: str, scene) -> dict:
    """
    이 scene의 그림은 어떤 상태인가.

    이미 만든 것이 먼저다 - 있으면 그것을 쓰고 내 자료를 다시 보지
    않는다. 그 다음이 내 자료에서 고를 수 있는가이고, 그 판단은
    local_stock_provider가 한다.
    """

    number = scene.get("scene")

    if _made_image(project_path, number):
        return {"ready": True, "from": "made", "name": f"scene{number}.png",
                "kind": None}

    from app.providers import local_stock_provider

    picked = local_stock_provider.find(
        project_path, scene.get("image_prompt") or "",
    )

    if picked is None:
        return {"ready": False, "from": None, "name": None, "kind": None}

    return {
        "ready": True,
        "from": "workspace",
        "name": picked["name"],
        # 영상에서 온 것인지 그림에서 온 것인지. 화면이 "영상 선택"을
        # 여기서 읽는다.
        "kind": picked["kind"],
    }


def _voice_status(project_path: str, scene) -> dict:
    """이 scene의 음성. 판단은 local_voice_provider가 한다."""

    number = scene.get("scene")

    if _made_voice(project_path, number):
        return {
            "ready": True, "from": "made",
            "name": audio_policy.scene_audio_filename(number),
            "seconds": None,
        }

    from app.providers import local_voice_provider

    picked = local_voice_provider.find(project_path, number)

    if picked is None:
        return {"ready": False, "from": None, "name": None, "seconds": None}

    return {
        "ready": True,
        "from": "workspace",
        "name": picked["name"],
        # 훑을 때 재 둔 값. 여기서 다시 재지 않는다.
        "seconds": picked.get("duration"),
    }


def preparation(project_path: str, scenes: list) -> dict:
    """
    지금 이 프로젝트를 무료로 만들 수 있는가. Scene마다 말한다.

    고쳐 주지 않는다. 만들지도 않는다. 무엇이 있고 무엇이 없는지만
    말한다 - 렌더를 누르고 몇 분 뒤에 아는 것보다 낫다.
    """

    index = local_library.load(project_path)
    scanned = bool(index.get("items"))

    rows = []
    ready = {"script": 0, "images": 0, "voice": 0, "videos": 0}
    missing = []

    for scene in scenes or []:
        number = scene.get("scene")

        has_script = bool((scene.get("narration") or "").strip())
        image = _image_status(project_path, scene)
        voice = _voice_status(project_path, scene)
        from_video = image["kind"] == local_library.VIDEOS

        rows.append({
            "scene": number,
            "script": has_script,
            "image": image,
            "voice": voice,
            # 사양의 "영상 선택". 이 scene의 그림이 영상에서 왔는가다.
            "video": from_video,
        })

        if has_script:
            ready["script"] += 1
        else:
            missing.append(f"Scene {number} 대본")

        if image["ready"]:
            ready["images"] += 1
        else:
            missing.append(f"Scene {number} 이미지")

        if from_video:
            ready["videos"] += 1

        if voice["ready"]:
            ready["voice"] += 1
        else:
            missing.append(f"Scene {number} 음성")

    return {
        "scanned": scanned,
        "root": index.get("root"),
        "total": len(rows),
        "ready": ready,
        "missing": missing,
        "scenes": rows,
    }
