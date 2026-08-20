"""
Sprint249-A - Instagram 이 실제로 닿을 수 있는 주소만 넘긴다.

무엇이 빠져 있었나
------------------
Adapter 는 공개 URL 이 **비어 있는지**만 보았다.

    if not asset.public_url:   -> 거절

비어 있지 않으면 무엇이든 지나간다. 그래서 누가 저장소를

    STORAGE_S3_PUBLIC_BASE_URL=http://localhost:9000

으로 잘못 잡아 두면 그 주소가 그대로 Instagram 에 간다. Meta 는 그
주소를 **자기 서버에서 cURL** 한다("we cURL media used in publishing
attempts"). localhost 는 그쪽에서 우리 PC 를 가리키지 않으므로 절대
닿지 않고, 사람은 왜 실패했는지 알 수 없다.

파일 경로도 마찬가지다. C:\\...\\final_short.mp4 는 비어 있지 않으니
통과한다.

scope 는 왜 여기서 재는가
-------------------------
Instagram Login 방식은 두 권한을 쓴다.

    instagram_business_basic            누구인지
    instagram_business_content_publish  올린다

옛 이름(instagram_basic 등)은 2025-01-27 에 폐기됐고, Facebook Login
전용 권한(pages_read_engagement 등)은 이 방식에 섞이면 안 된다.
지금은 맞게 적혀 있고, 그것이 조용히 되돌아가지 않게 붙잡아 둔다.

여기서 재는 것
--------------
실제 Instagram 은 한 번도 부르지 않는다. 런타임을 통째로 가짜로 바꿔
두고 **무엇이 video_url 로 건네졌는가**만 본다.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.upload import instagram_oauth_service
from app.providers.storage.asset_reference import AssetReference
from app.services.publishing.publishing_plan_model import PublishingPlan
from app.services.publishing.runtime_backed_publish_adapter import (
    RuntimeBackedPublishAdapter, resolve_video_path,
)
from app.services.publishing_runtime_protocol import RuntimeCapabilities


# -- 권한 ------------------------------------------------------------
class TheLoginAsksForTheRightPermissionsTest(unittest.TestCase):

    def test_올릴_권한을_받는다(self):
        self.assertIn("instagram_business_content_publish",
                      instagram_oauth_service._SCOPES)

    def test_누구인지도_받는다(self):
        self.assertIn("instagram_business_basic",
                      instagram_oauth_service._SCOPES)

    def test_폐기된_옛_이름을_쓰지_않는다(self):
        """2025-01-27 에 사라진 것들이다."""

        parts = set(instagram_oauth_service._SCOPES.split(","))

        for old in ("instagram_basic", "instagram_content_publish"):
            with self.subTest(old=old):
                self.assertNotIn(old, parts)

    def test_다른_로그인_방식의_권한이_섞이지_않는다(self):
        """pages_* 는 Facebook Login 쪽 어휘다."""

        self.assertNotIn("pages_", instagram_oauth_service._SCOPES)
        self.assertNotIn("ads_", instagram_oauth_service._SCOPES)

    def test_사람이_가는_주소가_공식_주소다(self):
        """
        토큰 교환은 api.instagram.com 이지만 사람이 로그인하러 가는
        자리는 www.instagram.com 이다. 둘은 다른 용도다.
        """

        self.assertEqual(instagram_oauth_service.AUTHORIZE_URL,
                         "https://www.instagram.com/oauth/authorize")

    def test_토큰_교환_주소는_그대로다(self):
        self.assertEqual(instagram_oauth_service.SHORT_LIVED_TOKEN_URL,
                         "https://api.instagram.com/oauth/access_token")


# -- 가짜들 ----------------------------------------------------------
class _Runtime:
    """공개 URL 을 요구하는 런타임. 바깥으로 나가지 않는다."""

    capabilities = RuntimeCapabilities(two_phase_publish=True,
                                       requires_public_url=True)

    def __init__(self):
        self.seen = []

    def login(self, account_id):
        return object()

    def upload_media(self, credential, video_url, caption, cover_url=None,
                     plan=None):
        self.seen.append(video_url)

        return "container-1"

    def get_publish_status(self, credential, container_id):
        return "FINISHED"

    def publish_media(self, credential, container_id):
        return "media-1"

    def get_permalink(self, credential, media_id):
        return "https://instagram.com/p/x"


class _Publisher:

    def __init__(self, url):
        self.url = url

    def publish(self, local_path):
        return AssetReference(public_url=self.url, local_path=local_path)


class _Case(unittest.TestCase):

    def setUp(self):
        self.project = tempfile.mkdtemp()

        video = resolve_video_path(self.project)
        os.makedirs(os.path.dirname(video), exist_ok=True)

        with open(video, "wb") as f:
            f.write(b"mp4" * 100)

        self.video = video

        self.plan = PublishingPlan(
            job_id="j", platform="instagram", title="제목",
            description="설명", hashtags=["건강"],
            output_folder=self.project)

    def send(self, url):
        runtime = _Runtime()

        adapter = RuntimeBackedPublishAdapter(
            platform="instagram", runtime=runtime,
            asset_publisher=_Publisher(url))

        return runtime, adapter.submit(self.plan)


# -- 닿을 수 없는 주소는 넘기지 않는다 -------------------------------
class AnUnreachableUrlIsRefusedTest(_Case):

    def test_빈_주소는_거절한다(self):
        runtime, result = self.send("")

        self.assertEqual(result.status, "Failed")
        self.assertFalse(result.retryable)
        self.assertEqual(runtime.seen, [])

    def test_localhost_는_거절한다(self):
        runtime, result = self.send("http://localhost:9000/v/final.mp4")

        self.assertEqual(result.status, "Failed")
        self.assertEqual(runtime.seen, [], "닿을 수 없는 주소를 넘겼다")

    def test_루프백_주소도_거절한다(self):
        for url in ("http://127.0.0.1:9000/v.mp4",
                    "https://127.0.0.1/v.mp4",
                    "http://[::1]:9000/v.mp4"):
            with self.subTest(url=url):
                runtime, result = self.send(url)

                self.assertEqual(result.status, "Failed")
                self.assertEqual(runtime.seen, [])

    def test_사설망_주소도_거절한다(self):
        """Meta 의 서버에서 우리 집 공유기 안쪽은 보이지 않는다."""

        for url in ("https://192.168.0.10/v.mp4",
                    "https://10.0.0.5/v.mp4",
                    "https://172.16.3.9/v.mp4"):
            with self.subTest(url=url):
                runtime, result = self.send(url)

                self.assertEqual(result.status, "Failed")
                self.assertEqual(runtime.seen, [])

    def test_파일_경로는_거절한다(self):
        for url in (r"C:\\output\\video\\final_short.mp4",
                    "/home/me/final_short.mp4",
                    "file:///C:/output/final_short.mp4"):
            with self.subTest(url=url):
                runtime, result = self.send(url)

                self.assertEqual(result.status, "Failed")
                self.assertEqual(runtime.seen, [])

    def test_평문_http_는_거절한다(self):
        runtime, result = self.send("http://cdn.example.com/v.mp4")

        self.assertEqual(result.status, "Failed")
        self.assertEqual(runtime.seen, [])

    def test_왜_안_되는지_사람_말로_적는다(self):
        _, result = self.send("http://localhost:9000/v.mp4")

        self.assertTrue(result.message.strip())
        self.assertNotIn("Traceback", result.message)

    def test_다시_눌러도_같은_자리라고_말한다(self):
        _, result = self.send("http://localhost:9000/v.mp4")

        self.assertFalse(result.retryable, "설정을 고치기 전에는 같다")


# -- 닿을 수 있는 주소는 그대로 간다 ---------------------------------
class AReachableUrlGoesThroughTest(_Case):

    def test_공개_HTTPS_는_그대로_넘어간다(self):
        url = "https://media.example.com/videos/final_short.mp4"

        runtime, result = self.send(url)

        self.assertEqual(runtime.seen, [url])
        self.assertEqual(result.status, "Published")

    def test_저장소가_무엇이든_주소만_맞으면_된다(self):
        """
        S3 든 R2 든 다른 무엇이든, 이 계층은 공개 주소 하나만 본다 -
        저장소 이름을 알지 않는다.
        """

        for url in ("https://bucket.s3.amazonaws.com/v.mp4",
                    "https://pub-abc.r2.dev/v.mp4",
                    "https://cdn.mysite.co.kr/v.mp4"):
            with self.subTest(url=url):
                runtime, result = self.send(url)

                self.assertEqual(runtime.seen, [url])
                self.assertEqual(result.status, "Published")

    def test_파일_경로가_아니라_그_주소가_간다(self):
        url = "https://media.example.com/v.mp4"

        runtime, _ = self.send(url)

        self.assertNotIn(self.video, runtime.seen)


# -- 다른 플랫폼은 이 길을 지나지 않는다 -----------------------------
class TheOtherPlatformsAreUntouchedTest(unittest.TestCase):

    def test_공개_URL_이_필요_없는_쪽은_이_검사를_지나지_않는다(self):
        from app.services import real_tiktok_runtime, real_youtube_runtime

        for engine in (real_tiktok_runtime.RealTikTokRuntime,
                       real_youtube_runtime.RealYouTubeRuntime):
            with self.subTest(engine=engine.__name__):
                self.assertFalse(engine.capabilities.requires_public_url)

    def test_검사는_그_갈래_안에만_있다(self):
        """
        공유하는 파일이라 밖으로 새면 세 플랫폼이 함께 움직인다.
        """

        import re

        from app.services.publishing import runtime_backed_publish_adapter

        with open(runtime_backed_publish_adapter.__file__,
                  encoding="utf-8") as f:
            source = f.read()

        at = source.index("if caps.requires_public_url:")
        after = source.index("source = asset.public_url", at)

        block = source[at:after]

        self.assertIn("_refuse_unreachable", block)

        # 부르는 자리는 하나뿐이어야 한다. 정의(def)까지 세지 않는다 -
        # 그것도 같은 글자를 담고 있다.
        calls = [line for line in source.splitlines()
                 if "_refuse_unreachable(" in line
                 and not line.lstrip().startswith("def ")]

        self.assertEqual(len(calls), 1, calls)


if __name__ == "__main__":
    unittest.main()
