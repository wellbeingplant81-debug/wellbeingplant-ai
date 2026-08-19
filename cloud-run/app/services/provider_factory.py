from app.providers import pexels_provider
from app.providers import pixabay_provider


# Sprint228 - 길이 조건을 걸 때 Pixabay 에서 더 받아 온다.
#
# Pixabay 영상 검색에는 길이로 거르는 질의 항목이 없다(응답에 duration 이
# 실려 올 뿐이다). 그래서 거르는 대신 더 받아 와서 고를 여지를 넓힌다 -
# 다섯 개가 전부 짧으면 순위를 아무리 잘 매겨도 결과는 hold 다.
#
# 크게 늘리지 않는다. 응답이 커지면 그만큼 느려지고 스톡 API 에는 호출
# 한도가 있다.
VIDEO_PER_PAGE = 5
WIDER_VIDEO_PER_PAGE = 15


def _wanted(min_seconds) -> bool:
    """길이 조건을 걸어야 하는 자리인가."""

    return bool(min_seconds) and min_seconds > 0


def _pexels_video(min_seconds):
    """
    조건이 없으면 예전 부름말 그대로다.

    None 을 굳이 넘기면 부름말이 달라지고, "체인은 그대로 넘긴다"를
    지키는 가드가 그것을 잡는다 - 그 가드가 옳다. 조건이 있을 때만
    한 항목이 는다.
    """

    if _wanted(min_seconds):
        return lambda query: pexels_provider.search_videos(
            query, min_duration=min_seconds)

    return lambda query: pexels_provider.search_videos(query)


def _pixabay_video(min_seconds):
    """
    Pixabay 에는 길이로 거르는 질의 항목이 없다. 거르는 대신 더 받아
    와서 고를 여지를 넓힌다.
    """

    if _wanted(min_seconds):
        return lambda query: pixabay_provider.search_videos(
            query, per_page=WIDER_VIDEO_PER_PAGE)

    return lambda query: pixabay_provider.search_videos(query)


def build_provider_chain(allow_video: bool = True, min_seconds=None) -> list:
    """
    Asset 검색에 사용할 provider 체인을 우선순위 순서대로 생성합니다.

    allow_video=True(기본값)이면 기존 AssetSelector와 완전히 동일한
    순서를 반환합니다: Pexels Video -> Pexels Image -> Pixabay Video
    -> Pixabay Image.

    allow_video=False이면 비디오 provider(Pexels Video, Pixabay
    Video)를 제외하고 이미지 provider만 순서대로 반환합니다: Pexels
    Image -> Pixabay Image.

    Sprint228 - min_seconds 를 주면 그 길이를 검색에 실어 보낸다.

        Pexels    min_duration 질의 항목이 있다 - 짧은 것을 안 받는다
        Pixabay   그런 항목이 없다 - 대신 더 받아 와서 고를 여지를 넓힌다

    주지 않으면 예전 요청 그대로다. 이미지 provider 는 어느 쪽이든 한
    글자도 바뀌지 않는다 - 사진에는 길이가 없다.

    각 항목은 (source, search_fn) 튜플이며, search_fn(query)는
    정규화된 결과 리스트를 반환합니다 (app.providers.*_provider의
    search_* 함수를 그대로 감쌉니다).
    """

    chain = []

    if allow_video:
        chain.append(("pexels_video", _pexels_video(min_seconds)))

    chain.append(
        ("pexels_image", lambda query: pexels_provider.search_photos(query))
    )

    if allow_video:
        chain.append(("pixabay_video", _pixabay_video(min_seconds)))

    chain.append(
        ("pixabay_image", lambda query: pixabay_provider.search_images(query))
    )

    return chain
