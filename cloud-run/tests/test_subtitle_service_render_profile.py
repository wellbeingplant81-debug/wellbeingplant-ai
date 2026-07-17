"""
Sprint122 (RED) - Subtitle Layout이 render_profile의 width에 따라
분기한다.

기존 SAFE_AREA_MAX_LINE_WIDTH는 VIDEO_WIDTH(1080, Shorts) 기준으로
import 시점에 한 번 계산된 모듈 상수였다. 이를 순수 함수
safe_area_max_line_width(width)로 일반화하고(기존 상수 값은 그대로
safe_area_max_line_width(VIDEO_WIDTH)로 재정의 - 하위 호환), create_
subtitle(project_path, render_profile=None)이 render_profile의 width
(없으면 VIDEO_WIDTH)로 계산한 max_line_width를 wrap_to_safe_lines()에
넘긴다.

subtitle_font_size/subtitle_margin_v(ffmpeg force_style)는 create_
subtitle()이 아니라 final_video_service.merge_video_audio()(step05)의
책임이라 여기서는 다루지 않는다 - test_final_video_service_render_
profile.py 참고.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.subtitle_service import (
    SAFE_AREA_MAX_LINE_WIDTH,
    VIDEO_WIDTH,
    create_subtitle,
    safe_area_max_line_width,
)
from app.services.render_profile import RenderProfile


class TestSafeAreaMaxLineWidthFunction(unittest.TestCase):

    def test_default_width_matches_existing_module_constant(self):
        self.assertEqual(safe_area_max_line_width(VIDEO_WIDTH), SAFE_AREA_MAX_LINE_WIDTH)

    def test_wider_canvas_allows_more_characters_per_line(self):
        longform_width = RenderProfile.get("longform")["width"]
        self.assertGreater(
            safe_area_max_line_width(longform_width),
            safe_area_max_line_width(VIDEO_WIDTH),
        )


class TestCreateSubtitleRenderProfile(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_path = os.path.join(self.tmp_dir, "project")
        os.makedirs(os.path.join(self.project_path, "audio", "scenes"))
        os.makedirs(os.path.join(self.project_path, "images"))

        scenes = [
            {"scene": 1, "narration": "안녕하세요.", "image_prompt": "p1"},
        ]

        with open(os.path.join(self.project_path, "script.json"), "w", encoding="utf-8") as f:
            json.dump({"scenes": scenes}, f, ensure_ascii=False)

        audio_path = os.path.join(self.project_path, "audio", "scenes", "scene1.mp3")
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", "2.0",
             "-i", "anullsrc=r=44100:cl=mono", "-c:a", "libmp3lame", audio_path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("app.services.subtitle_service.wrap_to_safe_lines", side_effect=lambda text, **kwargs: text)
    def test_default_render_profile_uses_existing_max_line_width(self, mock_wrap):
        create_subtitle(self.project_path)

        _, kwargs = mock_wrap.call_args
        self.assertEqual(kwargs["max_line_width"], SAFE_AREA_MAX_LINE_WIDTH)

    @patch("app.services.subtitle_service.wrap_to_safe_lines", side_effect=lambda text, **kwargs: text)
    def test_longform_render_profile_uses_wider_max_line_width(self, mock_wrap):
        longform = RenderProfile.get("longform")

        create_subtitle(self.project_path, render_profile=longform)

        _, kwargs = mock_wrap.call_args
        self.assertEqual(kwargs["max_line_width"], safe_area_max_line_width(longform["width"]))
        self.assertGreater(kwargs["max_line_width"], SAFE_AREA_MAX_LINE_WIDTH)


if __name__ == "__main__":
    unittest.main()
