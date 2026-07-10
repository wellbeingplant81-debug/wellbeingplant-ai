import os
import subprocess

from app.services import asset_feedback_service
from app.services.asset_mode_config import get_pexels_quality_threshold
from app.services.asset_priority_classifier import effective_pexels_threshold
from app.services.asset_ranking_service import select_best_with_score
from app.services.asset_selector import download_candidate, get_candidates
from app.services.image_service import generate_image
from app.services.search_query_extractor import extract_search_query
from app.services import subprompt_service
from app.services.visual_diversity_engine import apply_profile_to_prompt
from app.services.visual_type_classifier import VISUAL_TYPE_AI, VISUAL_TYPE_REAL


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
    visual_profile=None,
):
    # Sprint72-1 - Visual Diversity Engine: 실제 이미지 생성(Imagen)에
    # 넘기는 프롬프트에만 Profile 문구를 얹는다 - search_query 등
    # 메타데이터는 원본 image_prompt 기준으로 그대로 유지한다.
    enriched_prompt = apply_profile_to_prompt(image_prompt, visual_profile)

    ai_path = generate_image(
        enriched_prompt,
        staging_path,
        channel=channel,
        is_hook_scene=is_hook_scene,
        visual_type=visual_type,
    )

    return {
        "source": "ai_image",
        "local_path": ai_path,
        "metadata": {"query": extract_search_query(image_prompt)},
    }


def _select_real_first(
    image_prompt, staging_path, channel, is_hook_scene, visual_type=None,
    visual_profile=None,
):
    """
    Sprint60 - visual_type == "real": Pexels(스톡) 우선, 실패 시 Imagen
    폴백. "실패"는 후보가 아예 없는 경우와, 후보는 있었지만 다운로드
    자체가 실패한 경우(네트워크 오류 등) 둘 다 포함한다.
    """

    stock_candidates = get_candidates(image_prompt, allow_video=True)
    best_candidate, _ = select_best_with_score(
        stock_candidates, is_hook_scene=is_hook_scene,
    )

    if best_candidate is not None:
        try:
            return download_candidate(best_candidate, staging_path), False
        except Exception as exc:
            print(
                f"[AssetIntegration] visual_type=real, Pexels 다운로드 "
                f"실패, Imagen으로 폴백: {exc}"
            )

    return (
        _ai_result(
            image_prompt, staging_path, channel, is_hook_scene, visual_type,
            visual_profile,
        ),
        False,
    )


def _select_ai_first(
    image_prompt, staging_path, channel, is_hook_scene, visual_type=None,
    visual_profile=None,
):
    """
    Sprint60 - visual_type == "ai": Imagen 우선, 실패 시 Pexels 폴백.

    반환값: (result_dict, ai_was_deliberate_choice). ai_was_deliberate_
    choice는 Imagen이 첫 시도에서 바로 성공했는지(True) - 스톡 검색
    실패로 인한 어쩔 수 없는 폴백(False)과 구분해 feedback outcome을
    정확히 기록하기 위함이다.
    """

    try:
        return (
            _ai_result(
                image_prompt, staging_path, channel, is_hook_scene, visual_type,
                visual_profile,
            ),
            True,
        )
    except Exception as exc:
        print(
            f"[AssetIntegration] visual_type=ai, Imagen 생성 실패, "
            f"Pexels로 폴백: {exc}"
        )

    stock_candidates = get_candidates(image_prompt, allow_video=True)
    best_candidate, _ = select_best_with_score(
        stock_candidates, is_hook_scene=is_hook_scene,
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


def _finalize_downloaded_asset(result: dict, output_path: str) -> None:
    """
    Sprint71-2 - download_candidate()의 반환값을 최종 이미지 경로에
    저장합니다. 비디오였다면 첫 프레임을 추출 후 원본을 정리하고,
    이미지였다면 그대로 옮깁니다. integrate_asset()의 1차 asset
    경로와 _download_stock_asset()(Hybrid extra 슬롯)이 공유하는
    헬퍼입니다 - 기존에 integrate_asset() 안에 있던 동일 로직을
    추출했을 뿐, 동작은 바뀌지 않습니다.
    """

    source = result["source"]

    if "video" in source:
        try:
            _extract_first_frame(result["local_path"], output_path)
        finally:
            if os.path.exists(result["local_path"]):
                os.remove(result["local_path"])
    else:
        os.replace(result["local_path"], output_path)


def _download_stock_asset(search_prompt, output_path, is_hook_scene, staging_path):
    """
    Sprint71-2 - Hybrid Asset Composer. _select_real_first()와 동일한
    패턴(검색 -> 최고 점수 후보 다운로드)으로 스톡 후보를 찾아
    output_path에 저장하고 실제 source 문자열("pexels_image" 등)을
    반환합니다. 후보가 없거나 다운로드 자체가 실패하면(네트워크 오류
    등) None을 반환합니다 - 예외를 던지지 않으므로 호출자가 그대로
    AI 생성으로 이어갈 수 있습니다.
    """

    stock_candidates = get_candidates(search_prompt, allow_video=True)
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
    visual_profile=None,
):
    """
    Sprint62-4 - 1차 asset이 이미 AI(Imagen)로 생성된 scene에 한해,
    추가 이미지를 순차 생성합니다(AI_ASSET_COUNT - 1개).

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
    """

    enriched_prompt = apply_profile_to_prompt(image_prompt, visual_profile)

    subprompts = subprompt_service.generate_subprompts(
        enriched_prompt, count=AI_ASSET_COUNT,
    )

    extra_assets = []

    for i in range(2, AI_ASSET_COUNT + 1):

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
            )

        if source is None:
            generate_image(
                asset_prompt,
                output_file,
                channel=channel,
                is_hook_scene=is_hook_scene,
                visual_type=visual_type,
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

    return extra_assets


def integrate_asset(
    scene: dict,
    project_path: str,
    channel: str = "wellbeing",
    prefer_ai: bool = False,
    visual_profile: dict = None,
) -> dict:
    """
    Sprint30 - Multi-Candidate + Scoring 기반 선택.
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

    if visual_type == VISUAL_TYPE_REAL:
        result, ai_priority_choice = _select_real_first(
            image_prompt, staging_path, channel, is_hook_scene, visual_type,
            visual_profile,
        )
    elif visual_type == VISUAL_TYPE_AI:
        result, ai_priority_choice = _select_ai_first(
            image_prompt, staging_path, channel, is_hook_scene, visual_type,
            visual_profile,
        )
    else:
        # Sprint38 - visual_type이 없는 scene(구버전 데이터/다른 호출부)은
        # 기존 prefer_ai 소프트 품질 게이트 경로를 그대로 유지한다.
        stock_candidates = get_candidates(image_prompt, allow_video=True)
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
                visual_profile,
            )

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

    if source == "ai_image":
        # Sprint62-4 - 1차 asset이 AI로 생성된 scene만 동일 prompt로
        # 추가 이미지를 생성한다. 스톡(Pexels/Pixabay) 선택 scene은
        # 이번 스프린트에서 손대지 않는다(assets 1개 그대로 유지).
        # Sprint64-2 - AI 4-asset 경로에서만 role을 부여한다.
        primary_asset["role"] = ASSET_ROLES[0]
        # Sprint72-2 - 1차 asset이 실제로 AI 생성됐을 때만(즉 여기,
        # source == "ai_image") profile을 asset 메타데이터에도 남긴다.
        if visual_profile is not None:
            primary_asset["visual_profile"] = visual_profile
        extra_assets = _generate_extra_ai_assets(
            image_prompt, images_dir, scene_number, channel, is_hook_scene,
            visual_type, visual_profile,
        )
    else:
        extra_assets = []

    enriched["assets"] = [primary_asset] + extra_assets

    return enriched
