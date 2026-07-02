from moviepy import ImageClip

def build_kenburns_clip(
    image_path: str,
    duration: float,
):
    return (
        ImageClip(image_path)
        .with_duration(duration)
    )