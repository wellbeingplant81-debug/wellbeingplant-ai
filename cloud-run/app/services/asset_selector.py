import os
import subprocess

import requests

from app.providers import pexels_provider
from app.providers import pixabay_provider
from app.services.image_service import generate_image
from app.services.provider_factory import build_provider_chain
from app.services.search_query_extractor import extract_search_query
from app.services import video_relevance_service
from app.utils import asset_cache


# Sprint100-4 - Visual Intelligence Completion. 후보 하나가 통과로
# 인정되는 최소 관련성 점수(0.0~1.0). Sprint100-3.1에서 Stock Video
# 전용으로 쓰던 값과 동일하다 - AI Image/Stock Image까지 동일 기준을
# 적용하는 것이 이번 스프린트의 목표이므로 하나의 값만 쓴다.
RELEVANCE_THRESHOLD = 0.6

# 대표 프레임 추출 지점(영상 길이 대비 비율). 0(첫 프레임)은 인트로/
# 전환 컷을 대표 프레임으로 잘못 고르기 쉽다(Sprint100-3.1 실측).
RELEVANCE_FRAME_FRACTION = 0.3

# 후보를 무제한 평가하면 다운로드/AI 생성/Gemini Vision 호출 비용이
# scene당 무한히 늘어날 수 있어, 넘겨받은 후보 리스트 중 앞에서부터
# 이 개수까지만 평가한다.
MAX_RELEVANCE_CANDIDATES = 3


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
    search_query_override: str = None,
) -> list:
    """
    Sprint30 - Multi-Candidate 수집.

    Sprint100-4 - search_query_override를 주면(기본 None) 내부에서
    extract_search_query(image_prompt)를 다시 계산하지 않고 그 값을
    그대로 검색어로 쓴다. 호출자(asset_integration_service.py)가
    Scene Intent 기반으로 더 정교하게 뽑은 검색어(search_query_
    extractor.extract_intent_aware_search_query())를 쓰고 싶을 때
    사용한다. 넘기지 않으면(기본값 None) 기존과 100% 동일하다.

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

    # Sprint100-4 버그 수정 - search_query_override 파라미터가 추가만
    # 되고 실제로는 읽히지 않아(dead parameter), Scene Intent 기반
    # 검색어(extract_intent_aware_search_query())가 한 번도 실제
    # Pexels/Pixabay 호출에 반영되지 않았다(2026-07-14 Production QA
    # 실측: search_query_used와 실제 후보의 검색어가 서로 달랐음).
    # override가 있으면 그대로 쓰고, 없으면(기본값 None) 기존과 100%
    # 동일하게 image_prompt에서 다시 계산한다.
    query = search_query_override or extract_search_query(image_prompt)

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


# ---------------------------------------------------------------------
# Sprint100-4 - Visual Intelligence Completion.
#
# 이 아래는 순수 "Selection Engine" 책임만 담당한다: 주어진 후보
# 리스트(Stock Video/Stock Image/이미 생성된 AI Image가 섞여 있을 수
# 있음)를 동일한 기준(Gemini Visual Relevance)으로 채점해 최선의
# 하나를 고른다. 어떤 Asset Type을 후보로 넣을지(Motion Contract가
# Video를 허용하는지 등)는 호출자(asset_integration_service.py)의
# 책임이고, 렌더링(Video Builder)도 이 파일이 전혀 알지 못한다.
# ---------------------------------------------------------------------


def _get_video_duration_seconds(video_path: str) -> float:
    """ffprobe로 비디오 길이(초)를 구합니다."""

    command = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    return float(result.stdout.strip())


def _extract_frame_at_fraction(
    video_path: str, output_image_path: str, fraction: float = RELEVANCE_FRAME_FRACTION,
) -> str:
    """비디오의 fraction 지점 프레임을 추출합니다(관련성 채점용)."""

    timestamp = max(0.0, _get_video_duration_seconds(video_path) * fraction)

    command = [
        "ffmpeg", "-y",
        "-ss", f"{timestamp:.2f}",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_image_path,
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"대표 프레임 추출 실패: {result.stderr}")

    return output_image_path


def _remove_if_exists(path: str) -> None:
    if path and os.path.exists(path):
        os.remove(path)


def _candidate_type(candidate: dict) -> str:

    if candidate.get("local_path"):
        return "ai_image"

    return "video" if "video" in candidate["source"] else "image"


def _prepare_candidate_frame(candidate: dict, raw_path: str, frame_path: str) -> tuple:
    """
    candidate 하나를 채점 가능한 정지 이미지 경로로 바꿉니다.

    candidate에 이미 "local_path"가 있으면(이미 생성/확보된 자산 -
    예: AI Image, 호출자가 generate_image()로 미리 만들어 넘긴 경우)
    그 파일을 그대로 쓰고 다운로드하지 않습니다. 없으면 download_
    candidate()로 받아옵니다 - 비디오면 대표 프레임을 추출하고,
    이미지면 다운로드 결과 자체를 그대로 씁니다.

    반환값: (scorable_image_path, raw_video_path_or_None). raw_video_
    path는 candidate_type=="video"이고 승자로 뽑혔을 때만 최종
    보존됩니다(선택 후 select_with_relevance()가 처리).
    """

    if candidate.get("local_path"):
        return candidate["local_path"], None

    is_video = "video" in candidate["source"]
    download_target = raw_path if is_video else frame_path

    downloaded = download_candidate(candidate, download_target)

    if is_video:
        _extract_frame_at_fraction(
            downloaded["local_path"], frame_path, fraction=RELEVANCE_FRAME_FRACTION,
        )
        return frame_path, downloaded["local_path"]

    return frame_path, None


def select_with_relevance(
    candidates: list,
    narration: str,
    image_prompt: str,
    staging_path_prefix: str,
    max_candidates: int = MAX_RELEVANCE_CANDIDATES,
) -> tuple:
    """
    Sprint100-4 - Visual Intelligence Completion.

    candidates(호출자가 원하는 평가 순서대로 이미 정렬해 넘긴 리스트 -
    Stock Video/Stock Image/이미 생성된 AI Image 어떤 조합이든 무관)를
    앞에서부터 max_candidates개까지 전부 평가한 뒤(중간에 통과하는
    후보가 나와도 멈추지 않는다 - "후보를 끝까지 평가한 뒤에만 최종
    선택/폴백") 그중 최고점 하나를 고릅니다. AI Image/Stock Image/
    Stock Video 모두 video_relevance_service.score_relevance()라는
    동일한 채점 기준을 거칩니다.

    반환값: (result, trace, all_failed)
      - result: 후보가 하나도 없으면 None. 있으면 {"source",
        "local_path"(대표 이미지, already_frame=True로 재추출 없이
        그대로 옮길 수 있음), "metadata", "already_frame": True,
        "video_path"(승자가 video였을 때만)}.
      - trace: 후보별 {"candidate", "type", "score", "reasoning",
        "passed", "selected"} 또는 실패시 {"candidate", "type",
        "error"} 리스트.
      - all_failed: 평가된 후보 중 RELEVANCE_THRESHOLD를 넘긴 것이
        하나도 없으면 True(그래도 result는 최고점 후보를 담아 반환 -
        파이프라인은 항상 asset 하나를 반환해야 하므로 렌더링을
        막지는 않는다. 호출자가 QA Upload Readiness에 반영한다).

    패자로 남은 후보의 다운로드/추출 파일은 즉시 정리합니다(단,
    candidate_type=="ai_image"는 애초에 다운로드한 적이 없으므로
    지우지 않습니다 - 그 파일은 호출자가 생성한 자산으로, 소유권이
    이 함수에 있지 않습니다).
    """

    trace = []
    scored = []

    for index, candidate in enumerate(candidates[:max_candidates]):

        candidate_type = _candidate_type(candidate)
        label = candidate.get("query") or candidate_type

        raw_path = f"{staging_path_prefix}.candidate{index}.raw"
        frame_path = f"{staging_path_prefix}.candidate{index}.png"

        try:
            resolved_frame_path, raw_video_path = _prepare_candidate_frame(
                candidate, raw_path, frame_path,
            )
            relevance = video_relevance_service.score_relevance(
                resolved_frame_path, narration, image_prompt,
            )
        except Exception as exc:
            trace.append({
                "candidate": label,
                "type": candidate_type,
                "threshold": RELEVANCE_THRESHOLD,
                "error": str(exc),
                "reason": f"평가 실패(다운로드/추출/채점 오류): {exc}",
            })
            _remove_if_exists(raw_path)
            _remove_if_exists(frame_path)
            continue

        passed = relevance.score >= RELEVANCE_THRESHOLD

        trace.append({
            "candidate": label,
            "type": candidate_type,
            "score": relevance.score,
            "threshold": RELEVANCE_THRESHOLD,
            "reasoning": relevance.reasoning,
            "passed": passed,
            "selected": False,
            "reason": (
                f"relevance {relevance.score:.2f} < threshold {RELEVANCE_THRESHOLD} - 탈락"
                if not passed
                else f"relevance {relevance.score:.2f} >= threshold {RELEVANCE_THRESHOLD} - 통과"
            ),
        })
        scored.append((
            relevance.score, candidate, candidate_type,
            resolved_frame_path, raw_video_path, len(trace) - 1,
        ))

    if not scored:
        return None, trace, True

    scored.sort(key=lambda item: item[0], reverse=True)

    (
        best_score, best_candidate, best_type,
        best_frame_path, best_raw_video_path, best_trace_index,
    ) = scored[0]

    for _, _, candidate_type, frame_path, raw_video_path, _ in scored[1:]:
        if candidate_type != "ai_image":
            _remove_if_exists(frame_path)
        _remove_if_exists(raw_video_path)

    trace[best_trace_index]["selected"] = True
    trace[best_trace_index]["reason"] = (
        f"최종 선택 - 평가된 후보 중 최고점(relevance {best_score:.2f})"
        + ("" if best_score >= RELEVANCE_THRESHOLD else f", threshold {RELEVANCE_THRESHOLD} 미달이지만 폴백으로 채택")
    )

    result = {
        "source": best_candidate.get("source", "ai_image"),
        "local_path": best_frame_path,
        "metadata": {"query": best_candidate.get("query")},
        "already_frame": True,
    }

    if best_type == "video" and best_raw_video_path:
        final_video_path = f"{staging_path_prefix}.video.mp4"
        os.replace(best_raw_video_path, final_video_path)
        result["video_path"] = final_video_path

    return result, trace, best_score < RELEVANCE_THRESHOLD
