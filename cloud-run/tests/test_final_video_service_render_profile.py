"""
Sprint122 (RED) - merge_video_audio()의 ffmpeg force_style(FontSize/
MarginV)이 render_profile(기본값 None)에서 값을 읽는다. 안 넘기면
기존 하드코딩 값(FontSize=18, MarginV=115 - Sprint68-1 실측)과 100%
동일해야 한다.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.final_video_service import merge_video_audio
from app.services.render_profile import RenderProfile


def _vf_value(mock_run):
    command = mock_run.call_args[0][0]
    vf_index = command.index("-vf")
    return command[vf_index + 1]


class TestMergeVideoAudioRenderProfile(unittest.TestCase):

    @patch("app.services.final_video_service.subprocess.run")
    def test_default_matches_existing_hardcoded_values(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        merge_video_audio("output/proj")

        vf_value = _vf_value(mock_run)
        self.assertIn("FontSize=18", vf_value)
        self.assertIn("MarginV=115", vf_value)

    @patch("app.services.final_video_service.subprocess.run")
    def test_render_profile_overrides_font_size_and_margin(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        longform = RenderProfile.get("longform")
        merge_video_audio("output/proj", render_profile=longform)

        vf_value = _vf_value(mock_run)
        self.assertIn(f"FontSize={longform['subtitle_font_size']}", vf_value)
        self.assertIn(f"MarginV={longform['subtitle_margin_v']}", vf_value)


if __name__ == "__main__":
    unittest.main()
