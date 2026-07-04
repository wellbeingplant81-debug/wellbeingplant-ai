from app.services.video_builder import build_video
from app.services.final_video_service import merge_video_audio


def run(
    project_path,
):

    build_video(
        project_path,
    )

    merge_video_audio(
        project_path,
    )