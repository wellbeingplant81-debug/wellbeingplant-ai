"""
Sprint64 - Scene Timeline 단일화.

scene 경계(각 scene이 화면에 언제 나타나고 언제 사라지는지)를 계산하는
유일한 곳이다. video_builder.py도, subtitle_service.py도 여기서 나온
타임라인만 쓴다.

왜 단일화가 필요했나
--------------------
Sprint63까지 경계는 두 곳에서 따로 계산됐고, 측정 방식과 변환 규칙이
둘 다 달랐다:

    video_builder     moviepy AudioFileClip.duration
                      + _apply_duration_limits()  (Sprint55 duration clamp)
    subtitle_service  ffprobe(get_audio_duration)
                      + 원본 누적

실측한 경계 오차(2026-08-05):

    기존 production(mp3)             최대  62ms  측정 방식 차이만으로
    Sprint63 WAV 전환 후                    0ms  부수효과로 해소됐을 뿐
                                            구조는 그대로 남아 있었다
    _apply_duration_limits 발동 시   최대 800ms  잠복 결함

왜 오디오가 기준인가
--------------------
최종 MP4의 오디오(final_audio)는 scene 오디오를 실제 길이 그대로
이어붙인 것이다. 그러니 "scene 3의 나레이션이 언제 시작되는가"는 앞선
scene 오디오 길이의 합으로 이미 물리적으로 정해져 있다. 화면과 자막이
그 값을 따라야지, 그 값이 화면을 따라올 수는 없다.

따라서 어떤 재계산도 경계를 이동시키지 않는다. Sprint55가 duration
clamp로 막으려던 것("짧은 scene에서 Ken Burns 모션이 너무 빨라짐")은
경계가 아니라 모션 강도 쪽에서 처리한다 - kenburns.moderate_zoom_
intensity()/moderate_pan_travel() 참고.

측정은 ffprobe(get_audio_duration) 하나로 통일한다. moviepy의
AudioFileClip.duration은 추정치라 씬마다 수 ms씩 어긋나고(Sprint59에서
이미 확인), 실제로 만들어지는 final_audio는 ffprobe 값의 합과 일치한다.
"""

import os

from app.services import audio_policy
from app.services.duration_optimizer import get_audio_duration


def scene_audio_path(project_path: str, scene_number: int) -> str:
    """scene 번호에 대응하는 나레이션 오디오 경로."""

    return os.path.join(
        project_path,
        "audio",
        "scenes",
        audio_policy.scene_audio_filename(scene_number),
    )


def build_timeline(project_path: str, scenes: list) -> list:
    """
    scene 목록(script.json의 scenes)을 받아 각 scene의 화면 점유 구간을
    계산한다. 반환값은 scene 번호 오름차순이며, 각 항목은

        {"scene": int, "start": float, "duration": float, "end": float}

    구간은 빈틈도 겹침도 없다: 앞 scene의 end가 다음 scene의 start와
    정확히 같고, 전체 합은 나레이션 오디오 전체 길이와 같다.

    오디오 파일이 없으면 예외를 던진다 - 경계를 추측으로 채우면 그
    순간부터 화면과 소리가 어긋나기 때문이다.
    """

    ordered = sorted(scenes, key=lambda scene: scene["scene"])

    timeline = []
    cursor = 0.0

    for scene in ordered:

        scene_number = scene["scene"]
        path = scene_audio_path(project_path, scene_number)

        if not os.path.exists(path):
            raise Exception(
                f"Scene {scene_number}의 오디오 파일이 없습니다: {path}"
            )

        duration = get_audio_duration(path)

        timeline.append(
            {
                "scene": scene_number,
                "start": cursor,
                "duration": duration,
                "end": cursor + duration,
            }
        )

        cursor += duration

    return timeline


def timeline_total(timeline: list) -> float:
    """타임라인 전체 길이(= 나레이션 오디오 전체 길이)."""

    return timeline[-1]["end"] if timeline else 0.0


def durations(timeline: list) -> list:
    """각 scene의 화면 점유 길이만 순서대로."""

    return [slot["duration"] for slot in timeline]
