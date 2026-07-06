import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.final_video_service import merge_video_audio


class TestMergeVideoAudio(unittest.TestCase):

    @patch("app.services.final_video_service.subprocess.run")
    def test_force_style_disables_auto_wrap(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        merge_video_audio("output/proj")

        command = mock_run.call_args[0][0]
        vf_index = command.index("-vf")
        vf_value = command[vf_index + 1]

        self.assertIn("WrapStyle=2", vf_value)

    @patch("app.services.final_video_service.subprocess.run")
    def test_raises_on_ffmpeg_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

        with self.assertRaises(Exception):
            merge_video_audio("output/proj")


if __name__ == "__main__":
    unittest.main()
