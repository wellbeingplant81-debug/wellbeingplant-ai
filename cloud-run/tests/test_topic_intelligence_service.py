import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.topic_intelligence_service import (
    TopicIntelligenceService,
    TopicProfile,
)


class TestBuildTopicProfile(unittest.TestCase):

    def setUp(self):
        self.service = TopicIntelligenceService()

    def test_build_topic_profile_returns_topic_profile(self):
        profile = self.service.build_topic_profile("아침 스트레칭 루틴")

        self.assertIsInstance(profile, TopicProfile)
        self.assertEqual(profile.topic, "아침 스트레칭 루틴")

    def test_detect_disease_content_type(self):
        profile = self.service.build_topic_profile("당뇨병 예방하는 방법")

        self.assertEqual(profile.content_type, "disease")

    def test_detect_symptom_content_type(self):
        profile = self.service.build_topic_profile("두통이 심할 때 대처법")

        self.assertEqual(profile.content_type, "symptom")

    def test_detect_food_content_type(self):
        profile = self.service.build_topic_profile("토마토의 놀라운 효능")

        self.assertEqual(profile.content_type, "food")

    def test_default_values_are_present(self):
        # 특별한 키워드가 없는 일반 주제 - 모든 필드가 비어있지 않은
        # 기본값을 가져야 한다(None/빈 문자열 금지).
        profile = self.service.build_topic_profile("아침 스트레칭 루틴")

        self.assertTrue(profile.content_type)
        self.assertTrue(profile.medical_category)
        self.assertTrue(profile.target_age)
        self.assertIsInstance(profile.evergreen, bool)
        self.assertTrue(profile.conversation_style)

    def test_planner_hints_exists(self):
        profile = self.service.build_topic_profile("아침 스트레칭 루틴")

        self.assertIsInstance(profile.planner_hints, dict)


# --- Sprint83: Medical Topic Classification v1 (RED) ---


class TestMedicalTopicClassification(unittest.TestCase):

    def setUp(self):
        self.service = TopicIntelligenceService()

    def test_detect_medical_domain(self):
        profile = self.service.build_topic_profile("당뇨병 관리법")

        self.assertEqual(profile.medical_domain, "metabolism")

    def test_detect_urgency(self):
        profile = self.service.build_topic_profile("고혈압 위험 신호")

        self.assertEqual(profile.urgency, "high")

    def test_requires_medical_visual(self):
        food_profile = self.service.build_topic_profile("브로콜리 효능")
        disease_profile = self.service.build_topic_profile("당뇨병 관리법")

        self.assertFalse(food_profile.requires_medical_visual)
        self.assertTrue(disease_profile.requires_medical_visual)

    def test_asset_hints_exists(self):
        profile = self.service.build_topic_profile("아침 스트레칭 루틴")

        self.assertIsInstance(profile.asset_hints, dict)

    def test_dialogue_hints_exists(self):
        profile = self.service.build_topic_profile("아침 스트레칭 루틴")

        self.assertIsInstance(profile.dialogue_hints, dict)

    def test_default_medical_metadata(self):
        # 특별한 의료 키워드가 없는 일반 주제 - 새로 추가되는 의료
        # 메타데이터 필드들도 비어있지 않은 기본값을 가져야 한다.
        profile = self.service.build_topic_profile("아침 스트레칭 루틴")

        self.assertTrue(profile.medical_domain)
        self.assertTrue(profile.urgency)
        self.assertIsInstance(profile.requires_medical_visual, bool)
        self.assertTrue(profile.conversation_depth)


if __name__ == "__main__":
    unittest.main()
