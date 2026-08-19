"""
Sprint223 - 이 그림이 어디서 왔는가를 사람의 말로 (Epic 65).

스톡 영상이 실제로 재생되기 시작하면, 사람은 어떤 scene이 움직이고
어떤 scene이 정지 사진인지 알아볼 수 있어야 한다. 전부 정지 사진이던
시절에는 물을 일이 없었다.

새로 분류하지 않는다
--------------------
script.json에는 이미 provider와 asset_type이 적혀 있다. 여기서 하는
일은 그 값을 읽는 말로 옮기는 것뿐이고, 판정을 다시 하지 않는다 -
판정이 두 곳에 살면 어느 날 화면과 산출물이 서로 다른 말을 한다.

왜 studio_review 안에 두지 않았는가
-----------------------------------
처음에는 그 안에 표를 두었다가 가드가 울었다
(test_flux_provider.TestNothingElseMoved). 검수 흐름에 Provider 이름이
새어 드는 것을 막는 가드이고, **그 가드가 옳았다** - 검수 화면은
무엇으로 만들었는지를 판정할 자리가 아니다. 가드를 고치는 대신 표를
옮긴다.

이름을 다시 적지 않는다
-----------------------
provider_selection이 이미 들고 있는 상수를 쓴다. 스톡은 이름의 생김새로
가른다 - provider_factory가 <업체>_<종류>로 짓고(pexels_video ·
pixabay_image …), asset_selector도 이미 그 이름을 보고 종류를 정한다
("video" in source). 여기서 pexels·pixabay를 다시 나열하면 셋째 업체가
붙는 날 이 파일만 조용히 뒤처진다.

모르면 빈 글자다
----------------
지어내지 않는다. 화면은 빈 글자를 받으면 아무것도 그리지 않는다 -
"출처 미상"이라고 적는 것보다 낫다. provider를 적기 전에 만든
프로젝트가 실제로 있다.
"""

from app.services import provider_selection

STOCK_VIDEO = "스톡 영상"
STOCK_PHOTO = "스톡 사진"
AI_IMAGE = "AI 이미지"
MY_LIBRARY = "내 자료"
I_PUT_IN = "내가 넣은 그림"

VIDEO = "video"

# 엔진이 스스로 그린 것. asset_integration_service가 그 이름으로
# 기록한다("source": "ai_image").
AI_IMAGE_SOURCE = "ai_image"

# 사람이 준 파일을 그 자리에 놓는 provider. staging이 부르는 이름과
# 같다(staging.KINDS).
IMAGE_IMPORT = "image_import"

# 프롬프트를 주면 그림을 내놓는 것들.
#
# local_stock은 여기 들어가지 않는다. asset_integration_service의
# AI_SOURCES는 그것을 함께 세지만 그것은 confidence를 정하려는 것이고
# (프롬프트를 받아 그림을 놓는다는 점이 같다), 사람에게 그것은 제
# 폴더에서 고른 제 자료다. AI가 만들었다고 적으면 거짓말이다.
AI_PROVIDERS = (
    AI_IMAGE_SOURCE,
    provider_selection.FLUX,
    provider_selection.GPT_IMAGE,
)


def label(provider, asset_type=None) -> str:
    """이 그림이 어디서 왔는가. 순수 함수입니다."""

    name = str(provider or "").strip()

    if name in AI_PROVIDERS:
        return AI_IMAGE

    if name == provider_selection.LOCAL_STOCK:
        return MY_LIBRARY

    if name == IMAGE_IMPORT:
        return I_PUT_IN

    if name.endswith("_video"):
        return STOCK_VIDEO

    if name.endswith("_image"):
        return STOCK_PHOTO

    # 이름을 몰라도 영상이었다는 것은 안다 - 영상을 주는 곳은 스톡뿐이다
    # (provider_factory의 체인에 영상은 스톡 둘밖에 없다).
    if asset_type == VIDEO:
        return STOCK_VIDEO

    return ""


def moves(asset_type) -> bool:
    """이 scene이 최종 영상에서 움직이는가. 순수 함수입니다."""

    return asset_type == VIDEO
