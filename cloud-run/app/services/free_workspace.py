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


def status(store_path: str) -> dict:
    """
    Sprint153 - 지금 내 자료 폴더가 어떤 상태인가. 화면이 그대로 그린다.

    folders를 함께 준다 - 처음 쓰는 사람은 어떤 폴더를 만들어야
    하는지 모른다. 이름은 local_library가 아는 것을 그대로 옮긴다.
    """

    found = remembered(store_path)

    return {
        "root": found["root"],
        "counts": inventory(found["root"]),
        # 훑는 폴더 이름들. 별칭이 있으면 첫째(기준 이름)를 보여 준다.
        "folders": [local_library._folders(kind)[-1] for kind in KINDS],
    }


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


def _is_weak(picked: dict) -> bool:
    """
    Sprint157 - 근거가 가장 약한 경우인가.

    "몇 퍼센트 이하면 약하다"는 숫자를 만들지 않았다. 그런 숫자는
    근거가 없고, 한 번 적어 두면 아무도 왜 그 값인지 설명하지 못한다.

    대신 셀 수 있는 사실만 쓴다 - 낱말 하나로만 걸렸는데 프롬프트에는
    낱말이 더 있었다면, 그것이 우리가 가진 가장 약한 근거다. 0개는
    아예 안 걸린 것이므로 1개가 최소값이다.

    낱말이 하나뿐인 프롬프트에서 1/1은 전부 맞은 것이라 약하지 않다.
    """

    return picked["matched_count"] == 1 and picked["total_keywords"] > 1


# Sprint159 - 무엇을 쓰는가. 앞의 것이 이긴다.
#
#     override   사람이 보고 정했다
#     generated  이미 만들어 둔 파일이 있다
#     matched    낱말로 우리가 골랐다
#
# Sprint158까지는 generated가 override보다 앞이었다. 그래서 한 번
# 만들고 나면 화면이 "만들어 둠"이라고만 했고, 사람이 정한 것이 아직
# 살아 있는지 알 수 없었다. 만드는 쪽은 그때도 override를 따르고
# 있었으므로(collect_assets는 기존 파일을 건너뛰지 않는다), 여기서
# 뒤집는 것은 화면이 말하는 순서다.
OVERRIDE = "override"
GENERATED = "generated"
MATCHED = "matched"


def _made_status(project_path: str, number) -> dict:
    """이미 만들어 둔 그림. 고른 것이 아니라 그 scene의 제 파일이다."""

    return {
        "ready": True, "from": "made", "asset_source": GENERATED,
        "name": f"scene{number}.png", "kind": None,
        "path": os.path.join(project_path, "images", f"scene{number}.png"),
        "chosen_by": None,
        "selected_at": None, "selected_by": None, "instead_of": None,
        "matched_keywords": [], "matched_count": None,
        "total_keywords": None, "weak": False,
    }


def _image_status(project_path: str, scene) -> dict:
    """
    이 scene의 그림은 어떤 상태인가.

    사람이 정한 것이 먼저다(Sprint159). 그 다음이 이미 만들어 둔 것,
    마지막이 내 자료에서 낱말로 고른 것이다. 고르는 판단은 여기서
    하지 않는다 - local_stock_provider가 한다.
    """

    number = scene.get("scene")
    prompt = scene.get("image_prompt") or ""

    from app.providers import local_stock_provider

    picked = local_stock_provider.match(project_path, prompt, number)

    if picked is not None and picked["chosen_by"] == "user":
        from app.services import asset_override

        decision = asset_override.decision_for(project_path, number) or {}

        # 사람이 정한 것 대신 무엇이 쓰였을지. 화면이 "자동 매칭
        # ...(사용 안 함)"이라고 말할 근거다.
        if _made_image(project_path, number):
            instead = {"source": GENERATED, "file": f"scene{number}.png"}
        else:
            auto = local_stock_provider.match(project_path, prompt)
            instead = (None if auto is None
                       else {"source": MATCHED, "file": auto["file"]})

        return {
            "ready": True,
            "from": OVERRIDE,
            "asset_source": OVERRIDE,
            "chosen_by": picked["chosen_by"],
            "name": picked["file"],
            "path": picked["path"],
            "kind": picked["kind"],
            "selected_at": decision.get("selected_at"),
            "selected_by": decision.get("selected_by"),
            "instead_of": instead,
            "matched_keywords": picked["matched_keywords"],
            "matched_count": picked["matched_count"],
            "total_keywords": picked["total_keywords"],
            "weak": _is_weak(picked),
        }

    if _made_image(project_path, number):
        # 이미 만든 것은 scene 번호가 곧 파일 이름이라 겹칠 수가 없다.
        #
        # Sprint157 - 고른 것이 아니므로 "몇 낱말로 걸렸다"가 성립하지
        # 않는다. 없는 사실을 적지 않는다.
        return _made_status(project_path, number)

    if picked is None:
        return {"ready": False, "from": None, "name": None, "kind": None,
                "path": None, "chosen_by": None, "asset_source": None,
                "selected_at": None, "selected_by": None, "instead_of": None,
                "matched_keywords": [], "matched_count": None,
                "total_keywords": None, "weak": False}

    return {
        "ready": True,
        "from": "workspace",
        "asset_source": MATCHED,
        "chosen_by": picked["chosen_by"],
        "selected_at": None,
        "selected_by": None,
        "instead_of": None,
        "name": picked["file"],
        # Sprint156 - 어느 파일인지. 이름만으로는 폴더가 다른 같은
        # 이름을 구분하지 못한다.
        "path": picked["path"],
        # 영상에서 온 것인지 그림에서 온 것인지. 화면이 "영상 선택"을
        # 여기서 읽는다.
        "kind": picked["kind"],
        # Sprint157 - 왜 걸렸는가. 고른 쪽이 낸 값을 그대로 옮긴다.
        "matched_keywords": picked["matched_keywords"],
        "matched_count": picked["matched_count"],
        "total_keywords": picked["total_keywords"],
        "weak": _is_weak(picked),
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


# Sprint156 - 여러 Scene이 같은 그림을 쓰는 일.
#
# Sprint155 실측에서 세 Scene이 전부 "40.png" 하나로 채워졌는데
# 화면은 "이미지 3/3 준비 완료"라고만 했다. 낱말 뽑기를 고쳐 그런
# 일이 줄었지만, 없앨 수는 없다 - 사람이 가진 파일이 정말 하나뿐일
# 수도 있다.
#
# 그래서 막지 않고 말한다. 같은 그림을 쓰는 것이 틀린 것은 아니다 -
# 일부러 그렇게 할 수도 있고, 그것은 사람이 정할 일이다.

# Sprint160 - 지금 만들 수 있는가. 셋뿐이다.
#
#     READY    다 있고 볼 것도 없다
#     REVIEW   다 있으나 사람이 봐야 할 것이 있다
#     BLOCKED  없는 것이 있다
#
# BLOCKED만 막는다. REVIEW는 막지 않는다 - 같은 그림을 여러 Scene에
# 쓰는 것도, 낱말 하나로 걸린 것도 사람이 일부러 그랬을 수 있다.
#
# Sprint156~159는 이 값을 "missing"이라 불렀다. 뜻은 같고, 화면이
# "부족"과 "막힘"을 같은 말로 쓰던 것을 바로잡는다.
READY = "ready"
REVIEW = "review"
BLOCKED = "blocked"


def _scene_state(row: dict) -> tuple:
    """
    이 Scene 하나는 어떤 상태인가. (상태, 까닭들).

    까닭을 함께 돌려주는 것이 이 Sprint의 값어치다 - 표를 끝까지
    읽지 않아도 무엇을 봐야 하는지 알 수 있어야 한다.

    사람이 정한 것(override)은 검토 대상이 아니다. 이미 사람이 본
    것이므로, 다시 보라고 하면 자기가 정한 것을 의심하라는 말이 된다.
    """

    image = row["image"]
    voice = row["voice"]

    blocked = []

    if not row["script"]:
        blocked.append("script")

    if not image.get("ready"):
        blocked.append("image")

    if not voice.get("ready"):
        blocked.append("voice")

    if blocked:
        return BLOCKED, blocked

    review = []

    if image.get("asset_source") != OVERRIDE:
        if image.get("weak"):
            review.append("weak")

        if image.get("shared_with"):
            review.append("shared")

    return (REVIEW, review) if review else (READY, [])


def _shared_images(rows: list) -> dict:
    """
    파일 하나에 걸린 Scene 번호들. 둘 이상인 것만 돌려준다.

    경로로 묶는다 - 이름만 보면 폴더가 다른 같은 이름을 한 파일로
    센다.
    """

    by_path = {}

    for row in rows:
        image = row["image"]

        if not image.get("ready") or not image.get("path"):
            continue

        by_path.setdefault(os.path.normcase(image["path"]), []).append(row)

    return {
        path: found for path, found in by_path.items() if len(found) > 1
    }


def _review_notes(shared: dict, rows: list, gone: dict) -> list:
    """
    사람이 읽을 한 줄씩.

    까닭이 둘이다. 하나만 적으면 사람이 나머지 하나를 모른 채 넘어간다.

        여러 Scene이 같은 파일을 쓴다        Sprint156
        낱말 하나로만 걸렸다                  Sprint157
    """

    notes = []

    for _, found in sorted(
        shared.items(), key=lambda pair: pair[1][0]["scene"],
    ):
        numbers = [row["scene"] for row in found]
        name = found[0]["image"]["name"]

        notes.append(
            f"{len(numbers)}개 Scene이 같은 이미지를 사용합니다: "
            f"{name} (Scene {', '.join(str(n) for n in numbers)})"
        )

    for number, path in sorted(gone.items(), key=lambda pair: pair[0]):
        notes.append(
            f"Scene {number}에 정해 둔 파일이 없어졌습니다: "
            f"{os.path.basename(path)} - 지금은 자동으로 고른 것을 씁니다"
        )

    for row in rows:
        image = row["image"]

        if not image.get("weak"):
            continue

        notes.append(
            f"Scene {row['scene']}은(는) 낱말 {image['matched_count']}개로만 "
            f"걸렸습니다: {image['name']} "
            f"({', '.join(image['matched_keywords'])} / "
            f"낱말 {image['total_keywords']}개 중)"
        )

    return notes


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

        # Sprint156 - 같은 그림을 쓰는 Scene은 아래에서 채운다.
        image["shared_with"] = []

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

    shared = _shared_images(rows)

    for found in shared.values():
        numbers = [row["scene"] for row in found]

        for row in found:
            row["image"]["shared_with"] = [
                n for n in numbers if n != row["scene"]
            ]

    # Sprint158 - 사람이 정해 뒀는데 그 파일이 사라진 것들.
    from app.services import asset_override

    review = _review_notes(shared, rows, asset_override.missing(project_path))

    # Sprint160 - Scene 하나씩 판정하고, 전체는 그것을 센다. 두 곳에서
    # 따로 세면 화면에 뜬 숫자가 표와 달라지고, 사람은 어느 쪽을
    # 믿어야 할지 모른다.
    counts = {READY: 0, REVIEW: 0, BLOCKED: 0}

    for row in rows:
        state, reasons = _scene_state(row)

        row["state"] = state
        row["reasons"] = reasons
        counts[state] += 1

    if counts[BLOCKED] or not rows:
        # Scene이 없으면 만들 것이 없다. 빈 것을 "준비 완료"라고 하면
        # 제작 버튼이 열리고, 눌러도 아무 일도 일어나지 않는다.
        state = BLOCKED
    elif counts[REVIEW] or review:
        state = REVIEW
    else:
        state = READY

    return {
        "scanned": scanned,
        "root": index.get("root"),
        "total": len(rows),
        "ready": ready,
        "missing": missing,
        # Sprint156 - 없는 것은 아니지만 사람이 봐야 하는 것들.
        # 자동으로 실패시키지 않는다.
        "review": review,
        "counts": counts,
        "state": state,
        "scenes": rows,
    }


# ---- Sprint153 - 무엇을 어디에 넣으면 되는가 -------------------------
#
# "Scene 4 이미지 없음"까지가 Sprint152였다. 사람은 그 다음에 무엇을
# 해야 하는지 알아야 한다 - 어느 폴더에, 어떤 이름으로.
#
# 경로를 지어내면 안 된다. local_stock은 파일 이름의 낱말이 프롬프트와
# 겹치는 것을 고르므로, 그 규칙과 다른 이름을 알려 주면 사람이 시킨
# 대로 넣어도 안 찾힌다.

IMAGE_SUFFIX = ".png"

# 사람이 읽는 이름. 코드가 쓰는 열쇠(required_asset)와 따로 둔다.
ASSET_LABEL = {"script": "대본", "image": "이미지", "voice": "음성"}


def _image_hint(root, scene) -> tuple:
    """
    이 scene의 그림을 어디에 어떤 이름으로 두면 되는가.

    (어디, 상대경로)를 돌려준다. 어디는 "workspace" 또는 "project"다.

    낱말을 뽑는 것은 local_stock_provider가 한다. 여기서 다시 정하면
    두 규칙이 생기고, 그러면 알려 준 이름이 실제로는 안 찾히는 날이
    온다.
    """

    number = scene.get("scene")
    project_path = f"images/scene{number}{IMAGE_SUFFIX}"

    if not root:
        # 고를 폴더가 없다. 프로젝트에 직접 두는 길뿐이다.
        return "project", project_path

    from app.providers import local_stock_provider

    words = local_stock_provider._keywords(scene.get("image_prompt") or "")

    if not words:
        # 낱말이 하나도 없으면 내 자료에서는 영영 못 찾는다 - 검색이
        # 빈 목록을 돌려준다. 그때 내 자료 경로를 알려 주면 시킨 대로
        # 해도 안 된다.
        return "project", project_path

    return "workspace", f"images/{' '.join(words)}{IMAGE_SUFFIX}"


def _voice_hint(root, scene) -> tuple:
    """
    음성은 번호로 고른다(local_voice). 그러니 번호가 든 이름을 준다.

    폴더 이름은 local_library가 아는 것 중 사양이 적은 쪽(voices)이다 -
    voice/도 받지만, 새로 만드는 사람에게는 하나만 알려 주는 편이 낫다.
    """

    number = scene.get("scene")

    if not root:
        return "project", (
            f"audio/scenes/{audio_policy.scene_audio_filename(number)}"
        )

    folder = local_library._folders(local_library.VOICE)[-1]

    return "workspace", (
        f"{folder}/scene{number}{audio_policy.NARRATION_EXTENSION}"
    )


def _found_path(default_folder: str, slot: dict) -> str:
    """
    이미 있는 것이 어디 있는가. 있는 그대로 옮긴다.

    그림 자리라고 언제나 images/인 것은 아니다 - local_stock은 맞는
    영상이 있으면 그것을 골라 첫 프레임을 쓴다(Sprint150). 그때 파일은
    videos/에 있고, images/라고 적으면 사람이 그 폴더를 열어 봐도
    없다. 고른 쪽이 말한 kind를 그대로 쓴다.
    """

    if not slot.get("name"):
        return None

    folder = slot.get("kind") or default_folder

    return f"{folder}/{slot['name']}"


def _message(asset: str, status_name: str, path, location) -> str:
    """
    사람이 읽을 한 줄.

    만들어 주겠다고 하지 않는다 - 이 자리는 표시만 하는 곳이고,
    권하는 순간 사람은 눌러 보고 그러면 돈이 든다.
    """

    label = ASSET_LABEL.get(asset, asset)

    if status_name == "ready":
        return f"{label} 준비됨"

    if not path:
        return f"{label}이(가) 없습니다"

    where = "내 자료 폴더" if location == "workspace" else "프로젝트 폴더"

    return f"{label} 없음 - {where}에 {path} 를 넣어 주십시오"


def requirements(project_path: str, scenes: list) -> dict:
    """
    Sprint153 - 이 프로젝트에 무엇이 필요하고 어디에 두면 되는가.

    만들지 않는다. 고르지도 않는다. 읽고 말하기만 한다.

    판정은 preparation이 이미 낸 것을 그대로 쓴다 - 같은 사실을 두
    곳에서 다시 재면 두 화면이 서로 다른 말을 하게 된다.
    """

    prepared = preparation(project_path, scenes)
    root = prepared["root"]

    by_number = {scene.get("scene"): scene for scene in (scenes or [])}

    rows = []

    for row in prepared["scenes"]:
        number = row["scene"]
        scene = by_number.get(number, {})

        if not row["script"]:
            rows.append({
                "scene": number,
                "required_asset": "script",
                # 대본은 파일이 아니다. 둘 곳이 없다.
                "expected_path": None,
                "expected_root": None,
                "location": None,
                "status": "missing",
                "shared_with": [],
                "found": None,
                "message": _message("script", "missing", None, None),
            })

        for asset, slot, hint, folder in (
            ("image", row["image"], _image_hint, "images"),
            ("voice", row["voice"], _voice_hint,
             local_library._folders(local_library.VOICE)[-1]),
        ):
            if slot["ready"]:
                # 어디서 왔는지에 따라 사는 곳이 다르다.
                in_project = slot["from"] == "made"
                where = "project" if in_project else "workspace"
                base = project_path if in_project else root

                if asset == "voice" and in_project:
                    path = (
                        f"audio/scenes/"
                        f"{audio_policy.scene_audio_filename(number)}"
                    )
                elif in_project:
                    path = f"images/scene{number}{IMAGE_SUFFIX}"
                else:
                    path = _found_path(folder, slot)

                # Sprint156 - 준비는 됐지만 다른 Scene과 같은 파일을
                # 쓰는 경우. 없는 것으로 치지 않는다 - 사람이 일부러
                # 그렇게 했을 수도 있다.
                shared = slot.get("shared_with") or []
                message = _message(asset, "ready", path, where)

                if shared:
                    message += (
                        " · Scene "
                        + ", ".join(str(n) for n in shared)
                        + "과(와) 같은 파일입니다"
                    )

                rows.append({
                    "scene": number,
                    "required_asset": asset,
                    "expected_path": path,
                    "expected_root": base,
                    "location": where,
                    "status": "ready",
                    "shared_with": shared,
                    "found": slot.get("name"),
                    "message": message,
                })
                continue

            where, path = hint(root, scene)

            rows.append({
                "scene": number,
                "required_asset": asset,
                "expected_path": path,
                "expected_root": root if where == "workspace" else project_path,
                "location": where,
                "status": "missing",
                "shared_with": [],
                "found": None,
                "message": _message(asset, "missing", path, where),
            })

    return {
        "scanned": prepared["scanned"],
        "root": root,
        "total": prepared["total"],
        "ready": prepared["ready"],
        # 두 화면이 갈리지 않도록 같은 판정을 그대로 옮긴다.
        "review": prepared["review"],
        "counts": prepared["counts"],
        "state": prepared["state"],
        "requirements": rows,
    }
