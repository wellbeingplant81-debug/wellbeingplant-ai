import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.final_video_service import FINAL_CRF, merge_video_audio


class TestFinalEncodingContract(unittest.TestCase):
    """Sprint62 - Master Quality Render Pipeline. 최종 인코딩 품질은
    이번 Epic에서 건드리지 않는다(R4) - 화질 향상은 오직 video_builder의
    1차 인코딩 손실을 없애는 데서만 나와야, 실제로 무엇이 개선을
    만들었는지 측정할 수 있다. 이 테스트는 그 경계를 고정한다."""

    def test_final_crf_is_18(self):
        self.assertEqual(FINAL_CRF, 18)

    @patch("app.services.final_video_service.subprocess.run")
    def test_ffmpeg_command_uses_declared_crf(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        merge_video_audio("output/proj")

        command = mock_run.call_args[0][0]

        self.assertIn("-crf", command)
        self.assertEqual(
            command[command.index("-crf") + 1],
            str(FINAL_CRF),
        )


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
