import os

from app.prompts import prompt_elements as slots
from app.services import image_service
from app.services.image_service import generate_image


def create_thumbnail(
    title: str,
    topic: str,
    project_path: str,
    channel: str = "wellbeing",
    scene1_narration: str = "",
    scene1_image_prompt: str = "",
    character_reference: str = "",
):
    """
    Sprint75 - 썸네일도 구조화된 프롬프트로 그린다.

    앵커를 대본 최상위 character로 옮기면서 썸네일이 인물을 잃었다.
    예전에는 이 프롬프트가 scene 1의 image_prompt를 통째로 품었고 거기에
    외형 묘사가 문장으로 들어 있었다. 이제 scene 1의 subject는
    "the same man"처럼 짧고 외형은 다른 곳에 있는데, 여기서 그 필드를
    읽지 않았다.

    실측 - 영상 속 인물 일관성은 95인데 썸네일만
    consistency_with_scene1 = 0이었다. "썸네일 속 인물이 영상의
    주인공과 완전히 다른 사람입니다."

    부정어("No text", "No watermark")도 긍정 프롬프트에서 뺐다. 같은
    내용이 THUMBNAIL_NEGATIVE_PROMPT로 이미 간다.
    """

    subject = f"""YouTube Shorts thumbnail based on this exact scene:

{scene1_image_prompt}

The thumbnail must depict the same subject, setting, and mood as
the scene described above. Do not introduce a different subject,
location, or background.

Context, for emotional tone only (do not add new visual elements
from this beyond expression or mood):
{scene1_narration}"""

    elements = {
        slots.SUBJECT: subject,
        slots.COMPOSITION: (
            "tight close-up, strong focus on the subject, "
            "high emotion, slightly exaggerated facial expression "
            "for click-through"
        ),
    }

    if character_reference and character_reference.strip():
        elements[slots.REFERENCE] = character_reference.strip()

    output = os.path.join(
        project_path,
        "thumbnail.png",
    )

    generate_image(
        subject,
        output,
        channel,
        image_style=image_service.IMAGE_STYLE_THUMBNAIL,
        elements=elements,
    )

    return output
