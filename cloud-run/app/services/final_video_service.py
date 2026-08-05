import os
import subprocess
from app.services import audio_policy


# Sprint62 - Master Quality Render Pipeline. 최종 인코딩 품질 목표.
# 이번 Epic에서는 이 값을 바꾸지 않는다 - 화질 개선은 오직
# video_builder.py의 1차 인코딩 손실을 없애는 데서만 나와야, 무엇이
# 실제로 개선을 만들었는지 측정으로 분리할 수 있기 때문이다.
FINAL_CRF = 18


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
        audio_policy.FINAL_AUDIO_FILENAME,
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
        "MarginV=90,"
        # subtitle_service.py가 이미 한 줄에 맞춰 자막을 나눠두므로,
        # libass가 자체 판단으로 재줄바꿈(단어 중간에서 줄이 꺾이는
        # 현상)하지 않도록 자동 줄바꿈을 끈다.
        "WrapStyle=2"
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
        str(FINAL_CRF),

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        "-c:a",
        audio_policy.DELIVERY_AUDIO_CODEC,

        "-b:a",
        audio_policy.DELIVERY_AUDIO_BITRATE,

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