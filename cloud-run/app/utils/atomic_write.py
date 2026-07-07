import json
import os
import tempfile
import time


def atomic_replace(src: str, dst: str, retries: int = 5, initial_delay: float = 0.05):
    """os.replace() wrapper that retries on Windows WinError 5 (PermissionError).

    On Windows, os.replace() can transiently fail with PermissionError
    (WinError 5) when another process (e.g. antivirus, a file watcher)
    briefly holds a handle on the destination file. Retries with
    exponential backoff before giving up.
    """

    delay = initial_delay

    for attempt in range(retries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(delay)
            delay *= 2


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

        atomic_replace(tmp_path, path)

    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
