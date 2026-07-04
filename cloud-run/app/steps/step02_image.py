import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.image_service import generate_image


MAX_WORKERS = 3


def _generate(
    scene,
    index,
    project_path,
    channel,
):

    output_file = os.path.join(
        project_path,
        "images",
        f"scene{index}.png",
    )

    generate_image(
        prompt=scene["image_prompt"],
        output_file=output_file,
        channel=channel,
    )

    return output_file


def run(
    scenes,
    project_path,
    channel,
):

    futures = []

    results = []

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS,
    ) as executor:

        for index, scene in enumerate(
            scenes,
            start=1,
        ):

            futures.append(

                executor.submit(
                    _generate,
                    scene,
                    index,
                    project_path,
                    channel,
                )

            )

        for future in as_completed(
            futures,
        ):

            results.append(
                future.result()
            )

    return sorted(results)