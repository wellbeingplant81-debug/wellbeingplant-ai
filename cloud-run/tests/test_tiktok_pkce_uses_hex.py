"""
Sprint258 - TikTok 의 PKCE 는 hex 다.

무엇이 실제로 있었나
--------------------
실제 로그인이 여기까지 갔다.

    authorize 진입   OK
    TikTok 로그인    OK
    권한 승인        OK
    callback 복귀    OK
    토큰 교환        실패 - "Code verifier or code challenge is invalid."

verifier 는 흠이 없었다. authenticate() 한 함수 안의 지역변수라
authorize 에 쓴 것과 토큰 교환에 보낸 것이 같은 값이고, 저장하지도
덮어쓰지도 않는다.

문제는 challenge 를 만드는 방식이었다.

    RFC 7636    code_challenge = BASE64URL(SHA256(verifier))
    TikTok      code_challenge = HEX(SHA256(verifier))

공식 문서가 그렇게 적는다.

    "Create the code challenge by hashing the code verifier using hex
     encoding of SHA256. Since we only support S256 as
     code_challenge_method, use
     code_challenge = SHA256(code_verifier).toString(CryptoJS.enc.Hex)"

우리 코드는 RFC 를 정확히 따랐고, 그래서 TikTok 이 거절했다. 표준이
맞더라도 상대가 다른 것을 기다리면 통하지 않는다.

무엇을 바꾸지 않는가
--------------------
verifier 는 그대로다 - 만드는 방식도, 들고 다니는 방식도, 토큰 요청에
싣는 방식도. 바뀌는 것은 그 verifier 를 challenge 로 옮기는 한 걸음뿐이다.

여기서 재는 것
--------------
실제 TikTok 은 부르지 않는다. 값의 모양만 본다.
"""

import hashlib
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.upload.tiktok_oauth_service import (
    challenge_for, new_verifier,
)


class TheChallengeIsHexTest(unittest.TestCase):

    def test_공식_문서가_적은_그대로다(self):
        """
        문서의 예시 그대로: SHA256(verifier) 을 16진수 글자로.
        """

        verifier = "abc123-_~test"

        expected = hashlib.sha256(verifier.encode("ascii")).hexdigest()

        self.assertEqual(challenge_for(verifier), expected)

    def test_길이가_예순넷이다(self):
        """SHA-256 은 32바이트, 16진수로 적으면 64글자다."""

        for _ in range(5):
            self.assertEqual(len(challenge_for(new_verifier())), 64)

    def test_16진수_글자만_쓴다(self):
        got = challenge_for(new_verifier())

        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", got), got)

    def test_base64url_이_아니다(self):
        """
        예전 방식이 남아 있으면 여기서 걸린다 - 43글자에 대소문자가
        섞이고 - 나 _ 가 나온다.
        """

        import base64

        verifier = new_verifier()

        old = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")

        self.assertNotEqual(challenge_for(verifier), old)

    def test_패딩이_없다(self):
        self.assertNotIn("=", challenge_for(new_verifier()))

    def test_verifier_그대로가_아니다(self):
        """plain 방식이 아니다 - 가로채면 그대로 쓸 수 있으면 안 된다."""

        verifier = new_verifier()

        self.assertNotEqual(challenge_for(verifier), verifier)

    def test_같은_verifier_는_같은_challenge_를_준다(self):
        verifier = new_verifier()

        self.assertEqual(challenge_for(verifier), challenge_for(verifier))

    def test_다른_verifier_는_다른_challenge_를_준다(self):
        self.assertNotEqual(challenge_for(new_verifier()),
                            challenge_for(new_verifier()))


class TheVerifierIsUntouchedTest(unittest.TestCase):
    """
    이번 수정은 challenge 한 걸음만 바꾼다. verifier 쪽은 그대로여야
    한다 - 거기까지 손대면 무엇이 고쳐졌는지 알 수 없게 된다.
    """

    def test_길이가_문서_범위_안이다(self):
        """TikTok 도 RFC 와 같은 43~128 을 요구한다."""

        for _ in range(20):
            self.assertTrue(43 <= len(new_verifier()) <= 128)

    def test_허용된_글자만_쓴다(self):
        """unreserved: A-Z a-z 0-9 - . _ ~"""

        for _ in range(5):
            v = new_verifier()

            self.assertTrue(re.fullmatch(r"[A-Za-z0-9\-._~]+", v), v)

    def test_매번_다르다(self):
        self.assertEqual(len({new_verifier() for _ in range(200)}), 200)

    def test_앞뒤에_공백이_없다(self):
        v = new_verifier()

        self.assertEqual(v, v.strip())


class TheRequestShapeIsUnchangedTest(unittest.TestCase):
    """authorize 와 토큰 교환이 주고받는 모양은 그대로다."""

    def test_S256_그대로다(self):
        import inspect

        from app.providers.upload import tiktok_oauth_service as mod

        source = inspect.getsource(mod.TikTokOAuthService.authenticate)

        self.assertIn('"code_challenge_method": "S256"', source)

    def test_토큰_요청에_verifier_를_싣는다(self):
        import inspect

        from app.providers.upload import tiktok_oauth_service as mod

        source = inspect.getsource(mod.TikTokOAuthService.authenticate)

        self.assertIn('"code_verifier": verifier', source)

    def test_scope_가_그대로다(self):
        from app.providers.upload import tiktok_oauth_service as mod

        self.assertEqual(mod.SCOPES, "user.info.basic,video.publish")

    def test_다른_플랫폼은_건드리지_않았다(self):
        """이 방식은 TikTok 만의 것이다 - 표준과 다르기 때문이다."""

        from app.providers.upload import instagram_oauth_service as ig

        self.assertEqual(ig.AUTHORIZE_URL,
                         "https://www.instagram.com/oauth/authorize")


if __name__ == "__main__":
    unittest.main()
