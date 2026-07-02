import os
from moviepy import ImageClip, concatenate_videoclips


def build_video(project_path: str):

    image_folder = os.path.join(project_path, "images")

    images = [
        os.path.join(image_folder, "scene1.png"),
        os.path.join(image_folder, "scene2.png"),
        os.path.join(image_folder, "scene3.png"),
        os.path.join(image_folder, "scene4.png"),
    ]

    clips = []

    for image in images:

        clip = (
            ImageClip(image)
            .with_duration(3)
        )

        clips.append(clip)

    final = concatenate_videoclips(clips)

    video_folder = os.path.join(project_path, "video")
    os.makedirs(video_folder, exist_ok=True)

    output_path = os.path.join(video_folder, "short.mp4")

    final.write_videofile(
        output_path,
        fps=30
    )

    final.close()

    return output_path