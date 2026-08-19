"""
Sprint237 - 줄에 선 것을 집어 올린다 (Publish Automation, Phase 5).

Sprint235 가 줄을 만들었다. 세우기만 하고 아무도 집지 않았다 - 화면은
"줄에 세웠습니다. 올리는 것은 아직입니다" 라고 정직하게 적고 있었다.
이제 집는 쪽을 만든다.

무엇을 새로 만들지 않았는가
---------------------------
    올리는 법     각 플랫폼의 upload_step_service 그대로
    자격증명      social_accounts · OAuthManager 그대로
    줄            publish_queue 그대로
    결과 모양     success/outcome/upload_id/url/error - 두 스텝이 이미
                  같은 키를 쓴다(Instagram 쪽 주석이 그렇게 적어 두었다)

일꾼이 하는 일은 셋뿐이다 - 집고, 부르고, 적는다.

일꾼은 Adapter 를 모른다
------------------------
Sprint235 에서 라우터가 services.publishing 을 import 했다가 가드에
걸렸다. 그 경계는 "Adapter 를 쓰는 곳은 스텝 서비스뿐이고 Pipeline/
Queue/Workflow/UI 는 모른다" 이다.

일꾼도 모른다. 스텝 서비스를 부를 뿐이다 - 그래서 두 계층이 그대로
남고, 일꾼은 얇다.

집는 것이 곧 잠그는 것이다
--------------------------
next_pending 으로 보고 mark_uploading 으로 적으면 그 사이에 다른
일꾼이 같은 것을 볼 수 있다. 그래서 claim() 하나로 읽고-바꾸고-적는다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import publish_queue, publish_worker


def _uploaded(url="https://youtu.be/abc", upload_id="abc"):
    return {"success": True, "outcome": "uploaded", "upload_id": upload_id,
            "url": url, "error": None}


def _failed(error="망했다", retryable=False):
    return {"success": False, "outcome": "failed", "upload_id": None,
            "url": None, "error": error, "retryable": retryable}


class TheClaimIsTheLockTest(unittest.TestCase):
    """
    보고 나서 적으면 그 사이가 열려 있다. 한 번에 해야 한다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.store = os.path.join(self.root, "queue.json")

    def test_집으면_UPLOADING_이_된다(self):
        made = publish_queue.add(self.store, project_id="p1",
                                 platform="youtube")

        got = publish_queue.claim(self.store)

        self.assertEqual(got["id"], made["id"])
        self.assertEqual(got["state"], publish_queue.UPLOADING)

        # 파일에도 그렇게 적혀 있어야 한다 - 메모리에만 있으면
        # 다음 일꾼이 같은 것을 또 집는다.
        self.assertEqual(
            publish_queue.find(self.store, made["id"])["state"],
            publish_queue.UPLOADING)

    def test_두_번_집으면_두_번째는_없다(self):
        publish_queue.add(self.store, project_id="p1", platform="youtube")

        self.assertIsNotNone(publish_queue.claim(self.store))
        self.assertIsNone(publish_queue.claim(self.store))

    def test_빈_줄에서는_None(self):
        self.assertIsNone(publish_queue.claim(self.store))

    def test_집을_때마다_시도가_쌓인다(self):
        made = publish_queue.add(self.store, project_id="p1",
                                 platform="youtube")

        publish_queue.claim(self.store)

        self.assertEqual(
            publish_queue.find(self.store, made["id"])["attempts"], 1)


class TheWorkerPicksAndRecordsTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.store = os.path.join(self.root, "queue.json")
        self.project = os.path.join(self.root, "20260819_221009")
        os.makedirs(self.project, exist_ok=True)

        where = patch("app.services.project_service.resolve_project_path",
                      return_value=self.project)
        where.start()
        self.addCleanup(where.stop)

    def _queue(self, platform="youtube"):
        return publish_queue.add(self.store, project_id="20260819_221009",
                                 platform=platform)

    def _run(self, step, platform="youtube"):
        return publish_worker.run_once(
            self.store, steps={platform: step})

    # ── 집는다 ──────────────────────────────────────────────────────
    def test_기다리는_것이_없으면_아무것도_안_한다(self):
        step = MagicMock()

        self.assertIsNone(self._run(step))

        step.assert_not_called()

    def test_pending_을_집어_runtime_을_부른다(self):
        made = self._queue()
        step = MagicMock(return_value=_uploaded())

        found = self._run(step)

        step.assert_called_once()
        self.assertEqual(found["id"], made["id"])

    def test_부를_때_그_프로젝트_자리를_준다(self):
        self._queue()
        step = MagicMock(return_value=_uploaded())

        self._run(step)

        args, kwargs = step.call_args

        self.assertIn(self.project, list(args) + list(kwargs.values()))

    # ── 성공 ────────────────────────────────────────────────────────
    def test_성공하면_SUCCESS_와_주소를_적는다(self):
        made = self._queue()

        self._run(MagicMock(return_value=_uploaded(url="https://youtu.be/xyz")))

        row = publish_queue.find(self.store, made["id"])

        self.assertEqual(row["state"], publish_queue.SUCCESS)
        self.assertEqual(row["url"], "https://youtu.be/xyz")

    def test_주소가_없어도_성공은_성공이다(self):
        """
        TikTok 은 올린 것의 주소를 주지 않는다. 주소가 없다고 실패로
        적으면 사람은 올라간 영상을 다시 올린다.
        """

        made = self._queue(platform="tiktok")

        publish_worker.run_once(
            self.store,
            steps={"tiktok": MagicMock(
                return_value={"success": True, "outcome": "uploaded",
                              "upload_id": "pid", "url": None, "error": None})})

        row = publish_queue.find(self.store, made["id"])

        self.assertEqual(row["state"], publish_queue.SUCCESS)
        self.assertEqual(row["url"], "")

    # ── 실패 ────────────────────────────────────────────────────────
    def test_실패하면_FAILED_와_이유를_적는다(self):
        made = self._queue()

        self._run(MagicMock(return_value=_failed(error="토큰 없음")))

        row = publish_queue.find(self.store, made["id"])

        self.assertEqual(row["state"], publish_queue.FAILED)
        self.assertIn("토큰 없음", row["reason"])

    def test_다시_해_볼_만한_실패는_그렇게_적는다(self):
        made = self._queue()

        self._run(MagicMock(return_value=_failed(retryable=True)))

        row = publish_queue.find(self.store, made["id"])

        self.assertTrue(row["retryable"])

        # 그리고 실제로 다시 세울 수 있어야 한다.
        publish_queue.retry(self.store, made["id"])

        self.assertEqual(
            publish_queue.find(self.store, made["id"])["state"],
            publish_queue.PENDING)

    def test_다시_해도_소용없는_실패는_멈춘다(self):
        made = self._queue()

        self._run(MagicMock(return_value=_failed(retryable=False)))

        with self.assertRaises(ValueError):
            publish_queue.retry(self.store, made["id"])

    def test_스텝이_터져도_줄은_남는다(self):
        """
        예외가 그대로 올라가면 그 줄은 UPLOADING 인 채로 남는다 -
        아무도 집지 않는데 사람은 올라가는 중인 줄 안다.
        """

        made = self._queue()

        self._run(MagicMock(side_effect=RuntimeError("갑자기")))

        row = publish_queue.find(self.store, made["id"])

        self.assertEqual(row["state"], publish_queue.FAILED)
        self.assertIn("갑자기", row["reason"])
        self.assertTrue(row["retryable"], "무슨 일인지 모르면 다시 해 본다")

    def test_모르는_플랫폼은_멈춘다(self):
        made = publish_queue.add(self.store, project_id="20260819_221009",
                                 platform="tiktok")

        publish_worker.run_once(self.store, steps={})

        row = publish_queue.find(self.store, made["id"])

        self.assertEqual(row["state"], publish_queue.FAILED)
        self.assertFalse(row["retryable"], "다시 해도 그 플랫폼은 안 생긴다")

    def test_없는_프로젝트는_다시_시도하지_않는다(self):
        made = self._queue()

        with patch("app.services.project_service.resolve_project_path",
                   side_effect=ValueError("그런 프로젝트가 없습니다")):
            self._run(MagicMock())

        row = publish_queue.find(self.store, made["id"])

        self.assertEqual(row["state"], publish_queue.FAILED)
        self.assertFalse(row["retryable"])

    # ── 중복 방지 ───────────────────────────────────────────────────
    def test_올린_것을_다시_올리지_않는다(self):
        self._queue()

        step = MagicMock(return_value=_uploaded())

        self._run(step)
        self._run(step)

        step.assert_called_once()

    def test_올리는_중인_것을_또_집지_않는다(self):
        self._queue()

        publish_queue.claim(self.store)

        step = MagicMock()

        self._run(step)

        step.assert_not_called()

    def test_같은_영상_다른_플랫폼은_따로_올린다(self):
        self._queue(platform="youtube")
        self._queue(platform="tiktok")

        called = []

        steps = {
            "youtube": lambda *a, **k: (called.append("youtube"),
                                        _uploaded())[1],
            "tiktok": lambda *a, **k: (called.append("tiktok"),
                                       _uploaded(url=""))[1],
        }

        publish_worker.run_once(self.store, steps=steps)
        publish_worker.run_once(self.store, steps=steps)

        self.assertEqual(sorted(called), ["tiktok", "youtube"])

    # ── 여러 개 ─────────────────────────────────────────────────────
    def test_줄이_빌_때까지_돈다(self):
        for platform in ("youtube", "instagram", "tiktok"):
            self._queue(platform=platform)

        step = MagicMock(return_value=_uploaded())

        done = publish_worker.drain(
            self.store,
            steps={p: step for p in ("youtube", "instagram", "tiktok")})

        self.assertEqual(len(done), 3)
        self.assertEqual(step.call_count, 3)

        self.assertIsNone(publish_queue.next_pending(self.store))

    def test_한_번에_하나씩_집는다(self):
        self._queue(platform="youtube")
        self._queue(platform="tiktok")

        step = MagicMock(return_value=_uploaded())

        publish_worker.run_once(self.store,
                                steps={"youtube": step, "tiktok": step})

        self.assertEqual(step.call_count, 1)


class TheWorkerRecoversAfterARestartTest(unittest.TestCase):
    """
    올리던 중에 프로그램이 꺼지면 그 줄은 UPLOADING 인 채로 남는다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.store = os.path.join(self.root, "queue.json")

    def test_켤_때_끊긴_것을_다시_세운다(self):
        made = publish_queue.add(self.store, project_id="p1",
                                 platform="youtube")
        publish_queue.claim(self.store)          # 올리는 중에 꺼졌다

        woken = publish_worker.recover(self.store)

        self.assertEqual([row["id"] for row in woken], [made["id"]])
        self.assertEqual(
            publish_queue.find(self.store, made["id"])["state"],
            publish_queue.PENDING)

    def test_되살린_뒤에는_다시_집힌다(self):
        publish_queue.add(self.store, project_id="p1", platform="youtube")
        publish_queue.claim(self.store)

        publish_worker.recover(self.store)

        self.assertIsNotNone(publish_queue.claim(self.store))

    def test_끝난_것은_되살리지_않는다(self):
        made = publish_queue.add(self.store, project_id="p1",
                                 platform="youtube")
        publish_queue.claim(self.store)
        publish_queue.mark_success(self.store, made["id"], url="https://x/1")

        self.assertEqual(publish_worker.recover(self.store), [])


class TheWorkerStaysThinTest(unittest.TestCase):

    def _source(self) -> str:
        with open(publish_worker.__file__, encoding="utf-8") as f:
            return f.read()

    def _imports(self) -> str:
        return "\n".join(
            line for line in self._source().splitlines()
            if line.strip().startswith(("import ", "from ")))

    def test_Adapter_를_모른다(self):
        """
        Sprint235 의 경계 - Adapter 를 쓰는 곳은 스텝 서비스뿐이고
        Queue/Workflow/UI 는 모른다. 일꾼도 모른다.
        """

        self.assertNotIn("services.publishing", self._imports())

    def test_바깥을_직접_부르지_않는다(self):
        body = self._source()

        for outside in ("requests.", "graph.instagram", "tiktokapis",
                        "googleapis"):
            with self.subTest(outside=outside):
                self.assertNotIn(outside, body)

    def test_런타임을_직접_들이지_않는다(self):
        """올리는 법은 스텝 서비스가 안다."""

        self.assertNotIn("real_youtube_runtime", self._imports())
        self.assertNotIn("real_instagram_runtime", self._imports())

    def test_새_DB_를_만들지_않는다(self):
        self.assertNotIn("sqlite", self._source().lower())

    def test_세_플랫폼을_안다(self):
        self.assertEqual(sorted(publish_worker.STEPS),
                         ["instagram", "tiktok", "youtube"])


if __name__ == "__main__":
    unittest.main()
