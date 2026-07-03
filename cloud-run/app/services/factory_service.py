import json
import os

from app.services.project_service import create_project
from app.services.script_service import generate_script
from app.services.image_service import generate_image
from app.services.video_builder import build_video
from app.services.tts_service import create_tts
from app.services.final_video_service import merge_video_audio
from app.services.subtitle_service import create_subtitle
from app.services.audio_service import mix_audio


def generate_short_video(topic: str):

    # 프로젝트 생성
    project = create_project()
    project_path = str(project["path"])

    print(f"Project : {project_path}")

    # 대본 생성
    result = generate_script(
        topic=topic,
        target_duration=45,
        scene_count=6,
    )

    data = result["data"]

    # script.json 저장
    with open(
        os.path.join(project_path, "script.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4,
        )

    # 이미지 생성
    for i, scene in enumerate(data["scenes"], start=1):

        output_file = os.path.join(
            project_path,
            "images",
            f"scene{i}.png",
        )

        generate_image(
            scene["image_prompt"],
            output_file,
        )

    # 음성 생성
    script = " ".join(
        scene["narration"]
        for scene in data["scenes"]
    )

    create_tts(
        script,
        project_path,
    )

    mix_audio(project_path)

    # 자막 생성
    create_subtitle(project_path)

    # 영상 생성
    build_video(project_path)

    # 최종 영상 생성
    merge_video_audio(project_path)

    return {
        "success": True,
        "project_id": project["id"],
        "title": data["title"],
        "output": project_path,
    }