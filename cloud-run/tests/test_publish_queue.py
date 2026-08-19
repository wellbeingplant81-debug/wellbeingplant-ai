"""
Sprint235 - 올릴 것을 줄 세운다 (Publish Automation, Phase 1).

무엇이 있었나
-------------
영상은 만들어지는데 올리는 자리가 없었다. YouTube 는 파이프라인이
곧바로 부르고(studio_upload), Instagram 은 스텝이 있는데 부르는 곳이
없다. 셋 다 "언제 무엇을 어디에 올릴 것인가"를 아무도 들고 있지
않았다.

DB 를 만들지 않는다
-------------------
이 프로그램에는 DB 가 하나도 없다. 결정 하나를 적는 자리는 이미
정해져 있다 - %APPDATA%\\AI영상제작소\\ 아래의 json 한 장이고,
free_workspace · studio_upload 가 그렇게 산다. 줄 세우기 하나 때문에
SQLite 를 들이면 이 집에 없던 것이 생긴다.

무엇을 새로 만들지 않았는가
---------------------------
    자격증명   social_accounts · FileTokenStore 그대로
    올리는 일  PublishingRuntimeProtocol 구현체들 그대로
    메타데이터 publish_package.json 그대로
    공개 URL   AssetPublisher 그대로

이 파일이 만드는 것은 **줄** 하나뿐이다. 올리지 않는다 - 무엇을 올릴
차례인지만 안다.

왜 이 시험이 이렇게 생겼나
--------------------------
줄은 껐다 켜도 남아야 한다. 그래서 "넣고 읽는다"가 아니라 "넣고,
껐다 켜고, 읽는다"를 잰다 - 메모리에만 있는 줄은 컴퓨터를 끄는
순간 사라지고, 사람은 올린 줄 알았던 영상이 올라가지 않은 것을
나중에 안다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import publish_queue


class TheStoreLivesBesideTheOtherDecisionsTest(unittest.TestCase):
    """줄이 사는 자리는 사람 것이 사는 그 자리다."""

    def test_사람_자리_아래에_있다(self):
        from app import runtime_paths

        where = publish_queue.default_store_path()

        self.assertTrue(
            os.path.normcase(where).startswith(
                os.path.normcase(runtime_paths.home())),
            where)

        self.assertTrue(where.endswith(".json"), where)

    def test_새_DB_를_만들지_않는다(self):
        source = publish_queue.__file__

        with open(source, encoding="utf-8") as f:
            body = "\n".join(
                line for line in f.read().splitlines()
                if not line.lstrip().startswith("#"))

        for forbidden in ("sqlite3", "import sqlite", "CREATE TABLE"):
            self.assertNotIn(forbidden, body, forbidden)


class TheQueueRemembersTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.store = os.path.join(self.root, "publish_queue.json")

    def add(self, project="20260819_221009", platform="youtube", **rest):
        return publish_queue.add(self.store, project_id=project,
                                 platform=platform, **rest)

    # ── 추가 ────────────────────────────────────────────────────────
    def test_넣으면_PENDING_으로_들어간다(self):
        made = self.add()

        self.assertEqual(made["state"], publish_queue.PENDING)
        self.assertTrue(made["id"])
        self.assertEqual(made["project_id"], "20260819_221009")
        self.assertEqual(made["platform"], "youtube")

    def test_모르는_플랫폼은_받지_않는다(self):
        """
        받아 두면 나중에 조용히 아무 데도 안 올라간다. 사람은 줄에
        있는 것을 보고 올라갔다고 믿는다.
        """

        with self.assertRaises(ValueError):
            self.add(platform="facebook")

    def test_프로젝트_없이는_받지_않는다(self):
        with self.assertRaises(ValueError):
            self.add(project="  ")

    def test_같은_것을_두_번_넣지_않는다(self):
        """
        같은 영상을 같은 곳에 두 번 올리는 일이 실수로 일어나면 안
        된다. 아직 끝나지 않은 같은 줄이 있으면 그것을 돌려준다.
        """

        first = self.add()
        again = self.add()

        self.assertEqual(first["id"], again["id"])
        self.assertEqual(len(publish_queue.every(self.store)), 1)

    def test_다른_플랫폼은_따로_선다(self):
        self.add(platform="youtube")
        self.add(platform="instagram")

        self.assertEqual(len(publish_queue.every(self.store)), 2)

    def test_끝난_것과_같은_것은_다시_설_수_있다(self):
        """한 번 올렸다고 영영 못 올리는 것은 아니다."""

        first = self.add()
        publish_queue.mark_success(self.store, first["id"], url="https://x/1")

        again = self.add()

        self.assertNotEqual(first["id"], again["id"])
        self.assertEqual(len(publish_queue.every(self.store)), 2)

    # ── 조회 ────────────────────────────────────────────────────────
    def test_빈_줄은_빈_목록이다(self):
        self.assertEqual(publish_queue.every(self.store), [])

    def test_넣은_순서대로_선다(self):
        self.add(platform="youtube")
        self.add(platform="instagram")
        self.add(platform="tiktok")

        order = [row["platform"] for row in publish_queue.every(self.store)]

        self.assertEqual(order, ["youtube", "instagram", "tiktok"])

    def test_다음_차례는_가장_먼저_기다린_것이다(self):
        first = self.add(platform="youtube")
        self.add(platform="instagram")

        self.assertEqual(publish_queue.next_pending(self.store)["id"],
                         first["id"])

    def test_기다리는_것이_없으면_None(self):
        made = self.add()
        publish_queue.mark_success(self.store, made["id"], url="https://x/1")

        self.assertIsNone(publish_queue.next_pending(self.store))

    def test_올리는_중인_것은_다음_차례가_아니다(self):
        """두 일꾼이 같은 것을 집어 두 번 올리면 안 된다."""

        made = self.add()
        publish_queue.mark_uploading(self.store, made["id"])

        self.assertIsNone(publish_queue.next_pending(self.store))

    # ── 상태 변경 ───────────────────────────────────────────────────
    def test_네_가지_말고는_없다(self):
        self.assertEqual(
            publish_queue.STATES,
            (publish_queue.PENDING, publish_queue.UPLOADING,
             publish_queue.SUCCESS, publish_queue.FAILED))

    def test_올리는_중으로_바뀐다(self):
        made = self.add()

        found = publish_queue.mark_uploading(self.store, made["id"])

        self.assertEqual(found["state"], publish_queue.UPLOADING)
        self.assertTrue(found["started_at"])

    def test_끝나면_주소를_들고_있는다(self):
        made = self.add()
        publish_queue.mark_uploading(self.store, made["id"])

        found = publish_queue.mark_success(
            self.store, made["id"], url="https://youtu.be/abc")

        self.assertEqual(found["state"], publish_queue.SUCCESS)
        self.assertEqual(found["url"], "https://youtu.be/abc")
        self.assertTrue(found["finished_at"])

    def test_없는_것을_바꾸려_하면_말해_준다(self):
        with self.assertRaises(KeyError):
            publish_queue.mark_success(self.store, "없는줄", url="x")

    def test_끝난_것을_되돌리지_않는다(self):
        """
        올라간 것을 다시 PENDING 으로 만들면 같은 영상이 두 번 올라간다.
        """

        made = self.add()
        publish_queue.mark_success(self.store, made["id"], url="https://x/1")

        with self.assertRaises(ValueError):
            publish_queue.mark_uploading(self.store, made["id"])

    # ── 실패 기록 ───────────────────────────────────────────────────
    def test_실패는_이유를_남긴다(self):
        """
        "실패"만 적으면 사람은 무엇을 고쳐야 할지 모른다. 다시 눌러도
        같은 자리에서 같은 이유로 죽는다.
        """

        made = self.add()
        publish_queue.mark_uploading(self.store, made["id"])

        found = publish_queue.mark_failed(
            self.store, made["id"],
            reason="Instagram 컨테이너 생성 실패 (400)",
            retryable=True)

        self.assertEqual(found["state"], publish_queue.FAILED)
        self.assertIn("컨테이너", found["reason"])
        self.assertTrue(found["retryable"])
        self.assertEqual(found["attempts"], 1)

    def test_다시_해_볼_수_있는_실패는_다시_설_수_있다(self):
        made = self.add()
        publish_queue.mark_uploading(self.store, made["id"])
        publish_queue.mark_failed(self.store, made["id"],
                                  reason="일시적", retryable=True)

        found = publish_queue.retry(self.store, made["id"])

        self.assertEqual(found["state"], publish_queue.PENDING)
        self.assertEqual(found["attempts"], 1, "시도 횟수는 지워지지 않는다")

    def test_다시_해도_소용없는_실패는_다시_세우지_않는다(self):
        """
        토큰이 없어서 죽은 것을 다시 세우면 또 죽는다. 사람이 바깥에서
        할 일이 있다는 뜻이고, 그것은 줄이 해결할 수 없다.
        """

        made = self.add()
        publish_queue.mark_uploading(self.store, made["id"])
        publish_queue.mark_failed(self.store, made["id"],
                                  reason="토큰 없음", retryable=False)

        with self.assertRaises(ValueError):
            publish_queue.retry(self.store, made["id"])

    def test_시도할수록_쌓인다(self):
        made = self.add()

        for _ in range(3):
            publish_queue.mark_uploading(self.store, made["id"])
            publish_queue.mark_failed(self.store, made["id"],
                                      reason="또", retryable=True)
            publish_queue.retry(self.store, made["id"])

        self.assertEqual(
            publish_queue.find(self.store, made["id"])["attempts"], 3)

    # ── 재시작 후 복원 ──────────────────────────────────────────────
    def test_껐다_켜도_줄이_남는다(self):
        made = self.add(platform="instagram")
        publish_queue.mark_uploading(self.store, made["id"])

        # 껐다 켠다 - 파일만 남고 메모리는 사라진다.
        again = publish_queue.find(self.store, made["id"])

        self.assertEqual(again["state"], publish_queue.UPLOADING)
        self.assertEqual(again["platform"], "instagram")

    def test_올리던_중_꺼진_것은_되살릴_수_있다(self):
        """
        UPLOADING 인 채로 컴퓨터가 꺼지면 그 줄은 영영 그 상태로
        남는다. 아무도 집지 않고, 사람은 올라가는 중인 줄 안다.
        """

        made = self.add()
        publish_queue.mark_uploading(self.store, made["id"])

        woken = publish_queue.recover_stuck(self.store)

        self.assertEqual([row["id"] for row in woken], [made["id"]])
        self.assertEqual(
            publish_queue.find(self.store, made["id"])["state"],
            publish_queue.PENDING)

    def test_되살릴_때_이유를_남긴다(self):
        made = self.add()
        publish_queue.mark_uploading(self.store, made["id"])
        publish_queue.recover_stuck(self.store)

        found = publish_queue.find(self.store, made["id"])

        self.assertIn("끊", found.get("reason", "") + found.get("note", ""))

    def test_끝난_것은_되살리지_않는다(self):
        made = self.add()
        publish_queue.mark_success(self.store, made["id"], url="https://x/1")

        self.assertEqual(publish_queue.recover_stuck(self.store), [])

    def test_망가진_파일은_빈_줄로_읽는다(self):
        """
        기억 하나가 깨졌다고 화면 전체가 죽을 이유는 없다 -
        free_workspace 가 이미 그렇게 한다.
        """

        with open(self.store, "w", encoding="utf-8") as f:
            f.write("{망가진")

        self.assertEqual(publish_queue.every(self.store), [])

        # 그리고 그 위에 다시 쌓을 수 있어야 한다.
        self.add()

        self.assertEqual(len(publish_queue.every(self.store)), 1)

    def test_적힌_파일은_사람이_읽을_수_있다(self):
        self.add()

        with open(self.store, encoding="utf-8") as f:
            found = json.load(f)

        self.assertEqual(found["version"], publish_queue.VERSION)
        self.assertEqual(len(found["items"]), 1)

    def test_없는_폴더에도_적는다(self):
        deep = os.path.join(self.root, "없던", "곳", "publish_queue.json")

        publish_queue.add(deep, project_id="p1", platform="tiktok")

        self.assertTrue(os.path.isfile(deep))


class TheQueueDoesNotUploadTest(unittest.TestCase):
    """
    줄은 줄일 뿐이다. 여기서 올리기 시작하면 두 곳이 같은 일을 하게
    되고, 이 저장소가 여러 번 겪은 그 일이 또 생긴다.
    """

    def test_바깥을_부르지_않는다(self):
        with open(publish_queue.__file__, encoding="utf-8") as f:
            body = f.read()

        for forbidden in ("requests.", "urlopen", "https://"):
            self.assertNotIn(forbidden, body, forbidden)

    def test_런타임을_들이지_않는다(self):
        with open(publish_queue.__file__, encoding="utf-8") as f:
            body = "\n".join(
                line for line in f.read().splitlines()
                if line.startswith("import ") or line.startswith("from "))

        for forbidden in ("runtime", "oauth", "adapter"):
            self.assertNotIn(forbidden, body.lower(), forbidden)


if __name__ == "__main__":
    unittest.main()
