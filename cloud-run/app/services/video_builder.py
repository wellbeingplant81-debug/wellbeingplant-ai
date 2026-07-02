from moviepy import ImageClip, concatenate_videoclips
import os


def build_video():

    image_folder = "output/images"

    image_files = [
        "scene1.png",
        "scene2.png",
        "scene3.png",
        "scene4.png",
    ]

    clips = []

    for filename in image_files:

        path = os.path.join(image_folder, filename)

        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} 파일이 없습니다.")

        clip = ImageClip(path).with_duration(3)

        clips.append(clip)

    final_clip = concatenate_videoclips(clips, method="compose")

    os.makedirs("output/video", exist_ok=True)

    output_path = "output/video/short.mp4"

    final_clip.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio=False
    )

    final_clip.close()

    return {
        "success": True,
        "video": output_path
    }