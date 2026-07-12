"""
Sprint89 (RED) - Production Profile Foundation 테스트.

ProductionProfile.get(profile_name)은 "development"/"upload" 두 프로파일의
설정(duration_target, tts_provider, asset_strategy)을 조회하는 단일
진입점이다. 알 수 없는 profile_name은 예외 없이 기존 기본값(development)
으로 안전하게 대체된다. 아직 구현이 없으므로(RED) 모든 테스트는 실패해야
정상이다.
"""

import unittest

from app.services.production_profile import ProductionProfile


class TestProductionProfile(unittest.TestCase):

    def test_development_profile_exists(self):
        profile = ProductionProfile.get("development")
        self.assertIsNotNone(profile)

    def test_upload_profile_exists(self):
        profile = ProductionProfile.get("upload")
        self.assertIsNotNone(profile)

    def test_upload_duration_target(self):
        profile = ProductionProfile.get("upload")
        self.assertEqual(profile["duration_target"], 55)

    def test_upload_tts_provider(self):
        profile = ProductionProfile.get("upload")
        self.assertEqual(profile["tts_provider"], "elevenlabs")

    def test_upload_asset_strategy(self):
        profile = ProductionProfile.get("upload")
        self.assertEqual(profile["asset_strategy"], "upload")

    def test_unknown_profile_returns_default(self):
        profile = ProductionProfile.get("no_such_profile")
        self.assertEqual(profile, ProductionProfile.get("development"))


if __name__ == "__main__":
    unittest.main()
