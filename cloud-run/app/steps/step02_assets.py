from concurrent.futures import ThreadPoolExecutor, as_completed

from app import config
from app.services import best_of_n_service
from app.services.asset_integration_service import integrate_asset
from app.services.asset_mode_config import get_ai_ratio_cap
from app.services.asset_priority_classifier import select_ai_priority_scenes


MAX_WORKERS = 3


def collect_assets(
    scenes,
    project_path,
    channel="wellbeing",
):
    """
    기존 step02_image.py의 병렬 처리 구조(ThreadPoolExecutor,
    max_workers=3)를 그대로 재사용합니다. scene마다 AssetSelector ->
    (필요시) 비디오 프레임 추출까지 마친 확장된 scene dict를
    돌려받아, 원래 scenes 순서(scene 번호 기준)로 정렬해 반환합니다.

    Sprint38 - Hybrid Asset Engine: scene 배치 전체를 대상으로
    ASSET_MODE의 ai_ratio_cap 이내에서 AI 우선 품질 게이트 대상 scene을
    한 번만 골라두고(select_ai_priority_scenes), 각 scene에
    prefer_ai로 전달합니다. 실제 AI 사용 여부는 여전히
    asset_integration_service.integrate_asset()의 Pexels 품질
    게이트가 최종 결정합니다.

    기존 step02_image.py는 삭제/수정하지 않고 그대로 유지합니다.
    """

    ai_priority_scenes = select_ai_priority_scenes(
        scenes, get_ai_ratio_cap(),
    )

    # Sprint74 - 후보 배분은 여기서 끝낸다. integrate_asset은 아래에서
    # 스레드 3개로 병렬 실행되므로, 그 안에서 공유 예산을 깎으면 경쟁
    # 상태가 되고 같은 입력이 실행마다 다른 배분을 낸다.
    candidate_plan = best_of_n_service.plan_candidates(
        scenes,
        default_n=(
            config.BEST_OF_N_CANDIDATES if config.ENABLE_BEST_OF_N else 1
        ),
        budget=config.BEST_OF_N_MAX_CANDIDATES,
    )

    futures = []
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        for scene in scenes:

            futures.append(
                executor.submit(
                    integrate_asset,
                    scene,
                    project_path,
                    channel,
                    prefer_ai=scene["scene"] in ai_priority_scenes,
                    candidate_count=candidate_plan[scene["scene"]],
                )
            )

        for future in as_completed(futures):
            results.append(future.result())

    return sorted(results, key=lambda enriched_scene: enriched_scene["scene"])
