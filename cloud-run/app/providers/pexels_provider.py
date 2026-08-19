import math
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

    # Sprint76 - alt는 Pexels가 붙여 둔 사진 설명이고, url에는 내용을
    # 적은 슬러그가 들어 있다. 후보 순위를 매길 유일한 의미 정보인데
    # 여기서 버리고 있었다. 추가 호출은 없다 - 이미 받은 응답이다.
    return [
        {
            "source": "pexels_image",
            "source_url": photo.get("url"),
            "download_url": photo.get("src", {}).get("original"),
            "width": photo.get("width"),
            "height": photo.get("height"),
            "alt": photo.get("alt") or "",
            "query": query,
        }
        for photo in photos
    ]


def search_videos(
    query: str,
    orientation: str = "portrait",
    per_page: int = 5,
    min_duration=None,
) -> list:
    """
    Sprint228 - 필요한 길이를 검색에 실어 보낸다.

    순위를 아무리 잘 매겨도 받아 온 다섯 개가 전부 scene 보다 짧으면
    결과는 hold(마지막 프레임 정지)다 - 고를 것이 없다. 그래서 짧은
    것을 아예 받지 않는다.

    실제로 되는 것을 확인하고 넣었다(손검증, 2026-08-19).

        조건 없이         [5, 8, 10, 10, 10, 12, 18, 19, 22, 24]
        min_duration=10   [10, 10, 10, 10, 12, 18, 19, 22, 24, 26]

    없으면 안 보낸다. 지어낸 질의 항목을 붙이지 않는다.
    """

    params = {
        "query": query,
        "orientation": orientation,
        "per_page": per_page,
    }

    if min_duration and min_duration > 0:
        # API 는 초 단위 정수를 받는다. 올려서 보낸다 - 내림하면
        # 필요한 길이보다 짧은 것이 다시 섞인다.
        params["min_duration"] = math.ceil(min_duration)

    response = requests.get(
        VIDEO_SEARCH_URL,
        headers={"Authorization": _api_key()},
        params=params,
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

        # 비디오 응답에는 alt가 없다. 슬러그가 유일한 단서이고,
        # duration은 Shorts scene에 쓸 만한 길이인지를 가른다.
        results.append({
            "source": "pexels_video",
            "source_url": video.get("url"),
            "download_url": best_file.get("link"),
            "width": best_file.get("width"),
            "height": best_file.get("height"),
            "alt": "",
            "duration": video.get("duration"),
            # Sprint233 - 미리보기 그림의 자리.
            #
            # 그림을 쓰려는 것이 아니라 그 **파일 이름**을 쓴다. 영상
            # 응답에는 alt 가 없어서(사진에는 있다) 관련도 판정에 넣을
            # 말이 슬러그 하나뿐이었는데, 이 주소의 파일 이름에 다른
            # 슬러그가 들어 있는 경우가 있다.
            #
            #   url   .../video/a-woman-stretching-5510121/
            #   image .../videos/5510121/coaching-crossfit-training-fast-
            #         workout-at-home-fitness-5510121.jpeg
            #
            # 실측(2026-08-19, 표본 75): 36%가 새 낱말을 얻고(평균 1.7개)
            # 나머지 64%는 pexels-photo 같은 껍데기라 아무것도 늘지
            # 않는다. 새 API 를 부르지 않는다 - 같은 응답의 한 칸이다.
            "preview_url": video.get("image"),
            "query": query,
        })

    return results
