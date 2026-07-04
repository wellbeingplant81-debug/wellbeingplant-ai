import random

from moviepy import ImageClip


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920


def build_kenburns_clip(
    image_path: str,
    duration: float,
):

    direction = random.choice([
        "zoom_in",
        "zoom_out",
    ])

    base_scale = 1.15

    clip = (
        ImageClip(image_path)
        .resized(height=int(VIDEO_HEIGHT * base_scale))
        .with_duration(duration)
        .with_position("center")
    )

    if direction == "zoom_in":

        clip = clip.resized(
            lambda t: base_scale + (0.10 * (t / duration))
        )

    else:

        clip = clip.resized(
            lambda t: (base_scale + 0.10) - (0.10 * (t / duration))
        )

    return clip