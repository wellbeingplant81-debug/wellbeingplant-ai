"""
Sprint100-2 - Motion Contract. profile != "upload"면 None, "upload"면
scene 위치(hook/conclusion/explanation)로 motion/max_assets를 정하는지
확인한다.

Sprint101 - Video Intent Intelligence. motion_contract.py는 이제
"Rule Engine" 역할도 한다: Conclusion/의학 설명은 scene_intent_
classifier를 호출조차 하지 않고 즉시 required_image로 확정하고
(Rule Override), 그 외(Hook 포함)에는 분류기를 호출해 그 추천(AI
판단)을 그대로 최종 video_intent로 채택한다. 분류기는 실제 Gemini를
호출하므로 전부 mock한다 - 순수 오케스트레이션/Rule Override 구조만
검증한다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.video_intent import VideoIntent
from app.services import motion_contract


def _scene(number, narration):
    return {"scene": number, "narration": narration, "image_prompt": narration}


def _fake_classify(narration, image_prompt):
    """
    테스트용 classify_video_intent 대체 구현. 실제 분류기의 지능을
    흉내내지 않고, narration에 특정 키워드가 있으면 결정적으로 매핑
    한다 - motion_contract.py의 오케스트레이션(언제 호출하는지/결과를
    어떻게 반영하는지)만 검증하면 되기 때문이다.
    """

    if "운동" in narration or "걷기" in narration or "산책" in narration:
        return VideoIntent(
            intent=motion_contract.VIDEO_PREFERRED, confidence=0.9,
            reason="운동 동작이 핵심", source="ai_classifier",
        )
    if "식사" in narration:
        return VideoIntent(
            intent=motion_contract.VIDEO_PREFERRED, confidence=0.85,
            reason="음식 섭취 장면", source="ai_classifier",
        )
    return VideoIntent(
        intent=motion_contract.IMAGE_PREFERRED, confidence=0.7,
        reason="특별한 동작 없는 일반 장면", source="ai_classifier",
    )


class TestBuildMotionContractProfileGate(unittest.TestCase):

    def test_non_upload_profile_returns_none(self):
        scenes = [_scene(1, "hook")]
        self.assertIsNone(motion_contract.build_motion_contract(scenes, profile="development"))
        self.assertIsNone(motion_contract.build_motion_contract(scenes, profile=None))

    def test_empty_scenes_returns_empty_list_not_none(self):
        self.assertEqual(motion_contract.build_motion_contract([], profile="upload"), [])


@patch(
    "app.services.motion_contract.scene_intent_classifier.classify_video_intent",
    side_effect=_fake_classify,
)
class TestBuildMotionContractUploadProfile(unittest.TestCase):

    def setUp(self):
        self.scenes = [
            _scene(1, "이 증상 놓치면 큰일납니다"),
            _scene(2, "혈관 안에서 염증이 진행됩니다"),
            _scene(3, "매일 걷기 운동을 하면 도움이 됩니다"),
            _scene(4, "규칙적인 식사와 습관이 중요합니다"),
            _scene(5, "오늘부터 꼭 실천해보세요"),
        ]

    def test_first_scene_is_hook_dynamic(self, mock_classify):
        contract = motion_contract.build_motion_contract(self.scenes, profile="upload")
        entry = contract[0]
        self.assertEqual(entry["purpose"], motion_contract.PURPOSE_HOOK)
        self.assertEqual(entry["motion"], motion_contract.MOTION_DYNAMIC)
        self.assertEqual(entry["max_assets"], motion_contract.HOOK_MAX_ASSETS)
        self.assertIsNone(entry["hold_seconds"])

    def test_last_scene_is_conclusion_static(self, mock_classify):
        contract = motion_contract.build_motion_contract(self.scenes, profile="upload")
        entry = contract[-1]
        self.assertEqual(entry["purpose"], motion_contract.PURPOSE_CONCLUSION)
        self.assertEqual(entry["motion"], motion_contract.MOTION_STATIC)
        self.assertEqual(entry["max_assets"], 1)

    def test_medical_keyword_scene_is_static_ai(self, mock_classify):
        contract = motion_contract.build_motion_contract(self.scenes, profile="upload")
        entry = contract[1]
        self.assertEqual(entry["purpose"], motion_contract.PURPOSE_EXPLANATION)
        self.assertEqual(entry["motion"], motion_contract.MOTION_STATIC)
        self.assertEqual(entry["visual_intent"], motion_contract.INTENT_MEDICAL)
        self.assertEqual(entry["max_assets"], 1)

    def test_scene_id_matches_scene_number(self, mock_classify):
        contract = motion_contract.build_motion_contract(self.scenes, profile="upload")
        for entry, scene in zip(contract, self.scenes):
            self.assertEqual(entry["scene_id"], scene["scene"])

    def test_transition_field_present_but_unused_this_sprint(self, mock_classify):
        contract = motion_contract.build_motion_contract(self.scenes, profile="upload")
        for entry in contract:
            self.assertIn("transition", entry)
            self.assertIsNone(entry["transition"])

    def test_input_scenes_not_mutated(self, mock_classify):
        before = [dict(s) for s in self.scenes]
        motion_contract.build_motion_contract(self.scenes, profile="upload")
        self.assertEqual(self.scenes, before)


@patch(
    "app.services.motion_contract.scene_intent_classifier.classify_video_intent",
    side_effect=_fake_classify,
)
class TestVideoIntentRuleOverride(unittest.TestCase):
    """
    Sprint101 - Rule Override 구조 검증: Conclusion/의학 설명은
    분류기를 아예 호출하지 않고 즉시 required_image로 확정되는지,
    그 외(Hook 포함)에는 분류기 결과가 그대로 최종 video_intent로
    반영되는지 확인한다.
    """

    def test_conclusion_never_calls_classifier_and_is_required_image(self, mock_classify):
        scenes = [
            _scene(1, "hook"),
            _scene(2, "매일 걷기 운동을 하면 도움이 됩니다"),
            _scene(3, "오늘부터 꼭 실천해보세요"),  # Conclusion - scene2와 다른 narration
        ]

        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        conclusion_entry = contract[-1]
        self.assertEqual(conclusion_entry["video_intent"]["intent"], motion_contract.IMAGE_REQUIRED)
        self.assertEqual(conclusion_entry["video_intent"]["source"], "rule")

        # Conclusion scene의 narration으로는 분류기가 호출되지 않았어야
        # 한다 - Rule Override가 AI 판단보다 먼저 적용됨을 의미한다.
        called_narrations = [call.args[0] for call in mock_classify.call_args_list]
        self.assertNotIn(scenes[2]["narration"], called_narrations)
        self.assertEqual(mock_classify.call_count, 2)  # scene1(hook), scene2만 호출됨

    def test_medical_scene_never_calls_classifier_and_is_required_image(self, mock_classify):
        scenes = [
            _scene(1, "hook"),
            _scene(2, "혈관 안에서 염증이 진행됩니다"),
            _scene(3, "conclusion"),
        ]

        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        medical_entry = contract[1]
        self.assertEqual(medical_entry["video_intent"]["intent"], motion_contract.IMAGE_REQUIRED)
        self.assertEqual(medical_entry["video_intent"]["source"], "rule")
        self.assertEqual(mock_classify.call_count, 1)  # scene1(hook)만 호출됨

    def test_hook_calls_classifier_and_adopts_its_result(self, mock_classify):
        scenes = [
            _scene(1, "매일 걷기 운동을 하면 도움이 됩니다"),  # Hook
            _scene(2, "일반적인 설명입니다"),
            _scene(3, "conclusion"),
        ]

        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        hook_entry = contract[0]
        self.assertEqual(hook_entry["motion"], motion_contract.MOTION_DYNAMIC)  # 컷 수 정책은 그대로
        self.assertEqual(hook_entry["video_intent"]["intent"], motion_contract.VIDEO_PREFERRED)
        self.assertEqual(hook_entry["video_intent"]["source"], "ai_classifier")

    def test_explanation_scene_adopts_classifier_result(self, mock_classify):
        scenes = [
            _scene(1, "hook"),
            _scene(2, "매일 걷기 운동을 하면 도움이 됩니다"),
            _scene(3, "conclusion"),
        ]

        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        entry = contract[1]
        self.assertEqual(entry["video_intent"]["intent"], motion_contract.VIDEO_PREFERRED)
        self.assertEqual(entry["video_intent"]["confidence"], 0.9)
        self.assertEqual(entry["video_intent"]["source"], "ai_classifier")

    def test_classifier_required_video_result_is_reflected(self, mock_classify):
        mock_classify.side_effect = None
        mock_classify.return_value = VideoIntent(
            intent=motion_contract.VIDEO_REQUIRED, confidence=0.95,
            reason="스쿼트 동작 자체가 핵심이라 반드시 영상이어야 함",
            source="ai_classifier",
        )
        scenes = [_scene(1, "hook"), _scene(2, "스쿼트 자세를 보여드립니다"), _scene(3, "conclusion")]

        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        entry = contract[1]
        self.assertEqual(entry["video_intent"]["intent"], motion_contract.VIDEO_REQUIRED)
        self.assertEqual(entry["video_intent"]["reason"], "스쿼트 동작 자체가 핵심이라 반드시 영상이어야 함")

    def test_classifier_preferred_image_result_is_reflected(self, mock_classify):
        mock_classify.side_effect = None
        mock_classify.return_value = VideoIntent(
            intent=motion_contract.IMAGE_PREFERRED, confidence=0.8,
            reason="개념 설명이라 정지 이미지가 더 명확함",
            source="ai_classifier",
        )
        scenes = [_scene(1, "hook"), _scene(2, "이런 원리로 작용합니다"), _scene(3, "conclusion")]

        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        self.assertEqual(contract[1]["video_intent"]["intent"], motion_contract.IMAGE_PREFERRED)

    def test_classifier_fallback_result_flows_through_as_rule_source(self, mock_classify):
        # scene_intent_classifier.classify_video_intent()이 실패해도
        # 예외 없이 안전한 폴백(source="rule")을 반환한다는 계약은
        # test_scene_intent_classifier.py가 이미 검증한다 - 여기서는
        # motion_contract.py가 그 폴백 결과를 있는 그대로(재해석 없이)
        # 최종 contract에 반영하는지만 확인한다.
        mock_classify.side_effect = None
        mock_classify.return_value = VideoIntent(
            intent="preferred_image", confidence=0.0,
            reason="Gemini unavailable: network timeout", source="rule",
        )
        scenes = [_scene(1, "hook"), _scene(2, "설명 장면"), _scene(3, "conclusion")]

        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        entry = contract[1]
        self.assertEqual(entry["video_intent"]["source"], "rule")
        self.assertIn("Gemini unavailable", entry["video_intent"]["reason"])

    def test_video_intent_dict_has_exactly_four_fields(self, mock_classify):
        scenes = [_scene(1, "hook"), _scene(2, "conclusion")]
        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        for entry in contract:
            self.assertEqual(
                set(entry["video_intent"].keys()),
                {"intent", "confidence", "reason", "source"},
            )


@patch(
    "app.services.motion_contract.scene_intent_classifier.classify_video_intent",
    side_effect=_fake_classify,
)
class TestIndexByAndVideoPriorityHelpers(unittest.TestCase):
    """
    Sprint100-3 - Motion Contract Single Source of Truth. step02_assets.py
    가 UploadAssetStrategy.prefers_video()를 별도로 다시 호출하지 않고
    이 두 헬퍼만으로 조회할 수 있는지 확인한다. 핵심 회귀 케이스: 마지막
    scene(Conclusion)의 narration에 video 선호 키워드(걷기/산책 등)가
    있어도, Rule Override가 위치 기반으로 required_image를 강제했으면
    video_priority_scene_ids()에 포함되면 안 된다(2026-07-14 Production
    QA에서 실측된 정책 불일치 - 이 테스트가 그 재발을 막는다).
    """

    def test_conclusion_with_video_keywords_is_not_video_priority(self, mock_classify):
        scenes = [
            _scene(1, "hook"),
            _scene(2, "혈관 안에서 염증이 진행됩니다"),
            _scene(3, "매일 30분씩 가볍게 걷는 산책, 채소 위주 식사를 곁들이세요"),
        ]
        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        conclusion_entry = contract[-1]
        self.assertEqual(conclusion_entry["video_intent"]["intent"], motion_contract.IMAGE_REQUIRED)

        video_priority_ids = motion_contract.video_priority_scene_ids(contract)
        self.assertNotIn(conclusion_entry["scene_id"], video_priority_ids)

    def test_explanation_video_preferred_scene_is_video_priority(self, mock_classify):
        scenes = [
            _scene(1, "hook"),
            _scene(2, "매일 걷기 운동을 하면 도움이 됩니다"),
            _scene(3, "conclusion"),
        ]
        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        video_priority_ids = motion_contract.video_priority_scene_ids(contract)
        self.assertEqual(video_priority_ids, {2})

    def test_index_by_scene_id_matches_build_motion_contract(self, mock_classify):
        scenes = [_scene(1, "hook"), _scene(2, "conclusion")]
        contract = motion_contract.build_motion_contract(scenes, profile="upload")

        indexed = motion_contract.index_by_scene_id(contract)

        self.assertEqual(set(indexed.keys()), {1, 2})
        self.assertEqual(indexed[1], contract[0])

    def test_helpers_handle_none_contract(self, mock_classify):
        self.assertEqual(motion_contract.index_by_scene_id(None), {})
        self.assertEqual(motion_contract.video_priority_scene_ids(None), set())


class TestVideoPriorityByIntentLevel(unittest.TestCase):
    """
    video_priority_scene_ids()가 4단계 video_intent 전부에 대해 요구된
    매핑대로 동작하는지 직접 확인한다(순수 데이터 변환이라 classify_
    video_intent를 mock할 필요 없음 - 이미 만들어진 contract만 넘긴다).

    required_video/preferred_video -> 포함(=prefer_video True)
    preferred_image/required_image -> 제외(=prefer_video False)
    """

    def _contract_with_intent(self, intent):
        return [{
            "scene_id": 1,
            "video_intent": {
                "intent": intent, "confidence": 0.9, "reason": "r", "source": "ai_classifier",
            },
        }]

    def test_required_video_is_priority(self):
        contract = self._contract_with_intent(motion_contract.VIDEO_REQUIRED)
        self.assertEqual(motion_contract.video_priority_scene_ids(contract), {1})

    def test_preferred_video_is_priority(self):
        contract = self._contract_with_intent(motion_contract.VIDEO_PREFERRED)
        self.assertEqual(motion_contract.video_priority_scene_ids(contract), {1})

    def test_preferred_image_is_not_priority(self):
        contract = self._contract_with_intent(motion_contract.IMAGE_PREFERRED)
        self.assertEqual(motion_contract.video_priority_scene_ids(contract), set())

    def test_required_image_is_not_priority(self):
        contract = self._contract_with_intent(motion_contract.IMAGE_REQUIRED)
        self.assertEqual(motion_contract.video_priority_scene_ids(contract), set())


class TestAllowsVideo(unittest.TestCase):
    """Sprint101부터 allows_video()는 motion이 아니라 video_intent
    값을 받는다."""

    def test_required_image_disallows_video(self):
        self.assertFalse(motion_contract.allows_video(motion_contract.IMAGE_REQUIRED))

    def test_other_intents_allow_video(self):
        self.assertTrue(motion_contract.allows_video(motion_contract.VIDEO_REQUIRED))
        self.assertTrue(motion_contract.allows_video(motion_contract.VIDEO_PREFERRED))
        self.assertTrue(motion_contract.allows_video(motion_contract.IMAGE_PREFERRED))


if __name__ == "__main__":
    unittest.main()
