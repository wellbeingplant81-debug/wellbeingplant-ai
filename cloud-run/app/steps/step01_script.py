import json
import os

from app.services.script_service import generate_script


def run(
    topic: str,
    project_path: str,
):

    result = generate_script(
        topic=topic,
        target_duration=45,
        scene_count=6,
    )

    data = result["data"]

    print("\n" + "=" * 80)
    print("STEP01 RESULT")
    print("=" * 80)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print("=" * 80)

    with open(
        os.path.join(
            project_path,
            "script.json",
        ),
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4,
        )

    return data