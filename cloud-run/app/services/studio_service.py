"""
Sprint80 - AI Video Studio UI의 읽기 계층.

엔진은 한 줄도 건드리지 않는다. 여기서 하는 일은 파이프라인이 이미
디스크에 남긴 것을 읽어 화면이 쓸 모양으로 바꾸는 것뿐이다.

진행 상황을 로그가 아니라 **산출물**로 판정한다. 로그 문구는 아무 때나
바뀌고, 파이프라인에 진행 신호를 심으려면 파이프라인을 고쳐야 한다.
script.json이 있으면 대본이 끝난 것이고 video/final_short.mp4가 있으면
영상이 끝난 것이다 - 이 판정은 파이프라인이 무엇을 출력하든 성립하고,
중간에 죽은 프로젝트에도 그대로 통한다.
"""

import json
import os


# 화면 가운데 파이프라인 진행 막대. (키, 이름, 판정할 산출물).
#
# 업로드는 판정할 산출물이 없다 - 업로드 경로 자체가 없기 때문이다
# (app/providers/youtube_provider.py가 0바이트다). "아직 안 됨"이 아니라
# "연결 안 됨"으로 보여야 해서 따로 표시한다.
_STAGES = (
    ("plan", "기획", "project.json"),
    ("script", "대본", "script.json"),
    ("image", "이미지", "images"),
    ("voice", "음성", "audio/final_audio.wav"),
    ("subtitle", "자막", "subtitle/subtitle.srt"),
    ("video", "영상", "video/final_short.mp4"),
    ("thumbnail", "썸네일", "thumbnail.png"),
    ("quality", "품질", "quality_report.json"),
    ("upload", "업로드", None),
)

_MEDIA_KINDS = {
    "video": "video/final_short.mp4",
    "thumbnail": "thumbnail.png",
}


def _load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _exists(project_path: str, relative: str) -> bool:
    # 빈 경로면 상대 경로가 되어 실행 디렉터리의 파일을 보게 된다.
    # 생성이 막 시작돼 프로젝트 경로를 아직 모르는 순간이 실제로 있다.
    if not project_path:
        return False

    target = os.path.join(project_path, relative)

    if not os.path.exists(target):
        return False

    if os.path.isdir(target):
        return bool(os.listdir(target))

    return True


def stage_progress(project_path: str) -> list:
    """
    9단계의 완료 여부. 순수 읽기입니다.

    없는 프로젝트를 받아도 예외를 던지지 않는다 - 생성이 막 시작돼
    디렉터리가 아직 없는 순간에도 화면은 그려져야 한다.
    """

    stages = []

    for key, label, artifact in _STAGES:
        if artifact is None:
            stages.append({
                "key": key, "label": label,
                "done": False, "unavailable": True,
            })
            continue

        stages.append({
            "key": key, "label": label,
            "done": _exists(project_path, artifact),
        })

    return stages


def list_projects(root: str, limit: int = 30) -> list:
    """최근 프로젝트. 이름이 타임스탬프라 이름 역순이 곧 최신순이다."""

    if not os.path.isdir(root):
        return []

    projects = []

    for name in sorted(os.listdir(root), reverse=True):
        path = os.path.join(root, name)

        if not os.path.isdir(path):
            continue

        meta = _load(os.path.join(path, "project.json"))

        if meta is None:
            continue

        script = _load(os.path.join(path, "script.json")) or {}
        quality = _load(os.path.join(path, "quality_report.json")) or {}
        scores = (
            (quality.get("ai_quality_evaluation") or {}).get("scores") or {}
        )

        projects.append({
            "project_id": name,
            "topic": meta.get("topic"),
            "channel": meta.get("channel"),
            "title": script.get("title"),
            "scene_count": len(script.get("scenes") or []),
            "has_video": _exists(path, "video/final_short.mp4"),
            "has_thumbnail": _exists(path, "thumbnail.png"),
            "overall_quality": scores.get("overall_quality"),
        })

        if len(projects) >= limit:
            break

    return projects


def project_detail(project_path: str) -> dict:
    """
    Scene Explorer / Quality Panel / Asset Inspector가 쓰는 전부.

    평가가 아직 없어도 scene은 돌려준다 - 생성 중에도 화면이 채워져야
    하고, "아직 평가 전"과 "scene이 없음"은 다르다.
    """

    meta = _load(os.path.join(project_path, "project.json")) or {}
    script = _load(os.path.join(project_path, "script.json")) or {}
    quality = _load(os.path.join(project_path, "quality_report.json")) or {}
    observatory = _load(
        os.path.join(project_path, "asset_observatory.json"),
    ) or {}

    evaluation = quality.get("ai_quality_evaluation") or {}
    by_scene = {s.get("scene"): s for s in evaluation.get("scenes", [])}
    obs_by_scene = {
        s.get("scene"): s for s in observatory.get("scenes", [])
    }

    scenes = []

    for scene in script.get("scenes") or []:
        number = scene.get("scene")
        result = by_scene.get(number) or {}
        obs = obs_by_scene.get(number)

        scenes.append({
            "scene": number,
            "narration": scene.get("narration"),
            "subject": scene.get("subject"),
            "camera": scene.get("camera"),
            "lighting": scene.get("lighting"),
            "image_prompt": scene.get("image_prompt"),
            "provider": scene.get("provider"),
            "asset_type": scene.get("asset_type"),
            "search_query": scene.get("search_query"),
            "character_scene": bool(scene.get("character_scene")),
            "realism": result.get("realism_score"),
            "composition": result.get("composition_score"),
            "regenerate": bool(result.get("regenerate")),
            "reason": result.get("reason"),
            # 후보를 하나라도 본 scene만 붙는다. Imagen으로 바로 간
            # scene은 검사할 후보가 없다.
            "observatory": obs if (obs and obs.get("candidates")) else None,
        })

    return {
        "project_id": os.path.basename(project_path),
        "topic": meta.get("topic"),
        "channel": meta.get("channel"),
        "title": script.get("title"),
        "hook": script.get("hook"),
        "character": script.get("character"),
        "scenes": scenes,
        "quality": evaluation.get("scores") or {},
        "thumbnail_quality": evaluation.get("thumbnail") or {},
        "cache": observatory.get("cache") or {},
        "stages": stage_progress(project_path),
        "media": {
            "video": _exists(project_path, "video/final_short.mp4"),
            "thumbnail": _exists(project_path, "thumbnail.png"),
        },
    }


def media_path(project_path: str, kind: str, scene_number=None) -> str:
    """
    UI가 서빙할 파일의 실제 경로.

    kind와 scene 번호를 그대로 경로에 붙이지 않는다 - 요청 하나로
    프로젝트 밖을 가리킬 수 있게 된다. 알려진 종류만 허용하고, scene은
    정수로만 받는다(Sprint65의 resolve_project_path와 같은 원칙).
    """

    if kind == "scene":
        try:
            number = int(scene_number)
        except (TypeError, ValueError):
            raise ValueError(f"scene 번호가 올바르지 않습니다: {scene_number!r}")

        if number < 1:
            raise ValueError(f"scene 번호가 올바르지 않습니다: {number}")

        relative = f"images/scene{number}.png"

    elif kind in _MEDIA_KINDS:
        relative = _MEDIA_KINDS[kind]

    else:
        raise ValueError(f"알 수 없는 media 종류입니다: {kind!r}")

    target = os.path.join(project_path, relative)

    if not os.path.exists(target):
        raise FileNotFoundError(target)

    return target
