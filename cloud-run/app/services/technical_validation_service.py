import glob
import os
import subprocess

from PIL import Image


AUDIO_VIDEO_SYNC_TOLERANCE_MS = 250

HARD_CHECKS = [
    "required_files_exist",
    "scene_count_consistency",
    "video_duration",
    "subtitle_existence",
    "audio_video_sync",
    "thumbnail_existence",
]


def _ffprobe_duration(path):

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
    )

    text = result.stdout.strip()

    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        return None


def _check_required_files(project_path, scene_count):

    required = [
        "script.json",
        os.path.join("audio", "voice.mp3"),
        os.path.join("audio", "final_audio.mp3"),
        os.path.join("subtitle", "subtitle.srt"),
        os.path.join("video", "short.mp4"),
        os.path.join("video", "final_short.mp4"),
        "thumbnail.png",
    ]

    for index in range(1, scene_count + 1):
        required.append(os.path.join("images", f"scene{index}.png"))
        required.append(os.path.join("audio", "scenes", f"scene{index}.mp3"))

    missing = [
        path
        for path in required
        if not os.path.exists(os.path.join(project_path, path))
    ]

    return {
        "passed": len(missing) == 0,
        "missing": missing,
    }


def _check_scene_count(project_path, scene_count):

    image_files = glob.glob(
        os.path.join(project_path, "images", "scene*.png")
    )

    audio_files = glob.glob(
        os.path.join(project_path, "audio", "scenes", "scene*.mp3")
    )

    return {
        "passed": (
            len(image_files) == scene_count
            and len(audio_files) == scene_count
        ),
        "script_scenes": scene_count,
        "image_files": len(image_files),
        "audio_files": len(audio_files),
    }


def _check_image_resolution(project_path, scene_count):

    warnings = []
    details = []

    targets = [
        (f"scene_{index}", os.path.join(project_path, "images", f"scene{index}.png"))
        for index in range(1, scene_count + 1)
    ]

    targets.append(
        ("thumbnail", os.path.join(project_path, "thumbnail.png"))
    )

    for label, path in targets:

        if not os.path.exists(path):
            continue

        try:
            with Image.open(path) as image:
                width, height = image.size
        except Exception:
            warnings.append(f"{label}: unable to read image")
            continue

        portrait = height > width

        if not portrait:
            warnings.append(
                f"{label}: not portrait orientation ({width}x{height})"
            )

        details.append(
            {
                "label": label,
                "width": width,
                "height": height,
                "portrait": portrait,
            }
        )

    return {
        "passed": True,
        "warnings": warnings,
        "details": details,
    }


def _check_video_duration(project_path):

    path = os.path.join(project_path, "video", "final_short.mp4")

    duration = _ffprobe_duration(path)

    return {
        "passed": duration is not None and duration > 0,
        "duration_seconds": duration,
    }


def _check_subtitle_existence(project_path):

    path = os.path.join(project_path, "subtitle", "subtitle.srt")

    if not os.path.exists(path):
        return {
            "passed": False,
            "cue_count": 0,
        }

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    cue_count = content.count("-->")

    return {
        "passed": cue_count > 0,
        "cue_count": cue_count,
    }


def _check_audio_video_sync(project_path, scene_count):

    scene_audio_paths = [
        os.path.join(project_path, "audio", "scenes", f"scene{index}.mp3")
        for index in range(1, scene_count + 1)
    ]

    existing_paths = [
        path for path in scene_audio_paths if os.path.exists(path)
    ]

    if len(existing_paths) != scene_count:
        return {
            "passed": False,
            "video_duration_seconds": None,
            "audio_duration_seconds": None,
            "delta_ms": None,
            "tolerance_ms": AUDIO_VIDEO_SYNC_TOLERANCE_MS,
        }

    scene_durations = [_ffprobe_duration(path) for path in existing_paths]

    if any(duration is None for duration in scene_durations):
        return {
            "passed": False,
            "video_duration_seconds": None,
            "audio_duration_seconds": None,
            "delta_ms": None,
            "tolerance_ms": AUDIO_VIDEO_SYNC_TOLERANCE_MS,
        }

    audio_duration = sum(scene_durations)

    video_path = os.path.join(project_path, "video", "final_short.mp4")
    video_duration = _ffprobe_duration(video_path)

    if video_duration is None:
        return {
            "passed": False,
            "video_duration_seconds": None,
            "audio_duration_seconds": audio_duration,
            "delta_ms": None,
            "tolerance_ms": AUDIO_VIDEO_SYNC_TOLERANCE_MS,
        }

    delta_ms = abs(video_duration - audio_duration) * 1000

    return {
        "passed": delta_ms <= AUDIO_VIDEO_SYNC_TOLERANCE_MS,
        "video_duration_seconds": video_duration,
        "audio_duration_seconds": audio_duration,
        "delta_ms": delta_ms,
        "tolerance_ms": AUDIO_VIDEO_SYNC_TOLERANCE_MS,
    }


def _check_thumbnail_existence(project_path):

    path = os.path.join(project_path, "thumbnail.png")

    if not os.path.exists(path):
        return {"passed": False}

    try:
        with Image.open(path) as image:
            image.verify()
    except Exception:
        return {"passed": False}

    return {"passed": True}


def validate(project_path, data):

    scene_count = len(data["scenes"])

    checks = {
        "required_files_exist": _check_required_files(project_path, scene_count),
        "scene_count_consistency": _check_scene_count(project_path, scene_count),
        "image_resolution": _check_image_resolution(project_path, scene_count),
        "video_duration": _check_video_duration(project_path),
        "subtitle_existence": _check_subtitle_existence(project_path),
        "audio_video_sync": _check_audio_video_sync(project_path, scene_count),
        "thumbnail_existence": _check_thumbnail_existence(project_path),
    }

    blocking_failures = [
        name
        for name in HARD_CHECKS
        if not checks[name]["passed"]
    ]

    return {
        "passed": len(blocking_failures) == 0,
        "checks": checks,
        "blocking_failures": blocking_failures,
    }
