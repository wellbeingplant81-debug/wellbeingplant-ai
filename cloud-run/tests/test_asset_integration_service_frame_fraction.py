"""
Sprint100-3.1 - 대표 프레임(20~40% 지점) 추출 헬퍼. 기존 _extract_
first_frame()(항상 0초)와 별개로, 영상 길이를 ffprobe로 구한 뒤 그
비율 지점을 ffmpeg -ss로 seek해서 프레임을 뽑는다.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_integration_service as svc


class TestGetVideoDurationSeconds(unittest.TestCase):

    @patch("app.services.asset_integration_service.subprocess.run")
    def test_parses_duration_from_ffprobe_stdout(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12.345000\n"
        mock_run.return_value = mock_result

        duration = svc._get_video_duration_seconds("video.mp4")

        self.assertAlmostEqual(duration, 12.345)


class TestExtractFrameAtFraction(unittest.TestCase):

    @patch("app.services.asset_integration_service._get_video_duration_seconds")
    @patch("app.services.asset_integration_service.subprocess.run")
    def test_seeks_to_fraction_of_duration(self, mock_run, mock_duration):
        mock_duration.return_value = 10.0
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        svc._extract_frame_at_fraction("video.mp4", "out.png", fraction=0.3)

        command = mock_run.call_args[0][0]
        self.assertIn("-ss", command)
        seek_index = command.index("-ss") + 1
        self.assertAlmostEqual(float(command[seek_index]), 3.0, places=1)

    @patch("app.services.asset_integration_service._get_video_duration_seconds")
    @patch("app.services.asset_integration_service.subprocess.run")
    def test_raises_on_ffmpeg_failure(self, mock_run, mock_duration):
        mock_duration.return_value = 10.0
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "boom"
        mock_run.return_value = mock_result

        with self.assertRaises(Exception):
            svc._extract_frame_at_fraction("video.mp4", "out.png")


if __name__ == "__main__":
    unittest.main()
