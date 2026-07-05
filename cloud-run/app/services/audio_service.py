import os
import subprocess


def concat_scene_audio(scene_audio_paths, output_file):

    ffmpeg = "ffmpeg"

    list_file = os.path.join(
        os.path.dirname(output_file),
        "scene_audio_list.txt",
    )

    with open(
        list_file,
        "w",
        encoding="utf-8",
    ) as f:

        for path in scene_audio_paths:
            escaped = os.path.abspath(path).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    command = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        list_file,
        "-c:a",
        "libmp3lame",
        output_file,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    print(result.stderr)

    os.remove(list_file)

    if result.returncode != 0:
        raise Exception(result.stderr)

    return output_file


def mix_audio(project_path: str):

    ffmpeg = "ffmpeg"
    
    voice = os.path.join(
        project_path,
        "audio",
        "voice.mp3",
    )

    project_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
        )
    )

    bgm = os.path.join(
        project_root,
        "assets",
        "bgm",
        "relax.mp3",
    )

    output = os.path.join(
        project_path,
        "audio",
        "final_audio.mp3",
    )

    command = [
        ffmpeg,
        "-y",
        "-i",
        voice,
        "-stream_loop",
        "-1",
        "-i",
        bgm,
        "-filter_complex",
        (
            "[1:a]"
            "volume=0.05,"
            "afade=t=in:st=0:d=2,"
            "afade=t=out:st=43:d=2"
            "[bgm];"
            "[0:a][bgm]"
            "amix=inputs=2:duration=first:dropout_transition=2"
        ),
        "-c:a",
        "mp3",
        output,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    print(result.stderr)

    if result.returncode != 0:
        raise Exception(result.stderr)

    return output