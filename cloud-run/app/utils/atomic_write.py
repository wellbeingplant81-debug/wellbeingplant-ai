import json
import os
import tempfile


def atomic_write_json(path: str, data: dict):

    directory = os.path.dirname(path)

    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=directory,
        prefix=".tmp_",
        suffix=".json",
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        os.replace(tmp_path, path)

    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
