import os

import requests

from app.providers import pexels_provider
from app.providers import pixabay_provider
from app.services.image_service import generate_image
from app.services.search_query_extractor import extract_search_query
from app.utils import asset_cache

PROVIDER_CHAIN = [
    ("pexels_video", lambda query: pexels_provider.search_videos(query)),
    ("pexels_image", lambda query: pexels_provider.search_photos(query)),
    ("pixabay_video", lambda query: pixabay_provider.search_videos(query)),
    ("pixabay_image", lambda query: pixabay_provider.search_images(query)),
]


DOWNLOAD_TIMEOUT_SECONDS = 30


def _download(url: str) -> bytes:

    response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)

    if response.status_code != 200:
        raise Exception(f"에셋 다운로드 실패 ({response.status_code}): {url}")

    return response.content


def _filename_for(source: str, download_url: str) -> str:

    if "video" in source:
        return "asset.mp4"

    ext = os.path.splitext(download_url)[1].lstrip(".") or "jpg"

    return f"asset.{ext}"


def select_asset(
    image_prompt: str,
    output_file: str,
    channel: str = "wellbeing",
    is_thumbnail: bool = False,
    is_hook_scene: bool = False,
) -> dict:
    """
    우선순위(Pexels Video -> Pexels Image -> Pixabay Video ->
    Pixabay Image -> AI Image)에 따라 scene에 사용할 에셋을 선택합니다.

    스톡 에셋을 찾으면 캐시를 거쳐 output_file에 저장하고, 어떤
    provider에서도 결과를 찾지 못하거나 검색 자체가 실패하면 기존
    image_service.generate_image()로 폴백합니다 - 기존 AI Image
    Generator는 삭제되지 않고 그대로 유지되며 최후의 fallback으로만
    사용됩니다.

    이 함수는 파이프라인 어디에서도 아직 호출되지 않는 독립 모듈입니다.

    반환값: {"source": str, "local_path": str, "metadata": dict}
    """

    query = extract_search_query(image_prompt)

    for source, search_fn in PROVIDER_CHAIN:

        try:
            results = search_fn(query) if query else []
        except Exception as exc:
            print(
                f"[AssetSelector] {source} 검색 실패, "
                f"다음 provider로 넘어갑니다: {exc}"
            )
            continue

        if not results:
            continue

        chosen = results[0]

        if not chosen.get("download_url"):
            print(
                f"[AssetSelector] {source} 결과에 download_url이 없어 "
                f"건너뜁니다."
            )
            continue

        asset_type = "video" if "video" in source else "image"

        try:
            key = asset_cache.cache_key(source, asset_type, query)

            cached = asset_cache.get_cached(key)

            if cached:
                cached_path, meta = cached
            else:
                content = _download(chosen["download_url"])
                filename = _filename_for(source, chosen["download_url"])

                meta = {
                    "source": source,
                    "query": query,
                    "source_url": chosen.get("source_url"),
                    "download_url": chosen.get("download_url"),
                    "width": chosen.get("width"),
                    "height": chosen.get("height"),
                }

                cached_path = asset_cache.save_to_cache(
                    key, content, filename, meta,
                )

            os.makedirs(os.path.dirname(output_file), exist_ok=True)

            with open(cached_path, "rb") as src, open(output_file, "wb") as dst:
                dst.write(src.read())

        except Exception as exc:
            print(
                f"[AssetSelector] {source} 다운로드/캐시 처리 실패, "
                f"다음 provider로 넘어갑니다: {exc}"
            )
            continue

        return {
            "source": source,
            "local_path": output_file,
            "metadata": meta,
        }

    ai_path = generate_image(
        image_prompt,
        output_file,
        channel=channel,
        is_thumbnail=is_thumbnail,
        is_hook_scene=is_hook_scene,
    )

    return {
        "source": "ai_image",
        "local_path": ai_path,
        "metadata": {"query": query},
    }
