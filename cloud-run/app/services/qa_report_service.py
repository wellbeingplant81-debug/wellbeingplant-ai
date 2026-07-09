"""
Sprint56 - QA Report Service (개발환경 최적화, 기능 변경 없음).

Sprint53~55에서 실제 영상 생성(E2E)을 검증할 때마다 매번 즉석으로
짜던 ffprobe 반복문 + quality_report.json 파싱을 재사용 가능한
함수로 옮긴 것뿐이다. 파이프라인/영상 생성 로직은 전혀 건드리지 않고,
이미 만들어진 산출물을 읽기만 한다.
"""

import glob
import json
import os
import re

from app.services import asset_duplicate_detector
from app.services import asset_usage_planner
from app.services.asset_integration_service import ASSET_ROLES
from app.services.duration_optimizer import get_audio_duration

TARGET_MIN_SECONDS = 43.0
TARGET_MAX_SECONDS = 47.0

_SCENE_NUMBER_PATTERN = re.compile(r"scene(\d+)\.mp3$")


def _scene_number(path: str) -> int:
    match = _SCENE_NUMBER_PATTERN.search(path)
    return int(match.group(1)) if match else -1


def get_real_durations(project_path: str) -> dict:
    """project_path 아래 실제 오디오/영상 파일들의 ffprobe 실측 길이를
    모은다. 없는 파일은 None(voice/final_audio/final_video) 또는
    빈 리스트(scenes)로 표시하고 에러를 던지지 않는다."""

    scenes_dir = os.path.join(project_path, "audio", "scenes")
    scene_paths = sorted(
        glob.glob(os.path.join(scenes_dir, "scene*.mp3")),
        key=_scene_number,
    )

    scenes = [
        {"scene": _scene_number(path), "duration": get_audio_duration(path)}
        for path in scene_paths
    ]

    def _duration_or_none(*relative_parts):
        path = os.path.join(project_path, *relative_parts)
        return get_audio_duration(path) if os.path.exists(path) else None

    return {
        "scenes": scenes,
        "voice": _duration_or_none("audio", "voice.mp3"),
        "final_audio": _duration_or_none("audio", "final_audio.mp3"),
        "final_video": _duration_or_none("video", "final_short.mp4"),
    }


def load_quality_summary(project_path: str):
    """quality_report.json이 있으면 technical_validation 요약을,
    없으면 None을 반환한다."""

    path = os.path.join(project_path, "quality_report.json")

    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tv = data.get("technical_validation", {})

    return {
        "passed": tv.get("passed"),
        "checks": tv.get("checks", {}),
        "blocking_failures": tv.get("blocking_failures", []),
    }


def _validate_roles(roles: list) -> bool:
    """
    role이 하나도 없으면(레거시/스톡 - 하위 호환) 위반이 아니라
    정상으로 취급한다. role이 있다면 asset_integration_service.
    ASSET_ROLES(environment/subject/detail/transition) 순서와 정확히
    일치해야 한다. 새로운 판정 규칙이 아니라 기존 ASSET_ROLES 상수를
    그대로 재사용한 단순 비교다.
    """

    if all(role is None for role in roles):
        return True

    return roles == ASSET_ROLES


def build_asset_intelligence_summary(project_path: str) -> list:
    """
    Sprint64-5 - script.json의 scene별 assets/role을 읽어, 실제
    이미지 파일의 중복 여부(asset_duplicate_detector.find_duplicate_
    assets, Sprint64-1)와 role 기반 기대 duration(asset_usage_planner.
    plan_asset_usage, Sprint64-3)을 읽기 전용으로 리포트한다. 새로운
    판정 로직은 만들지 않고 기존 함수를 그대로 재사용한다. 파이프라인/
    렌더링 로직에는 전혀 영향을 주지 않는다.

    script.json이 없으면 빈 리스트를 반환한다. scene["assets"]가 없는
    레거시 scene, role이 없는 asset(스톡/비디오프레임)도 예외 없이
    처리된다.
    """

    script_path = os.path.join(project_path, "script.json")

    if not os.path.exists(script_path):
        return []

    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scene_audio_durations = {
        entry["scene"]: entry["duration"]
        for entry in get_real_durations(project_path)["scenes"]
    }

    summary = []

    for scene in data.get("scenes", []):

        assets = scene.get("assets") or []
        roles = [asset.get("role") for asset in assets]
        asset_paths = [asset["path"] for asset in assets]

        duplicates = (
            asset_duplicate_detector.find_duplicate_assets(asset_paths)
            if asset_paths
            else []
        )

        scene_duration = scene_audio_durations.get(scene["scene"])

        expected_durations = (
            [
                round(entry["duration"], 1)
                for entry in asset_usage_planner.plan_asset_usage(
                    assets, scene_duration,
                )
            ]
            if assets and scene_duration is not None
            else []
        )

        summary.append({
            "scene": scene["scene"],
            "asset_count": len(assets),
            "roles": roles,
            "duplicates": duplicates,
            "expected_durations": expected_durations,
            "role_validation": _validate_roles(roles),
        })

    return summary


def build_qa_report(project_path: str) -> dict:
    """get_real_durations + load_quality_summary를 합치고,
    Sprint53 Duration Gate/Optimizer의 목표 범위(43~47초) 안에
    실제 최종 길이가 들어오는지 판정한 값을 더한 종합 리포트.

    Sprint64-5 - asset_intelligence(멀티에셋/role/중복/기대 duration)
    를 추가한다. 기존 키(durations/quality/target_range_ok)는 전혀
    바뀌지 않는다."""

    durations = get_real_durations(project_path)
    quality = load_quality_summary(project_path)

    final_duration = durations["final_video"] or durations["voice"]

    target_range_ok = (
        final_duration is not None
        and TARGET_MIN_SECONDS <= final_duration <= TARGET_MAX_SECONDS
    )

    return {
        "project_path": project_path,
        "durations": durations,
        "quality": quality,
        "target_range_ok": target_range_ok,
        "asset_intelligence": build_asset_intelligence_summary(project_path),
    }


def format_report(report: dict) -> str:

    lines = [f"QA Report: {report['project_path']}"]

    durations = report["durations"]

    lines.append("")
    lines.append("Scene durations:")
    if durations["scenes"]:
        for scene in durations["scenes"]:
            lines.append(f"  scene{scene['scene']}: {scene['duration']:.3f}s")
    else:
        lines.append("  (no scene audio files found)")

    lines.append("")
    lines.append(f"voice.mp3        : {durations['voice']}")
    lines.append(f"final_audio.mp3  : {durations['final_audio']}")
    lines.append(f"final_short.mp4  : {durations['final_video']}")
    lines.append(
        f"target range (43-47s): {'OK' if report['target_range_ok'] else 'OUT OF RANGE'}"
    )

    quality = report["quality"]
    lines.append("")

    if quality is None:
        lines.append("quality_report.json: not found")
    else:
        lines.append(f"technical_validation.passed: {quality['passed']}")
        if quality["blocking_failures"]:
            lines.append(f"blocking_failures: {quality['blocking_failures']}")

    asset_intelligence = report.get("asset_intelligence")

    if asset_intelligence:
        lines.append("")
        lines.append("Asset Intelligence (Sprint64):")
        for entry in asset_intelligence:
            lines.append(
                f"  scene{entry['scene']}: assets={entry['asset_count']} "
                f"roles={entry['roles']} role_validation={entry['role_validation']} "
                f"duplicates={len(entry['duplicates'])} "
                f"expected_durations={entry['expected_durations']}"
            )

    return "\n".join(lines)
