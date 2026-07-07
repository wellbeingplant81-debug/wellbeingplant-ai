"""
Music Review Tool (Operation Mode).

BGM 파일을 assets/music/inbox/에서 하나씩 재생해가며, 사용자가 키
하나로 카테고리를 고르면 해당 폴더로 옮기고
assets/music/metadata/music_library.json을 갱신하는 터미널 도구입니다.

Pure Python, Windows 호환, 외부 API/LLM/파이프라인 변경 없음 -
독립적으로 실행하는 운영 도구입니다 (app/tools/music_review.py를
직접 실행: `python -m app.tools.music_review`).
"""

import json
import os
import shutil
from datetime import datetime, timezone

from app.utils.atomic_write import atomic_write_json

CATEGORY_MAP = {
    "1": "bright",
    "2": "calm",
    "3": "dramatic",
    "4": "energetic",
    "5": "emotional",
    "6": "food",
    "7": "healing",
    "8": "mystery",
    "9": "nature",
    "10": "technology",
    "11": "tension",
    "12": "uplifting",
    "0": "rejected",
}

ACTION_SKIP = "SKIP"
ACTION_QUIT = "QUIT"

MUSIC_EXTENSION = ".mp3"

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_CLOUD_RUN_DIR = os.path.dirname(os.path.dirname(_TOOLS_DIR))
DEFAULT_MUSIC_ROOT = os.path.join(_CLOUD_RUN_DIR, "assets", "music")


def resolve_key(key: str):
    """
    사용자 입력 키 하나를 행동으로 해석합니다. 순수 함수입니다.

    반환값: 카테고리 이름(str) | ACTION_SKIP | ACTION_QUIT | None(잘못된 키)
    """

    if key is None:
        return None

    normalized = key.strip()

    if not normalized:
        return None

    upper = normalized.upper()

    if upper == "Q":
        return ACTION_QUIT

    if upper == "S":
        return ACTION_SKIP

    return CATEGORY_MAP.get(normalized)


def scan_inbox(inbox_dir: str) -> list:
    """inbox_dir 안의 .mp3 파일 이름을 정렬된 리스트로 반환합니다."""

    if not os.path.isdir(inbox_dir):
        return []

    return sorted(
        entry
        for entry in os.listdir(inbox_dir)
        if os.path.isfile(os.path.join(inbox_dir, entry))
        and entry.lower().endswith(MUSIC_EXTENSION)
    )


def _unique_destination_path(dest_dir: str, filename: str) -> str:
    """
    dest_dir에 filename이 이미 있으면 "_1", "_2"...를 붙여 겹치지 않는
    경로를 찾습니다 - 기존 분류된 동명 파일을 덮어쓰지 않기 위함입니다.
    """

    candidate = os.path.join(dest_dir, filename)

    if not os.path.exists(candidate):
        return candidate

    name, ext = os.path.splitext(filename)
    counter = 1

    while True:
        candidate = os.path.join(dest_dir, f"{name}_{counter}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def move_file(src_path: str, dest_dir: str) -> str:
    """src_path를 dest_dir로 옮기고 최종 경로를 반환합니다."""

    os.makedirs(dest_dir, exist_ok=True)
    dest_path = _unique_destination_path(dest_dir, os.path.basename(src_path))
    shutil.move(src_path, dest_path)
    return dest_path


def load_library(metadata_path: str) -> dict:
    """music_library.json을 읽습니다. 없으면 빈 라이브러리를 반환합니다."""

    if not os.path.exists(metadata_path):
        return {"version": 1, "tracks": []}

    with open(metadata_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _upsert_track(tracks: list, entry: dict) -> list:
    """
    같은 "file" 이름의 기존 기록이 있으면 교체하고, 없으면 추가합니다 -
    같은 파일을 다시 분류해도 music_library.json에 중복 항목이
    쌓이지 않게 합니다.
    """

    updated = False
    result = []

    for track in tracks:
        if track.get("file") == entry["file"]:
            result.append(entry)
            updated = True
        else:
            result.append(track)

    if not updated:
        result.append(entry)

    return result


def record_classification(
    metadata_path: str,
    file_name: str,
    category: str,
    classified_at: str = None,
) -> dict:
    """
    entry를 만들어 music_library.json에 upsert하고, 그 entry를
    반환합니다 (atomic_write_json으로 저장 - Sprint41/42 파일 쓰기
    안정화 유틸을 그대로 재사용합니다).
    """

    library = load_library(metadata_path)

    entry = {
        "file": file_name,
        "category": category,
        "classified_at": classified_at or datetime.now(timezone.utc).isoformat(),
        "reviewed": True,
    }

    library["tracks"] = _upsert_track(library.get("tracks", []), entry)
    atomic_write_json(metadata_path, library)

    return entry


def classify_one(inbox_dir: str, file_name: str, category: str, music_root: str) -> dict:
    """
    파일 하나를 category 폴더로 옮기고 metadata를 갱신합니다.

    반환값: {"dest_path": str, "entry": dict}
    """

    src_path = os.path.join(inbox_dir, file_name)
    dest_dir = os.path.join(music_root, category)

    dest_path = move_file(src_path, dest_dir)

    metadata_path = os.path.join(music_root, "metadata", "music_library.json")
    entry = record_classification(metadata_path, file_name, category)

    return {"dest_path": dest_path, "entry": entry}


def play_music(path: str) -> None:
    """Windows 기본 연결 프로그램으로 재생을 시도합니다(실패해도 무시)."""

    try:
        os.startfile(path)  # noqa: S606 - Windows 전용 도구
    except Exception as exc:
        print(f"Could not play {path}: {exc}")


def _print_menu() -> None:
    print("1 Bright    2 Calm       3 Dramatic    4 Energetic")
    print("5 Emotional 6 Food       7 Healing     8 Mystery")
    print("9 Nature    10 Technology 11 Tension   12 Uplifting")
    print("0 Rejected  S Skip  Q Quit")


def run_review_session(
    music_root: str = None,
    input_fn=input,
    play_fn=None,
) -> None:
    """
    inbox의 mp3 파일을 하나씩 순회하며 재생 -> 키 입력 -> 이동/스킵/
    종료를 반복하는 대화형 세션입니다. input_fn/play_fn을 주입 가능하게
    해 테스트에서 실제 입력/재생 없이 로직만 검증할 수 있습니다.
    """

    music_root = music_root or DEFAULT_MUSIC_ROOT
    inbox_dir = os.path.join(music_root, "inbox")
    play_fn = play_fn or play_music

    files = scan_inbox(inbox_dir)
    total = len(files)

    for index, file_name in enumerate(files, start=1):

        remaining = total - index

        print(f"\nFile: {file_name}")
        print(f"Index: {index}/{total}  Remaining: {remaining}")
        _print_menu()

        play_fn(os.path.join(inbox_dir, file_name))

        action = None
        while action is None:
            key = input_fn("Select category (1-12, 0=Rejected, S=Skip, Q=Quit): ")
            action = resolve_key(key)
            if action is None:
                print("Invalid key. Try again.")

        if action == ACTION_QUIT:
            print("Quitting review session.")
            return

        if action == ACTION_SKIP:
            print(f"Skipped {file_name}")
            continue

        result = classify_one(inbox_dir, file_name, action, music_root)
        print(f"Moved {file_name} -> {action}/ ({result['dest_path']})")


if __name__ == "__main__":
    run_review_session()
