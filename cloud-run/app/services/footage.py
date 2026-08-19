"""
Sprint223 - 받아 온 영상이 실제로 움직인다 (Epic 65).

무엇이 잘못되어 있었나
----------------------
이 프로그램은 스톡 영상을 검색하고, 내려받고, **첫 프레임만 뽑은 뒤
원본을 지웠다**(asset_integration_service). 최종 영상에서 움직이는
것은 Ken Burns 로 밀고 당긴 정지 사진뿐이었다.

    받아 온 것        20초짜리 무릎 스트레칭 영상
    최종에 남은 것    그 영상의 0초 프레임 한 장

이미 값을 치르고 받아 온 움직임을 매번 버리고 있었다.

이 파일이 하는 일
-----------------
kenburns.build_kenburns_clip 옆에 서는 형제 하나를 둔다. 부르는 쪽이
아는 것은 "이 자산으로 이 길이짜리 clip 하나를 달라"뿐이고, 사진이냐
영상이냐로 갈리는 자리는 **여기 한 곳**이다.

    is_footage(path)                 이 자산이 영상인가
    build_footage_clip(path, 길이)   그 길이짜리 clip

타임라인을 건드리지 않는다
--------------------------
돌려주는 clip 의 크기(1080x1920) · 길이 · fps(30) · 소리 없음이 Ken
Burns 쪽과 똑같다. 그래야 video_builder 의 겹침(CROSSFADE_DURATION)과
padding 계산이 자산의 종류를 몰라도 된다 - 그 계산은 이번에 한 줄도
바뀌지 않았다.

크기를 여기서 새로 정하지 않고 kenburns 에서 가져오는 것도 같은
이유다. 두 곳에 적으면 어느 날 한쪽만 바뀌고, 그날 이어 붙인 영상의
절반이 다른 크기가 된다.

소리를 먼저 뗀다
----------------
스톡 영상에는 대개 현장음이나 음악이 붙어 있다. 그것이 최종에 섞이면
나레이션 위에 남의 음악이 깔린다. video_builder 의
write_videofile(audio=False) 가 중간본에서 이미 막고 있지만 여기서도
뗀다 - 막는 자리가 하나뿐이면 그 자리가 바뀌는 날 조용히 새어 나온다.

9:16 은 채우고 남는 쪽을 자른다
-------------------------------
스톡 영상은 대개 가로다. 세로 화면에 맞추면서 여백을 두면 검은 띠가
남고, 늘이면 사람이 홀쭉해진다. 그래서 짧은 변이 화면을 덮을 때까지
비율 그대로 키운 뒤 넘치는 쪽을 **가운데 기준으로** 자른다.

kenburns 가 쓰는 SAFETY_SCALE 을 여기서도 쓴다. 정수 반올림 때문에
1px 이 비는 것을 막는 여유일 뿐, 구도상의 여백이 아니다.

길이가 안 맞을 때
-----------------
scene 의 길이는 나레이션 오디오가 정한다(scene_timeline). 받아 온
영상이 그 길이에 맞을 이유가 없다.

    길면          앞에서 필요한 만큼만 자른다
    짧으면        되풀이한다
    아주 짧으면   한 번 재생하고 마지막 프레임을 붙잡는다

아주 짧은 것을 되풀이하지 않는 이유는, 0.4초짜리를 열 번 잇는 것이
움직임이 아니라 딸꾹질로 보이기 때문이다. 그 경계는 아래
LOOP_MIN_SOURCE_SECONDS 하나로 정한다.

무엇을 하지 않는가
------------------
검색 순위를 건드리지 않는다. 어떤 scene 이 영상을 받을지 정하는 것은
여전히 asset_ranking_service 이고, 이 파일은 이미 정해져 받아 온 것을
화면에 올릴 뿐이다.
"""

import math
import os

from moviepy import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.fx.Freeze import Freeze
from moviepy.video.fx.Loop import Loop

# 화면의 크기와 여유는 Ken Burns 쪽이 정한 것을 그대로 쓴다. 두 clip 이
# 같은 타임라인에 이어 붙으므로 같아야 한다.
from app.services.kenburns import SAFETY_SCALE, VIDEO_HEIGHT, VIDEO_WIDTH


# 이어 붙이는 clip 이 전부 같은 fps 여야 한다. video_builder 가
# 최종본을 30으로 쓰고, Ken Burns clip 도 그 값으로 맞춰진다.
FPS = 30

# 자산이 영상인지 아는 방법. 확장자로 본다 - 파일을 열어 보는 것은
# 렌더가 시작되기 전에 scene 마다 한 번씩 프로세스를 더 띄우는 일이고,
# 이 폴더에 놓는 것은 우리 코드(asset_integration_service)뿐이다.
#
# Sprint224 - .mkv 와 .avi 가 늘었다. 사람이 제 폴더에 넣어 둔 영상이
# 그대로 복사되어 오기 때문이다(확장자를 바꾸지 않는다). 이 목록이
# local_library 가 영상이라고 부르는 것을 덮지 못하면, 덮이지 않은
# 확장자는 여기서 사진으로 읽혀 ImageClip 에 넘어간다 - 그 순간
# 렌더가 깨진다. 두 목록이 갈라지지 않는 것은 시험으로 잠근다
# (test_footage.TheKindOfAssetTest).
FOOTAGE_EXTENSIONS = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi")

# 이보다 짧으면 되풀이하지 않고 마지막 프레임을 붙잡는다.
LOOP_MIN_SOURCE_SECONDS = 1.0

TRIM = "trim"
LOOP = "loop"
HOLD = "hold"


def is_footage(path: str) -> bool:
    """이 자산이 영상인가. 순수 함수입니다."""

    return str(path or "").lower().endswith(FOOTAGE_EXTENSIONS)


def cover_scale(source_width: int, source_height: int) -> float:
    """
    9:16 화면을 덮을 때까지 키우는 배율. 순수 함수입니다.

    kenburns._fit_scale 과 같은 식이다 - 같은 화면을 덮는 같은 계산이라
    다르면 그것이 결함이다.
    """

    if source_width <= 0 or source_height <= 0:
        raise ValueError(
            f"영상 크기를 알 수 없습니다: {source_width}x{source_height}")

    return SAFETY_SCALE * max(
        VIDEO_WIDTH / source_width,
        VIDEO_HEIGHT / source_height,
    )


def scaled_size(source_width: int, source_height: int) -> tuple:
    """키운 뒤의 크기(픽셀). 순수 함수입니다."""

    scale = cover_scale(source_width, source_height)

    return (round(source_width * scale), round(source_height * scale))


def crop_box(source_width: int, source_height: int) -> tuple:
    """
    키운 그림에서 잘라낼 자리 (x1, y1, x2, y2). 순수 함수입니다.

    가운데를 남긴다. 스톡 영상의 피사체는 대개 가운데에 있고, 어느
    쪽을 남길지 고를 근거가 우리에게 없다 - 근거 없이 한쪽으로
    치우치면 그것은 구도를 정한 것이 아니라 던진 것이다.
    """

    wide, tall = scaled_size(source_width, source_height)

    x1 = max(0, (wide - VIDEO_WIDTH) // 2)
    y1 = max(0, (tall - VIDEO_HEIGHT) // 2)

    return (x1, y1, x1 + VIDEO_WIDTH, y1 + VIDEO_HEIGHT)


def plan(source_duration: float, want_duration: float) -> dict:
    """
    받아 온 길이로 원하는 길이를 어떻게 채울지. 순수 함수입니다.

    파일을 열지 않는다 - 여기가 이 파일에서 가장 틀리기 쉬운 곳이라
    영상 없이 검사할 수 있어야 한다.
    """

    if want_duration <= 0:
        raise ValueError(f"scene 길이가 0 이하입니다: {want_duration}")

    if source_duration <= 0:
        raise ValueError(f"영상 길이를 알 수 없습니다: {source_duration}")

    if source_duration >= want_duration:
        return {"mode": TRIM, "take": want_duration}

    if source_duration >= LOOP_MIN_SOURCE_SECONDS:
        return {
            "mode": LOOP,
            "times": math.ceil(want_duration / source_duration),
            "take": want_duration,
        }

    return {
        "mode": HOLD,
        "play": source_duration,
        "freeze": want_duration - source_duration,
        "take": want_duration,
    }


def _fitted(clip, source_width: int, source_height: int):
    """비율 그대로 키우고 가운데를 남긴다."""

    x1, y1, x2, y2 = crop_box(source_width, source_height)

    return clip.resized(
        scaled_size(source_width, source_height),
    ).cropped(x1=x1, y1=y1, x2=x2, y2=y2)


def _stretched(clip, how: dict):
    """받아 온 길이를 원하는 길이로 맞춘다."""

    if how["mode"] == TRIM:
        return clip.subclipped(0, how["take"])

    if how["mode"] == LOOP:
        return clip.with_effects([Loop(duration=how["take"])])

    return clip.with_effects([Freeze(t="end", total_duration=how["take"])])


def build_footage_clip(footage_path: str, duration: float,
                       scene_number=None):
    """
    그 영상으로 이 길이짜리 clip 하나. Ken Burns 쪽과 같은 모양이다.

    돌려주는 것은 항상 1080x1920 · duration · fps 30 · 소리 없음이다.

    Sprint227 - scene 번호를 주면 어떻게 채웠는지 적어 둔다
    ------------------------------------------------------
    받아 온 영상이 scene보다 많이 짧으면 마지막 프레임을 붙잡게 되고
    (hold), 그 scene은 사실상 예전의 정지 사진으로 되돌아간다. 그 일이
    얼마나 자주 일어나는지 지금까지 아무 데도 남지 않았다.

    적는 것은 관측이지 판정이 아니다. 못 적어도 렌더는 그대로 간다 -
    관측이 제품을 멈추게 하면 관찰을 켠 것이 잘못이 된다.

    번호를 주지 않으면 아무것도 적지 않는다. 예전 호출부가 그 길이다.
    """

    if not os.path.exists(footage_path):
        raise Exception(f"영상 파일이 없습니다: {footage_path}")

    raw = VideoFileClip(footage_path).without_audio()

    how = plan(raw.duration, duration)

    if scene_number is not None:
        try:
            from app.services import asset_observatory

            asset_observatory.record_footage(
                scene_number, how["mode"], raw.duration, duration,
            )
        except Exception as exc:
            print(f"[Footage] 관측 기록 실패(무시): {exc}")

    clip = _fitted(_stretched(raw, how), raw.w, raw.h)

    clip = clip.with_duration(duration).with_fps(FPS)

    # Ken Burns 쪽과 같은 자리에서 끝난다 - 정확히 화면 크기인 clip
    # 하나로 나가야 겹침 계산이 종류를 몰라도 된다.
    return CompositeVideoClip(
        [clip],
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
    ).with_duration(duration)
