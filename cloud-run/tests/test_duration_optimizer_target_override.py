"""
Sprint94 (RED) - Duration Optimizer target_duration/tolerance override.

optimize_scene_audio()에 optional 파라미터 target_duration/tolerance를
추가한다(기본값 = 기존 모듈 상수 TARGET_DURATION_SECONDS/TOLERANCE_
SECONDS와 동일). 파라미터를 넘기지 않으면 지금까지와 완전히 동일하게
43~47초 범위로 판정하고, 넘기면 그 값 기준(target±tolerance)으로
판정이 바뀐다. 실제 ffmpeg 호출(append_silence/speed_up_audio)은
mocking해 파라미터 전달/판정 로직만 검증한다. 아직 구현이 없으므로
(RED) 모든 테스트는 실패해야 정상이다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.duration_optimizer import optimize_scene_audio


SIX_PATHS = [f"scene{i}.mp3" for i in range(1, 7)]


class TestOptimizeSceneAudioTargetOverride(unittest.TestCase):

    @patch("app.services.duration_optimizer.get_audio_duration")
    def test_default_call_still_uses_43_47_range(self, mock_duration):
        # 45.0s 총합 - 파라미터를 안 넘기면 기존 43~47 기준 그대로 "none".
        mock_duration.side_effect = [7.5] * 6

        result = optimize_scene_audio(SIX_PATHS)

        self.assertEqual(result["action"], "none")

    @patch("app.services.duration_optimizer.get_audio_duration")
    def test_override_target_55_total_54_is_in_range(self, mock_duration):
        # 54.0s 총합 - target=55/tolerance=2(53~57) 기준으로는 "none"이어야
        # 하지만, 기존 43~47 기준으로는 범위 밖(over)이었을 값.
        mock_duration.side_effect = [9.0] * 6

        result = optimize_scene_audio(SIX_PATHS, target_duration=55.0, tolerance=2.0)

        self.assertEqual(result["action"], "none")

    @patch("app.services.duration_optimizer.speed_up_audio")
    @patch("app.services.duration_optimizer.append_silence")
    @patch("app.services.duration_optimizer.os.replace")
    @patch("app.services.duration_optimizer.get_audio_duration")
    def test_override_target_55_total_45_now_needs_expand(
        self, mock_duration, mock_replace, mock_append, mock_speed_up,
    ):
        # 45.0s 총합 - 기존 기준(43~47)으로는 "none"이었을 값이지만,
        # target=55/tolerance=2(53~57) 기준으로는 "expand"가 되어야 한다
        # (override가 실제로 판정을 바꾼다는 것을 증명). 45+3(pad cap)=48은
        # 여전히 53 미만이라 2차 cascade(다른 scene 감속)도 발동하므로
        # speed_up_audio도 함께 mocking한다.
        mock_duration.side_effect = [7.5] * 6

        result = optimize_scene_audio(SIX_PATHS, target_duration=55.0, tolerance=2.0)

        self.assertEqual(result["action"], "expand")

    @patch("app.services.duration_optimizer.speed_up_audio")
    @patch("app.services.duration_optimizer.os.replace")
    @patch("app.services.duration_optimizer.get_audio_duration")
    def test_override_target_55_total_60_needs_contract(
        self, mock_duration, mock_replace, mock_speed_up,
    ):
        # 60.0s 총합 - target=55/tolerance=2(53~57) 기준으로 초과 -> contract.
        mock_duration.side_effect = [10.0] * 6

        result = optimize_scene_audio(SIX_PATHS, target_duration=55.0, tolerance=2.0)

        self.assertEqual(result["action"], "contract")

    @patch("app.services.duration_optimizer.get_audio_duration")
    def test_override_tolerance_widens_range(self, mock_duration):
        # 45.0s 총합, target=45(기존과 동일)이지만 tolerance=5(40~50)로
        # 넓히면 여전히 "none"이어야 한다 - tolerance override 자체가
        # 반영되는지 별도로 확인.
        mock_duration.side_effect = [7.5] * 6

        result = optimize_scene_audio(SIX_PATHS, target_duration=45.0, tolerance=5.0)

        self.assertEqual(result["action"], "none")


if __name__ == "__main__":
    unittest.main()
