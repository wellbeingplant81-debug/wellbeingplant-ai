"""
Sprint235 - Instagram 은 파일을 받지 않는다 (Publish Automation, Phase 3).

무엇이 문제였나
---------------
실제 영상 1편을 만들고 나서 올리려 보니, Instagram Graph API 는
파일 업로드를 받지 않는다.

    POST graph.instagram.com/{ig_user_id}/media
        media_type · **video_url** · caption · access_token

video_url 은 **인터넷에서 닿을 수 있는 주소**여야 한다. 데스크톱
프로그램이 만든 C:\\...\\video\\final_short.mp4 를 그대로 줄 수 없다 -
Meta 서버가 그 경로를 열 수 없다.

TikTok 과 갈리는 자리다
-----------------------
    TikTok     FILE_UPLOAD - 로컬 파일을 그대로 밀어 넣는다. 저장소 불필요
    Instagram  공개 URL 필수 - 어딘가에 먼저 올려 두어야 한다

이 차이는 이미 RuntimeCapabilities.requires_public_url 로 적혀 있고,
Adapter 가 그것을 보고 AssetPublisher 를 부른다. 그러니 새로 만들
것은 없다 - **정말 이어지는지**를 이 시험이 잰다.

왜 이 시험이 필요한가
---------------------
조각은 다 있었는데 아무도 끝까지 이어 보지 않았다. requires_public_url
이 True 인 것도, AssetPublisher 가 public_url 을 만드는 것도 각자
시험이 있다. 그런데 "그래서 Instagram 이 받는 video_url 이 정말 그
공개 주소인가"를 재는 자리가 없었다. 그 사이가 끊겨 있으면 실제로
올리는 날에야 안다.

바깥을 부르지 않는다
--------------------
MockStorageProvider 로 공개 주소를 만들고, Instagram 쪽은 requests 를
가로채 무엇을 받았는지만 본다. 실제 S3 와 실제 Meta 는 각각 열쇠가
생긴 뒤의 일이다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.storage.mock_storage_provider import MockStorageProvider
from app.providers.storage.storage_asset_publisher import StorageAssetPublisher
from app.providers.upload.instagram_credential import InstagramCredential
from app.services import real_instagram_runtime, real_tiktok_runtime
from app.services.publishing.publishing_plan_model import PublishingPlan
from app.services.publishing.runtime_backed_publish_adapter import (
    RuntimeBackedPublishAdapter, resolve_video_path,
)


def _response(status=200, payload=None):
    made = MagicMock()
    made.status_code = status
    made.json.return_value = payload or {}
    made.text = json.dumps(payload or {}, ensure_ascii=False)
    made.headers = {}

    return made


class TheTwoPlatformsWantDifferentThingsTest(unittest.TestCase):
    """
    이 차이를 코드가 알고 있어야 한다. 모르면 한쪽 방식으로 둘 다
    보내다가 한쪽이 조용히 실패한다.
    """

    def test_인스타는_공개_주소가_필요하다(self):
        self.assertTrue(
            real_instagram_runtime.RealInstagramRuntime
            .capabilities.requires_public_url)

    def test_틱톡은_필요_없다(self):
        self.assertFalse(
            real_tiktok_runtime.RealTikTokRuntime
            .capabilities.requires_public_url)


class TheLocalFileBecomesAPublicUrlTest(unittest.TestCase):
    """
    만든 영상 -> 저장소 -> 공개 주소 -> Instagram. 그 사슬이 정말
    이어지는지 끝까지 따라간다.
    """

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        # 실제 산출물과 같은 자리에 같은 이름으로 둔다.
        video = resolve_video_path(self.project)
        os.makedirs(os.path.dirname(video), exist_ok=True)

        with open(video, "wb") as f:
            f.write(b"mp4" * 100)

        self.video = video

        with open(os.path.join(self.project, "thumbnail.png"), "wb") as f:
            f.write(b"png")

        self.storage = MockStorageProvider()
        self.publisher = StorageAssetPublisher(self.storage)

        self.runtime = real_instagram_runtime.RealInstagramRuntime(
            client_id="cid", client_secret="csecret")

        self.credential = InstagramCredential(
            account_id="default", access_token="tok",
            obtained_at=datetime.now(timezone.utc) - timedelta(days=2),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            ig_user_id="ig-1")

        self.plan = PublishingPlan(
            job_id="j1", platform="instagram",
            title="아침 물 한 잔이 하루를 바꾸는 이유",
            description="아침 공복에 마시는 물 한 잔에 대한 이야기입니다.",
            hashtags=["하루", "공복"],
            output_folder=self.project)

    def _adapter(self):
        return RuntimeBackedPublishAdapter(
            platform="instagram", runtime=self.runtime,
            asset_publisher=self.publisher)

    def test_저장소가_공개_주소를_만든다(self):
        made = self.publisher.publish(self.video)

        self.assertTrue(made.public_url, "공개 주소가 없다")
        self.assertTrue(made.public_url.startswith("http"), made.public_url)

    def test_인스타가_받는_주소가_그_공개_주소다(self):
        """
        이 시험이 이 파일의 중심이다. 로컬 경로가 그대로 흘러가면
        Meta 는 그것을 열 수 없고, 우리는 실제로 올리는 날에야 안다.
        """

        posted = []

        def post(url, **kwargs):
            posted.append((url, kwargs))

            if url.endswith("/media"):
                return _response(200, {"id": "container-1"})

            return _response(200, {"id": "media-1"})

        with patch.object(real_instagram_runtime.requests, "post",
                          side_effect=post), \
                patch.object(real_instagram_runtime.requests, "get",
                             return_value=_response(200, {
                                 "status_code": "FINISHED",
                                 "permalink": "https://instagram.com/p/x"})), \
                patch.object(self.runtime, "login",
                             return_value=self.credential):
            result = self._adapter().submit(self.plan)

        self.assertEqual(result.status, "Published", result.message)

        container = next(kwargs for url, kwargs in posted
                         if url.endswith("/media"))

        sent = container["data"]["video_url"]

        self.assertTrue(sent.startswith("http"),
                        f"로컬 경로가 그대로 갔다: {sent}")

        self.assertNotEqual(sent, self.video)

        # 저장소가 실제로 그 파일을 받았는가.
        self.assertTrue(self.storage._uploaded,
                        "저장소를 거치지 않고 주소만 지어냈다")

    def test_제목과_해시태그가_함께_간다(self):
        posted = []

        with patch.object(real_instagram_runtime.requests, "post",
                          side_effect=lambda url, **kw: (
                              posted.append((url, kw)),
                              _response(200, {"id": "x"}))[1]), \
                patch.object(real_instagram_runtime.requests, "get",
                             return_value=_response(200, {
                                 "status_code": "FINISHED"})), \
                patch.object(self.runtime, "login",
                             return_value=self.credential):
            self._adapter().submit(self.plan)

        caption = next(kw for url, kw in posted
                       if url.endswith("/media"))["data"]["caption"]

        self.assertIn("아침 공복", caption)
        self.assertIn("#하루", caption)

    def test_저장소가_없으면_올리지_않고_말해_준다(self):
        """
        저장소 없이 Instagram 을 고르면 아무것도 못 올린다. 그것을
        미리 말해야 사람이 무엇을 갖춰야 하는지 안다.
        """

        adapter = RuntimeBackedPublishAdapter(
            platform="instagram", runtime=self.runtime, asset_publisher=None)

        result = adapter.submit(self.plan)

        self.assertEqual(result.status, "Failed")
        self.assertFalse(result.retryable, "저장소는 다시 눌러도 안 생긴다")

    def test_영상이_없으면_바로_멈춘다(self):
        os.remove(self.video)

        result = self._adapter().submit(self.plan)

        self.assertEqual(result.status, "Failed")
        self.assertFalse(result.retryable,
                         "다시 시도해도 파일이 다시 생기지 않는다")

    def test_저장소가_주소를_못_주면_올리지_않는다(self):
        """
        주소 없이 Instagram 을 부르면 Meta 가 거절하고, 그 이유는
        우리 쪽 문제인데 저쪽 말로 온다.
        """

        blind = MockStorageProvider(public_url_template="")

        adapter = RuntimeBackedPublishAdapter(
            platform="instagram", runtime=self.runtime,
            asset_publisher=StorageAssetPublisher(blind))

        with patch.object(self.runtime, "login", return_value=self.credential):
            result = adapter.submit(self.plan)

        self.assertEqual(result.status, "Failed")


class TheTikTokPathNeedsNoStorageTest(unittest.TestCase):
    """
    같은 Adapter 인데 TikTok 은 저장소 없이 지나가야 한다. 여기서
    막히면 저장소가 없는 사람은 아무 데도 못 올린다.
    """

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        video = resolve_video_path(self.project)
        os.makedirs(os.path.dirname(video), exist_ok=True)

        with open(video, "wb") as f:
            f.write(b"mp4" * 100)

        self.video = video

        self.plan = PublishingPlan(
            job_id="j2", platform="tiktok", title="제목",
            description="설명", hashtags=["건강"],
            output_folder=self.project)

    def test_로컬_경로가_그대로_간다(self):
        runtime = real_tiktok_runtime.RealTikTokRuntime(
            client_key="k", client_secret="s")

        from app.providers.upload.oauth_credential import OAuthCredential

        credential = OAuthCredential(
            account_id="default", access_token="tok", refresh_token="r",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

        posted = []

        def post(url, **kwargs):
            posted.append((url, kwargs))

            if url == real_tiktok_runtime.INIT_URL:
                return _response(200, {"data": {
                    "publish_id": "pid", "upload_url": "https://up/1"}})

            return _response(200, {"data": {"status": "PUBLISH_COMPLETE"}})

        adapter = RuntimeBackedPublishAdapter(
            platform="tiktok", runtime=runtime, asset_publisher=None)

        with patch.object(real_tiktok_runtime.requests, "post",
                          side_effect=post), \
                patch.object(real_tiktok_runtime.requests, "put",
                             return_value=_response(201)), \
                patch.object(runtime, "login", return_value=credential):
            result = adapter.submit(self.plan)

        self.assertEqual(result.status, "Published", result.message)

        started = next(kw for url, kw in posted
                       if url == real_tiktok_runtime.INIT_URL)

        # 로컬 파일 크기를 그대로 알렸다는 것은, 그 파일을 직접
        # 읽었다는 뜻이다 - 저장소를 거치지 않았다.
        self.assertEqual(started["json"]["source_info"]["video_size"],
                         os.path.getsize(self.video))


if __name__ == "__main__":
    unittest.main()
