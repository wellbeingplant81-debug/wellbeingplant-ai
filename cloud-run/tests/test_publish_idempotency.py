"""
Sprint238 - 같은 영상을 두 번 올리지 않는다 (Publish Automation, Phase 6).

무엇이 있었나
-------------
Sprint235 의 줄은 **줄 안에서만** 중복을 막았다. 아직 끝나지 않은 같은
(프로젝트, 플랫폼) 이 있으면 다시 세우지 않는다 - 거기까지다.

줄 바깥은 모른다. 실제로 이 PC 에 그런 것이 있었다.

    output/20260819_221009/youtube_upload_result.json
      {"success": true, "upload_id": "JpJ74dkxb9s"}   <- 손으로 올린 것

그 프로젝트를 지금 줄에 세우고 일꾼을 돌리면 같은 영상이 채널에 두 번
올라간다. 줄은 제 안의 SUCCESS 만 알기 때문이다.

무엇을 새로 만들지 않았는가
---------------------------
    결과 파일   각 스텝 서비스가 이미 남긴다(모양도 같다)
    업로드      스텝 서비스 그대로 - 한 줄도 건드리지 않는다
    줄          publish_queue 그대로

늘어난 것은 "이미 올렸는가" 를 묻는 자리 하나다.

다시 만든 영상은 다시 올릴 수 있어야 한다
-----------------------------------------
결과 파일은 그때 올린 것의 기록이다. 그 뒤에 영상을 다시 만들었다면
그것은 다른 영상이고, 올릴 수 있어야 한다. 결과 파일에 어떤 영상이었는지
적혀 있지 않으므로(스텝을 고치지 않기로 했다) **시각**으로 가른다 -
영상이 결과보다 나중이면 다시 만든 것이다.

두 겹으로 막는다
----------------
    줄에 세울 때   이미 올렸으면 세우지 않고 그때 주소를 돌려준다
    일꾼이 집을 때 한 번 더 본다 - 세운 뒤에 누가 올렸을 수도 있다

한 겹만 두면, 그 겹을 지나온 길이 하나라도 생기는 날 뚫린다.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import publish_history, publish_queue, publish_worker


class TheFileNamesMatchTheStepsTest(unittest.TestCase):
    """
    이름을 여기서 새로 짓지 않는다. 스텝 서비스가 적는 그 이름이다 -
    갈리면 영원히 "올린 적 없다" 가 된다.
    """

    def test_세_이름이_스텝이_적는_것과_같다(self):
        from app.services import (
            instagram_upload_step_service, studio_upload,
            tiktok_upload_step_service,
        )

        self.assertEqual(publish_history.RESULT_FILENAMES["youtube"],
                         studio_upload.RESULT_FILENAME)

        self.assertEqual(publish_history.RESULT_FILENAMES["instagram"],
                         instagram_upload_step_service.RESULT_FILENAME)

        self.assertEqual(publish_history.RESULT_FILENAMES["tiktok"],
                         tiktok_upload_step_service.RESULT_FILENAME)

    def test_줄이_아는_곳과_같은_곳을_안다(self):
        self.assertEqual(sorted(publish_history.RESULT_FILENAMES),
                         sorted(publish_queue.PLATFORMS))


class _WithProject(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.project = os.path.join(self.root, "20260819_221009")
        os.makedirs(os.path.join(self.project, "video"), exist_ok=True)

        self.video = os.path.join(self.project, "video", "final_short.mp4")

        with open(self.video, "wb") as f:
            f.write(b"mp4")

    def _result(self, platform, payload, newer_than_video=True):
        where = os.path.join(
            self.project, publish_history.RESULT_FILENAMES[platform])

        with open(where, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

        if newer_than_video:
            # 올린 뒤에 영상을 다시 만들지 않았다는 뜻.
            stamp = os.path.getmtime(self.video) + 10
            os.utime(where, (stamp, stamp))

        return where

    def _succeeded(self, platform="youtube", url="https://youtu.be/JpJ74dkxb9s"):
        return self._result(platform, {
            "success": True, "outcome": "uploaded",
            "upload_id": "JpJ74dkxb9s", "url": url, "error": None})


class TheHistoryAnswersTruthfullyTest(_WithProject):

    def test_기록이_없으면_올린_적_없다(self):
        self.assertIsNone(
            publish_history.already_published(self.project, "youtube"))

    def test_성공_기록이_있으면_그것을_돌려준다(self):
        self._succeeded()

        found = publish_history.already_published(self.project, "youtube")

        self.assertIsNotNone(found)
        self.assertEqual(found["url"], "https://youtu.be/JpJ74dkxb9s")
        self.assertEqual(found["upload_id"], "JpJ74dkxb9s")

    def test_실패_기록은_올린_것이_아니다(self):
        """실패했으면 다시 해 볼 수 있어야 한다."""

        self._result("youtube", {"success": False, "outcome": "failed",
                                 "error": "토큰 없음"})

        self.assertIsNone(
            publish_history.already_published(self.project, "youtube"))

    def test_건너뛴_기록도_올린_것이_아니다(self):
        self._result("instagram", {"success": False, "outcome": "skipped",
                                   "error": "Meta 앱이 없습니다"})

        self.assertIsNone(
            publish_history.already_published(self.project, "instagram"))

    def test_플랫폼마다_따로_본다(self):
        self._succeeded("youtube")

        self.assertIsNotNone(
            publish_history.already_published(self.project, "youtube"))

        self.assertIsNone(
            publish_history.already_published(self.project, "tiktok"))

    def test_주소가_없어도_올린_것은_올린_것이다(self):
        """TikTok 은 주소를 주지 않는다."""

        self._result("tiktok", {"success": True, "outcome": "uploaded",
                                "upload_id": "pid-1", "url": None})

        found = publish_history.already_published(self.project, "tiktok")

        self.assertIsNotNone(found)
        self.assertEqual(found.get("url"), None)

    def test_망가진_기록은_없는_것으로_읽는다(self):
        where = os.path.join(
            self.project, publish_history.RESULT_FILENAMES["youtube"])

        with open(where, "w", encoding="utf-8") as f:
            f.write("{망가진")

        self.assertIsNone(
            publish_history.already_published(self.project, "youtube"))

    def test_모르는_플랫폼은_없는_것으로_읽는다(self):
        self.assertIsNone(
            publish_history.already_published(self.project, "facebook"))

    def test_없는_프로젝트도_던지지_않는다(self):
        self.assertIsNone(
            publish_history.already_published(
                os.path.join(self.root, "없는곳"), "youtube"))

    def test_다시_만든_영상은_다시_올릴_수_있다(self):
        """
        결과 파일은 그때 올린 것의 기록이다. 그 뒤에 영상을 다시
        만들었다면 다른 영상이고, 막으면 사람은 고친 영상을 영영 못
        올린다.
        """

        self._succeeded()

        # 영상을 다시 만든다 - 결과보다 나중이 된다.
        stamp = time.time() + 100
        os.utime(self.video, (stamp, stamp))

        self.assertIsNone(
            publish_history.already_published(self.project, "youtube"))

    def test_영상이_없으면_기록을_믿는다(self):
        """
        영상이 지워졌다고 "안 올렸다" 가 되면 안 된다 - 올린 것은
        이미 채널에 있다.
        """

        self._succeeded()
        os.remove(self.video)

        self.assertIsNotNone(
            publish_history.already_published(self.project, "youtube"))


class TheQueueRefusesWhatIsAlreadyUpTest(_WithProject):
    """첫째 겹 - 줄에 세울 때."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)
        self.store = os.path.join(self.root, "queue.json")

        for target, value in (
            ("app.services.publish_queue.default_store_path", self.store),
            ("app.routers.studio._project_path", self.project),
        ):
            patched = patch(target, return_value=value)
            patched.start()
            self.addCleanup(patched.stop)

    def _post(self, platform="youtube"):
        return self.client.post(
            "/studio/api/publish/queue",
            json={"project_id": "20260819_221009", "platform": platform})

    def test_기록이_없으면_평소대로_선다(self):
        r = self._post()

        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["state"], "PENDING")

    def test_이미_올렸으면_세우지_않는다(self):
        self._succeeded()

        r = self._post()

        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["state"], publish_queue.SUCCESS)

        # 줄에는 아무것도 생기지 않는다.
        self.assertEqual(publish_queue.every(self.store), [])

    def test_이미_올렸으면_그때_주소를_준다(self):
        self._succeeded(url="https://youtu.be/JpJ74dkxb9s")

        self.assertEqual(self._post().json()["url"],
                         "https://youtu.be/JpJ74dkxb9s")

    def test_다른_플랫폼은_막지_않는다(self):
        self._succeeded("youtube")

        r = self._post("tiktok")

        self.assertEqual(r.json()["state"], "PENDING")
        self.assertEqual(len(publish_queue.every(self.store)), 1)

    def test_실패한_것은_다시_설_수_있다(self):
        self._result("youtube", {"success": False, "outcome": "failed",
                                 "error": "일시적"})

        self.assertEqual(self._post().json()["state"], "PENDING")


class TheWorkerLooksAgainTest(_WithProject):
    """
    둘째 겹 - 집은 뒤에 한 번 더. 줄에 세운 다음 누가 손으로 올렸을
    수도 있고, 그 사이는 얼마든지 길 수 있다.
    """

    def setUp(self):
        super().setUp()

        self.store = os.path.join(self.root, "queue.json")

        patched = patch(
            "app.services.project_service.resolve_project_path",
            return_value=self.project)
        patched.start()
        self.addCleanup(patched.stop)

    def _queue(self, platform="youtube"):
        return publish_queue.add(self.store, project_id="20260819_221009",
                                 platform=platform)

    def test_세운_뒤에_올라갔으면_올리지_않는다(self):
        made = self._queue()

        # 줄에 선 뒤에 누가 손으로 올렸다.
        self._succeeded()

        step = MagicMock()

        publish_worker.run_once(self.store, steps={"youtube": step})

        step.assert_not_called()

        row = publish_queue.find(self.store, made["id"])

        self.assertEqual(row["state"], publish_queue.SUCCESS)
        self.assertEqual(row["url"], "https://youtu.be/JpJ74dkxb9s")

    def test_기록이_없으면_평소대로_올린다(self):
        self._queue()

        step = MagicMock(return_value={
            "success": True, "outcome": "uploaded",
            "upload_id": "x", "url": "https://youtu.be/x", "error": None})

        publish_worker.run_once(self.store, steps={"youtube": step})

        step.assert_called_once()

    def test_실패_기록은_막지_않는다(self):
        self._queue()
        self._result("youtube", {"success": False, "outcome": "failed",
                                 "error": "일시적"})

        step = MagicMock(return_value={"success": True, "url": "https://x/1"})

        publish_worker.run_once(self.store, steps={"youtube": step})

        step.assert_called_once()


class TheUploadCodeIsUntouchedTest(unittest.TestCase):
    """Sprint238 의 4번 - 실제 업로드 코드는 변경하지 않는다."""

    def test_스텝과_런타임과_provider_를_건드리지_않았다(self):
        import subprocess

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=os.path.dirname(root))

        if out.returncode != 0:
            self.skipTest("git 을 쓸 수 없다")

        touched = {line.strip() for line in out.stdout.splitlines()
                   if line.strip()}

        forbidden = {
            "cloud-run/app/services/youtube_upload_step_service.py",
            "cloud-run/app/services/instagram_upload_step_service.py",
            "cloud-run/app/services/tiktok_upload_step_service.py",
            "cloud-run/app/services/real_youtube_runtime.py",
            "cloud-run/app/services/real_instagram_runtime.py",
            "cloud-run/app/services/real_tiktok_runtime.py",
            "cloud-run/app/providers/upload/youtube_upload_provider.py",
        }

        self.assertEqual(touched & forbidden, set(), touched & forbidden)


if __name__ == "__main__":
    unittest.main()
