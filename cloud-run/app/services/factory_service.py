import json
import os

from app.services.project_service import create_project
from app.services.content_service import generate_short
from app.services.image_service import generate_image
from app.services.video_builder import build_video
from app.services.tts_service import create_tts
from app.services.final_video_service import merge_video_audio


def generate_short_video(topic: str):

    # 프로젝트 생성
    project = create_project()

    project_path = str(project["path"])

    print(f"Project : {project_path}")

    # 1. 대본 생성
    short = generate_short(topic)

    data = short["data"]

    # 2. script.json 저장
    with open(
        os.path.join(project_path, "script.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    # 3. 이미지 생성
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

    # 4. 영상 생성
    build_video(project_path)

    # 5. 음성 생성
    create_tts(
        data["script"],
        project_path,
    )

    # 6. 영상 + 음성 합치기
    merge_video_audio(project_path)

    return {
        "success": True,
        "project_id": project["id"],
        "title": data["title"],
        "output": project_path,
    }