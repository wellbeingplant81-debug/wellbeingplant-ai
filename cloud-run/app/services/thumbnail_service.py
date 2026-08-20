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

    # Sprint243 - AI 를 쓰지 않기로 한 프로젝트는 이미 있는 그림을 쓴다.
    #
    # 이 자리가 실제로 제작을 멈춰 세웠다(실측). 자산 6장은 관문에 막혀
    # 스톡으로 갔고 영상까지 다 만들어졌는데, 썸네일 한 장이 유료
    # 모델로 곧장 가서 404 로 죽었다.
    #
    #     [424s] 영상 완료
    #     [440s] 썸네일 -> FAILED  imagen-4.0-generate-001
    #
    # 자산 쪽에는 스톡으로 내려가는 길이 있는데 여기에는 없었다. 그래서
    # 첫 장면 그림을 쓴다 - 그 영상의 그림이고, 돈이 들지 않고, 결과가
    # 늘 같다.
    from app.services import media_policy

    if not media_policy.ai_allowed(media_policy.mode_for(project_path)):
        return _copy_first_scene(project_path, output)

    generate_image(
        subject,
        output,
        channel,
        image_style=image_service.IMAGE_STYLE_THUMBNAIL,
        elements=elements,
    )

    return output


def _copy_first_scene(project_path: str, output: str):
    """
    첫 장면 그림을 썸네일 자리에 베낀다.

    옮기지 않고 베낀다 - 그 그림은 영상이 쓰는 것이라 사라지면 안 된다.

    첫 장면 그림도 없으면 썸네일 없이 둔다. 하류는 이미 그것을 견딘다 -
    publishing 은 없으면 None 을 돌려주고, 업로드는 있을 때만 붙인다.
    없는 것을 지어내는 것보다 없다고 두는 편이 낫다.
    """

    import shutil

    scene1 = os.path.join(project_path, "images", "scene1.png")

    if not os.path.isfile(scene1):
        print("[Thumbnail] 첫 장면 그림이 없어 썸네일을 만들지 않습니다.")

        return None

    shutil.copyfile(scene1, output)

    print(f"[Thumbnail] AI 를 쓰지 않는 방식이라 첫 장면 그림을 씁니다: "
          f"{output}")

    return output
