"""
Sprint64 - Scene Timeline 단일화.

Sprint63까지 scene 경계는 두 곳에서 따로 계산됐다:

  video_builder    moviepy AudioFileClip.duration + _apply_duration_limits()
  subtitle_service ffprobe(get_audio_duration)    + 원본 누적

측정 방식도 변환 규칙도 달라서 경계가 어긋났다(실측):

  기존 production(mp3)          최대 62ms   - 측정 방식 차이만으로
  Sprint63 WAV 전환 후            0ms       - 부수효과로 해소, 구조는 그대로
  _apply_duration_limits 발동 시  최대 800ms - 잠복 결함

최종 MP4의 오디오는 scene 오디오를 실제 길이 그대로 이어붙인 것이므로,
scene 경계의 진실은 "나레이션 오디오 누적값" 하나뿐이다. 이 테스트들은
그 단일 타임라인을 고정한다.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import audio_policy
from app.services import scene_timeline


TOLERANCE_SECONDS = 0.020


class TestBuildTimeline(unittest.TestCase):

    def _project(self, tmp_dir, durations):
        """duration 목록에 대응하는 더미 scene 오디오 파일을 만든다.
        길이는 get_audio_duration을 패치해 주입하므로 내용은 무의미하다."""

        scenes_dir = os.path.join(tmp_dir, "audio", "scenes")
        os.makedirs(scenes_dir, exist_ok=True)

        scenes = []

        for index, _ in enumerate(durations, start=1):
            path = os.path.join(
                scenes_dir, audio_policy.scene_audio_filename(index),
            )
            with open(path, "wb") as f:
                f.write(b"stub")
            scenes.append({"scene": index, "narration": "x"})

        return scenes

    def _build(self, tmp_dir, durations, scenes):
        by_path = {}
        for index, duration in enumerate(durations, start=1):
            by_path[
                os.path.join(
                    tmp_dir, "audio", "scenes",
                    audio_policy.scene_audio_filename(index),
                )
            ] = duration

        with patch.object(
            scene_timeline, "get_audio_duration", lambda p: by_path[p],
        ):
            return scene_timeline.build_timeline(tmp_dir, scenes)

    def test_slots_are_contiguous_with_no_gap_or_overlap(self):
        durations = [7.6, 7.0, 5.68, 8.76, 6.68, 5.32]

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenes = self._project(tmp_dir, durations)
            timeline = self._build(tmp_dir, durations, scenes)

        self.assertEqual(len(timeline), len(durations))

        self.assertAlmostEqual(timeline[0]["start"], 0.0, places=9)

        for previous, current in zip(timeline, timeline[1:]):
            self.assertAlmostEqual(
                previous["end"], current["start"], places=9,
            )

    def test_boundaries_equal_cumulative_audio_durations(self):
        durations = [7.6, 7.0, 5.68, 8.76, 6.68, 5.32]

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenes = self._project(tmp_dir, durations)
            timeline = self._build(tmp_dir, durations, scenes)

        expected = 0.0
        for slot, duration in zip(timeline, durations):
            expected += duration
            self.assertLess(
                abs(slot["end"] - expected), TOLERANCE_SECONDS,
            )

    def test_short_scene_does_not_move_any_boundary(self):
        """Sprint55의 duration clamp가 경계를 밀던 케이스. 이제는 어떤
        scene이 아무리 짧아도 경계가 오디오를 그대로 따라야 한다."""

        durations = [1.2, 8.0, 8.0, 8.0, 8.0, 8.0]

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenes = self._project(tmp_dir, durations)
            timeline = self._build(tmp_dir, durations, scenes)

        expected = 0.0
        for slot, duration in zip(timeline, durations):
            expected += duration
            self.assertLess(
                abs(slot["end"] - expected), TOLERANCE_SECONDS,
                f"scene {slot['scene']} 경계가 오디오에서 벗어남",
            )

        self.assertAlmostEqual(timeline[0]["duration"], 1.2, places=9)

    def test_very_long_scene_does_not_move_any_boundary(self):
        durations = [5.0, 5.0, 30.0, 5.0]

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenes = self._project(tmp_dir, durations)
            timeline = self._build(tmp_dir, durations, scenes)

        self.assertAlmostEqual(timeline[2]["duration"], 30.0, places=9)
        self.assertAlmostEqual(timeline[-1]["end"], 45.0, places=9)

    def test_total_equals_sum_of_audio(self):
        durations = [7.6, 7.0, 5.68, 8.76, 6.68, 8.32]

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenes = self._project(tmp_dir, durations)
            timeline = self._build(tmp_dir, durations, scenes)

        self.assertAlmostEqual(
            scene_timeline.timeline_total(timeline), sum(durations), places=9,
        )

    def test_scenes_are_ordered_by_scene_number(self):
        durations = [3.0, 4.0, 5.0]

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenes = self._project(tmp_dir, durations)
            shuffled = [scenes[2], scenes[0], scenes[1]]
            timeline = self._build(tmp_dir, durations, shuffled)

        self.assertEqual([s["scene"] for s in timeline], [1, 2, 3])

    def test_missing_audio_file_raises(self):
        durations = [3.0, 4.0]

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenes = self._project(tmp_dir, durations)
            os.remove(
                os.path.join(
                    tmp_dir, "audio", "scenes",
                    audio_policy.scene_audio_filename(2),
                )
            )

            with self.assertRaises(Exception):
                scene_timeline.build_timeline(tmp_dir, scenes)


class TestKenBurnsMotionIsModeratedByDuration(unittest.TestCase):
    """Sprint64 R4 - Sprint55가 duration clamp로 막으려던 것은 "짧은
    scene에서 Ken Burns 모션이 부자연스럽게 빨라지는 것"이었다. 경계를
    옮기는 대신 모션 강도 자체를 duration에 맞춰 줄여 같은 목적을
    달성한다 - 이러면 타임라인은 오디오를 그대로 따르면서도 화면은
    안정적이다."""

    def test_short_scene_gets_reduced_zoom_intensity(self):
        from app.services.kenburns import moderate_zoom_intensity

        base = 0.10

        short = moderate_zoom_intensity(base, duration=0.5)
        normal = moderate_zoom_intensity(base, duration=8.0)

        self.assertLess(short, normal)
        self.assertAlmostEqual(normal, base, places=9)

    def test_zoom_rate_stays_within_cap_for_any_duration(self):
        from app.services.kenburns import (
            moderate_zoom_intensity,
            MAX_ZOOM_RATE_PER_SECOND,
        )

        for duration in (0.2, 0.5, 1.0, 2.0, 5.0, 12.0):
            with self.subTest(duration=duration):
                intensity = moderate_zoom_intensity(0.10, duration)
                self.assertLessEqual(
                    intensity / duration, MAX_ZOOM_RATE_PER_SECOND + 1e-9,
                )

    def test_short_scene_gets_reduced_pan_travel(self):
        from app.services.kenburns import moderate_pan_travel

        base = 160.0

        short = moderate_pan_travel(base, duration=0.5)
        normal = moderate_pan_travel(base, duration=8.0)

        self.assertLess(short, normal)
        self.assertAlmostEqual(normal, base, places=9)

    def test_pan_rate_stays_within_cap_for_any_duration(self):
        from app.services.kenburns import (
            moderate_pan_travel,
            MAX_PAN_RATE_PX_PER_SECOND,
        )

        for duration in (0.2, 0.5, 1.0, 2.0, 5.0, 12.0):
            with self.subTest(duration=duration):
                travel = moderate_pan_travel(160.0, duration)
                self.assertLessEqual(
                    travel / duration, MAX_PAN_RATE_PX_PER_SECOND + 1e-9,
                )

    def test_zero_duration_is_handled_without_dividing_by_zero(self):
        from app.services.kenburns import (
            moderate_pan_travel,
            moderate_zoom_intensity,
        )

        self.assertGreaterEqual(moderate_zoom_intensity(0.10, 0.0), 0.0)
        self.assertGreaterEqual(moderate_pan_travel(160.0, 0.0), 0.0)


class TestNoIndependentTimelineComputation(unittest.TestCase):
    """구조 회귀 방지: video_builder와 subtitle_service가 각자 다시
    scene 길이를 재기 시작하면 Sprint64가 되돌려진다."""

    def test_video_builder_no_longer_exposes_duration_limits(self):
        from app.services import video_builder

        self.assertFalse(
            hasattr(video_builder, "_apply_duration_limits"),
            "duration 재분배는 경계를 이동시키므로 제거되어야 한다",
        )

    def test_video_builder_uses_the_shared_timeline(self):
        from app.services import video_builder

        self.assertIs(video_builder.build_timeline, scene_timeline.build_timeline)

    def test_subtitle_service_uses_the_shared_timeline(self):
        from app.services import subtitle_service

        self.assertIs(
            subtitle_service.build_timeline, scene_timeline.build_timeline,
        )


if __name__ == "__main__":
    unittest.main()
