"""
Sprint260 - Instagram 정식 업로드 경로를 연다 (Release Gate).

무엇이 실제로 있었나
--------------------
Sprint101 이 이 플래그를 False 로 두면서 이유를 적어 두었다.

    "이 저장소에서 Instagram 실업로드는 아직 한 번도 검증되지 않았다."

그 문장이 이제 사실이 아니다. Sprint259 에서 실제로 올라갔다.

    Reel        https://www.instagram.com/reel/DcS1RrNCiCC/
    media id    18033618371832629
    영상        output/20260820_233933/video/final_short.mp4 (16,062,348 바이트)
    경로        R2 공개 URL -> /{ig-user-id}/media -> 상태 확인
                -> /{ig-user-id}/media_publish
    파이프라인   preparing · uploading_storage · preparing_platform
                · processing · publishing · completed  (전부 success)

mock 도 fake 도 없었다. 실제 자격증명, 실제 ig_user_id, 실제 R2 주소,
실제 Graph API 였다. 플래그 검사 한 줄만 건너뛰고 나머지 관문은
production 순서 그대로 밟았다.

그래서 여기서 여는 것
---------------------
Release Gate 가 요구한 증거가 생겼으므로 플래그를 True 로 올린다.
바뀌는 것은 그 한 줄뿐이다 - Runtime · Adapter · Storage · OAuth 는
이미 실제로 통과한 코드라 손대지 않는다.

여기서 재는 것
--------------
실제 게시는 하지 않는다. 플래그가 열렸다는 사실과, 열려도 뒤쪽
안전장치가 그대로라는 사실만 본다. Adapter 는 자리만 채운 가짜를
쓴다(_Adapter) - 네트워크로 나가지 않는다.
"""

import ast
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.services import instagram_upload_step_service as step


class TheFlagIsOpenTest(unittest.TestCase):
    """정본 Queue -> Worker 경로가 열려 있다."""

    def test_플래그가_켜져_있다(self):
        self.assertTrue(config.ENABLE_INSTAGRAM_UPLOAD)

    def test_소스에_적힌_값도_True_다(self):
        """
        실행 중에 누가 바꿔 놓은 것이 아니라 파일에 그렇게 적혀 있어야
        한다. 텍스트로 찾으면 주석에도 걸리므로 AST 로 읽는다.
        """

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tree = ast.parse(
            open(os.path.join(here, "app", "config.py"), encoding="utf-8").read())

        found = [
            node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
            and target.id == "ENABLE_INSTAGRAM_UPLOAD"
            and isinstance(node.value, ast.Constant)
        ]

        self.assertEqual(found, [True])

    def test_환경변수로_연_것이_아니다(self):
        """
        우회가 아니라 플래그 자체를 열었다. 환경변수를 지워도 True 다.
        """

        with patch.dict(os.environ, {}, clear=True):
            import importlib

            importlib.reload(config)

            try:
                self.assertTrue(config.ENABLE_INSTAGRAM_UPLOAD)
            finally:
                importlib.reload(config)


class TheGateStillHoldsTest(unittest.TestCase):
    """
    열었다고 해서 뒤쪽 관문까지 열린 것은 아니다.

    플래그가 첫 번째 관문일 뿐이고, 자격증명과 로그인 상태는 그대로
    지켜야 한다 - 특히 브라우저를 여는 login() 까지 가면 안 된다.
    """

    def test_꺼_두면_여전히_거절한다(self):
        """미래에 누가 다시 끄면 그때도 안전해야 한다."""

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "20260101_000001")
            os.makedirs(os.path.join(project, "video"))

            with patch.object(config, "ENABLE_INSTAGRAM_UPLOAD", False):
                result = step.run_instagram_upload_step(
                    "t", project, {"title": "t"})

        self.assertEqual(result["outcome"], "skipped")
        self.assertIn("ENABLE_INSTAGRAM_UPLOAD", result["error"])

    def test_자격증명_관문이_그대로다(self):
        """플래그가 켜져도 Meta 자격증명이 없으면 거기서 멈춘다."""

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "20260101_000001")
            os.makedirs(os.path.join(project, "video"))

            with patch.dict(os.environ, {"INSTAGRAM_OAUTH_CLIENT_ID": "",
                                         "INSTAGRAM_OAUTH_CLIENT_SECRET": ""}):
                result = step.run_instagram_upload_step(
                    "t", project, {"title": "t"})

        self.assertEqual(result["outcome"], "skipped")
        self.assertIn("INSTAGRAM_OAUTH_CLIENT_ID", result["error"])

    def test_판정_순서가_그대로다(self):
        """플래그 -> 자격증명 -> 로그인 상태. 소스가 그 순서다."""

        import inspect

        source = inspect.getsource(step.run_instagram_upload_step)

        flag = source.index("ENABLE_INSTAGRAM_UPLOAD")
        creds = source.index("_client_id()")
        health = source.index("_check_health()")

        self.assertLess(flag, creds)
        self.assertLess(creds, health)


class TheWorkerKnowsInstagramTest(unittest.TestCase):
    """정본 경로는 Queue -> Worker 다. 그 배선을 확인한다."""

    def test_worker_가_instagram_을_안다(self):
        from app.services import publish_worker

        self.assertIn("instagram", publish_worker.STEPS)

    def test_worker_가_부르는_것이_이_업로드_걸음이다(self):
        """
        이름만 아는 것으로는 모자란다 - 물었을 때 정말 이 함수를
        내주는지 본다(STEPS 는 부를 때 찾는 구조다).
        """

        from app.services import publish_worker

        self.assertIs(
            publish_worker.STEPS["instagram"],
            step.run_instagram_upload_step,
        )

    def test_화면이_instagram_을_안다(self):
        from app.services import social_accounts

        self.assertIn("instagram", social_accounts.PLATFORMS)


class TheOtherPlatformsAreUntouchedTest(unittest.TestCase):
    """
    이번에 연 것은 Instagram 하나다.

    Sprint243 이 이미지에서, Sprint244 가 음성에서 배운 것과 같다 -
    한 곳을 열 때 옆에 있는 문까지 같이 열리면 아무도 알아차리지
    못한다.
    """

    def test_youtube_플래그가_그대로다(self):
        self.assertTrue(config.ENABLE_YOUTUBE_UPLOAD)

    def test_tiktok_은_여전히_SELF_ONLY_다(self):
        from app.services import real_tiktok_runtime

        self.assertEqual(real_tiktok_runtime.DEFAULT_PRIVACY, "SELF_ONLY")

    def test_instagram_에는_공개범위_인자가_없다(self):
        """
        TikTok 의 privacy_level 을 Instagram 에 옮겨 붙이지 않았다 -
        Graph API 에 그런 인자가 없다.
        """

        import inspect

        from app.services import real_instagram_runtime

        source = inspect.getsource(real_instagram_runtime)

        self.assertNotIn("privacy_level", source)
        self.assertNotIn("SELF_ONLY", source)

    def test_instagram_은_여전히_공개_URL_이_필요하다(self):
        from app.services import real_instagram_runtime

        self.assertTrue(
            real_instagram_runtime.RealInstagramRuntime
            .capabilities.requires_public_url)


if __name__ == "__main__":
    unittest.main()
