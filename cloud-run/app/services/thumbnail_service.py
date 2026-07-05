import os

from app.services.image_service import generate_image


def create_thumbnail(
    title: str,
    topic: str,
    project_path: str,
    channel: str = "wellbeing",
    scene1_narration: str = "",
    scene1_image_prompt: str = "",
):

    prompt = f"""
YouTube Shorts thumbnail based on this exact scene:

{scene1_image_prompt}

The thumbnail must depict the same subject, setting, and mood as
the scene described above. Do not introduce a different subject,
location, or background.

Context, for emotional tone only (do not add new visual elements
from this beyond expression or mood):
{scene1_narration}

For maximum click-through-rate, you may slightly exaggerate:

- facial expression (more surprised, curious, or emotionally intense)
- composition (tighter close-up, stronger focus on the subject)

YouTube Shorts thumbnail

Close-up

High emotion

Cinematic lighting

Bright color grading

Focus on subject

No text

No watermark
"""

    output = os.path.join(
        project_path,
        "thumbnail.png",
    )

    generate_image(
        prompt,
        output,
        channel,
        is_thumbnail=True,
    )

    return output
