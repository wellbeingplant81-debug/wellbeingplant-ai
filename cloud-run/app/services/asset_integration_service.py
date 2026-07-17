import os
import subprocess

from app import config
from app.services import asset_feedback_service
from app.services import motion_contract
from app.services.asset_mode_config import get_pexels_quality_threshold
from app.services.asset_priority_classifier import effective_pexels_threshold
from app.services.asset_ranking_service import select_best_with_score
from app.services.asset_selector import (
    download_candidate,
    get_candidates,
    select_with_relevance,
)
from app.services.image_service import generate_image
from app.services.search_query_extractor import (
    extract_search_query,
    generate_semantic_primary_query,
)
from app.services import subprompt_service
from app.services import video_relevance_service
from app.services import video_search_planner
from app.services.visual_diversity_engine import apply_profile_to_prompt
from app.services.visual_type_classifier import VISUAL_TYPE_AI, VISUAL_TYPE_REAL


# Sprint102 - Video Coverage Intelligence. _gather_stock_result()가
# video_search_planner.plan_video_search_queries()에서 최대 이
# 개수까지만 검색어를 시도한다 - 무제한으로 시도하면 scene당 다운로드/
# Gemini Vision 호출 비용이 무한히 늘어날 수 있다.
MAX_QUERY_ATTEMPTS = 3


# Sprint100-3.1 - Stock Video Visual Relevance. 후보를 무제한 다운로드/
# 채점하면 Pexels 다운로드+Gemini Vision 호출 비용이 scene당 무한히
# 늘어날 수 있어, 원래 랭킹(score_asset) 순서로 상위 N개까지만 채점한다.
MAX_RELEVANCE_CANDIDATES = 3

# 0.0~1.0 중 이 값 미만이면 "narration/image_prompt와 무관"으로 보고
# 후보에서 제외한다 - 통과하는 후보가 하나도 없으면 호출자가 AI/Stock
# Image로 자연스럽게 폴백한다.
RELEVANCE_THRESHOLD = 0.6

# 프레임 추출 지점(영상 길이 대비 비율). 0(첫 프레임)은 Pexels 영상의
# 인트로/전환 컷을 대표 프레임으로 잘못 고르기 쉬워(Production QA
# 2026-07-13 실측), 본문 구간일 가능성이 높은 30% 지점을 쓴다.
RELEVANCE_FRAME_FRACTION = 0.3


# Sprint62-4 - Visual Diversity 첫 단계: AI로 생성된 scene 하나당
# 만들 asset 총 개수(1차 asset 포함). 프롬프트 다양화는 다음
# 스프린트 범위이므로 지금은 상수로 고정한다.
AI_ASSET_COUNT = 4

# Sprint64-2 - Asset Role Metadata. AI_ASSET_COUNT와 동일 길이이며
# assets 리스트의 인덱스와 1:1 대응한다. source == "ai_image"인
# scene(1차+추가 asset 전부)에만 부여하고, 스톡/비디오프레임 단일
# asset에는 붙이지 않는다(하위 호환 - role 없는 asset도 그대로 유효).
ASSET_ROLES = ["environment", "subject", "detail", "transition"]

# Sprint71-2 - Hybrid Asset Composer. AI 4-asset scene에서 4장 모두
# 같은 생성기(Imagen)로 나오면 "사진이 한 장면에 몰려 나오는" 반복감이
# 생긴다(Sprint71-1 조사). environment/subject는 narration이 지시하는
# 핵심 개념이라 스톡으로 부정확할 위험이 크므로 AI를 유지하고, 상대적
# 으로 일반적인 브릿지 컷인 detail/transition만 스톡을 먼저 시도한다.
# role 값 자체는 asset 출처와 무관하게 그대로 유지되므로(Sprint71-1
# 설계 결정), asset_usage_planner/video_builder/qa_report_service의
# role 기반 로직은 전혀 수정하지 않아도 된다.
HYBRID_STOCK_ROLES = {"detail", "transition"}


def _ai_result(
    image_prompt, staging_path, channel, is_hook_scene, visual_type=None,
    visual_profile=None, aspect_ratio=None,
):
    # Sprint72-1 - Visual Diversity Engine: 실제 이미지 생성(Imagen)에
    # 넘기는 프롬프트에만 Profile 문구를 얹는다 - search_query 등
    # 메타데이터는 원본 image_prompt 기준으로 그대로 유지한다.
    enriched_prompt = apply_profile_to_prompt(image_prompt, visual_profile)

    # Sprint122 - Longform Foundation: render_profile의 image_aspect_
    # ratio가 있을 때만 kwarg를 보탠다(없으면 generate_image() 자체의
    # 기본값 "9:16"이 그대로 적용됨) - 기존 호출부/mock과 완전히 하위
    # 호환된다.
    generate_image_kwargs = {
        "channel": channel,
        "is_hook_scene": is_hook_scene,
        "visual_type": visual_type,
    }
    if aspect_ratio is not None:
        generate_image_kwargs["aspect_ratio"] = aspect_ratio

    ai_path = generate_image(
        enriched_prompt,
        staging_path,
        **generate_image_kwargs,
    )

    return {
        "source": "ai_image",
        "local_path": ai_path,
        "metadata": {"query": extract_search_query(image_prompt)},
    }


def _select_real_first(
    image_prompt, staging_path, channel, is_hook_scene, visual_type=None,
    visual_profile=None, asset_strategy=None, prefer_video=False, narration=None,
    aspect_ratio=None, image_orientation=None,
):
    """
    Sprint60 - visual_type == "real": Pexels(스톡) 우선, 실패 시 Imagen
    폴백. "실패"는 후보가 아예 없는 경우와, 후보는 있었지만 다운로드
    자체가 실패한 경우(네트워크 오류 등) 둘 다 포함한다.

    Sprint100-3 Stock Video Intelligence - asset_strategy/prefer_video를
    select_best_with_score()에 전달한다. 이전에는 integrate_asset()이
    asset_strategy를 받으면서도 이 호출에는 넘기지 않아, Sprint96.1
    Hotfix(video 근소 우대)가 upload profile 실사용 경로에서 한 번도
    적용되지 않았다 - 이 배선 누락을 함께 고친다.

    Sprint100-3.1 Stock Video Visual Relevance - asset_strategy="upload"
    and prefer_video=True면, video 후보에 한해 먼저 _select_relevant_
    video_candidate()로 실제 대표 프레임이 narration/image_prompt와
    맞는지 채점해 선택한다. 통과하는 후보가 없으면(전부 무관하거나
    video 후보 자체가 없으면) 기존 select_best_with_score() 랭킹으로
    폴백한다 - 이 경우 이미지가 자연스럽게 이길 수 있다. 어느 경로든
    trace는 result["video_relevance_trace"]에 담아 QA가 "왜 이
    asset이 선택됐는지" 확인할 수 있게 한다.

    video 후보가 있었는데 전부 관련성 기준을 통과하지 못했다면, 폴백
    랭킹에서 video 후보 자체를 아예 제외하고 prefer_video도 끈다 -
    그러지 않으면 SCENE_INTENT_VIDEO_BONUS가 다시 적용되어 방금
    "무관하다"고 판정한 video가 (다른 후보라도) 또 이겨버리는 문제가
    있었다(2026-07-13 Production QA에서 실측).
    """

    get_candidates_kwargs = {}
    if image_orientation is not None:
        get_candidates_kwargs["image_orientation"] = image_orientation

    stock_candidates = get_candidates(image_prompt, allow_video=True, **get_candidates_kwargs)

    video_relevance_trace = None

    if asset_strategy == "upload" and prefer_video:
        video_candidates = [c for c in stock_candidates if "video" in c["source"]]
        if video_candidates:
            relevant_result, video_relevance_trace = _select_relevant_video_candidate(
                video_candidates, narration or "", image_prompt, staging_path,
            )
            if relevant_result is not None:
                relevant_result["video_relevance_trace"] = video_relevance_trace
                return relevant_result, False

            # 전부 무관 판정 - video를 완전히 배제하고 image/AI로 넘긴다.
            stock_candidates = [
                c for c in stock_candidates if "video" not in c["source"]
            ]
            prefer_video = False

    best_candidate, _ = select_best_with_score(
        stock_candidates, is_hook_scene=is_hook_scene,
        asset_strategy=asset_strategy, prefer_video=prefer_video,
    )

    if best_candidate is not None:
        try:
            result = download_candidate(best_candidate, staging_path)
            if video_relevance_trace is not None:
                result["video_relevance_trace"] = video_relevance_trace
            return result, False
        except Exception as exc:
            print(
                f"[AssetIntegration] visual_type=real, Pexels 다운로드 "
                f"실패, Imagen으로 폴백: {exc}"
            )

    ai_result = _ai_result(
        image_prompt, staging_path, channel, is_hook_scene, visual_type,
        visual_profile, aspect_ratio=aspect_ratio,
    )
    if video_relevance_trace is not None:
        ai_result["video_relevance_trace"] = video_relevance_trace

    return ai_result, False


def _select_ai_first(
    image_prompt, staging_path, channel, is_hook_scene, visual_type=None,
    visual_profile=None, asset_strategy=None, prefer_video=False, aspect_ratio=None,
    image_orientation=None,
):
    """
    Sprint60 - visual_type == "ai": Imagen 우선, 실패 시 Pexels 폴백.

    반환값: (result_dict, ai_was_deliberate_choice). ai_was_deliberate_
    choice는 Imagen이 첫 시도에서 바로 성공했는지(True) - 스톡 검색
    실패로 인한 어쩔 수 없는 폴백(False)과 구분해 feedback outcome을
    정확히 기록하기 위함이다.

    Sprint100-3 Stock Video Intelligence - Pexels 폴백 시에도
    asset_strategy/prefer_video를 그대로 전달한다([[_select_real_first]]
    와 동일한 배선 누락 수정).
    """

    try:
        return (
            _ai_result(
                image_prompt, staging_path, channel, is_hook_scene, visual_type,
                visual_profile, aspect_ratio=aspect_ratio,
            ),
            True,
        )
    except Exception as exc:
        print(
            f"[AssetIntegration] visual_type=ai, Imagen 생성 실패, "
            f"Pexels로 폴백: {exc}"
        )

    get_candidates_kwargs = {}
    if image_orientation is not None:
        get_candidates_kwargs["image_orientation"] = image_orientation

    stock_candidates = get_candidates(image_prompt, allow_video=True, **get_candidates_kwargs)
    best_candidate, _ = select_best_with_score(
        stock_candidates, is_hook_scene=is_hook_scene,
        asset_strategy=asset_strategy, prefer_video=prefer_video,
    )

    if best_candidate is None:
        raise Exception(
            "visual_type=ai 폴백 실패: Imagen과 Pexels 모두 사용할 수 "
            "없습니다."
        )

    return download_candidate(best_candidate, staging_path), False


def _extract_first_frame(video_path: str, output_image_path: str) -> str:
    """
    비디오 파일의 첫 프레임을 이미지로 추출합니다. 기존
    audio_service.py/final_video_service.py와 동일하게 bare "ffmpeg"
    명령어(PATH 의존)와 subprocess.run 패턴을 사용합니다.
    """

    command = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_image_path,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise Exception(f"비디오 첫 프레임 추출 실패: {result.stderr}")

    return output_image_path


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
    video_path: str, output_image_path: str, fraction: float = 0.3,
) -> str:
    """
    Sprint100-3.1 - Stock Video Visual Relevance. 비디오의 fraction
    지점(기본 30%) 프레임을 추출합니다. _extract_first_frame()(항상
    0초)과 달리, Pexels 영상이 인트로/전환 컷으로 시작해 실제 주제를
    대표하지 못하는 문제(Production QA 2026-07-13 실측: "shocked
    korean woman" 검색 결과의 첫 프레임이 머리카락 클로즈업)를
    완화하기 위해 relevance 채점용으로만 쓰입니다.
    """

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


# ---------------------------------------------------------------------
# Sprint100-4 - Visual Intelligence Completion.
#
# Motion Contract가 붙은 scene(asset_strategy="upload" and config.
# ENABLE_MOTION_CONTRACT)에서만 쓰이는 새 통합 선택 경로. 이 함수들은
# "선택된 결과를 다운로드/통합/폴백"하는 asset_integration_service.py
# 본연의 책임 안에서, Motion Contract(허용 여부)/Search Query(생성
# 결과)/Asset Selector(채점·선택)가 이미 결정한 것을 그대로 실행할
# 뿐이다 - 이 파일은 motion 정책도 검색어 생성도 다시 판단하지 않는다.
# Motion Contract가 없는 scene(kill switch off/개발 profile)은 이
# 경로를 전혀 타지 않고 기존 _select_real_first()/_select_ai_first()
# 가 100% 그대로 쓰인다.
# ---------------------------------------------------------------------


def _build_ai_candidate(
    image_prompt, staging_path, channel, is_hook_scene, visual_type, visual_profile,
    aspect_ratio=None,
):
    """
    AI Image를 실제로 생성해, asset_selector.select_with_relevance()가
    Stock 후보와 동일하게 다룰 수 있는 candidate 형태로 감싼다.
    "local_path"가 이미 있으므로 그 함수가 다시 다운로드를 시도하지
    않는다.
    """

    ai_path = f"{staging_path}.ai.png"

    ai_result = _ai_result(
        image_prompt, ai_path, channel, is_hook_scene, visual_type, visual_profile,
        aspect_ratio=aspect_ratio,
    )

    return {
        "source": "ai_image",
        "local_path": ai_result["local_path"],
        "query": ai_result["metadata"].get("query"),
    }


def _discard(result):
    # 최종 채택되지 않은 쪽의 결과 파일을 정리한다 - select_with_
    # relevance()는 자기 안에서 진 후보만 정리하고, "이 함수 호출
    # 전체의 결과가 버려지는 경우"는 호출자 책임이다. 버그 실측:
    # 2026-07-14 Production QA에서 discard된 stock 결과 파일
    # (scene5.raw.candidate0.png 등)이 정리되지 않고 images/ 아래
    # 그대로 남아있었다.
    if result is None:
        return
    _remove_if_exists(result.get("local_path"))
    _remove_if_exists(result.get("video_path"))


def _gather_stock_result(
    image_prompt, allow_video, search_query_override, narration, staging_path,
    image_orientation=None,
):
    """
    Sprint102 - Video Coverage Intelligence.

    config.ENABLE_VIDEO_SEARCH_PLANNER가 켜져 있고 allow_video면,
    video_search_planner.plan_video_search_queries()가 만든 검색어를
    Primary(search_query_override - 이미 Sprint100-4의 Scene Intent
    기반 값, 첫 시도로 그대로 쓴다) 다음으로 최대 MAX_QUERY_ATTEMPTS
    개까지 순서대로 시도한다.

    "충분한 품질의 후보를 확보했는지"는 새 채점 로직을 만들지 않고
    select_with_relevance()가 이미 판정하는 "통과하는 후보가 있는가"
    (all_failed=False)를 그대로 기준으로 쓴다 - 통과하면 그 자리에서
    멈추고 그 select_with_relevance() 호출 자체를 "최종 선택"으로
    반환한다. 전부 실패하면 마지막 시도의 결과를 반환해 호출자가
    AI로 이어가게 한다. 시도했다가 버려진 후보 파일은 즉시 정리한다.

    플래그가 꺼져 있거나 allow_video가 아니면 기존과 100% 동일하게
    search_query_override 하나만 시도한다(하위 호환).

    반환값: (result, combined_trace, all_failed) - select_with_
    relevance()와 동일한 모양이라 호출부의 기존 처리 로직을 그대로
    재사용할 수 있다.
    """

    queries = [search_query_override]

    if config.ENABLE_VIDEO_SEARCH_PLANNER and allow_video:
        planned = video_search_planner.plan_video_search_queries(narration or "", image_prompt)
        # planned[0]은 plan_video_search_queries() 자체의 Primary다 -
        # search_query_override를 이미 1번 시도로 쓰므로 중복 시도를
        # 피하기 위해 건너뛴다.
        for query in planned[1:]:
            if query not in queries:
                queries.append(query)
        queries = queries[:MAX_QUERY_ATTEMPTS]

    combined_trace = []
    best_result, best_all_failed = None, True

    for attempt_index, query in enumerate(queries):

        # Sprint102 하드닝 - 시도마다 고유한 staging 경로를 쓴다. 모든
        # 시도가 같은 staging_path를 공유하면, select_with_relevance()
        # 내부의 candidate{index} 파일명이 시도마다 0부터 다시 시작해
        # 이전 시도의 아직 discard되지 않은 결과 파일을 다음 시도가
        # 덮어쓸 수 있다(최종 반환값 자체는 항상 마지막 시도 결과라
        # 결과가 틀리게 나오진 않지만, 중간 상태가 불필요하게 서로
        # 간섭하는 것은 피한다).
        attempt_staging_path = f"{staging_path}.q{attempt_index}"

        get_candidates_kwargs = {}
        if image_orientation is not None:
            get_candidates_kwargs["image_orientation"] = image_orientation

        candidates = get_candidates(
            image_prompt, allow_video=allow_video, search_query_override=query,
            **get_candidates_kwargs,
        )
        result, trace, all_failed = select_with_relevance(
            candidates, narration or "", image_prompt, attempt_staging_path,
        )

        for entry in trace:
            entry["search_query"] = query

        combined_trace.extend(trace)

        if best_result is not None:
            _discard(best_result)

        best_result, best_all_failed = result, all_failed

        if result is not None and not all_failed:
            break

    return best_result, combined_trace, best_all_failed


def _select_with_visual_relevance(
    image_prompt, staging_path, channel, is_hook_scene, visual_type,
    visual_profile, narration, prefer_ai, allow_video, search_query_override,
    video_intent=None, aspect_ratio=None, image_orientation=None,
):
    """
    AI Image/Stock Image/Stock Video 전부 asset_selector.
    select_with_relevance()라는 동일한 Visual Relevance 기준으로
    평가한다. prefer_ai면 AI를 먼저 평가해 통과하면 그대로 채택하고
    (기존 _select_ai_first()의 "AI 우선" 의미 유지), 실패하면 Stock을
    평가한다. prefer_ai가 아니면 Stock을 먼저 평가하고, 전부 실패
    했을 때만(select_with_relevance가 후보 전부를 이미 다 평가한
    뒤에만 반환하므로 "다음 후보 평가" 요구사항은 그 함수 내부에서
    보장된다) AI를 최후 수단으로 생성해 평가한다 - AI 생성은 비용이
    크므로 stock이 이미 통과했으면 호출하지 않는다.

    Sprint102 - "Stock을 평가"하는 부분은 이제 _gather_stock_result()
    를 거친다 - Video Search Planner가 켜져 있으면 검색어를 여러 개
    시도해 후보 풀 자체를 보강하고, 꺼져 있으면 기존과 동일하게 검색어
    하나만 시도한다.

    Sprint101 - video_intent(Motion Contract가 이미 결정한 VideoIntent
    dict 전체 - intent/confidence/reason/source)는 여기서 새 선택
    정책을 만드는 데 쓰지 않는다 - Selection Trace의 모든 항목에
    그대로 태깅해 QA가 "이 scene의 Motion Contract 판정이 무엇이고
    왜(reason)/어디서(source) 나왔는지"를 확인할 수 있게 하는
    Orchestration 전달 용도일 뿐이다. 실제 승자 결정은 지금처럼
    select_with_relevance()의 점수 비교만으로 이뤄진다.

    반환값: (result, ai_priority_choice, selection_trace, relevance_all_failed)
    """

    def _tag_fallback(trace, fallback):
        for entry in trace:
            entry["fallback"] = fallback
            entry["video_intent"] = video_intent
        return trace

    if prefer_ai:
        ai_candidate = _build_ai_candidate(
            image_prompt, staging_path, channel, is_hook_scene, visual_type, visual_profile,
            aspect_ratio=aspect_ratio,
        )
        ai_result, ai_trace, ai_all_failed = select_with_relevance(
            [ai_candidate], narration or "", image_prompt, staging_path,
        )
        _tag_fallback(ai_trace, False)

        if ai_result is not None and not ai_all_failed:
            return ai_result, True, ai_trace, False

        stock_result, stock_trace, stock_all_failed = _gather_stock_result(
            image_prompt, allow_video, search_query_override, narration, staging_path,
            image_orientation=image_orientation,
        )
        _tag_fallback(stock_trace, True)
        combined_trace = ai_trace + stock_trace

        if stock_result is not None and not stock_all_failed:
            _discard(ai_result)
            return stock_result, False, combined_trace, False

        # 요구사항 6 - 후보가 모두 실패하면 NOT READY. 그래도 파이프
        # 라인은 항상 asset 하나를 반환해야 하므로, 이미 생성해둔 AI
        # 결과를 최종 채택하되 relevance_all_failed=True로 표시한다.
        _discard(stock_result)
        return ai_result, True, combined_trace, True

    stock_result, stock_trace, stock_all_failed = _gather_stock_result(
        image_prompt, allow_video, search_query_override, narration, staging_path,
        image_orientation=image_orientation,
    )
    _tag_fallback(stock_trace, False)

    if stock_result is not None and not stock_all_failed:
        return stock_result, False, stock_trace, False

    ai_candidate = _build_ai_candidate(
        image_prompt, staging_path, channel, is_hook_scene, visual_type, visual_profile,
        aspect_ratio=aspect_ratio,
    )
    ai_result, ai_trace, ai_all_failed = select_with_relevance(
        [ai_candidate], narration or "", image_prompt, staging_path,
    )
    _tag_fallback(ai_trace, True)
    combined_trace = stock_trace + ai_trace

    _discard(stock_result)
    return ai_result, True, combined_trace, ai_all_failed


def _select_relevant_video_candidate(
    video_candidates: list, narration: str, image_prompt: str,
    staging_path_prefix: str,
) -> tuple:
    """
    Sprint100-3.1 - Stock Video Visual Relevance. video_candidates를
    (원래 랭킹 순서 그대로) 최대 MAX_RELEVANCE_CANDIDATES개까지 순회
    하며 각각 다운로드 -> 대표 프레임(RELEVANCE_FRAME_FRACTION 지점)
    추출 -> video_relevance_service.score_relevance()로 채점한다.
    RELEVANCE_THRESHOLD 이상인 후보 중 최고점을 골라 (result, trace)로
    반환한다. 통과하는 후보가 없으면 (None, trace) - 호출자가 다른
    소스(AI/Stock Image)로 폴백한다. 개별 후보의 다운로드/추출/채점이
    실패해도 trace에 error로 남기고 다음 후보로 계속 진행한다.

    Sprint100-2 - Video as First-Class Asset. 이전에는 채점용으로
    다운로드한 원본 mp4를 (승자 포함) 매 후보마다 즉시 삭제했다 -
    result에는 대표 프레임(already_frame=True)만 담겨, 실제 Stock
    Video가 파이프라인 끝까지 살아남을 방법이 없었다. 이제 순위가
    확정될 때까지(scored에 담아) 삭제를 미루고, 패자만 정리한 뒤
    승자의 mp4는 staging_path_prefix 옆(`.video.mp4`)으로 옮겨
    result["video_path"]에 담는다 - video_builder.py가 있으면 실제
    재생, 없으면(기존과 동일하게) 대표 프레임 + Ken Burns로 폴백한다.
    """

    trace = []
    scored = []

    for index, candidate in enumerate(video_candidates[:MAX_RELEVANCE_CANDIDATES]):

        candidate_video_path = f"{staging_path_prefix}.candidate{index}.raw"
        candidate_frame_path = f"{staging_path_prefix}.candidate{index}.png"

        try:
            downloaded = download_candidate(candidate, candidate_video_path)
            _extract_frame_at_fraction(
                downloaded["local_path"], candidate_frame_path,
                fraction=RELEVANCE_FRAME_FRACTION,
            )
            relevance = video_relevance_service.score_relevance(
                candidate_frame_path, narration, image_prompt,
            )
        except Exception as exc:
            trace.append({"candidate": candidate.get("query"), "error": str(exc)})
            _remove_if_exists(candidate_video_path)
            continue

        trace.append({
            "candidate": candidate.get("query"),
            "score": relevance.score,
            "reasoning": relevance.reasoning,
        })
        scored.append(
            (relevance.score, candidate, candidate_frame_path, candidate_video_path)
        )

    scored.sort(key=lambda item: item[0], reverse=True)

    if not scored or scored[0][0] < RELEVANCE_THRESHOLD:
        for _, _, frame_path, video_path in scored:
            _remove_if_exists(frame_path)
            _remove_if_exists(video_path)
        return None, trace

    best_score, best_candidate, best_frame_path, best_video_path = scored[0]

    for _, _, frame_path, video_path in scored[1:]:
        _remove_if_exists(frame_path)
        _remove_if_exists(video_path)

    final_video_path = f"{staging_path_prefix}.video.mp4"
    os.replace(best_video_path, final_video_path)

    result = {
        "source": best_candidate["source"],
        "local_path": best_frame_path,
        "metadata": {"query": best_candidate.get("query")},
        "already_frame": True,
        "video_path": final_video_path,
    }

    return result, trace


def _finalize_downloaded_asset(result: dict, output_path: str) -> None:
    """
    Sprint71-2 - download_candidate()의 반환값을 최종 이미지 경로에
    저장합니다. 비디오였다면 첫 프레임을 추출 후 원본을 정리하고,
    이미지였다면 그대로 옮깁니다. integrate_asset()의 1차 asset
    경로와 _download_stock_asset()(Hybrid extra 슬롯)이 공유하는
    헬퍼입니다 - 기존에 integrate_asset() 안에 있던 동일 로직을
    추출했을 뿐, 동작은 바뀌지 않습니다.

    Sprint100-3.1 - result에 already_frame=True가 있으면(Visual
    Relevance 채점 과정에서 대표 프레임을 이미 추출해둔 경우)
    재추출 없이 그 프레임 파일을 그대로 옮깁니다.
    """

    if result.get("already_frame"):
        os.replace(result["local_path"], output_path)
        return

    source = result["source"]

    if "video" in source:
        try:
            _extract_first_frame(result["local_path"], output_path)
        finally:
            if os.path.exists(result["local_path"]):
                os.remove(result["local_path"])
    else:
        os.replace(result["local_path"], output_path)


def _download_stock_asset(
    search_prompt, output_path, is_hook_scene, staging_path, image_orientation=None,
):
    """
    Sprint71-2 - Hybrid Asset Composer. _select_real_first()와 동일한
    패턴(검색 -> 최고 점수 후보 다운로드)으로 스톡 후보를 찾아
    output_path에 저장하고 실제 source 문자열("pexels_image" 등)을
    반환합니다. 후보가 없거나 다운로드 자체가 실패하면(네트워크 오류
    등) None을 반환합니다 - 예외를 던지지 않으므로 호출자가 그대로
    AI 생성으로 이어갈 수 있습니다.
    """

    get_candidates_kwargs = {}
    if image_orientation is not None:
        get_candidates_kwargs["image_orientation"] = image_orientation

    stock_candidates = get_candidates(search_prompt, allow_video=True, **get_candidates_kwargs)
    best_candidate, _ = select_best_with_score(
        stock_candidates, is_hook_scene=is_hook_scene,
    )

    if best_candidate is None:
        return None

    try:
        result = download_candidate(best_candidate, staging_path)
    except Exception as exc:
        print(
            f"[AssetIntegration] Hybrid 스톡 다운로드 실패, AI로 폴백: {exc}"
        )
        return None

    _finalize_downloaded_asset(result, output_path)

    return result["source"]


def _generate_extra_ai_assets(
    image_prompt, images_dir, scene_number, channel, is_hook_scene, visual_type,
    visual_profile=None, max_assets=None, aspect_ratio=None, image_orientation=None,
):
    """
    Sprint62-4 - 1차 asset이 이미 AI(Imagen)로 생성된 scene에 한해,
    추가 이미지를 순차 생성합니다(AI_ASSET_COUNT - 1개).

    Sprint100-2 - Motion Contract: max_assets(기본 None -> 기존
    AI_ASSET_COUNT=4)를 주면 그 개수까지만 생성합니다. role은 항상
    ASSET_ROLES 순서의 접두사이므로(예: max_assets=3 -> environment/
    subject/detail) qa_report_service._validate_roles()도 접두사
    매칭을 허용하도록 함께 확장했습니다. integrate_asset()이
    max_assets=1이면 이 함수 자체를 호출하지 않습니다(extra 없음).

    Sprint62-5 - 동일 prompt를 반복하는 대신, subprompt_service로
    image_prompt를 시각적으로 다른 AI_ASSET_COUNT개의 서브프롬프트로
    나눠 각 추가 이미지에 하나씩 사용합니다. subprompts[0]은 1차
    asset(asset_path)에 대응하는 자리라 이번 스프린트에서는 쓰지
    않습니다 - 1차 asset은 여전히 원본 image_prompt로 생성됩니다
    (integrate_asset()의 기존 _ai_result() 경로, 미수정). 서브프롬프트
    생성이 실패하면 subprompt_service 자체가 image_prompt를 반복한
    리스트로 폴백하므로, 이 함수는 항상 정상적으로 동작합니다.

    Sprint71-2 - Hybrid Asset Composer: role이 HYBRID_STOCK_ROLES
    (detail/transition)인 슬롯만 먼저 스톡을 시도하고, 후보가 없거나
    다운로드가 실패하면 기존처럼 AI로 생성합니다. environment(1차,
    이 함수 밖)/subject(extra 1번)는 대상이 아니라 항상 AI입니다.
    role 값은 asset 출처와 무관하게 그대로 ASSET_ROLES 순서를
    따릅니다 - 다른 소비처(asset_usage_planner/video_builder/
    qa_report_service)는 role만 보므로 영향받지 않습니다.

    Sprint72-1 - Visual Diversity Engine: subprompt_service에 넘기는
    베이스 프롬프트에 Profile 문구를 얹어, 이 scene에서 파생되는
    4개 subprompt 전부(따라서 1차를 제외한 3개 extra asset 전부)가
    같은 Profile을 공유하게 한다("같은 Scene에서는 Profile을 유지").

    Sprint73 - Subprompt Quality Gate Observability: 반환값이
    (extra_assets, subprompt_diagnostics) 튜플로 바뀐다 - 이 함수는
    integrate_asset() 하나만 호출하므로(직접 테스트 대상 아님) 하위
    호환을 신경 쓸 필요가 없다. subprompt_diagnostics는 subprompt_
    service.get_last_diagnostics()를 그대로 담을 뿐, 새 판정 로직은
    없다.
    """

    enriched_prompt = apply_profile_to_prompt(image_prompt, visual_profile)

    # Sprint73 - Subprompt Quality Gate Observability: generate_
    # subprompts()의 반환 타입(순수 list)은 그대로 두고, 방금 이
    # 호출이 실제로 폴백했는지/왜 폴백했는지를 스레드 로컬 곁가지로
    # 읽는다. reset_diagnostics()를 먼저 호출해 두면, 테스트 등에서
    # generate_subprompts() 자체가 통째로 mock되어 실행되지 않는
    # 경우에도 다른 호출의 진단 정보가 잘못 남아있는 일이 없다.
    subprompt_service.reset_diagnostics()

    count = max_assets or AI_ASSET_COUNT

    subprompts = subprompt_service.generate_subprompts(
        enriched_prompt, count=count,
    )

    subprompt_diagnostics = subprompt_service.get_last_diagnostics()

    extra_assets = []

    for i in range(2, count + 1):

        asset_prompt = subprompts[i - 1]
        role = ASSET_ROLES[i - 1]

        output_file = os.path.join(images_dir, f"scene{scene_number}_{i}.png")

        source = None

        if role in HYBRID_STOCK_ROLES:
            staging_path = os.path.join(
                images_dir, f"scene{scene_number}_{i}.raw",
            )
            source = _download_stock_asset(
                asset_prompt, output_file, is_hook_scene, staging_path,
                image_orientation=image_orientation,
            )

        if source is None:
            generate_image_kwargs = {
                "channel": channel,
                "is_hook_scene": is_hook_scene,
                "visual_type": visual_type,
            }
            if aspect_ratio is not None:
                generate_image_kwargs["aspect_ratio"] = aspect_ratio

            generate_image(
                asset_prompt,
                output_file,
                **generate_image_kwargs,
            )

        asset_entry = {
            "type": "image",
            "path": output_file,
            "prompt": asset_prompt,
            "role": role,
        }

        if source is not None:
            asset_entry["source"] = source
        elif visual_profile is not None:
            # Sprint72-2 - source가 None이면 이 슬롯은 실제로 AI로
            # 생성됐다는 뜻이다(HYBRID_STOCK_ROLES가 아니었거나, 스톡
            # 시도가 실패해 AI로 폴백한 경우 모두 포함) - 그 경우에만
            # 실제로 적용된 profile을 기록한다.
            asset_entry["visual_profile"] = visual_profile

        extra_assets.append(asset_entry)

    return extra_assets, subprompt_diagnostics


def integrate_asset(
    scene: dict,
    project_path: str,
    channel: str = "wellbeing",
    prefer_ai: bool = False,
    visual_profile: dict = None,
    asset_strategy: str = None,
    prefer_video: bool = False,
    max_assets: int = None,
    render_profile: dict = None,
) -> dict:
    """
    Sprint30 - Multi-Candidate + Scoring 기반 선택.
    Sprint100-2 - Motion Contract: max_assets(기본 None -> 기존
    AI_ASSET_COUNT=4와 동일)를 주면 AI 1차 asset의 추가 생성 개수를
    그 값까지로 제한합니다(1이면 추가 생성 자체를 건너뜁니다). 스톡
    (이미지/비디오) 1차 asset은 원래도 assets 1개뿐이라 영향받지
    않습니다. 완전히 하위 호환 - 호출자가 넘기지 않으면 이전과 100%
    동일하게 동작합니다.
    Sprint38 - Hybrid Asset Engine: prefer_ai 품질 게이트.
    Sprint60 - Smart Visual Selection v1: scene["visual_type"]("real"/
    "ai", visual_type_classifier.apply_visual_type()이 미리 채워둠)이
    있으면 소프트 게이트 대신 하드 분기한다 - "real"은 Pexels 우선(실패
    시 Imagen 폴백), "ai"는 Imagen 우선(실패 시 Pexels 폴백). visual_type
    이 없는 scene은 기존 prefer_ai 경로를 그대로 탄다(완전 하위 호환).

    Scene 하나에 대해 후보 자산을 모두 수집(get_candidates)하고,
    Asset Ranking Service로 최고 점수 후보를 선택한 뒤 그 결과를
    반영한 새 scene dict를 반환합니다. 입력 scene dict는 변경하지
    않습니다. 후보가 하나도 없으면(모든 provider 실패/결과 없음)
    기존 AI Image Generator로 폴백합니다.

    prefer_ai=True(인물/의료 등 정확도가 중요한 scene - 호출자가 배치
    단위로 판단해 전달)여도 Pexels/Pixabay 검색 자체는 그대로
    수행합니다 - 비용보다 품질을 우선하므로, 검색된 최고 후보의 점수가
    ASSET_MODE의 pexels_quality_threshold 이상이면 그대로 그 스톡
    자산을 채택합니다. 임계값 미만일 때만 AI로 생성합니다. prefer_ai가
    아닌 scene(기본값 False)은 기존 Sprint30 동작과 완전히 동일하게
    후보가 하나라도 있으면 그대로 채택합니다.

    AssetSelector가 비디오(asset_type == "video")를 선택한 경우,
    ffmpeg로 첫 프레임을 추출해 이미지로 저장합니다 - Video Builder는
    이 함수를 거친 뒤에는 항상 이미지 파일만 다루면 되므로 전혀
    수정할 필요가 없습니다 (Video -> frame extract -> image pipeline).

    추가/갱신되는 필드:
      - search_query: 실제 스톡 검색에 사용된 키워드
      - provider: "pexels_video" | "pexels_image" | "pixabay_video" |
        "pixabay_image" | "ai_image"
      - asset_type: "video" | "image" - 원본 자산의 실제 종류를
        그대로 기록 (비디오였다면 프레임 추출 후에도 "video"로 남음)
      - asset_path: 항상 이미지 파일 경로 (비디오였던 경우 추출된
        프레임의 경로)
      - confidence: AI Image는 프롬프트로 직접 생성되므로 1.0, 스톡
        자산은 검색 키워드 기반 매칭이라 0.8 (관련성 스코어링은 아직
        없음 - Sprint28 설계 문서에 명시된 열린 이슈)

    기존 image_prompt/narration 등 다른 필드는 그대로 보존됩니다.
    """

    scene_number = scene["scene"]
    image_prompt = scene["image_prompt"]
    is_hook_scene = (scene_number == 1)

    images_dir = os.path.join(project_path, "images")

    final_image_path = os.path.join(images_dir, f"scene{scene_number}.png")
    staging_path = os.path.join(images_dir, f"scene{scene_number}.raw")

    visual_type = scene.get("visual_type")

    # Sprint122 - Longform Foundation: render_profile이 있을 때만
    # image_aspect_ratio를 꺼내 아래 각 선택 경로 -> generate_image()로
    # 흘려보낸다. render_profile이 없으면(기본값 None) aspect_ratio도
    # None으로 남아, 이 함수 전체가 오늘과 100% 동일하게 동작한다.
    aspect_ratio = render_profile.get("image_aspect_ratio") if render_profile else None

    # Sprint122 - Longform Foundation (Stock 크롭 Hotfix). render_
    # profile이 있을 때만 Stock Image(Pexels/Pixabay) 검색 orientation을
    # 넘긴다 - width>height면 "landscape"(Longform), 아니면 "portrait"
    # (Shorts). Stock Video 검색/orientation은 이 스프린트에서 전혀
    # 건드리지 않는다(get_candidates_kwargs가 image_orientation만
    # 옮기고 allow_video 분기는 그대로다 - 아래 각 호출부 참고).
    image_orientation = None
    if render_profile is not None:
        image_orientation = (
            "landscape" if render_profile["width"] > render_profile["height"]
            else "portrait"
        )

    # Sprint100-4 - Visual Intelligence Completion. selection_trace/
    # relevance_all_failed는 새 통합 경로(motion_contract가 있는
    # scene)에서만 채워진다 - 다른 모든 분기는 그대로 None/False로
    # 남아 기존과 동일하게 아무 필드도 추가되지 않는다.
    selection_trace = None
    relevance_all_failed = False

    motion_contract_entry = scene.get("motion_contract")

    if motion_contract_entry is not None:
        # Sprint101 - Motion Contract가 이미 결정한 값(video_intent -
        # video 허용 여부 + 우선순위)과 Search Query가 이미 생성한
        # 값을 그대로 실행만 한다 - 이 파일은 motion/video_intent
        # 정책도 검색어 생성도 다시 판단하지 않는다.
        video_intent = motion_contract_entry["video_intent"]
        allow_video = motion_contract.allows_video(video_intent["intent"])
        # Sprint103 - Semantic Query Intelligence. 이전에는
        # extract_intent_aware_search_query()로 카테고리 단어장에 등록된
        # 단어만 앞당겼지만, 여전히 위치 기반 8단어 절단이 남아있어
        # 근본 해결책이 아니었다(Sprint102 Root Cause 분석). 카메라 메타
        # 어휘 자체를 제거하는 generate_semantic_primary_query()로
        # 교체한다 - 카테고리/토픽 단어장에 의존하지 않는다.
        search_query_override = generate_semantic_primary_query(image_prompt)
        result, ai_priority_choice, selection_trace, relevance_all_failed = (
            _select_with_visual_relevance(
                image_prompt, staging_path, channel, is_hook_scene, visual_type,
                visual_profile, scene.get("narration"), prefer_ai, allow_video,
                search_query_override, video_intent, aspect_ratio=aspect_ratio,
                image_orientation=image_orientation,
            )
        )
    elif asset_strategy == "upload":
        # Sprint96.1 Hotfix - UploadAssetStrategy(Sprint88)의 prefer_ai가
        # visual_type보다 우선한다(visual_type 유무와 무관하게 최종
        # 결정권을 가짐). asset_strategy가 None/"default"면 이 분기를
        # 타지 않으므로 기존 visual_type 하드 분기는 그대로 유지된다.
        if prefer_ai:
            result, ai_priority_choice = _select_ai_first(
                image_prompt, staging_path, channel, is_hook_scene, visual_type,
                visual_profile, asset_strategy=asset_strategy, prefer_video=prefer_video,
                aspect_ratio=aspect_ratio, image_orientation=image_orientation,
            )
        else:
            result, ai_priority_choice = _select_real_first(
                image_prompt, staging_path, channel, is_hook_scene, visual_type,
                visual_profile, asset_strategy=asset_strategy, prefer_video=prefer_video,
                narration=scene.get("narration"), aspect_ratio=aspect_ratio,
                image_orientation=image_orientation,
            )
    elif visual_type == VISUAL_TYPE_REAL:
        result, ai_priority_choice = _select_real_first(
            image_prompt, staging_path, channel, is_hook_scene, visual_type,
            visual_profile, aspect_ratio=aspect_ratio, image_orientation=image_orientation,
        )
    elif visual_type == VISUAL_TYPE_AI:
        result, ai_priority_choice = _select_ai_first(
            image_prompt, staging_path, channel, is_hook_scene, visual_type,
            visual_profile, aspect_ratio=aspect_ratio, image_orientation=image_orientation,
        )
    else:
        # Sprint38 - visual_type이 없는 scene(구버전 데이터/다른 호출부)은
        # 기존 prefer_ai 소프트 품질 게이트 경로를 그대로 유지한다.
        get_candidates_kwargs = {}
        if image_orientation is not None:
            get_candidates_kwargs["image_orientation"] = image_orientation

        stock_candidates = get_candidates(image_prompt, allow_video=True, **get_candidates_kwargs)
        best_candidate, best_score = select_best_with_score(
            stock_candidates, is_hook_scene=is_hook_scene,
        )

        ai_priority_choice = (
            prefer_ai
            and best_candidate is not None
            and best_score < effective_pexels_threshold(
                scene, get_pexels_quality_threshold(),
            )
        )

        if best_candidate is not None and not ai_priority_choice:
            result = download_candidate(best_candidate, staging_path)
        else:
            result = _ai_result(
                image_prompt, staging_path, channel, is_hook_scene, visual_type,
                visual_profile, aspect_ratio=aspect_ratio,
            )

    # Sprint100-3.1 - _finalize_downloaded_asset()에 넘기기 전에 꺼내
    # 둔다(그 함수의 인자 계약을 바꾸지 않기 위함) - QA가 "왜 이 asset이
    # 선택됐는지" 확인할 수 있도록 scene 레벨에만 별도로 기록한다.
    video_relevance_trace = result.pop("video_relevance_trace", None)

    # Sprint100-2 - Video as First-Class Asset. 있을 때만(실제 Stock
    # Video가 Relevance 채점을 통과해 원본 mp4가 보존된 경우) 꺼내서
    # primary_asset에 추가 필드로 얹는다 - 기존 asset_path(PNG) 생성
    # 경로/값은 전혀 바뀌지 않는다.
    video_path = result.pop("video_path", None)

    source = result["source"]
    asset_type = "video" if "video" in source else "image"

    _finalize_downloaded_asset(result, final_image_path)

    confidence = 1.0 if source == "ai_image" else 0.8

    if source != "ai_image":
        outcome = "success"
    elif ai_priority_choice:
        # AI가 의도적으로 선택된 경우 - (a) 기존 prefer_ai 품질 게이트가
        # Pexels 품질 미달로 AI를 택했거나, (b) visual_type="ai" scene이
        # Imagen을 첫 시도에서 그대로 성공한 경우. 스톡 검색/다운로드
        # 자체가 실패해 어쩔 수 없이 AI로 넘어간 "fallback"과는 구분한다.
        outcome = "ai_priority"
    else:
        outcome = "fallback"

    try:
        asset_feedback_service.record(
            scene_id=scene_number,
            provider=source,
            asset_type=asset_type,
            selected_asset=final_image_path,
            outcome=outcome,
        )
    except Exception as exc:
        # Learning Layer는 optional overlay이므로, 기록 실패가 asset
        # 선택 자체를 막아서는 안 된다.
        print(f"[AssetIntegration] feedback 기록 실패(무시): {exc}")

    enriched = dict(scene)
    enriched["search_query"] = result["metadata"].get("query")
    enriched["provider"] = source
    enriched["asset_type"] = asset_type
    enriched["asset_path"] = final_image_path
    enriched["confidence"] = confidence

    # Sprint100-3.1 - Stock Video Visual Relevance Selection Trace.
    # video 후보를 채점했을 때만(asset_strategy="upload" and prefer_
    # video=True and video 후보가 하나 이상 있었을 때) 추가된다 - 그
    # 외에는 기존과 동일하게 필드 자체가 없다.
    if video_relevance_trace is not None:
        enriched["video_relevance_trace"] = video_relevance_trace

    # Sprint100-4 - Visual Intelligence Completion Selection Trace.
    # motion_contract가 있는 scene(새 통합 선택 경로)에서만 채워진다 -
    # video_relevance_trace(Sprint100-3.1, video 전용, 구 경로)와는
    # 서로 배타적이다 - 한 scene은 둘 중 하나만 갖는다.
    if selection_trace is not None:
        enriched["selection_trace"] = selection_trace
        enriched["relevance_all_failed"] = relevance_all_failed
        enriched["search_query_used"] = search_query_override

    # Sprint72-2 - Visual Diversity Engine Observability: "배정된"
    # profile은 실제로 AI가 그 profile을 썼는지와 무관하게 scene
    # 레벨에 항상 기록한다(QA가 diversity 배정 자체를 볼 수 있어야
    # 함) - profile이 없으면(기본값 None) 기존과 동일하게 필드 자체를
    # 추가하지 않는다.
    if visual_profile is not None:
        enriched["visual_profile"] = visual_profile

    # Sprint62-1 - Visual Diversity 기반 구조: scene["assets"][0]은
    # 항상 asset_path와 동일한 1차 이미지다.
    primary_asset = {
        "type": "image",
        "path": final_image_path,
        "prompt": image_prompt,
    }

    if video_path is not None:
        # Sprint100-2 - Video as First-Class Asset: asset_path(PNG)는
        # Fallback/Thumbnail 용도로 계속 유지하고, video_path를 새
        # 필드로만 추가한다. video_builder.py는 이 필드가 있고 실제
        # 파일이 존재할 때만 VideoFileClip 경로를 타고, 없으면(또는
        # 이 필드 자체가 없으면) 기존 Ken Burns 경로를 그대로 쓴다.
        primary_asset["video_path"] = video_path

    if source == "ai_image":
        # Sprint62-4 - 1차 asset이 AI로 생성된 scene만 동일 prompt로
        # 추가 이미지를 생성한다. 스톡(Pexels/Pixabay) 선택 scene은
        # 이번 스프린트에서 손대지 않는다(assets 1개 그대로 유지).
        if max_assets == 1:
            # Sprint100-2 - Motion Contract Static Scene: role 기반
            # 멀티 asset 구성 자체를 쓰지 않으므로 role을 부여하지
            # 않는다(단일 asset) - qa_report_service._validate_roles()의
            # 기존 "role 전부 없음=정상" 분기를 그대로 탄다.
            extra_assets, subprompt_diagnostics = [], None
        else:
            # Sprint64-2 - AI 멀티 asset 경로에서만 role을 부여한다.
            primary_asset["role"] = ASSET_ROLES[0]
            # Sprint72-2 - 1차 asset이 실제로 AI 생성됐을 때만(즉 여기,
            # source == "ai_image") profile을 asset 메타데이터에도 남긴다.
            if visual_profile is not None:
                primary_asset["visual_profile"] = visual_profile
            extra_assets, subprompt_diagnostics = _generate_extra_ai_assets(
                image_prompt, images_dir, scene_number, channel, is_hook_scene,
                visual_type, visual_profile, max_assets=max_assets,
                aspect_ratio=aspect_ratio, image_orientation=image_orientation,
            )
        # Sprint73 - Subprompt Quality Gate Observability: 이 scene의
        # subprompt 생성이 폴백했는지/왜 폴백했는지를 scene 레벨에
        # 기록한다 - step07_quality.py가 quality_report.json에 그대로
        # 옮겨 싣는다(Sprint72-2 visual_profile과 동일 패턴).
        if subprompt_diagnostics is not None:
            enriched["subprompt_diagnostics"] = subprompt_diagnostics
    else:
        extra_assets = []

    enriched["assets"] = [primary_asset] + extra_assets

    return enriched
