"""
Sprint122 (RED) - Camera Motion(Ken Burns)이 render_profile의 canvas
크기(width/height)에 맞춰 분기한다.

build_kenburns_clip()/_fit_scale()이 width/height를 옵션으로 받는다
(기본값 None -> 기존 모듈 상수 VIDEO_WIDTH/VIDEO_HEIGHT와 100% 동일 -
완전히 하위 호환). video_builder.py는 render_profile["width"]/["height"]
를 여기로 그대로 흘려보낸다(test_video_builder_render_profile.py 참고).
"""

import os
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import kenburns
from app.services.kenburns import MOTIONS, VIDEO_HEIGHT, VIDEO_WIDTH, _fit_scale


def _make_test_image(path, size=(200, 400)):
    Image.new("RGB", size, color=(120, 130, 140)).save(path)


class TestFitScaleCustomCanvas(unittest.TestCase):

    def test_default_canvas_matches_module_constants(self):
        self.assertEqual(_fit_scale(200, 400), _fit_scale(200, 400, VIDEO_WIDTH, VIDEO_HEIGHT))

    def test_custom_canvas_changes_scale(self):
        default_scale = _fit_scale(200, 400)
        longform_scale = _fit_scale(200, 400, width=1920, height=1080)
        self.assertNotEqual(default_scale, longform_scale)


class TestBuildKenburnsClipCustomCanvas(unittest.TestCase):

    def setUp(self):
        kenburns._last_motion = None
        self.addCleanup(setattr, kenburns, "_last_motion", None)

        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.image_path = os.path.join(self._tmp_dir.name, "test.png")
        _make_test_image(self.image_path)

    def test_no_width_height_args_uses_existing_canvas(self):
        clip = kenburns.build_kenburns_clip(self.image_path, 1.0, motion="zoom_in")
        self.addCleanup(clip.close)
        self.assertEqual(clip.size, (VIDEO_WIDTH, VIDEO_HEIGHT))

    def test_custom_width_height_produces_matching_canvas(self):
        clip = kenburns.build_kenburns_clip(
            self.image_path, 1.0, motion="zoom_in", width=1920, height=1080,
        )
        self.addCleanup(clip.close)
        self.assertEqual(clip.size, (1920, 1080))

    def test_every_motion_respects_custom_canvas(self):
        for motion in MOTIONS:
            with self.subTest(motion=motion):
                clip = kenburns.build_kenburns_clip(
                    self.image_path, 1.0, motion=motion, width=1920, height=1080,
                )
                self.addCleanup(clip.close)
                self.assertEqual(clip.size, (1920, 1080))


if __name__ == "__main__":
    unittest.main()
