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
            "pan_left",
            "pan_right",
            "pan_up",
            "pan_down",
        ]
    )

    base_scale = random.uniform(
        1.15,
        1.25,
    )

    zoom_amount = random.uniform(
        0.06,
        0.12,
    )

    clip = (
        ImageClip(image_path)
        .resized(height=int(VIDEO_HEIGHT * base_scale))
        .with_duration(duration)
    )

    img_w, img_h = clip.size

    max_x = max(
        0,
        img_w - VIDEO_WIDTH,
    )

    max_y = max(
        0,
        img_h - VIDEO_HEIGHT,
    )

    if motion == "zoom_in":

        clip = (
            clip
            .resized(
                lambda t: base_scale
                + zoom_amount * (t / duration)
            )
            .with_position("center")
        )

    elif motion == "zoom_out":

        clip = (
            clip
            .resized(
                lambda t: (base_scale + zoom_amount)
                - zoom_amount * (t / duration)
            )
            .with_position("center")
        )

    elif motion == "pan_left":

        clip = clip.with_position(
            lambda t: (
                -(max_x * (t / duration)),
                "center",
            )
        )

    elif motion == "pan_right":

        clip = clip.with_position(
            lambda t: (
                -(max_x * (1 - t / duration)),
                "center",
            )
        )

    elif motion == "pan_up":

        clip = clip.with_position(
            lambda t: (
                "center",
                -(max_y * (t / duration)),
            )
        )

    else:

        clip = clip.with_position(
            lambda t: (
                "center",
                -(max_y * (1 - t / duration)),
            )
        )

    return clip