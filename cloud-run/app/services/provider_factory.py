from app.providers import pexels_provider
from app.providers import pixabay_provider


def build_provider_chain(allow_video: bool = True) -> list:
    """
    Asset 검색에 사용할 provider 체인을 우선순위 순서대로 생성합니다.

    allow_video=True(기본값)이면 기존 AssetSelector와 완전히 동일한
    순서를 반환합니다: Pexels Video -> Pexels Image -> Pixabay Video
    -> Pixabay Image.

    allow_video=False이면 비디오 provider(Pexels Video, Pixabay
    Video)를 제외하고 이미지 provider만 순서대로 반환합니다: Pexels
    Image -> Pixabay Image.

    각 항목은 (source, search_fn) 튜플이며, search_fn(query)는
    정규화된 결과 리스트를 반환합니다 (app.providers.*_provider의
    search_* 함수를 그대로 감쌉니다).
    """

    chain = []

    if allow_video:
        chain.append(
            ("pexels_video", lambda query: pexels_provider.search_videos(query))
        )

    chain.append(
        ("pexels_image", lambda query: pexels_provider.search_photos(query))
    )

    if allow_video:
        chain.append(
            ("pixabay_video", lambda query: pixabay_provider.search_videos(query))
        )

    chain.append(
        ("pixabay_image", lambda query: pixabay_provider.search_images(query))
    )

    return chain
