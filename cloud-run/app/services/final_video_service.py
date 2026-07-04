import os
import subprocess


def merge_video_audio(project_path: str):

    ffmpeg = "ffmpeg"

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

    subtitle_path = subtitle_path.replace("\\", "/")
    subtitle_path = subtitle_path.replace(":", "\\:")

    style = (
        "FontName=Malgun Gothic,"
        "FontSize=22,"
        "PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H000000&,"
        "BorderStyle=1,"
        "Outline=4,"
        "Shadow=0,"
        "Bold=1,"
        "Alignment=2,"
        "MarginV=90"
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

        "-preset",
        "slow",

        "-crf",
        "18",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        "-c:a",
        "aac",

        "-b:a",
        "192k",

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