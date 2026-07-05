import os

import requests

PHOTO_SEARCH_URL = "https://api.pexels.com/v1/search"
VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

REQUEST_TIMEOUT_SECONDS = 10


def has_api_key() -> bool:
    """PEXELS_API_KEY가 환경변수에 설정되어 있는지만 확인합니다 (호출 없음)."""

    return bool(os.getenv("PEXELS_API_KEY"))


def _api_key() -> str:

    api_key = os.getenv("PEXELS_API_KEY")

    if not api_key:
        raise Exception("PEXELS_API_KEY 환경변수가 설정되어 있지 않습니다.")

    return api_key


def search_photos(
    query: str,
    orientation: str = "portrait",
    per_page: int = 5,
) -> list:

    response = requests.get(
        PHOTO_SEARCH_URL,
        headers={"Authorization": _api_key()},
        params={
            "query": query,
            "orientation": orientation,
            "per_page": per_page,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise Exception(
            f"Pexels Photo 검색 실패 ({response.status_code}): {response.text}"
        )

    photos = response.json().get("photos", [])

    return [
        {
            "source": "pexels_image",
            "source_url": photo.get("url"),
            "download_url": photo.get("src", {}).get("original"),
            "width": photo.get("width"),
            "height": photo.get("height"),
            "query": query,
        }
        for photo in photos
    ]


def search_videos(
    query: str,
    orientation: str = "portrait",
    per_page: int = 5,
) -> list:

    response = requests.get(
        VIDEO_SEARCH_URL,
        headers={"Authorization": _api_key()},
        params={
            "query": query,
            "orientation": orientation,
            "per_page": per_page,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise Exception(
            f"Pexels Video 검색 실패 ({response.status_code}): {response.text}"
        )

    videos = response.json().get("videos", [])

    results = []

    for video in videos:

        video_files = video.get("video_files", [])

        if not video_files:
            continue

        best_file = max(
            video_files,
            key=lambda f: (f.get("width") or 0) * (f.get("height") or 0),
        )

        results.append({
            "source": "pexels_video",
            "source_url": video.get("url"),
            "download_url": best_file.get("link"),
            "width": best_file.get("width"),
            "height": best_file.get("height"),
            "query": query,
        })

    return results
