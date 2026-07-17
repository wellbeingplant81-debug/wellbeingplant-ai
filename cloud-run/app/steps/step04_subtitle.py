from app.services.subtitle_service import create_subtitle


def run(
    project_path,
    render_profile=None,
):

    return create_subtitle(
        project_path,
        render_profile=render_profile,
    )