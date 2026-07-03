import os
import subprocess


def merge_video_audio(project_path: str):

    ffmpeg = r"C:\Users\baeku\Downloads\ffmpeg-8.1.2-essentials_build\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe"

    video_path = os.path.join(
        project_path,
        "video",
        "short.mp4",
    )

    audio_path = os.path.join(
        project_path,
        "audio",
        "final_audio.mp3",
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

    # Windows FFmpeg용 경로 변환
    subtitle_path = subtitle_path.replace("\\", "/")
    subtitle_path = subtitle_path.replace(":", "\\:")

    style = (
        "FontName=Malgun Gothic,"
        "FontSize=18,"
        "PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H000000&,"
        "BorderStyle=1,"
        "Outline=2,"
        "Shadow=1,"
        "Bold=1,"
        "Alignment=2,"
        "MarginV=220"
    )

    command = [
        ffmpeg,
        "-y",
        "-i",
        video_path,
        "-i",
        audio_path,
        "-vf",
        f"subtitles='{subtitle_path}':force_style='{style}'",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
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

    print(result.stdout)
    print(result.stderr)

    if result.returncode != 0:
        raise Exception(result.stderr)

    return output_path