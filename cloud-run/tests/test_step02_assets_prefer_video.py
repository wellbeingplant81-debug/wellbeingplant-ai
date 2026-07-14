"""
Sprint100-3 - Motion Contract Single Source of Truth. collect_assets()가
asset_strategy="upload"이고 config.ENABLE_MOTION_CONTRACT가 켜져 있을
때, prefer_video/max_assets를 UploadAssetStrategy.prefers_video()로
별도로 다시 계산하지 않고 motion_contract.build_motion_contract()의
결과만 그대로 integrate_asset()에 전달하는지 확인한다.

핵심 회귀 케이스: narration에 video 선호 키워드(산책 등)가 있어도
Motion Contract가 위치(Conclusion) 기반으로 static을 강제하면
prefer_video는 반드시 False여야 한다 - 2026-07-14 Production QA에서
실측된 정책 불일치(Motion Contract=static인데 실제로는 video로
렌더링됨)의 재발 방지 테스트다.

config.ENABLE_MOTION_CONTRACT가 꺼져 있을 때(kill switch off, 기본값)는
Sprint100-2 이전 동작(UploadAssetStrategy.prefers_video() 직접 호출,
위치 오버라이드 없음)이 100% 보존되는지만 별도로 확인한다 - 이는
"정책"이 아니라 안전한 폴백 경로임을 명시적으로 보여준다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.models.video_intent import VideoIntent
from app.steps.step02_assets import collect_assets


SAMPLE_SCENES = [
    {"scene": 1, "narration": "hook", "image_prompt": "p1"},
    {"scene": 2, "narration": "매일 30분씩 가벼운 산책을 해보세요", "image_prompt": "p2"},
    {"scene": 3, "narration": "매일 30분씩 가벼운 산책을 해보세요", "image_prompt": "p3"},
]


def _fake_classify_video_intent(narration, image_prompt):
    """
    Sprint101 - motion_contract.build_motion_contract()가 Hook/
    explanation scene마다 실제 Gemini를 호출하므로, step02_assets.py
    오케스트레이션만 검증하는 이 테스트에서는 결정적 가짜 분류기로
    대체한다(회귀 안정성 + 속도, 실제 네트워크 호출 없음).
    """
    if "산책" in narration:
        return VideoIntent(
            intent="preferred_video", confidence=0.9, reason="산책 장면", source="ai_classifier",
        )
    return VideoIntent(
        intent="preferred_image", confidence=0.7, reason="일반 장면", source="ai_classifier",
    )


def _fake_integrate_asset(
    scene, project_path, channel="wellbeing", prefer_ai=False, visual_profile=None,
    asset_strategy=None, prefer_video=False, max_assets=None,
):
    enriched = dict(scene)
    enriched["asset_path"] = f"{project_path}/images/scene{scene['scene']}.png"
    enriched["provider"] = "ai_image"
    enriched["asset_type"] = "image"
    enriched["search_query"] = "query"
    enriched["confidence"] = 1.0
    return enriched


class TestStep02AssetsFollowsMotionContract(unittest.TestCase):

    def setUp(self):
        original_flag = config.ENABLE_MOTION_CONTRACT
        config.ENABLE_MOTION_CONTRACT = True
        self.addCleanup(setattr, config, "ENABLE_MOTION_CONTRACT", original_flag)

    @patch(
        "app.services.motion_contract.scene_intent_classifier.classify_video_intent",
        side_effect=_fake_classify_video_intent,
    )
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_prefer_video_and_max_assets_come_from_motion_contract(
        self, mock_integrate, mock_classify,
    ):
        collect_assets(SAMPLE_SCENES, "output/proj", asset_strategy="upload")

        by_scene = {
            call.args[0]["scene"]: call.kwargs
            for call in mock_integrate.call_args_list
        }

        # scene1 = Hook -> dynamic(컷 수), narration="hook"이라 분류기가
        # preferred_image를 추천 -> prefer_video는 False. max_assets=3.
        self.assertFalse(by_scene[1]["prefer_video"])
        self.assertEqual(by_scene[1]["max_assets"], 3)

        # scene2 = 중간 explanation, "산책" -> 분류기가 preferred_video
        # 추천 -> prefer_video는 True.
        self.assertTrue(by_scene[2]["prefer_video"])
        self.assertEqual(by_scene[2]["max_assets"], 1)

        # scene3 = 마지막(Conclusion), scene2와 완전히 동일한 "산책"
        # 키워드를 갖고 있어도 Rule Override(Conclusion=required_image)가
        # 분류기 호출 자체를 막으므로 prefer_video는 반드시 False여야
        # 한다(회귀 방지 핵심 검증).
        self.assertFalse(by_scene[3]["prefer_video"])
        self.assertEqual(by_scene[3]["max_assets"], 1)

    @patch(
        "app.services.motion_contract.scene_intent_classifier.classify_video_intent",
        side_effect=_fake_classify_video_intent,
    )
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_scene_copy_carries_motion_contract_field(self, mock_integrate, mock_classify):
        collect_assets(SAMPLE_SCENES, "output/proj", asset_strategy="upload")

        scene_arg_by_number = {
            call.args[0]["scene"]: call.args[0]
            for call in mock_integrate.call_args_list
        }

        self.assertEqual(scene_arg_by_number[1]["motion_contract"]["motion"], "dynamic")
        self.assertEqual(scene_arg_by_number[2]["motion_contract"]["motion"], "static")
        self.assertEqual(scene_arg_by_number[3]["motion_contract"]["motion"], "static")

        # Sprint101 - video 시도 여부는 이제 motion이 아니라 video_intent가 담당.
        self.assertEqual(scene_arg_by_number[1]["motion_contract"]["video_intent"]["intent"], "preferred_image")
        self.assertEqual(scene_arg_by_number[2]["motion_contract"]["video_intent"]["intent"], "preferred_video")
        self.assertEqual(scene_arg_by_number[3]["motion_contract"]["video_intent"]["intent"], "required_image")
        self.assertEqual(scene_arg_by_number[3]["motion_contract"]["video_intent"]["source"], "rule")


class TestStep02AssetsMotionContractKillSwitchOff(unittest.TestCase):
    """
    config.ENABLE_MOTION_CONTRACT가 꺼져 있을 때(기본값)의 폴백 경로.
    Motion Contract 자체가 계산되지 않고, UploadAssetStrategy.
    prefers_video()가 scene 위치와 무관하게 직접 쓰인다 - 이게 바로
    Sprint100-3이 "켜져 있을 때" 고친 정책 불일치가 재현되는 경로임을
    대조로 보여준다(Conclusion인 scene3도 그대로 True가 된다).
    """

    def setUp(self):
        original_flag = config.ENABLE_MOTION_CONTRACT
        config.ENABLE_MOTION_CONTRACT = False
        self.addCleanup(setattr, config, "ENABLE_MOTION_CONTRACT", original_flag)

    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_kill_switch_off_preserves_pre_sprint100_2_behavior(
        self, mock_integrate, mock_select_ai_priority,
    ):
        collect_assets(SAMPLE_SCENES, "output/proj", asset_strategy="upload")

        for call in mock_integrate.call_args_list:
            self.assertNotIn("motion_contract", call.args[0])
            self.assertNotIn("max_assets", call.kwargs)

        by_scene = {
            call.args[0]["scene"]: call.kwargs.get("prefer_video")
            for call in mock_integrate.call_args_list
        }

        self.assertFalse(by_scene[1])
        self.assertTrue(by_scene[2])
        # 대조 포인트: Motion Contract 없이는 Conclusion 위치 오버라이드가
        # 없어 scene3도 scene2와 동일하게 True가 된다.
        self.assertTrue(by_scene[3])

    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_no_asset_strategy_omits_prefer_video_kwarg(
        self, mock_integrate, mock_select_ai_priority,
    ):
        collect_assets(SAMPLE_SCENES, "output/proj")

        for call in mock_integrate.call_args_list:
            self.assertNotIn("prefer_video", call.kwargs)


if __name__ == "__main__":
    unittest.main()
