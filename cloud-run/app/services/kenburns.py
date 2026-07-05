import math
import random

from moviepy import ImageClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

# Tiny safety margin over the exact cover-fit scale, purely to absorb
# floating point / integer-rounding error in the resizer — not a framing margin.
SAFETY_SCALE = 1.001

ZOOM_INTENSITY_RANGE = (0.04, 0.10)
PAN_DISTANCE_RANGE = (40, 160)
MAX_PAN_EXTRA_SCALE = 0.12
MIN_PAN_TRAVEL = 40

MOTIONS = [
    "zoom_in",
    "zoom_out",
    "pan_horizontal",
    "pan_vertical",
]

_last_motion = None


def _ease_in_out(progress):
    return 0.5 - 0.5 * math.cos(math.pi * progress)


def _progress(t, duration):
    return _ease_in_out(min(1.0, max(0.0, t / duration)))


def _pick_motion():

    global _last_motion

    choices = MOTIONS

    if _last_motion is not None:
        choices = [m for m in MOTIONS if m != _last_motion] or MOTIONS

    motion = random.choice(choices)

    _last_motion = motion

    return motion


def _fit_scale(img_w, img_h):
    return SAFETY_SCALE * max(
        VIDEO_WIDTH / img_w,
        VIDEO_HEIGHT / img_h,
    )


def _scale_for_travel(img_dim, canvas_dim, travel):
    return (canvas_dim + travel) / img_dim


def _pan_offsets(slack, travel):

    travel = min(travel, slack)

    start = random.uniform(-slack, 0)
    end = start + random.choice([-1, 1]) * travel
    end = min(0.0, max(-slack, end))

    if slack > 0 and abs(end - start) < min(MIN_PAN_TRAVEL, slack):
        end = 0.0 if start < -slack / 2 else -slack

    return start, end


def build_kenburns_clip(
    image_path: str,
    duration: float,
):

    motion = _pick_motion()

    raw = ImageClip(image_path).with_duration(duration)
    img_w, img_h = raw.w, raw.h

    fit_scale = _fit_scale(img_w, img_h)

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
    # PAN HORIZONTAL
    # -------------------------

    elif motion == "pan_horizontal":

        desired_travel = random.uniform(*PAN_DISTANCE_RANGE)

        capped_scale = fit_scale * (1 + MAX_PAN_EXTRA_SCALE)
        max_slack_x = max(0.0, img_w * capped_scale - VIDEO_WIDTH)

        travel = min(desired_travel, max_slack_x)

        required_scale = _scale_for_travel(img_w, VIDEO_WIDTH, travel)
        scale = max(fit_scale, min(required_scale, capped_scale))

        clip = raw.resized(scale).with_duration(duration)

        slack_x = max(0.0, clip.w - VIDEO_WIDTH)
        slack_y = max(0.0, clip.h - VIDEO_HEIGHT)

        start_x, end_x = _pan_offsets(slack_x, travel)
        y = -slack_y / 2

        clip = clip.with_position(
            lambda t: (
                start_x + (end_x - start_x) * _progress(t, duration),
                y,
            )
        )

    # -------------------------
    # PAN VERTICAL
    # -------------------------

    else:

        desired_travel = random.uniform(*PAN_DISTANCE_RANGE)

        capped_scale = fit_scale * (1 + MAX_PAN_EXTRA_SCALE)
        max_slack_y = max(0.0, img_h * capped_scale - VIDEO_HEIGHT)

        travel = min(desired_travel, max_slack_y)

        required_scale = _scale_for_travel(img_h, VIDEO_HEIGHT, travel)
        scale = max(fit_scale, min(required_scale, capped_scale))

        clip = raw.resized(scale).with_duration(duration)

        slack_x = max(0.0, clip.w - VIDEO_WIDTH)
        slack_y = max(0.0, clip.h - VIDEO_HEIGHT)

        start_y, end_y = _pan_offsets(slack_y, travel)
        x = -slack_x / 2

        clip = clip.with_position(
            lambda t: (
                x,
                start_y + (end_y - start_y) * _progress(t, duration),
            )
        )

    clip = CompositeVideoClip(
        [clip],
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
    ).with_duration(duration)

    return clip
