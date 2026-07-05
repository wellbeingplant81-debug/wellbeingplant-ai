from app.services.thumbnail_service import create_thumbnail


def run(
    title,
    topic,
    project_path,
    channel,
    scene1_narration,
    scene1_image_prompt,
):

    create_thumbnail(
        title,
        topic,
        project_path,
        channel,
        scene1_narration,
        scene1_image_prompt,
    )