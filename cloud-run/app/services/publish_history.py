"""
Sprint238 - 이미 올렸는가 (Publish Automation, Phase 6).

Sprint235 의 줄은 **줄 안에서만** 중복을 막았다. 아직 끝나지 않은 같은
(프로젝트, 플랫폼) 이 있으면 다시 세우지 않는다 - 거기까지다. 줄 바깥은
모른다.

실제로 이 PC 에 그런 것이 있었다.

    output/20260819_221009/youtube_upload_result.json
      {"success": true, "upload_id": "JpJ74dkxb9s"}   <- 손으로 올린 것

그 프로젝트를 줄에 세우고 일꾼을 돌리면 같은 영상이 채널에 두 번
올라간다. 사람이 알아채는 것은 채널을 열어 본 다음이다.

이 파일이 하는 일은 하나다 - **이미 올렸는지 묻는다.** 올리지 않고,
줄도 모르고, 결과 파일을 적지도 않는다.

이름을 새로 짓지 않는다
-----------------------
결과 파일 이름은 스텝 서비스가 이미 정해 두었다. 여기서 다시 지으면
갈리는 날 영원히 "올린 적 없다" 가 된다 - 그 사실을 시험이 지킨다.

다시 만든 영상은 다시 올릴 수 있어야 한다
-----------------------------------------
결과 파일은 그때 올린 것의 기록이다. 그 뒤에 영상을 다시 만들었다면
그것은 다른 영상이고, 막으면 사람은 고친 영상을 영영 못 올린다.

결과 파일에는 어떤 영상이었는지 적혀 있지 않다. 적게 하려면 스텝
서비스를 고쳐야 하고 이번 Sprint 는 그것을 금지한다. 그래서 **시각**으로
가른다 - 영상이 기록보다 나중이면 다시 만든 것이다.

거친 잣대다. 파일을 만지기만 해도 시각은 바뀐다. 그래도 한쪽으로만
틀린다 - "다시 올릴 수 있다" 쪽이다. 반대로 틀리면 올라간 것을 또
올린다.
"""

import json
import os

# 스텝 서비스가 적는 그 이름들. 여기서 새로 짓지 않는다.
RESULT_FILENAMES = {
    "youtube": "youtube_upload_result.json",
    "instagram": "instagram_upload_result.json",
    "tiktok": "tiktok_upload_result.json",
}

# 올린 영상. MEDIA_KINDS 가 정한 그 자리다.
_VIDEO = ("video", "final_short.mp4")


def result_path(project_path: str, platform: str) -> str:
    """그 플랫폼의 기록이 있을 자리. 모르는 곳이면 빈 문자열."""

    name = RESULT_FILENAMES.get(str(platform or "").strip().lower())

    if not name or not project_path:
        return ""

    return os.path.join(project_path, name)


def _read(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            found = json.load(f)
    except Exception:
        # 기록 하나가 망가졌다고 올리기를 막을 이유는 없다. 다만
        # 없는 것으로 읽으면 다시 올릴 수 있게 된다 - 그쪽이 낫다.
        return None

    return found if isinstance(found, dict) else None


def _remade_after(project_path: str, when: float) -> bool:
    """기록을 남긴 뒤에 영상을 다시 만들었는가."""

    video = os.path.join(project_path, *_VIDEO)

    if not os.path.isfile(video):
        # 영상이 지워졌다고 "안 올렸다" 가 되면 안 된다 - 올린 것은
        # 이미 채널에 있다.
        return False

    return os.path.getmtime(video) > when


def already_published(project_path: str, platform: str):
    """
    이미 올렸으면 그때의 기록, 아니면 None.

    성공한 것만 센다. 실패도 건너뜀도 올린 것이 아니다 - 그것을
    막으면 사람은 고칠 기회를 잃는다.
    """

    where = result_path(project_path, platform)

    if not where or not os.path.isfile(where):
        return None

    found = _read(where)

    if not found or not found.get("success"):
        return None

    if _remade_after(project_path, os.path.getmtime(where)):
        return None

    return found
