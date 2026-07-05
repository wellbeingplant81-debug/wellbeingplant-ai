from app.steps import step01_script
from app.steps import step02_image
from app.steps import step03_tts
from app.steps import step04_subtitle
from app.steps import step05_video
from app.steps import step06_thumbnail


def run_pipeline(
    topic: str,
    project_path: str,
    channel: str,
):

    data = step01_script.run(
        topic,
        project_path,
    )

    step02_image.run(
        data["scenes"],
        project_path,
        channel,
    )

    step03_tts.run(
        data["scenes"],
        project_path,
    )

    step04_subtitle.run(
        project_path,
    )

    step05_video.run(
        project_path,
    )

    scene1 = data["scenes"][0]

    step06_thumbnail.run(
        data["title"],
        topic,
        project_path,
        channel,
        scene1["narration"],
        scene1["image_prompt"],
    )

    return data
