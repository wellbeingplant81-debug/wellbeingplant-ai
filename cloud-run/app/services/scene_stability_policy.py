"""
Sprint121 - Scene Stability & Stock Video Priority.

Scene 길이에 따라 그 scene 안에서 허용할 최대 asset(컷) 개수를
정하는 순수 함수. 1~2초마다 asset이 계속 바뀌는 산만한 편집을
막기 위해, Scene 길이 구간별로 컷 수 상한을 두고 - 그 상한이 항상
MIN_ASSET_DURATION_SECONDS(2.5초) 이상의 per-asset 재생 시간을
보장하도록 설계되었다.

파일 I/O/렌더링/파이프라인 연결 없음.
"""

MIN_ASSET_DURATION_SECONDS = 2.5

SHORT_SCENE_THRESHOLD_SECONDS = 5.0
MEDIUM_SCENE_THRESHOLD_SECONDS = 8.0

SHORT_SCENE_MAX_ASSETS = 1
MEDIUM_SCENE_MAX_ASSETS = 2
LONG_SCENE_MAX_ASSETS = 3


def max_assets_for_duration(duration: float) -> int:

    if duration < SHORT_SCENE_THRESHOLD_SECONDS:
        return SHORT_SCENE_MAX_ASSETS

    if duration < MEDIUM_SCENE_THRESHOLD_SECONDS:
        return MEDIUM_SCENE_MAX_ASSETS

    return LONG_SCENE_MAX_ASSETS
