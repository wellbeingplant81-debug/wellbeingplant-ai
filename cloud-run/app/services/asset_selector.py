import os

import requests

from app.providers import pexels_provider
from app.providers import pixabay_provider
from app.services.image_service import generate_image
from app.services.provider_factory import build_provider_chain
from app.services.search_query_extractor import extract_search_query
from app.utils import asset_cache


def _has_api_key(source: str) -> bool:
    """
    source 이름으로부터 해당 provider의 API Key 보유 여부만 확인합니다
    (실제 호출 없음) - get_candidates()의 로그 분류에만 사용됩니다.
    """

    if source.startswith("pexels"):
        return pexels_provider.has_api_key()

    if source.startswith("pixabay"):
        return pixabay_provider.has_api_key()

    return True

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
    allow_video: bool = True,
) -> dict:
    """
    우선순위(Pexels Video -> Pexels Image -> Pixabay Video ->
    Pixabay Image -> AI Image)에 따라 scene에 사용할 에셋을 선택합니다.
    allow_video=False로 호출하면 비디오 provider를 건너뛰고 이미지
    provider만 시도합니다 (기본값 True는 기존 동작과 동일).

    스톡 에셋을 찾으면 캐시를 거쳐 output_file에 저장하고, 어떤
    provider에서도 결과를 찾지 못하거나 검색 자체가 실패하면 기존
    image_service.generate_image()로 폴백합니다 - 기존 AI Image
    Generator는 삭제되지 않고 그대로 유지되며 최후의 fallback으로만
    사용됩니다.

    반환값: {"source": str, "local_path": str, "metadata": dict}
    """

    query = extract_search_query(image_prompt)

    provider_chain = build_provider_chain(allow_video=allow_video)

    for source, search_fn in provider_chain:

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


MAX_CANDIDATES_PER_PROVIDER = 3


def get_candidates(
    image_prompt: str,
    allow_video: bool = True,
    max_per_provider: int = MAX_CANDIDATES_PER_PROVIDER,
) -> list:
    """
    Sprint30 - Multi-Candidate 수집.

    select_asset()과 달리 첫 성공 provider에서 멈추지 않고, provider
    체인 전체를 순회하며 각 provider당 최대 max_per_provider개의
    후보를 모두 모아 하나의 리스트로 반환합니다. 검색이 실패하는
    provider는 건너뛰고 계속 진행합니다 (select_asset()과 동일한
    장애 허용 방식).

    download_url이 없는 결과는 후보에서 제외합니다. AI Image 폴백은
    이 함수의 책임이 아닙니다 - 호출자가 빈 리스트를 근거로 판단해야
    합니다 (asset_integration_service.py 참고).

    Sprint32 - 진단 로그: 각 provider마다 API Key 보유 여부를 미리
    확인해두었다가(search_fn 호출 여부 자체는 바꾸지 않음 - 항상
    호출합니다), 예외가 나면 "Key가 아예 없어서"인지 "Key는 있는데
    다른 이유로 실패"인지 구분해서 출력합니다. 마지막에는 전체
    provider가 전부 Key 미설정으로 실패했는지, 아니면 Key는 있었지만
    유효한 후보를 찾지 못했는지를 명확히 구분한 요약 로그를 남깁니다.
    """

    query = extract_search_query(image_prompt)

    if not query:
        print(
            "[ProviderLog] 검색 쿼리가 비어 있어 provider를 호출하지 "
            "않고 AI fallback으로 진행합니다."
        )
        return []

    candidates = []
    status_log = []

    for source, search_fn in build_provider_chain(allow_video=allow_video):

        key_present = _has_api_key(source)

        print(f"[ProviderLog] {source}: ATTEMPTING (API Key 보유={key_present})")

        try:
            results = search_fn(query)
        except Exception as exc:
            if not key_present:
                print(f"[ProviderLog] {source}: SKIPPED - API Key 없음 ({exc})")
                status_log.append((source, "no_key"))
            else:
                print(f"[ProviderLog] {source}: FAILED - {exc}")
                status_log.append((source, "error"))
            continue

        valid_results = [
            result
            for result in results[:max_per_provider]
            if result.get("download_url")
        ]

        if valid_results:
            print(f"[ProviderLog] {source}: SUCCESS - {len(valid_results)}건 발견")
            status_log.append((source, "success"))
        else:
            print(f"[ProviderLog] {source}: EMPTY - 호출은 성공했으나 결과 없음")
            status_log.append((source, "empty"))

        candidates.extend(valid_results)

    if not candidates:
        if status_log and all(status == "no_key" for _, status in status_log):
            print(
                "[ProviderLog] FINAL: 모든 stock provider에 API Key가 "
                "없어 AI fallback으로 진행합니다 (실제 검색은 시도되지 "
                "않은 것과 동일한 상황)."
            )
        else:
            print(
                "[ProviderLog] FINAL: API Key는 있었지만 유효한 후보를 "
                "찾지 못해 AI fallback으로 진행합니다."
            )
    else:
        print(
            f"[ProviderLog] FINAL: 후보 {len(candidates)}건 수집 완료 - "
            f"AI fallback 없이 스톡 자산을 사용합니다."
        )

    return candidates


def download_candidate(candidate: dict, output_file: str) -> dict:
    """
    Sprint30 - Ranking으로 선택된 후보 하나를 실제로 다운로드(또는
    캐시 재사용)하여 output_file에 저장합니다. select_asset()의
    다운로드/캐시 로직과 동일한 방식입니다.

    반환값: {"source": str, "local_path": str, "metadata": dict}
    """

    source = candidate["source"]
    query = candidate.get("query", "")
    asset_type = "video" if "video" in source else "image"

    key = asset_cache.cache_key(source, asset_type, query)

    cached = asset_cache.get_cached(key)

    if cached:
        cached_path, meta = cached
    else:
        content = _download(candidate["download_url"])
        filename = _filename_for(source, candidate["download_url"])

        meta = {
            "source": source,
            "query": query,
            "source_url": candidate.get("source_url"),
            "download_url": candidate.get("download_url"),
            "width": candidate.get("width"),
            "height": candidate.get("height"),
        }

        cached_path = asset_cache.save_to_cache(key, content, filename, meta)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(cached_path, "rb") as src, open(output_file, "wb") as dst:
        dst.write(src.read())

    return {
        "source": source,
        "local_path": output_file,
        "metadata": meta,
    }
