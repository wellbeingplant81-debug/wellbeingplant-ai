import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from PIL import Image

from app.services import kenburns
from app.services.kenburns import (
    MOTIONS,
    _directional_pan_offsets,
    _pick_motion,
)


def _make_test_image(path, size=(200, 400)):
    Image.new("RGB", size, color=(120, 130, 140)).save(path)


class TestMotionsList(unittest.TestCase):
    """Sprint70-1 - Ken Burns 다양화. pan_horizontal/pan_vertical
    (내부에서 방향이 랜덤이던) 두 모션을, 방향이 이름에 고정된 4개
    (pan_left/pan_right/pan_up/pan_down)로 나눈다 - zoom_in/zoom_out과
    합쳐 총 6개."""

    def test_contains_exactly_six_motions(self):
        self.assertEqual(len(MOTIONS), 6)

    def test_contains_expected_motion_names(self):
        self.assertEqual(
            set(MOTIONS),
            {"zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"},
        )

    def test_no_longer_contains_undirected_pan_names(self):
        self.assertNotIn("pan_horizontal", MOTIONS)
        self.assertNotIn("pan_vertical", MOTIONS)


class TestPickMotionExclude(unittest.TestCase):
    """Sprint70-1 - 동일 scene 안에서 연속 asset이 같은 모션을 쓰지
    않도록, 호출자가 이미 쓴 모션 집합을 exclude로 넘길 수 있다."""

    def setUp(self):
        kenburns._last_motion = None
        self.addCleanup(setattr, kenburns, "_last_motion", None)

    def test_exclude_prevents_those_motions_from_being_picked(self):
        # 매 반복 전에 _last_motion을 리셋한다 - _pick_motion()이 고를
        # 때마다 전역 _last_motion을 그 결과로 갱신하므로(다음 회차의
        # 회피 대상이 바뀜), 리셋 없이 반복하면 이 테스트가 검증하려는
        # "exclude 자체의 효과"가 아니라 그 부작용을 테스트하게 된다.
        exclude = set(MOTIONS) - {"zoom_in"}
        for _ in range(20):
            kenburns._last_motion = None
            self.assertEqual(_pick_motion(exclude=exclude), "zoom_in")

    def test_all_motions_excluded_falls_back_to_full_list(self):
        # 제외할 게 하나도 안 남으면(예: 4개 asset, 이미 4개 다 다르게
        # 썼는데 5번째가 필요한 극단적 상황) 예외 없이 전체 목록에서
        # 다시 고른다.
        motion = _pick_motion(exclude=set(MOTIONS))
        self.assertIn(motion, MOTIONS)

    def test_no_exclude_still_avoids_immediately_previous_global_motion(self):
        # exclude를 안 넘겨도 기존 전역 _last_motion 회피 동작은 유지된다.
        for _ in range(20):
            kenburns._last_motion = "zoom_in"
            self.assertNotEqual(_pick_motion(), "zoom_in")

    def test_exclude_and_global_last_motion_are_combined(self):
        exclude = {"pan_left", "pan_right"}
        for _ in range(20):
            kenburns._last_motion = "zoom_out"
            motion = _pick_motion(exclude=exclude)
            self.assertNotIn(motion, exclude)
            self.assertNotEqual(motion, "zoom_out")

    def test_sequential_calls_with_growing_exclude_produce_all_distinct_motions(self):
        # _build_scene_clip()이 실제로 하는 것과 동일한 패턴: 매번
        # 지금까지 쓴 모션을 exclude에 누적하면서 뽑으면, asset 개수가
        # MOTIONS 개수 이하인 한 항상 서로 다른 모션이 나와야 한다.
        used = []
        for _ in range(len(MOTIONS)):
            motion = _pick_motion(exclude=set(used))
            self.assertNotIn(motion, used)
            used.append(motion)

        self.assertEqual(len(set(used)), len(MOTIONS))


class TestDirectionalPanOffsets(unittest.TestCase):
    """Sprint70-1 - pan_left/right/up/down은 방향이 이름에 고정돼야
    한다(기존 pan_horizontal/vertical처럼 내부에서 랜덤으로 뒤집히면
    안 됨)."""

    def test_negative_direction_moves_toward_negative_slack(self):
        for _ in range(20):
            start, end = _directional_pan_offsets(slack=100.0, travel=60.0, direction=-1)
            self.assertLess(end, start)
            self.assertAlmostEqual(start - end, 60.0, places=6)

    def test_positive_direction_moves_toward_zero(self):
        for _ in range(20):
            start, end = _directional_pan_offsets(slack=100.0, travel=60.0, direction=1)
            self.assertGreater(end, start)
            self.assertAlmostEqual(end - start, 60.0, places=6)

    def test_offsets_stay_within_slack_bounds(self):
        for direction in (-1, 1):
            for _ in range(20):
                start, end = _directional_pan_offsets(slack=100.0, travel=60.0, direction=direction)
                for value in (start, end):
                    self.assertLessEqual(value, 0.0)
                    self.assertGreaterEqual(value, -100.0)

    def test_travel_clamped_to_slack(self):
        start, end = _directional_pan_offsets(slack=30.0, travel=999.0, direction=-1)
        self.assertAlmostEqual(abs(end - start), 30.0, places=6)

    def test_zero_slack_is_degenerate_but_safe(self):
        start, end = _directional_pan_offsets(slack=0.0, travel=60.0, direction=-1)
        self.assertEqual(start, 0.0)
        self.assertEqual(end, 0.0)


class TestBuildKenburnsClipMotionParam(unittest.TestCase):
    """Sprint70-1 - build_kenburns_clip()이 motion을 명시적으로 받으면
    그 모션을 그대로 쓰고(자동 선택 안 함), 안 받으면(기본값 None)
    기존처럼 자동 선택한다 - 완전히 하위 호환."""

    def setUp(self):
        kenburns._last_motion = None
        self.addCleanup(setattr, kenburns, "_last_motion", None)

        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.image_path = os.path.join(self._tmp_dir.name, "test.png")
        _make_test_image(self.image_path)

    def test_explicit_motion_is_used_without_calling_pick_motion(self):
        with patch("app.services.kenburns._pick_motion") as mock_pick:
            kenburns.build_kenburns_clip(self.image_path, 2.0, motion="zoom_in")
            mock_pick.assert_not_called()

    def test_no_motion_arg_still_auto_picks(self):
        with patch(
            "app.services.kenburns._pick_motion", return_value="zoom_out",
        ) as mock_pick:
            kenburns.build_kenburns_clip(self.image_path, 2.0)
            mock_pick.assert_called_once()

    def test_explicit_motion_updates_last_motion_global(self):
        kenburns.build_kenburns_clip(self.image_path, 2.0, motion="pan_up")
        self.assertEqual(kenburns._last_motion, "pan_up")

    def test_each_motion_renders_without_error(self):
        for motion in MOTIONS:
            with self.subTest(motion=motion):
                clip = kenburns.build_kenburns_clip(
                    self.image_path, 1.0, motion=motion,
                )
                self.assertAlmostEqual(clip.duration, 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
