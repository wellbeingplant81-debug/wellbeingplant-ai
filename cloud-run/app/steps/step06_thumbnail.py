from app.services.thumbnail_service import create_thumbnail


def run(
    title,
    topic,
    project_path,
):

    create_thumbnail(
        title,
        topic,
        project_path,
    )