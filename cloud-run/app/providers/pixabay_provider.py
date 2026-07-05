import os

import requests

IMAGE_SEARCH_URL = "https://pixabay.com/api/"
VIDEO_SEARCH_URL = "https://pixabay.com/api/videos/"

MIN_PER_PAGE = 3
REQUEST_TIMEOUT_SECONDS = 10


def _api_key() -> str:

    api_key = os.getenv("PIXABAY_API_KEY")

    if not api_key:
        raise Exception("PIXABAY_API_KEY 환경변수가 설정되어 있지 않습니다.")

    return api_key


def search_images(
    query: str,
    orientation: str = "vertical",
    per_page: int = 5,
) -> list:

    response = requests.get(
        IMAGE_SEARCH_URL,
        params={
            "key": _api_key(),
            "q": query,
            "image_type": "photo",
            "orientation": orientation,
            "per_page": max(per_page, MIN_PER_PAGE),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise Exception(
            f"Pixabay Image 검색 실패 ({response.status_code}): {response.text}"
        )

    hits = response.json().get("hits", [])

    return [
        {
            "source": "pixabay_image",
            "source_url": hit.get("pageURL"),
            "download_url": hit.get("largeImageURL"),
            "width": hit.get("imageWidth"),
            "height": hit.get("imageHeight"),
            "query": query,
        }
        for hit in hits
    ]


def search_videos(
    query: str,
    per_page: int = 5,
) -> list:

    response = requests.get(
        VIDEO_SEARCH_URL,
        params={
            "key": _api_key(),
            "q": query,
            "per_page": max(per_page, MIN_PER_PAGE),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise Exception(
            f"Pixabay Video 검색 실패 ({response.status_code}): {response.text}"
        )

    hits = response.json().get("hits", [])

    results = []

    for hit in hits:

        videos = hit.get("videos", {})

        if not videos:
            continue

        best_variant = max(
            videos.values(),
            key=lambda v: (v.get("width") or 0) * (v.get("height") or 0),
        )

        results.append({
            "source": "pixabay_video",
            "source_url": hit.get("pageURL"),
            "download_url": best_variant.get("url"),
            "width": best_variant.get("width"),
            "height": best_variant.get("height"),
            "query": query,
        })

    return results
