"""
Sprint123 (GREEN) - merge_video_audio()가 render_profile에 따라 입력/
출력 파일명을 분기한다 (Shorts: short.mp4/final_short.mp4 그대로,
Longform: longform.mp4/final_longform.mp4).
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


LONGFORM = RenderProfile.get("longform")


class TestMergeVideoAudioLongformFilenames(unittest.TestCase):

    @patch("app.services.final_video_service.subprocess.run")
    def test_default_uses_existing_short_filenames(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        output_path = merge_video_audio("output/proj")

        command = mock_run.call_args[0][0]
        video_input = command[command.index("-i") + 1]

        self.assertIn("short.mp4", video_input)
        self.assertNotIn("longform", video_input)
        self.assertTrue(output_path.endswith("final_short.mp4"))

    @patch("app.services.final_video_service.subprocess.run")
    def test_longform_uses_distinct_filenames(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        output_path = merge_video_audio("output/proj", render_profile=LONGFORM)

        command = mock_run.call_args[0][0]
        video_input = command[command.index("-i") + 1]

        self.assertTrue(video_input.endswith(os.path.join("video", "longform.mp4")))
        self.assertTrue(output_path.endswith("final_longform.mp4"))


if __name__ == "__main__":
    unittest.main()
