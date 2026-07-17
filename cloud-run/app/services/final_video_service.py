import os
import subprocess

from app.services.render_profile import final_video_filename, silent_video_filename


def merge_video_audio(project_path: str, render_profile: dict = None):

    ffmpeg = "ffmpeg"

    video_path = os.path.join(
        project_path,
        "video",
        silent_video_filename(render_profile),
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
        final_video_filename(render_profile),
    )

    subtitle_path = subtitle_path.replace("\\", "/")
    subtitle_path = subtitle_path.replace(":", "\\:")

    # Sprint68-1 - Shorts 자막 UI 개선. 실측 보정(2026-07-10, 1080x1920
    # 검정 배경에 동일 force_style로 실제 렌더링해 흰 글자 픽셀
    # bounding box를 측정) 결과, libass는 MarginV를 지정값 그대로가
    # 아니라 내부 PlayRes 기준 스케일(약 6.67배)을 적용해 실제
    # 픽셀로 환산한다 - MarginV=90/150/200/250에서 세로 중심이
    # 1920px 기준 65.8%/45.0%/27.6%/12.4%로 선형 이동함을 확인했고,
    # 이 관계를 그대로 보간해 MarginV=115가 목표인 화면 높이
    # 56~58% 지점(실측 57.1%)에 해당함을 검증했다. FontSize는
    # 22->18로 낮춰(실측 "가나다" 폭 320px->263px, 약 18% 축소 -
    # 요구사항 15~20% 범위 안) 모바일 Shorts 가독성을 유지하면서
    # 자막을 축소한다. Alignment=2(하단 고정)만 쓰고 scene별 상단
    # override는 더 이상 만들지 않는다(subtitle_service.py 참고) -
    # 모든 cue가 항상 같은 위치에 고정된다.
    # Sprint122 - Longform Foundation: render_profile이 있으면 그
    # subtitle_font_size/subtitle_margin_v를, 없으면(기본값 None)
    # 기존 하드코딩 값(Sprint68-1 실측)을 그대로 쓴다 - 완전히 하위
    # 호환.
    font_size = render_profile["subtitle_font_size"] if render_profile else 18
    margin_v = render_profile["subtitle_margin_v"] if render_profile else 115

    style = (
        "FontName=Malgun Gothic,"
        f"FontSize={font_size},"
        "PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H000000&,"
        "BorderStyle=1,"
        "Outline=4,"
        "Shadow=0,"
        "Bold=1,"
        "Alignment=2,"
        f"MarginV={margin_v},"
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