"""
Sprint122 (RED) - Longform Production Profile Foundation.

RenderProfile은 production_profile.py(development/upload - duration_
target/tts_provider/asset_strategy 축)와 완전히 분리된 새 축이다 -
과거 3번(scene_role/scene_shot/scene_intent, scene_planner_service.
purpose) 반복된 naming-collision을 피하기 위해 별도 모듈로 둔다.

"shorts"가 기본값이고, 오늘의 하드코딩된 값(kenburns.VIDEO_WIDTH=1080/
VIDEO_HEIGHT=1920, image_service의 aspect_ratio="9:16", final_video_
service의 FontSize=18/MarginV=115)과 정확히 같아야 Regression Zero가
성립한다. "longform"은 16:9(1920x1080)이고, subtitle_font_size/
subtitle_margin_v는 이번 스프린트에서 Shorts 값을 그대로 물려받는다
(인터페이스만 완성 - 실측 재보정은 Sprint123 범위, Sprint68-1과 동일한
방법론으로 진행 예정).
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.render_profile import DEFAULT_RENDER_PROFILE, RenderProfile


class TestRenderProfileDefault(unittest.TestCase):

    def test_default_profile_name_is_shorts(self):
        self.assertEqual(DEFAULT_RENDER_PROFILE, "shorts")

    def test_none_resolves_to_shorts(self):
        self.assertEqual(RenderProfile.get(None)["profile"], "shorts")

    def test_unknown_profile_name_falls_back_to_shorts(self):
        self.assertEqual(RenderProfile.get("does_not_exist")["profile"], "shorts")


class TestShortsProfileMatchesExistingHardcodedValues(unittest.TestCase):
    """Regression Zero 근거 - 이 값들은 kenburns.VIDEO_WIDTH/HEIGHT,
    image_service.py의 aspect_ratio="9:16", final_video_service.py의
    FontSize=18/MarginV=115와 정확히 같아야 한다."""

    def setUp(self):
        self.shorts = RenderProfile.get("shorts")

    def test_width_height(self):
        self.assertEqual(self.shorts["width"], 1080)
        self.assertEqual(self.shorts["height"], 1920)

    def test_image_aspect_ratio(self):
        self.assertEqual(self.shorts["image_aspect_ratio"], "9:16")

    def test_thumbnail_aspect_ratio(self):
        self.assertEqual(self.shorts["thumbnail_aspect_ratio"], "9:16")

    def test_subtitle_font_size_and_margin(self):
        self.assertEqual(self.shorts["subtitle_font_size"], 18)
        self.assertEqual(self.shorts["subtitle_margin_v"], 115)


class TestLongformProfile(unittest.TestCase):

    def setUp(self):
        self.longform = RenderProfile.get("longform")

    def test_width_height(self):
        self.assertEqual(self.longform["width"], 1920)
        self.assertEqual(self.longform["height"], 1080)

    def test_image_aspect_ratio(self):
        self.assertEqual(self.longform["image_aspect_ratio"], "16:9")

    def test_thumbnail_aspect_ratio(self):
        self.assertEqual(self.longform["thumbnail_aspect_ratio"], "16:9")

    def test_return_type_is_dict(self):
        self.assertIsInstance(self.longform, dict)


if __name__ == "__main__":
    unittest.main()
