"""
EPIC Instagram Connector (Production) (RED->GREEN) -
app/providers/upload/instagram_token_store.py.

app.providers.upload.file_token_store.FileTokenStore(Google/YouTube 전용,
무수정)와 동일한 save(credential)/load(account_id) 관례를 따르되,
InstagramCredential(refresh_token 없음, obtained_at 있음) 모양에 맞춘
별도 구현체다 - FileTokenStore를 억지로 재사용하지 않는다(그 파일은
credential.refresh_token을 직접 읽는 코드가 있어 그대로 못 쓴다).
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.upload.instagram_credential import InstagramCredential
from app.providers.upload.instagram_token_store import InstagramTokenStore

DEFAULT_ACCOUNT_ID = "default"


def _credential(account_id=DEFAULT_ACCOUNT_ID):
    now = datetime.now(timezone.utc)
    return InstagramCredential(
        account_id=account_id, access_token="tok",
        obtained_at=now, expires_at=now + timedelta(days=60),
    )


class TestInstagramTokenStore(unittest.TestCase):

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = InstagramTokenStore(storage_path=os.path.join(tmp_dir, "ig_tokens.json"))
            credential = _credential()

            store.save(credential)
            loaded = store.load(DEFAULT_ACCOUNT_ID)

        self.assertEqual(loaded.access_token, credential.access_token)
        self.assertEqual(loaded.account_id, credential.account_id)

    def test_load_missing_account_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = InstagramTokenStore(storage_path=os.path.join(tmp_dir, "ig_tokens.json"))
            self.assertIsNone(store.load("nonexistent"))

    def test_restored_after_program_restart_simulation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "ig_tokens.json")
            first = InstagramTokenStore(storage_path=path)
            first.save(_credential())

            second = InstagramTokenStore(storage_path=path)
            restored = second.load(DEFAULT_ACCOUNT_ID)

        self.assertEqual(restored.access_token, "tok")

    def test_supports_multiple_accounts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = InstagramTokenStore(storage_path=os.path.join(tmp_dir, "ig_tokens.json"))
            store.save(_credential("account-a"))
            store.save(_credential("account-b"))

            self.assertEqual(store.load("account-a").account_id, "account-a")
            self.assertEqual(store.load("account-b").account_id, "account-b")


class TestInstagramTokenStoreIgUserId(unittest.TestCase):
    """EPIC Setup Wizard Instagram Validation - Existing Access Token
    입력 경로가 fetch_channel_info()로 얻은 ig_user_id를 저장해 둘 수
    있어야 한다(기존에는 access_token/obtained_at/expires_at만 저장돼
    재시작 후 ig_user_id가 항상 빈 문자열로 복원됐다)."""

    def test_ig_user_id_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = InstagramTokenStore(storage_path=os.path.join(tmp_dir, "ig_tokens.json"))
            credential = _credential()
            credential.ig_user_id = "178414123456789"

            store.save(credential)
            loaded = store.load(DEFAULT_ACCOUNT_ID)

        self.assertEqual(loaded.ig_user_id, "178414123456789")

    def test_missing_ig_user_id_in_old_file_loads_as_empty_string(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "ig_tokens.json")
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    DEFAULT_ACCOUNT_ID: {
                        "access_token": "tok",
                        "obtained_at": datetime.now(timezone.utc).isoformat(),
                        "expires_at": datetime.now(timezone.utc).isoformat(),
                    },
                }, f)

            store = InstagramTokenStore(storage_path=path)
            loaded = store.load(DEFAULT_ACCOUNT_ID)

        self.assertEqual(loaded.ig_user_id, "")


class TestInstagramTokenStoreDelete(unittest.TestCase):
    """EPIC Instagram Production Ready - RealInstagramRuntime.revoke()가
    쓰는 로컬 로그아웃(저장된 토큰 삭제). 기존 save()/load()는 그대로
    두고 delete()만 추가한다(기존 기능 삭제 금지 - 새 메서드 추가일
    뿐이다)."""

    def test_delete_removes_only_the_given_account(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = InstagramTokenStore(storage_path=os.path.join(tmp_dir, "ig_tokens.json"))
            store.save(_credential("account-a"))
            store.save(_credential("account-b"))

            store.delete("account-a")

            self.assertIsNone(store.load("account-a"))
            self.assertIsNotNone(store.load("account-b"))

    def test_delete_missing_account_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = InstagramTokenStore(storage_path=os.path.join(tmp_dir, "ig_tokens.json"))

            store.delete("nonexistent")  # 예외 없어야 한다.

    def test_delete_when_file_does_not_exist_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = InstagramTokenStore(storage_path=os.path.join(tmp_dir, "never_created.json"))

            store.delete("default")  # 예외 없어야 한다.


if __name__ == "__main__":
    unittest.main()
