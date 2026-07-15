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
from app.services.visual_diversity_engine import summarize_visual_diversity

TARGET_MIN_SECONDS = 43.0
TARGET_MAX_SECONDS = 47.0

# Sprint100-1 - pipeline.py의 DURATION_TOLERANCE_SECONDS(Sprint93+
# ProductionProfile Activation)와 동일한 값. 이 모듈은 pipeline.py를
# import하지 않고 상수만 그대로 복제한다 - QA 리포트는 순수 읽기
# 전용이라 파이프라인 모듈에 의존할 이유가 없다.
DURATION_TOLERANCE_SECONDS = 2

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
    ASSET_ROLES(environment/subject/detail/transition) 순서의
    접두사여야 한다. 새로운 판정 규칙이 아니라 기존 ASSET_ROLES
    상수를 그대로 재사용한 단순 비교다.

    Sprint100-2 - Motion Contract: max_assets로 AI 추가 asset 개수를
    캡핑하면(Hook=3 등) role 개수가 4개 미만일 수 있다 - 정확히
    ASSET_ROLES와 같아야 한다는 기존 조건은 그대로 두되(len(roles)==4
    인 기존 케이스는 100% 동일하게 판정됨), len(roles)<4인 경우도
    "순서대로 앞에서부터 잘린 것"이면 정상으로 인정하도록 접두사
    비교로 일반화했다.
    """

    if all(role is None for role in roles):
        return True

    return roles == ASSET_ROLES[:len(roles)]


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
            # Sprint72-2 - Visual Diversity Engine Observability. scene에
            # 배정된 profile(step02_assets.assign_visual_profiles())을
            # 읽기 전용으로 그대로 보고한다 - 필드가 없는 scene(Sprint
            # 72-2 이전 데이터/스톡 전용 파이프라인)은 None으로 보고한다.
            "visual_profile": scene.get("visual_profile"),
            # Sprint100-3.1 - Stock Video Visual Relevance Selection
            # Trace. asset_integration_service.integrate_asset()이
            # video 후보를 채점했을 때만(asset_strategy="upload" and
            # prefer_video=True and video 후보 존재) scene에 남긴
            # 값을 읽기 전용으로 그대로 보고한다 - 없으면 None.
            "video_relevance_trace": scene.get("video_relevance_trace"),
        })

    return summary


def build_visual_diversity_summary(asset_intelligence: list) -> dict:
    """
    Sprint72-3 - Visual Diversity QA. build_asset_intelligence_summary()
    가 이미 읽어둔 scene별 visual_profile(Sprint72-2)을 재사용해
    분포/다양성 개수/점수(visual_diversity_engine.summarize_visual_
    diversity)를 계산하고, scene 번호 -> profile 맵도 함께 담는다.
    visual_profile이 없는 scene은 자동으로 제외되고(요구사항: 기존
    동작 유지), 전부 없으면(profile=None) 0으로 채운 요약을 그대로
    반환한다(완전 no-op) - 새 판정 로직 없이 기존 함수만 조합한다.
    """

    profiles_by_scene = {
        entry["scene"]: entry["visual_profile"]
        for entry in asset_intelligence
        if entry.get("visual_profile")
    }

    summary = summarize_visual_diversity(list(profiles_by_scene.values()))
    summary["profiles_by_scene"] = profiles_by_scene

    return summary


def build_video_coverage_summary(project_path: str) -> dict:
    """
    Sprint102 - Video Coverage Intelligence QA. scene별 Motion
    Contract의 video_intent 판정과 실제 Render Mode(VideoFileClip인지
    Ken Burns(Image)인지 - assets[0].video_path 존재 여부로 판정,
    video_builder.py의 _resolve_video_only_path()와 동일한 신호)를
    대조하고, Video/Image Scene 수를 집계한다. selection_trace에서
    scene마다 실제로 시도된 검색어 cascade(Primary -> Action ->
    Fallback...)도 중복 없이 순서대로 뽑는다.

    script.json이 없거나 scene에 motion_contract/selection_trace가
    없는 경우(Motion Contract 비활성 profile)는 새 판정 없이 None/
    빈 값으로 읽기 전용 보고한다 - 렌더링/선택 로직에는 전혀 영향을
    주지 않는다.
    """

    script_path = os.path.join(project_path, "script.json")

    if not os.path.exists(script_path):
        return {"video_scene_count": 0, "image_scene_count": 0, "scenes": []}

    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scenes_summary = []
    video_count = 0
    image_count = 0

    for scene in data.get("scenes", []):

        assets = scene.get("assets") or []
        primary_asset = assets[0] if assets else {}
        video_path = primary_asset.get("video_path")
        render_mode = "VideoFileClip" if video_path else "Ken Burns (Image)"

        if video_path:
            video_count += 1
        else:
            image_count += 1

        video_intent = (scene.get("motion_contract") or {}).get("video_intent") or {}

        search_query_cascade = []
        for entry in (scene.get("selection_trace") or []):
            query = entry.get("search_query")
            if query and query not in search_query_cascade:
                search_query_cascade.append(query)

        scenes_summary.append({
            "scene": scene["scene"],
            "provider": scene.get("provider"),
            "render_mode": render_mode,
            "video_intent": video_intent.get("intent"),
            "video_intent_source": video_intent.get("source"),
            "search_query_cascade": search_query_cascade,
        })

    return {
        "video_scene_count": video_count,
        "image_scene_count": image_count,
        "scenes": scenes_summary,
    }


def get_target_range(project_path: str) -> tuple:
    """
    Sprint100-1 - Production Profile-aware target range.

    script.json에 production_profile(pipeline.py가 ENABLE_PRODUCTION_
    PROFILE일 때 채우는 Sprint93+ 필드)이 있으면 그 duration_target ±
    DURATION_TOLERANCE_SECONDS를 목표 범위로 쓴다 - 그래야 upload
    profile(ElevenLabs, 55초 목표)로 만든 영상이 development profile
    기준(43~47초)으로 잘못 "OUT OF RANGE" 판정받지 않는다.

    production_profile이 없으면(레거시 데이터/플래그 꺼짐) 기존
    TARGET_MIN_SECONDS~TARGET_MAX_SECONDS(43~47)를 그대로 반환한다 -
    완전히 하위 호환.
    """

    script_path = os.path.join(project_path, "script.json")

    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        profile = data.get("production_profile")

        if profile and "duration_target" in profile:
            target = profile["duration_target"]
            return (
                target - DURATION_TOLERANCE_SECONDS,
                target + DURATION_TOLERANCE_SECONDS,
            )

    return TARGET_MIN_SECONDS, TARGET_MAX_SECONDS


def build_qa_report(project_path: str) -> dict:
    """get_real_durations + load_quality_summary를 합치고,
    Sprint53 Duration Gate/Optimizer의 목표 범위(기본 43~47초, Sprint100-1
    부터는 get_target_range()로 Production Profile-aware) 안에 실제
    최종 길이가 들어오는지 판정한 값을 더한 종합 리포트.

    Sprint64-5 - asset_intelligence(멀티에셋/role/중복/기대 duration)
    를 추가한다. 기존 키(durations/quality/target_range_ok)는 전혀
    바뀌지 않는다.

    Sprint72-3 - visual_diversity(scene별 카메라/구도/조명 분포 및
    다양성 점수)를 추가한다. 기존 키는 전혀 바뀌지 않는다.

    Sprint100-1 - target_min_seconds/target_max_seconds 키를 추가한다.
    기존 target_range_ok는 이제 이 값들로 판정되지만, 값 자체(True/
    False)는 production_profile이 없는 기존 프로젝트에 한해 이전과
    동일하다."""

    durations = get_real_durations(project_path)
    quality = load_quality_summary(project_path)

    final_duration = durations["final_video"] or durations["voice"]

    target_min, target_max = get_target_range(project_path)

    target_range_ok = (
        final_duration is not None
        and target_min <= final_duration <= target_max
    )

    asset_intelligence = build_asset_intelligence_summary(project_path)

    return {
        "project_path": project_path,
        "durations": durations,
        "quality": quality,
        "target_min_seconds": target_min,
        "target_max_seconds": target_max,
        "target_range_ok": target_range_ok,
        "asset_intelligence": asset_intelligence,
        "visual_diversity": build_visual_diversity_summary(asset_intelligence),
        "video_coverage": build_video_coverage_summary(project_path),
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
    target_min = report["target_min_seconds"]
    target_max = report["target_max_seconds"]
    lines.append(
        f"target range ({target_min:g}-{target_max:g}s): "
        f"{'OK' if report['target_range_ok'] else 'OUT OF RANGE'}"
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
                f"expected_durations={entry['expected_durations']} "
                f"visual_profile={entry['visual_profile']}"
            )

    # Sprint100-3.1 - Stock Video Visual Relevance Selection Trace.
    # video 후보를 채점한 scene에 한해서만 출력한다(그 외 scene은
    # trace가 없으므로 자동으로 건너뛴다).
    trace_entries = [
        entry for entry in (asset_intelligence or [])
        if entry.get("video_relevance_trace")
    ]

    if trace_entries:
        lines.append("")
        lines.append("Stock Video Relevance Trace (Sprint100-3.1):")
        for entry in trace_entries:
            lines.append(f"  Scene{entry['scene']}")
            for i, candidate in enumerate(entry["video_relevance_trace"], start=1):
                if "error" in candidate:
                    lines.append(
                        f"    {i}. {candidate.get('candidate')} - error: {candidate['error']}"
                    )
                else:
                    lines.append(
                        f"    {i}. {candidate.get('candidate')} "
                        f"Score {candidate['score']:.2f} ({candidate['reasoning']})"
                    )

    diversity = report.get("visual_diversity")

    if diversity:
        lines.append("")
        lines.append("Visual Diversity Summary (Sprint72-3):")
        lines.append(
            f"  Camera Distance distribution: {diversity['camera_distance_distribution']}"
        )
        lines.append(
            f"  Camera Angle distribution: {diversity['camera_angle_distribution']}"
        )
        lines.append(
            f"  Composition distribution: {diversity['composition_distribution']}"
        )
        lines.append(
            f"  Lighting distribution: {diversity['lighting_distribution']}"
        )
        lines.append(
            "  Diversity counts: "
            f"distance={diversity['camera_distance_diversity_count']} "
            f"angle={diversity['camera_angle_diversity_count']} "
            f"composition={diversity['composition_diversity_count']} "
            f"lighting={diversity['lighting_diversity_count']}"
        )
        lines.append(f"  Diversity Score: {diversity['diversity_score']}/100")

    video_coverage = report.get("video_coverage")

    if video_coverage and video_coverage["scenes"]:
        lines.append("")
        lines.append("Video Coverage (Sprint102):")
        lines.append(f"  Video: {video_coverage['video_scene_count']} Scene")
        lines.append(f"  Image: {video_coverage['image_scene_count']} Scene")
        for entry in video_coverage["scenes"]:
            lines.append(
                f"  scene{entry['scene']}: render={entry['render_mode']} "
                f"video_intent={entry['video_intent']}({entry['video_intent_source']}) "
                f"provider={entry['provider']}"
            )
            if entry["search_query_cascade"]:
                lines.append(f"    query cascade: {entry['search_query_cascade']}")

    return "\n".join(lines)
