"""
EPIC Instagram Connector (Production) (RED->GREEN) -
app/providers/upload/instagram_credential.py.

InstagramCredential은 app.providers.upload.oauth_credential.OAuthCredential
(Google/YouTube 전용, 무수정)과 의도적으로 다른 모양이다 - Instagram
장기 토큰에는 별도 refresh_token이 없다(같은 토큰을 "24시간 이상 지났고
아직 안 만료됐을 때"만 자체 갱신 API로 연장할 수 있을 뿐이다 - Google의
"영구 refresh_token" 모델과 근본적으로 다르다). 그래서 is_refreshable()
판정에 obtained_at(마지막 발급/갱신 시각)이 필요하다 - expires_at만으로는
"24시간이 지났는가"를 알 수 없다.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.upload.instagram_credential import InstagramCredential, is_refreshable
from app.providers.upload.oauth_credential import is_expired


def _credential(obtained_hours_ago: float, expires_in_days: float = 60):
    now = datetime.now(timezone.utc)
    return InstagramCredential(
        account_id="default",
        access_token="tok",
        obtained_at=now - timedelta(hours=obtained_hours_ago),
        expires_at=now - timedelta(hours=obtained_hours_ago) + timedelta(days=expires_in_days),
    )


class TestInstagramCredentialHasNoRefreshToken(unittest.TestCase):

    def test_dataclass_has_no_refresh_token_field(self):
        credential = _credential(obtained_hours_ago=1)
        self.assertFalse(hasattr(credential, "refresh_token"))


class TestInstagramCredentialIgUserId(unittest.TestCase):
    """EPIC Instagram Production Ready - InstagramRuntimeProtocol.login()이
    Credential 하나로 access_token과 ig_user_id를 함께 돌려줄 수 있도록
    ig_user_id 필드를 추가한다(기존 fetch_channel_info()가 하던 조회를
    없애지 않는다 - RealInstagramRuntime.login()이 여전히 그 함수를
    호출해 이 필드를 채운다). 기존 4개 필드 생성 호출부가 전부 keyword
    인자만 쓰므로 default 값 추가는 회귀 없이 안전하다."""

    def test_defaults_to_empty_string(self):
        credential = _credential(obtained_hours_ago=1)
        self.assertEqual(credential.ig_user_id, "")

    def test_can_be_set_explicitly(self):
        now = datetime.now(timezone.utc)
        credential = InstagramCredential(
            account_id="default", access_token="tok",
            obtained_at=now, expires_at=now + timedelta(days=60),
            ig_user_id="17841400000000000",
        )
        self.assertEqual(credential.ig_user_id, "17841400000000000")


class TestInstagramCredentialIsExpiredReusesExistingFunction(unittest.TestCase):
    """app.providers.upload.oauth_credential.is_expired()는 duck typing으로
    그대로 재사용 가능해야 한다(expires_at만 읽는다) - 새 함수를 만들지
    않는다."""

    def test_not_yet_expired(self):
        credential = _credential(obtained_hours_ago=1, expires_in_days=60)
        self.assertFalse(is_expired(credential))

    def test_already_expired(self):
        credential = _credential(obtained_hours_ago=61 * 24, expires_in_days=60)
        self.assertTrue(is_expired(credential))


class TestIsRefreshable(unittest.TestCase):

    def test_too_young_is_not_refreshable(self):
        credential = _credential(obtained_hours_ago=1)  # 24시간 미만.
        self.assertFalse(is_refreshable(credential))

    def test_old_enough_and_not_expired_is_refreshable(self):
        credential = _credential(obtained_hours_ago=25, expires_in_days=60)
        self.assertTrue(is_refreshable(credential))

    def test_already_expired_is_not_refreshable(self):
        # 만료된 뒤에는 갱신 API 자체가 실패한다 - 재로그인만 답이다.
        credential = _credential(obtained_hours_ago=61 * 24, expires_in_days=60)
        self.assertFalse(is_refreshable(credential))

    def test_exactly_24_hours_is_refreshable(self):
        credential = _credential(obtained_hours_ago=24, expires_in_days=60)
        self.assertTrue(is_refreshable(credential))


if __name__ == "__main__":
    unittest.main()
