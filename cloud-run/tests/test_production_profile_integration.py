"""
Sprint91 (RED) - Production Profile Integration Foundation 테스트.

ProductionProfileIntegration.load_profile(profile_name=None, enabled=False)는
Pipeline이 ProductionProfile을 읽을지 말지 결정하는 단일 Feature Flag
진입점이다. enabled=False(기본값)이면 기존 Pipeline 동작과 동일하게
None을 반환하고(= 프로파일 개입 없음), enabled=True일 때만
ProductionProfile.get(profile_name)을 읽어 반환한다(profile_name 생략 시
"development"). 아직 구현이 없으므로(RED) 모든 테스트는 실패해야 정상이다.
"""

import unittest

from app.services.production_profile import ProductionProfile
from app.services.production_profile_integration import ProductionProfileIntegration


class TestProductionProfileIntegration(unittest.TestCase):

    def test_default_profile_is_development(self):
        result = ProductionProfileIntegration.load_profile(enabled=True)
        self.assertEqual(result, ProductionProfile.get("development"))

    def test_profile_flag_disabled_preserves_existing_behavior(self):
        result = ProductionProfileIntegration.load_profile(profile_name="upload", enabled=False)
        self.assertEqual(result, ProductionProfile.get("development"))

    def test_profile_flag_enabled_loads_upload_profile(self):
        result = ProductionProfileIntegration.load_profile(profile_name="upload", enabled=True)
        self.assertEqual(result, ProductionProfile.get("upload"))

    def test_pipeline_reads_production_profile(self):
        result = ProductionProfileIntegration.load_profile(profile_name="development", enabled=True)
        self.assertEqual(result["duration_target"], 45)

    def test_existing_pipeline_path_unchanged(self):
        result = ProductionProfileIntegration.load_profile()
        self.assertEqual(result, ProductionProfile.get("development"))

    def test_feature_flag_default_off(self):
        result = ProductionProfileIntegration.load_profile(profile_name="upload")
        self.assertEqual(result, ProductionProfile.get("development"))


if __name__ == "__main__":
    unittest.main()
