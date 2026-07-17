import os

from app.services.image_service import generate_image
from app.services.render_profile import thumbnail_filename


def create_thumbnail(
    title: str,
    topic: str,
    project_path: str,
    channel: str = "wellbeing",
    scene1_narration: str = "",
    scene1_image_prompt: str = "",
    render_profile: dict = None,
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
        thumbnail_filename(render_profile),
    )

    # Sprint122 - Longform Foundation: render_profile이 있을 때만
    # aspect_ratio를 보탠다(없으면 generate_image()의 기본값 "9:16"이
    # 그대로 적용됨) - 완전히 하위 호환.
    generate_image_kwargs = {"is_thumbnail": True}
    if render_profile is not None:
        generate_image_kwargs["aspect_ratio"] = render_profile["thumbnail_aspect_ratio"]

    generate_image(
        prompt,
        output,
        channel,
        **generate_image_kwargs,
    )

    return output
