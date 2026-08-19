"""
Sprint235 - 누르면 줄에 선다. 올라가지는 않는다 (Publish Automation, Phase 4).

왜 이 시험이 있는가
-------------------
단추 하나가 두 가지를 뜻할 수 있다.

    "줄에 세웠다"      맞는 말
    "올렸다"           아직 거짓말

올리는 일꾼이 아직 없다. 그런데 화면이 "올렸습니다"라고 적으면 사람은
Instagram 을 열어 보고 없는 것을 확인한 다음, 프로그램이 고장났다고
생각한다. 그래서 지금 할 수 있는 말만 하도록 못 박는다.

무엇을 새로 만들지 않았는가
---------------------------
    계정 상태   social_accounts · #socialBox 그대로
    줄          publish_queue (Phase 1)
    영상 자리    resolve_video_path - MEDIA_KINDS 가 정한 그것
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _page() -> str:
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _markup() -> str:
    page = re.sub(r"(?m)^[ \t]*//.*$", "", _page())

    return re.sub(r"/\*.*?\*/", "", page, flags=re.S)


class TheButtonSaysOnlyWhatIsTrueTest(unittest.TestCase):

    def _block(self) -> str:
        page = _markup()
        at = page.index("async function queueUpload(")

        return page[at:at + 1400]

    def test_연결된_곳에만_단추가_붙는다(self):
        """
        연결도 안 된 곳에 올리기 단추를 내놓으면, 눌러도 안 되는
        단추가 된다 - 이 화면이 이미 지켜 온 규칙이다.
        """

        page = _markup()
        at = page.index("function socialRow(a){")
        block = page[at:at + 1800]

        button = block.index("queueUpload")
        connected = block.index("a.connected")

        self.assertLess(connected, button,
                        "연결 여부를 보기 전에 단추를 내놓는다")

    def test_올렸다고_말하지_않는다(self):
        block = self._block()

        for lie in ("올렸습니다", "업로드 완료", "게시했습니다"):
            self.assertNotIn(lie, block, lie)

    def test_줄에_섰다고_말한다(self):
        block = self._block()

        self.assertIn("줄에 세웠습니다", block)

    def test_여기서_올리지_않는다(self):
        """
        화면이 직접 플랫폼을 부르기 시작하면 같은 일을 두 곳이 한다.
        """

        block = self._block()

        for outside in ("graph.instagram", "tiktokapis", "googleapis"):
            self.assertNotIn(outside, block, outside)

    def test_영상이_없으면_먼저_말한다(self):
        block = self._block()

        self.assertIn("currentProject", block)
        self.assertIn("먼저 영상을", block)

    def test_새_고르기_화면을_만들지_않는다(self):
        """지금 열어 둔 프로젝트를 쓴다 - 이미 화면이 들고 있다."""

        block = self._block()

        self.assertIn("project_id: currentProject", block)


class TheEndpointQueuesAndNothingMoreTest(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

        self.store = os.path.join(tempfile.mkdtemp(), "publish_queue.json")
        self.addCleanup(shutil.rmtree, os.path.dirname(self.store),
                        ignore_errors=True)

        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        patched = patch("app.services.publish_queue.default_store_path",
                        return_value=self.store)
        patched.start()
        self.addCleanup(patched.stop)

        where = patch("app.routers.studio._project_path",
                      return_value=self.project)
        where.start()
        self.addCleanup(where.stop)

    def _make_video(self):
        from app.services.publishing.runtime_backed_publish_adapter import (
            resolve_video_path,
        )

        video = resolve_video_path(self.project)
        os.makedirs(os.path.dirname(video), exist_ok=True)

        with open(video, "wb") as f:
            f.write(b"mp4")

    def test_영상이_있으면_줄에_선다(self):
        self._make_video()

        r = self.client.post("/studio/api/publish/queue",
                             json={"project_id": "p1", "platform": "tiktok"})

        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["state"], "PENDING")

    def test_영상이_없으면_세우지_않는다(self):
        r = self.client.post("/studio/api/publish/queue",
                             json={"project_id": "p1", "platform": "tiktok"})

        self.assertEqual(r.status_code, 400)
        self.assertIn("영상", r.json()["detail"])

    def test_모르는_곳은_받지_않는다(self):
        self._make_video()

        r = self.client.post("/studio/api/publish/queue",
                             json={"project_id": "p1", "platform": "facebook"})

        self.assertEqual(r.status_code, 400)

    def test_줄을_볼_수_있다(self):
        self._make_video()

        self.client.post("/studio/api/publish/queue",
                         json={"project_id": "p1", "platform": "youtube"})

        r = self.client.get("/studio/api/publish/queue")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["items"]), 1)

    def test_두_번_눌러도_한_줄이다(self):
        self._make_video()

        for _ in range(2):
            self.client.post("/studio/api/publish/queue",
                             json={"project_id": "p1", "platform": "youtube"})

        self.assertEqual(
            len(self.client.get("/studio/api/publish/queue").json()["items"]),
            1)

    def test_줄에_세우는_동안_아무_데도_부르지_않는다(self):
        """올리는 일은 아직 아무도 하지 않는다."""

        self._make_video()

        import requests

        with patch.object(requests, "post") as called:
            self.client.post("/studio/api/publish/queue",
                             json={"project_id": "p1", "platform": "instagram"})

        called.assert_not_called()


if __name__ == "__main__":
    unittest.main()
