import os

from app.services.image_service import generate_image


def create_thumbnail(
    title: str,
    topic: str,
    project_path: str,
):

    prompt = f"""
Ultra realistic

YouTube Shorts thumbnail

Close-up

Korean person

Extreme facial expression

High emotion

Cinematic lighting

Bright color grading

Photorealistic

8K

Vertical composition

Focus on face

No text

No watermark

Subject:
{topic}

Emotion:
Surprised, shocking, curiosity
"""

    output = os.path.join(
        project_path,
        "thumbnail.png",
    )

    generate_image(
        prompt,
        output,
    )

    return output