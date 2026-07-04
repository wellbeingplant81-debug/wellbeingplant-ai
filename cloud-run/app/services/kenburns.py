import random

from moviepy import ImageClip


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920


def build_kenburns_clip(
    image_path: str,
    duration: float,
):

    motion = random.choice(
        [
            "zoom_in",
            "zoom_out",
            "left",
            "right",
            "up",
            "down",
        ]
    )

    base_scale = 1.15

    clip = (
        ImageClip(image_path)
        .resized(height=int(VIDEO_HEIGHT * base_scale))
        .with_duration(duration)
    )

    # -------------------------
    # ZOOM IN
    # -------------------------

    if motion == "zoom_in":

        clip = clip.resized(
            lambda t: base_scale + (0.12 * (t / duration))
        )

        clip = clip.with_position("center")

    # -------------------------
    # ZOOM OUT
    # -------------------------

    elif motion == "zoom_out":

        clip = clip.resized(
            lambda t: (base_scale + 0.12) - (0.12 * (t / duration))
        )

        clip = clip.with_position("center")

    # -------------------------
    # PAN LEFT
    # -------------------------

    elif motion == "left":

        clip = clip.with_position(
            lambda t: (
                -120 * (t / duration),
                "center",
            )
        )

    # -------------------------
    # PAN RIGHT
    # -------------------------

    elif motion == "right":

        clip = clip.with_position(
            lambda t: (
                120 * (t / duration),
                "center",
            )
        )

    # -------------------------
    # PAN UP
    # -------------------------

    elif motion == "up":

        clip = clip.with_position(
            lambda t: (
                "center",
                -120 * (t / duration),
            )
        )

    # -------------------------
    # PAN DOWN
    # -------------------------

    elif motion == "down":

        clip = clip.with_position(
            lambda t: (
                "center",
                120 * (t / duration),
            )
        )

    return clip