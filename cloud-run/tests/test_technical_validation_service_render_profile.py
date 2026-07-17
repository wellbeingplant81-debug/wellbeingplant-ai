"""
Sprint123 (GREEN) - technical_validation_service가 render_profile을
받으면 Longform 산출물 파일명(final_longform.mp4/longform.mp4/
thumbnail_longform.png)을 찾고, 이미지 방향 기대치도 뒤집는다
(Shorts=portrait 기대, Longform=landscape 기대). render_profile을
안 넘기면(기본값 None) 기존과 100% 동일하다.
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

from app.services import technical_validation_service as tvs
from app.services.render_profile import RenderProfile


LONGFORM = RenderProfile.get("longform")


class TestCheckRequiredFilesRenderProfile(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name
        os.makedirs(os.path.join(self.project_path, "video"))
        os.makedirs(os.path.join(self.project_path, "audio"))
        os.makedirs(os.path.join(self.project_path, "subtitle"))

        for rel in [
            "script.json",
            os.path.join("audio", "voice.mp3"),
            os.path.join("audio", "final_audio.mp3"),
            os.path.join("subtitle", "subtitle.srt"),
        ]:
            open(os.path.join(self.project_path, rel), "wb").close()

    def test_default_looks_for_short_filenames(self):
        open(os.path.join(self.project_path, "video", "short.mp4"), "wb").close()
        open(os.path.join(self.project_path, "video", "final_short.mp4"), "wb").close()
        open(os.path.join(self.project_path, "thumbnail.png"), "wb").close()

        result = tvs._check_required_files(self.project_path, scene_count=0)
        self.assertTrue(result["passed"])

    def test_longform_looks_for_longform_filenames(self):
        open(os.path.join(self.project_path, "video", "longform.mp4"), "wb").close()
        open(os.path.join(self.project_path, "video", "final_longform.mp4"), "wb").close()
        open(os.path.join(self.project_path, "thumbnail_longform.png"), "wb").close()

        result = tvs._check_required_files(
            self.project_path, scene_count=0, render_profile=LONGFORM,
        )
        self.assertTrue(result["passed"])

    def test_longform_does_not_accept_shorts_filenames(self):
        # short.mp4/thumbnail.png만 있고 longform 전용 파일이 없으면
        # Longform 기준으로는 실패해야 한다 - 서로 다른 산출물이다.
        open(os.path.join(self.project_path, "video", "short.mp4"), "wb").close()
        open(os.path.join(self.project_path, "video", "final_short.mp4"), "wb").close()
        open(os.path.join(self.project_path, "thumbnail.png"), "wb").close()

        result = tvs._check_required_files(
            self.project_path, scene_count=0, render_profile=LONGFORM,
        )
        self.assertFalse(result["passed"])


class TestCheckImageResolutionOrientation(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name
        os.makedirs(os.path.join(self.project_path, "images"))

    def test_default_warns_on_landscape_image(self):
        Image.new("RGB", (1920, 1080)).save(
            os.path.join(self.project_path, "images", "scene1.png"),
        )
        result = tvs._check_image_resolution(self.project_path, scene_count=1)
        self.assertTrue(any("portrait" in w for w in result["warnings"]))

    def test_longform_warns_on_portrait_image(self):
        Image.new("RGB", (1080, 1920)).save(
            os.path.join(self.project_path, "images", "scene1.png"),
        )
        result = tvs._check_image_resolution(
            self.project_path, scene_count=1, render_profile=LONGFORM,
        )
        self.assertTrue(any("landscape" in w for w in result["warnings"]))

    def test_longform_does_not_warn_on_landscape_image(self):
        Image.new("RGB", (1920, 1080)).save(
            os.path.join(self.project_path, "images", "scene1.png"),
        )
        result = tvs._check_image_resolution(
            self.project_path, scene_count=1, render_profile=LONGFORM,
        )
        self.assertEqual(result["warnings"], [])


if __name__ == "__main__":
    unittest.main()
