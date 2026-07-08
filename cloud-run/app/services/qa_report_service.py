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


def build_qa_report(project_path: str) -> dict:
    """get_real_durations + load_quality_summary를 합치고,
    Sprint53 Duration Gate/Optimizer의 목표 범위(43~47초) 안에
    실제 최종 길이가 들어오는지 판정한 값을 더한 종합 리포트."""

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

    return "\n".join(lines)
