import math
import os
import random
import tempfile

from PIL import Image
from moviepy import ImageClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

# Sprint76 - 일부 스톡/생성 이미지가 PIL의 decompression-bomb 안전
# 한도(기본 178,956,970 = 2 * Image.MAX_IMAGE_PIXELS)를 넘어 Video
# Builder가 PIL.Image.DecompressionBombError로 죽는 게 실제 E2E에서
# 확인됐다(2026-07-11, Sprint74 검증 중 200,540,160 픽셀 이미지).
# Ken Burns는 최종 1080x1920 캔버스에 맞춰 리사이즈하므로 원본이 이
# 정도로 클 필요가 전혀 없다 - 정상 이미지(절대다수)는 전혀 건드리지
# 않고, 이 한도를 실제로 넘어서 예외가 나는 경우에만 안전한 해상도로
# 축소한 임시 사본을 만들어 한 번 더 시도한다.
SAFE_MAX_PIXELS = 25_000_000

# Tiny safety margin over the exact cover-fit scale, purely to absorb
# floating point / integer-rounding error in the resizer — not a framing margin.
SAFETY_SCALE = 1.001

ZOOM_INTENSITY_RANGE = (0.04, 0.10)
PAN_DISTANCE_RANGE = (40, 160)
MAX_PAN_EXTRA_SCALE = 0.12

# Sprint70-1 - Ken Burns 다양화. 기존 pan_horizontal/pan_vertical은
# 내부적으로 방향(왼쪽/오른쪽, 위/아래)이 랜덤이라 "같은 모션"이어도
# 실제로는 다르게 보일 수 있었다 - 방향까지 이름에 고정해 4방향 pan +
# zoom_in/zoom_out 총 6개로 늘려, scene마다/scene 안 연속 asset마다
# 서로 다른 모션을 실제로 구별해 고를 수 있게 한다.
MOTIONS = [
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "pan_up",
    "pan_down",
]

_last_motion = None


def _ease_in_out(progress):
    return 0.5 - 0.5 * math.cos(math.pi * progress)


def _progress(t, duration):
    return _ease_in_out(min(1.0, max(0.0, t / duration)))


def _pick_motion(exclude=None):
    """
    Sprint70-1 - exclude(호출자가 이미 이번 scene에서 쓴 모션들)가
    주어지면 그 모션들을 후보에서 뺀다. 기존 전역 _last_motion 회피
    (scene 경계를 넘어서도 바로 직전 모션은 피함)와 함께 적용된다.
    둘을 합쳐도 후보가 하나도 안 남으면(극단적으로 asset이 MOTIONS
    개수보다 많은 경우) 예외 없이 전체 목록으로 폴백한다.
    """

    global _last_motion

    excluded = set(exclude) if exclude else set()

    if _last_motion is not None:
        excluded.add(_last_motion)

    choices = [m for m in MOTIONS if m not in excluded] or MOTIONS

    motion = random.choice(choices)

    _last_motion = motion

    return motion


def _directional_pan_offsets(slack, travel, direction):
    """
    Sprint70-1 - pan_left/right/up/down처럼 이름에 방향이 고정된
    모션을 위한 offset 계산. direction<0이면 위치가 0에서 -slack
    쪽으로(콘텐츠가 오른쪽/아래로 흐르는 것처럼 보임 - pan_right/
    pan_down), direction>0이면 -slack에서 0 쪽으로(pan_left/pan_up)
    정확히 travel만큼 이동한다. 기존 _pan_offsets()는 방향이 랜덤이라
    경계에 너무 가까운 시작점을 뽑으면 실제 이동 거리가 travel보다
    훨씬 작아지는 보정이 필요했지만, 여기서는 방향이 고정이라 start를
    처음부터 travel만큼 이동 가능한 범위에서만 뽑아 그런 보정이
    필요 없다.
    """

    travel = min(travel, slack)

    if direction < 0:
        start = random.uniform(-slack + travel, 0.0)
        end = start - travel
    else:
        start = random.uniform(-slack, -travel)
        end = start + travel

    return start, end


def _fit_scale(img_w, img_h, width=VIDEO_WIDTH, height=VIDEO_HEIGHT):
    return SAFETY_SCALE * max(
        width / img_w,
        height / img_h,
    )


def _scale_for_travel(img_dim, canvas_dim, travel):
    return (canvas_dim + travel) / img_dim


def _downscaled_copy_for_oversized_image(image_path: str) -> str:
    """
    Sprint76 - PIL의 decompression-bomb 한도를 실제로 넘은 이미지만
    호출되는 복구 경로. Image.MAX_IMAGE_PIXELS를 이 함수 실행 동안만
    해제해 원본을 열고, SAFE_MAX_PIXELS 이하로 비율을 유지한 채 축소한
    사본을 임시 파일로 저장해 그 경로를 반환한다. 원본 파일은 전혀
    수정하지 않는다.
    """

    original_limit = Image.MAX_IMAGE_PIXELS
    # 정상 운영 환경에서는 SAFE_MAX_PIXELS(25M)를 그대로 쓴다. 하지만
    # 이 값은 항상 "현재 PIL 한도보다 확실히 안전한 크기"여야 하므로,
    # 누군가 Image.MAX_IMAGE_PIXELS를 더 낮게 설정해 둔 환경(테스트
    # 포함)에서는 그 한도를 넘지 않도록 더 작은 쪽을 목표로 삼는다.
    pixel_budget = min(SAFE_MAX_PIXELS, original_limit) if original_limit else SAFE_MAX_PIXELS

    try:
        Image.MAX_IMAGE_PIXELS = None

        with Image.open(image_path) as img:
            width, height = img.size
            scale = min(1.0, (pixel_budget / (width * height)) ** 0.5)
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))

            resized = img.convert("RGB").resize(new_size, Image.LANCZOS)

            fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            resized.save(tmp_path, "JPEG", quality=95)

            return tmp_path

    finally:
        Image.MAX_IMAGE_PIXELS = original_limit


def _load_image_clip(image_path: str, duration: float):
    try:
        return ImageClip(image_path).with_duration(duration)
    except Image.DecompressionBombError:
        safe_path = _downscaled_copy_for_oversized_image(image_path)
        return ImageClip(safe_path).with_duration(duration)


def build_kenburns_clip(
    image_path: str,
    duration: float,
    motion: str = None,
    width: int = None,
    height: int = None,
):
    """
    Sprint70-1 - motion을 명시적으로 넘기면(예: video_builder.py가
    scene 안 연속 asset마다 서로 다른 모션을 미리 골라 넘기는 경우)
    그 모션을 그대로 쓰고 자동 선택(_pick_motion)은 하지 않는다.
    motion을 안 넘기면(기본값 None) 기존과 100% 동일하게 자동
    선택한다 - 완전히 하위 호환.

    Sprint122 - Longform Foundation: width/height를 안 넘기면(기본값
    None) 기존 모듈 상수 VIDEO_WIDTH/VIDEO_HEIGHT를 그대로 쓴다 -
    완전히 하위 호환. render_profile의 width/height(예: Longform
    1920x1080)를 넘기면 그 canvas 기준으로 pan/zoom과 최종 clip
    크기가 계산된다.
    """

    global _last_motion

    if width is None:
        width = VIDEO_WIDTH
    if height is None:
        height = VIDEO_HEIGHT

    if motion is None:
        motion = _pick_motion()
    else:
        _last_motion = motion

    raw = _load_image_clip(image_path, duration)
    img_w, img_h = raw.w, raw.h

    fit_scale = _fit_scale(img_w, img_h, width, height)

    # -------------------------
    # ZOOM IN / OUT
    # -------------------------

    if motion in ("zoom_in", "zoom_out"):

        intensity = random.uniform(*ZOOM_INTENSITY_RANGE)

        start_scale, end_scale = (
            (fit_scale, fit_scale * (1 + intensity))
            if motion == "zoom_in"
            else (fit_scale * (1 + intensity), fit_scale)
        )

        def zoom_size(t):
            s = start_scale + (end_scale - start_scale) * _progress(t, duration)
            return (img_w * s, img_h * s)

        clip = (
            raw.resized(zoom_size)
            .with_duration(duration)
            .with_position("center")
        )

    # -------------------------
    # PAN LEFT / RIGHT
    # -------------------------

    elif motion in ("pan_left", "pan_right"):

        desired_travel = random.uniform(*PAN_DISTANCE_RANGE)

        capped_scale = fit_scale * (1 + MAX_PAN_EXTRA_SCALE)
        max_slack_x = max(0.0, img_w * capped_scale - width)

        travel = min(desired_travel, max_slack_x)

        required_scale = _scale_for_travel(img_w, width, travel)
        scale = max(fit_scale, min(required_scale, capped_scale))

        clip = raw.resized(scale).with_duration(duration)

        slack_x = max(0.0, clip.w - width)
        slack_y = max(0.0, clip.h - height)

        direction = -1 if motion == "pan_right" else 1
        start_x, end_x = _directional_pan_offsets(slack_x, travel, direction)
        y = -slack_y / 2

        clip = clip.with_position(
            lambda t: (
                start_x + (end_x - start_x) * _progress(t, duration),
                y,
            )
        )

    # -------------------------
    # PAN UP / DOWN
    # -------------------------

    else:

        desired_travel = random.uniform(*PAN_DISTANCE_RANGE)

        capped_scale = fit_scale * (1 + MAX_PAN_EXTRA_SCALE)
        max_slack_y = max(0.0, img_h * capped_scale - height)

        travel = min(desired_travel, max_slack_y)

        required_scale = _scale_for_travel(img_h, height, travel)
        scale = max(fit_scale, min(required_scale, capped_scale))

        clip = raw.resized(scale).with_duration(duration)

        slack_x = max(0.0, clip.w - width)
        slack_y = max(0.0, clip.h - height)

        direction = -1 if motion == "pan_down" else 1
        start_y, end_y = _directional_pan_offsets(slack_y, travel, direction)
        x = -slack_x / 2

        clip = clip.with_position(
            lambda t: (
                x,
                start_y + (end_y - start_y) * _progress(t, duration),
            )
        )

    clip = CompositeVideoClip(
        [clip],
        size=(width, height),
    ).with_duration(duration)

    return clip
