import os
import subprocess

from app.services import asset_feedback_service
from app.services.asset_mode_config import get_pexels_quality_threshold
from app.services.asset_priority_classifier import effective_pexels_threshold
from app.services.asset_ranking_service import select_best_with_score
from app.services.asset_selector import download_candidate, get_candidates
from app.services.image_service import generate_image
from app.services.search_query_extractor import extract_search_query
from app.services.visual_type_classifier import VISUAL_TYPE_AI, VISUAL_TYPE_REAL


def _ai_result(image_prompt, staging_path, channel, is_hook_scene, visual_type=None):
    ai_path = generate_image(
        image_prompt,
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


def _select_real_first(image_prompt, staging_path, channel, is_hook_scene, visual_type=None):
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
        _ai_result(image_prompt, staging_path, channel, is_hook_scene, visual_type),
        False,
    )


def _select_ai_first(image_prompt, staging_path, channel, is_hook_scene, visual_type=None):
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


def integrate_asset(
    scene: dict,
    project_path: str,
    channel: str = "wellbeing",
    prefer_ai: bool = False,
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
        )
    elif visual_type == VISUAL_TYPE_AI:
        result, ai_priority_choice = _select_ai_first(
            image_prompt, staging_path, channel, is_hook_scene, visual_type,
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
            )

    source = result["source"]
    asset_type = "video" if "video" in source else "image"

    if asset_type == "video":
        try:
            _extract_first_frame(result["local_path"], final_image_path)
        finally:
            if os.path.exists(result["local_path"]):
                os.remove(result["local_path"])
    else:
        os.replace(result["local_path"], final_image_path)

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

    return enriched
