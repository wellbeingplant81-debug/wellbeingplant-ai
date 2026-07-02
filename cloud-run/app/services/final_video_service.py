import os

from moviepy import VideoFileClip, AudioFileClip


def merge_video_audio(project_path: str):

    video_path = os.path.join(
        project_path,
        "video",
        "short.mp4"
    )

    audio_path = os.path.join(
        project_path,
        "audio",
        "voice.mp3"
    )

    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)

    if audio.duration > video.duration:
        audio = audio.subclipped(0, video.duration)

    final = video.with_audio(audio)

    output_path = os.path.join(
        project_path,
        "video",
        "final_short.mp4"
    )

    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=30,
    )

    video.close()
    audio.close()
    final.close()

    return output_path