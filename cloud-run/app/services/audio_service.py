import os
import subprocess


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