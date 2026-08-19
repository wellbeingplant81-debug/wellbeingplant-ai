"""
Sprint236 - 평문 토큰이 다음 저장까지 남지 않는다 (Epic 61 뒷마무리).

무엇이 있었나
-------------
Sprint217 이 secret_box(Windows DPAPI)를 붙였고, 두 보관소는 이미 그것을
지나간다. 그런데 감싸는 일이 **save() 에만** 붙어 있었다. load() 는
평문을 읽어 넘기기만 하고 다시 적지 않는다.

그래서 예전에 평문으로 적힌 파일은 다음 저장이 일어날 때까지 그대로
남는다. 실제로 이 PC 에서 그랬다.

    8월 6일 ~ 8월 19일   평문. 그 사이 프로그램은 여러 번 실행됐다
    8월 19일 23:46       실제 YouTube 업로드가 토큰을 갱신하면서
                         비로소 감싸였다

13일이다. access_token 이 살아 있는 동안에는 저장할 일이 없기 때문이고,
refresh_token 은 만료되지 않으므로 그 기간은 며칠일 수도 몇 달일 수도
있다. 그동안 그 파일 하나면 이 채널에 영상을 올릴 수 있다.

무엇을 새로 만들지 않았는가
---------------------------
    감싸는 법     secret_box.wrap/unwrap 그대로
    파일 쓰기     각 보관소의 _write_all 그대로
    보관소 계약   save/load/delete 그대로

늘어난 것은 "읽었는데 평문이었으면 그 자리에서 다시 적는다" 하나다.

두 곳이 같은 병을 앓는다
------------------------
FileTokenStore(YouTube · TikTok)와 InstagramTokenStore 의 _read_all 은
글자까지 같다. 그래서 판단은 secret_box 한 곳에 두고 둘이 그것을
부른다 - 파일 모양을 아는 곳이 두 곳이 되면 한쪽만 고치는 날이 온다
(FileTokenStore 의 주석이 이미 그렇게 적어 두었다).
"""

import base64
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.upload.file_token_store import FileTokenStore
from app.providers.upload.instagram_credential import InstagramCredential
from app.providers.upload.instagram_token_store import InstagramTokenStore
from app.providers.upload.oauth_credential import OAuthCredential
from app.services import secret_box

NEEDLE = "REFRESH-NEEDLE-9f2a"


def _skip_without_dpapi(case):
    if not secret_box.available():
        case.skipTest("이 자리에서는 DPAPI 를 쓸 수 없다")


class TheDecisionLivesInOnePlaceTest(unittest.TestCase):
    """
    두 보관소가 같은 판단을 따로 들면 어느 날 한쪽만 고쳐진다.
    """

    def test_감쌀_필요가_있는지_묻는_자리가_있다(self):
        self.assertTrue(callable(getattr(secret_box, "needs_protecting", None)))

    def test_평문이고_감쌀_수_있으면_참이다(self):
        _skip_without_dpapi(self)

        self.assertTrue(secret_box.needs_protecting({"default": {"a": 1}}))

    def test_이미_감싸인_것은_거짓이다(self):
        _skip_without_dpapi(self)

        sealed = secret_box.wrap({"default": {"a": 1}})

        self.assertFalse(secret_box.needs_protecting(sealed))

    def test_빈_것은_거짓이다(self):
        """적을 것이 없는데 파일을 건드릴 이유가 없다."""

        self.assertFalse(secret_box.needs_protecting({}))

    def test_감쌀_수_없으면_거짓이다(self):
        """
        못 감싸는 자리에서 참을 돌려주면, 읽을 때마다 같은 평문을
        의미 없이 다시 적는다.
        """

        with patch.object(secret_box, "available", return_value=False):
            self.assertFalse(secret_box.needs_protecting({"default": {"a": 1}}))

    def test_두_보관소가_같은_판단을_쓴다(self):
        for module in ("file_token_store", "instagram_token_store"):
            with self.subTest(store=module):
                path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "app", "providers", "upload", f"{module}.py")

                with open(path, encoding="utf-8") as f:
                    body = f.read()

                self.assertIn("needs_protecting", body)


class _MigrationCase(unittest.TestCase):
    """두 보관소가 같은 시험을 받는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.where = os.path.join(self.root, "tokens.json")

    def _write_plain(self, entry: dict) -> None:
        with open(self.where, "w", encoding="utf-8") as f:
            json.dump({"default": entry}, f, ensure_ascii=False)

    def _raw(self) -> dict:
        with open(self.where, encoding="utf-8") as f:
            return json.load(f)

    def _text(self) -> str:
        with open(self.where, encoding="utf-8") as f:
            return f.read()


class TheYouTubeStoreMigratesOnReadTest(_MigrationCase):

    def _store(self):
        return FileTokenStore(storage_path=self.where)

    def _plain(self):
        self._write_plain({
            "access_token": "at",
            "refresh_token": NEEDLE,
            "expires_at": datetime.now(timezone.utc).isoformat(),
        })

    def test_읽는_순간_감싸진다(self):
        _skip_without_dpapi(self)

        self._plain()

        self.assertIn(NEEDLE, self._text(), "시작이 평문이 아니다")

        self._store().load("default")

        self.assertNotIn(NEEDLE, self._text(), "읽은 뒤에도 평문이다")
        self.assertIn(secret_box.MARKER_DPAPI, self._text())

    def test_감싸도_읽히는_것은_그대로다(self):
        _skip_without_dpapi(self)

        self._plain()

        back = self._store().load("default")

        self.assertEqual(back.refresh_token, NEEDLE)
        self.assertEqual(back.account_id, "default")

        # 감싼 뒤에 다시 읽어도 같아야 한다.
        again = self._store().load("default")

        self.assertEqual(again.refresh_token, NEEDLE)

    def test_이미_감싸인_것은_다시_적지_않는다(self):
        _skip_without_dpapi(self)

        self._plain()
        self._store().load("default")          # 여기서 감싸진다

        before = self._text()

        for _ in range(3):
            self._store().load("default")

        self.assertEqual(self._text(), before,
                         "감싸인 파일을 읽을 때마다 다시 적었다")

    def test_다시_적기에_실패해도_로그인은_살아_있다(self):
        """
        마이그레이션은 곁다리다. 그것 때문에 로그인이 사라지면
        사람은 이유도 모른 채 다시 로그인해야 한다.
        """

        _skip_without_dpapi(self)

        self._plain()

        store = self._store()

        with patch.object(type(store), "_write_all",
                          side_effect=OSError("읽기 전용")):
            back = store.load("default")

        self.assertIsNotNone(back)
        self.assertEqual(back.refresh_token, NEEDLE)

        # 파일은 손대지 않은 채 평문 그대로 남는다 - 지워지지 않는다.
        self.assertIn(NEEDLE, self._text())

    def test_감쌀_수_없는_자리에서는_그대로_읽는다(self):
        self._plain()

        with patch.object(secret_box, "available", return_value=False):
            back = self._store().load("default")

        self.assertEqual(back.refresh_token, NEEDLE)
        self.assertIn(NEEDLE, self._text(), "못 감싸면서 파일을 건드렸다")

    def test_없는_파일은_건드리지_않는다(self):
        self.assertIsNone(self._store().load("default"))
        self.assertFalse(os.path.exists(self.where))

    def test_없는_계정을_물어도_감싸기는_일어난다(self):
        """
        감쌀 이유는 "누구를 물었는가" 와 무관하다. 파일이 평문이면
        평문인 것이다.
        """

        _skip_without_dpapi(self)

        self._plain()

        self.assertIsNone(self._store().load("없는사람"))
        self.assertNotIn(NEEDLE, self._text())

    def test_저장은_예전처럼_감싸_적는다(self):
        _skip_without_dpapi(self)

        self._store().save(OAuthCredential(
            account_id="default", access_token="at", refresh_token=NEEDLE,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))

        self.assertNotIn(NEEDLE, self._text())


class TheInstagramStoreHasTheSameIllnessTest(_MigrationCase):
    """
    Sprint236 의 6번 - 같은 구조인지 확인한다. _read_all 이 글자까지
    같으므로 같은 병이고, 같은 약이 들어야 한다.
    """

    def _store(self):
        return InstagramTokenStore(storage_path=self.where)

    def _plain(self):
        now = datetime.now(timezone.utc)

        self._write_plain({
            "access_token": NEEDLE,
            "obtained_at": now.isoformat(),
            "expires_at": (now + timedelta(days=60)).isoformat(),
            "ig_user_id": "ig-1",
        })

    def test_읽는_순간_감싸진다(self):
        _skip_without_dpapi(self)

        self._plain()

        self._store().load("default")

        self.assertNotIn(NEEDLE, self._text())
        self.assertIn(secret_box.MARKER_DPAPI, self._text())

    def test_감싸도_읽히는_것은_그대로다(self):
        _skip_without_dpapi(self)

        self._plain()

        back = self._store().load("default")

        self.assertEqual(back.access_token, NEEDLE)
        self.assertEqual(back.ig_user_id, "ig-1")

    def test_이미_감싸인_것은_다시_적지_않는다(self):
        _skip_without_dpapi(self)

        self._plain()
        self._store().load("default")

        before = self._text()

        self._store().load("default")

        self.assertEqual(self._text(), before)

    def test_다시_적기에_실패해도_로그인은_살아_있다(self):
        _skip_without_dpapi(self)

        self._plain()

        store = self._store()

        with patch.object(type(store), "_write_all",
                          side_effect=OSError("읽기 전용")):
            back = store.load("default")

        self.assertIsNotNone(back)
        self.assertEqual(back.access_token, NEEDLE)


class TheUploadPathIsUntouchedTest(unittest.TestCase):
    """
    Sprint236 의 5번 - OAuth · provider · 업로드 코드는 건드리지
    않는다. 방금 실제로 영상 하나를 올린 길이다.
    """

    def test_건드리지_않은_파일들(self):
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
            "cloud-run/app/providers/upload/google_oauth_service.py",
            "cloud-run/app/providers/upload/youtube_upload_provider.py",
            "cloud-run/app/services/youtube_upload_step_service.py",
            "cloud-run/app/services/real_youtube_runtime.py",
        }

        self.assertEqual(touched & forbidden, set(), touched & forbidden)


if __name__ == "__main__":
    unittest.main()
