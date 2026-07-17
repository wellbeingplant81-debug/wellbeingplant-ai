from app.providers import pexels_provider
from app.providers import pixabay_provider


# Sprint123 - Production Policy item 6: Pexels는 "landscape"/"portrait"를
# orientation 값으로 쓰지만, Pixabay는 "horizontal"/"vertical"을 쓴다
# (pixabay_provider.py의 기본값 "vertical"이 그 증거 - Sprint122에서
# image_orientation="landscape"를 Pixabay에도 그대로 전달한 것은 버그
#였다). 여기서 한 곳에서만 변환해 두 provider 모두 항상 자기 API가
# 이해하는 값을 받게 한다.
_PIXABAY_ORIENTATION_MAP = {
    "landscape": "horizontal",
    "portrait": "vertical",
}


def _pixabay_orientation(orientation):
    if orientation is None:
        return None
    return _PIXABAY_ORIENTATION_MAP.get(orientation, orientation)


def build_provider_chain(allow_video: bool = True, image_orientation: str = None) -> list:
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

    Sprint122 - Longform Foundation: image_orientation(기본값 None)이
    주어졌을 때만 provider 호출에 orientation kwarg를 보탠다 - 안 주면
    각 provider 자체의 기본값("portrait"/"vertical")이 적용되는 기존
    호출과 바이트 단위로 동일하다(기존 테스트들이 orientation 없는
    bare 호출을 그대로 검증하므로, 기본값을 여기서 미리 채워 넣으면
    안 된다).

    Sprint123 - Production Policy item 6: 이름은 여전히
    "image_orientation"이지만(호출부 하위 호환을 위해 이름은 바꾸지
    않음), Stock **Video** provider(Pexels/Pixabay)에도 동일하게
    적용된다 - Longform은 Stock Video로 채워진 Scene도 landscape
    원본을 받아야 크롭이 생기지 않는다. Pixabay는 "horizontal"/
    "vertical" 값을 쓰므로 _pixabay_orientation()으로 변환한다.
    """

    def _pexels_video_search(query):
        if image_orientation is not None:
            return pexels_provider.search_videos(query, orientation=image_orientation)
        return pexels_provider.search_videos(query)

    def _pexels_image_search(query):
        if image_orientation is not None:
            return pexels_provider.search_photos(query, orientation=image_orientation)
        return pexels_provider.search_photos(query)

    def _pixabay_video_search(query):
        pixabay_value = _pixabay_orientation(image_orientation)
        if pixabay_value is not None:
            return pixabay_provider.search_videos(query, orientation=pixabay_value)
        return pixabay_provider.search_videos(query)

    def _pixabay_image_search(query):
        pixabay_value = _pixabay_orientation(image_orientation)
        if pixabay_value is not None:
            return pixabay_provider.search_images(query, orientation=pixabay_value)
        return pixabay_provider.search_images(query)

    chain = []

    if allow_video:
        chain.append(("pexels_video", _pexels_video_search))

    chain.append(("pexels_image", _pexels_image_search))

    if allow_video:
        chain.append(("pixabay_video", _pixabay_video_search))

    chain.append(("pixabay_image", _pixabay_image_search))

    return chain
