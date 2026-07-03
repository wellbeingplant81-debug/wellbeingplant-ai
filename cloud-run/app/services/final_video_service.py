import os
import subprocess


def merge_video_audio(project_path: str):

    video_path = os.path.join(
        project_path,
        "video",
        "short.mp4",
    )

    audio_path = os.path.join(
        project_path,
        "audio",
        "voice.mp3",
    )

    subtitle_path = os.path.join(
        project_path,
        "subtitle",
        "subtitle.srt",
    )

    output_path = os.path.join(
        project_path,
        "video",
        "final_short.mp4",
    )

    # Windows용 경로 변환
    subtitle_path = subtitle_path.replace("\\", "/").replace(":", "\\:")

    command = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-i",
        audio_path,
        "-vf",
        f"subtitles='{subtitle_path}'",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        output_path,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    print("========== FFMPEG STDOUT ==========")
    print(result.stdout)

    print("========== FFMPEG STDERR ==========")
    print(result.stderr)

    if result.returncode != 0:
        raise Exception(result.stderr)

    return output_path