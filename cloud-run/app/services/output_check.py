"""
Sprint163 - 만든 뒤에 결과를 본다 (Epic 57, Phase 14).

Sprint162가 "누르기 전"을 봤다. 이번은 "누른 뒤"다.

    final_check   지금 누르면 되는가     자료와 산출물이 있는가
    output_check  나온 것이 쓸 만한가    영상·길이·자막이 있는가

앞의 것은 만들기 전의 재료를 보고, 이것은 만들어진 결과를 본다.

상태는 셋이다
-------------
    READY   영상이 나왔고 볼 것도 없다
    REVIEW  영상은 나왔으나 빠지거나 어긋난 것이 있다
    FAILED  영상이 없다

FAILED를 따로 두는 이유는, 아직 안 만든 것과 만들었는데 실패한 것을
가르지 않으면 사람이 "왜 아무 말도 없지"를 묻게 되기 때문이다.
영상이 없으면 나머지를 아무리 말해 봐야 쓸 것이 없다.

재지 않는다. 이미 재 둔 것을 읽는다
-----------------------------------
qa_report_service.get_real_durations가 ffprobe로 실측을 모은다
(Sprint56). 여기서 다시 재면 같은 파일이 자리마다 다른 길이를 갖는다.

고치지 않는다
-------------
빠진 것을 우리가 만들어 주면, 사람은 무엇이 빠졌는지 영영 모른 채
다음에도 같은 자리에서 걸린다. 읽고 말하기만 한다.
"""

import os

from app.services import audio_policy

READY = "ready"
REVIEW = "review"
FAILED = "failed"

# 엔진이 최종 영상을 놓는 자리. publish_gate가 보는 그 파일이다.
VIDEO_RELATIVE = ("video", "final_short.mp4")

# 자막이 놓이는 자리. subtitle_service가 쓰는 그 이름이다.
SUBTITLE_RELATIVE = ("subtitle", "subtitle.srt")


def _subtitle(project_path: str) -> dict:
    """
    자막이 있는가.

    빈 파일은 자막이 아니다 - 있다고 말해 놓고 화면에 아무것도 안
    나오면 사람은 그것을 재생해 보고서야 안다.
    """

    path = os.path.join(project_path, *SUBTITLE_RELATIVE)

    try:
        size = os.path.getsize(path)
    except OSError:
        return {"exists": False, "path": path, "bytes": None}

    return {"exists": size > 0, "path": path, "bytes": size}


def _scene_rows(project_path: str, scenes: list, measured: dict) -> list:
    """
    Scene마다 무엇이 남았는가. 길이는 재 둔 것을 그대로 옮긴다.
    """

    seconds = {
        row["scene"]: row["duration"] for row in measured.get("scenes") or []
    }

    rows = []

    for scene in scenes or []:
        number = scene.get("scene")

        image = os.path.join(project_path, "images", f"scene{number}.png")
        voice = os.path.join(
            project_path, "audio", "scenes",
            audio_policy.scene_audio_filename(number),
        )

        rows.append({
            "scene": number,
            "image": os.path.exists(image),
            "voice": os.path.exists(voice),
            "seconds": seconds.get(number),
            "narration": scene.get("narration") or "",
        })

    return rows


def _warnings(rows: list) -> list:
    """
    영상은 나왔으나 사람이 봐야 하는 것들.

    길이가 짧다는 판정은 Duration Optimizer가 쓰는 허용 오차를 그대로
    쓴다 - 여기서 새 숫자를 만들지 않는다.
    """

    from app.services import duration_estimator, duration_optimizer

    found = []

    for row in rows:
        if not row["image"]:
            found.append(f"Scene {row['scene']} 이미지 없음")

        if not row["voice"]:
            found.append(f"Scene {row['scene']} 음성 없음")
            continue

        seconds = row["seconds"]

        if seconds is None:
            continue

        expected = duration_estimator.estimate_duration(row["narration"])

        if seconds < expected - duration_optimizer.TOLERANCE_SECONDS:
            found.append(
                f"Scene {row['scene']} 음성이 짧습니다 - "
                f"대본 기준 {expected:.1f}초, 실제 {seconds:.1f}초"
            )

    return found


def build(project_path: str, scenes: list) -> dict:
    """
    나온 것이 쓸 만한가. 읽고 말하기만 한다.

    돌려주는 것:

        state       READY / REVIEW / FAILED
        video       있는가 · 몇 초인가
        scenes      이미지가 있는 Scene 수 / 전체
        voices      음성이 있는 Scene 수 / 전체
        subtitle    있는가
        problems    영상이 없다 - 그때만 찬다
        warnings    영상은 나왔으나 봐야 하는 것들
        scene_rows  Scene 하나씩
    """

    from app.services import qa_report_service

    # 재는 일은 이 함수가 한다. 여기서 다시 재지 않는다.
    measured = qa_report_service.get_real_durations(project_path)

    video_path = os.path.join(project_path, *VIDEO_RELATIVE)
    video_seconds = measured.get("final_video")

    # 길이를 못 읽으면 결과가 아니다. 0바이트 파일을 "완료"라고 하면
    # 사람은 재생해 보고서야 안다.
    has_video = bool(video_seconds and video_seconds > 0)

    rows = _scene_rows(project_path, scenes, measured)
    subtitle = _subtitle(project_path)

    warnings = _warnings(rows)

    if not subtitle["exists"]:
        warnings.append("자막이 없습니다")

    problems = [] if has_video else ["영상이 없습니다"]

    if problems:
        state = FAILED
    elif warnings:
        state = REVIEW
    else:
        state = READY

    return {
        "state": state,
        "video": {
            "exists": has_video,
            "path": video_path if has_video else None,
            "seconds": video_seconds if has_video else None,
        },
        "scenes": {
            "ready": sum(1 for row in rows if row["image"]),
            "total": len(rows),
        },
        "voices": {
            "ready": sum(1 for row in rows if row["voice"]),
            "total": len(rows),
        },
        "subtitle": {"exists": subtitle["exists"]},
        "problems": problems,
        "warnings": warnings,
        "scene_rows": rows,
    }
