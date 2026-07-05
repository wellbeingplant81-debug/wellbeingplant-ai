from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.asset_integration_service import integrate_asset


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

    기존 step02_image.py는 삭제/수정하지 않고 그대로 유지합니다.
    """

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
                )
            )

        for future in as_completed(futures):
            results.append(future.result())

    return sorted(results, key=lambda enriched_scene: enriched_scene["scene"])
