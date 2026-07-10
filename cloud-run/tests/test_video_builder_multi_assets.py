import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from moviepy.video.fx.CrossFadeIn import CrossFadeIn
from moviepy.video.fx.CrossFadeOut import CrossFadeOut

from app.services import asset_usage_planner
from app.services.video_builder import (
    ASSET_CROSSFADE_DURATION,
    _build_scene_clip,
    _resolve_asset_paths,
    _resolve_cut_durations,
    _split_duration_equally,
)


class TestResolveAssetPaths(unittest.TestCase):
    """
    Sprint62-3 - scene["assets"]의 모든 항목을 순서대로 반환한다
    (Scene을 여러 컷으로 재생하기 위한 목록). assets가 없거나
    비어있으면 기존 _resolve_asset_path()의 단일 결과를 그대로
    1개짜리 리스트로 반환한다(완전 하위 호환).
    """

    def test_multiple_assets_returns_all_paths_in_order(self):
        scene = {
            "scene": 1,
            "assets": [
                {"type": "image", "path": "a.png", "prompt": "p1"},
                {"type": "image", "path": "b.png", "prompt": "p2"},
                {"type": "image", "path": "c.png", "prompt": "p3"},
                {"type": "image", "path": "d.png", "prompt": "p4"},
            ],
        }

        result = _resolve_asset_paths("proj", scene)

        self.assertEqual(result, ["a.png", "b.png", "c.png", "d.png"])

    def test_single_asset_returns_single_item_list(self):
        scene = {
            "scene": 1,
            "assets": [{"type": "image", "path": "only.png", "prompt": "p"}],
        }

        result = _resolve_asset_paths("proj", scene)

        self.assertEqual(result, ["only.png"])

    def test_empty_assets_list_falls_back_to_asset_path(self):
        scene = {"scene": 2, "assets": [], "asset_path": "fallback.png"}

        result = _resolve_asset_paths("proj", scene)

        self.assertEqual(result, ["fallback.png"])

    def test_no_assets_key_falls_back_to_asset_path(self):
        scene = {"scene": 2, "asset_path": "fallback.png"}

        result = _resolve_asset_paths("proj", scene)

        self.assertEqual(result, ["fallback.png"])

    def test_no_assets_and_no_asset_path_falls_back_to_legacy_filename(self):
        scene = {"scene": 5}

        result = _resolve_asset_paths("proj", scene)

        self.assertEqual(result, [os.path.join("proj", "images", "scene5.png")])


class TestSplitDurationEqually(unittest.TestCase):
    """Scene duration을 asset 개수로 균등 분배한다. 합은 항상 원래
    scene duration과 일치해야 한다."""

    def test_count_one_returns_full_duration(self):
        result = _split_duration_equally(8.0, 1)
        self.assertEqual(result, [8.0])

    def test_count_four_splits_equally(self):
        result = _split_duration_equally(8.0, 4)

        self.assertEqual(len(result), 4)
        for value in result:
            self.assertAlmostEqual(value, 2.0, places=6)

    def test_total_duration_is_preserved(self):
        for total, count in [(8.0, 4), (7.0, 3), (12.5, 5), (2.0, 4)]:
            with self.subTest(total=total, count=count):
                result = _split_duration_equally(total, count)
                self.assertAlmostEqual(sum(result), total, places=6)


class TestBuildSceneClip(unittest.TestCase):
    """
    Sprint62-3 - video_builder가 scene당 여러 asset을 순차 재생하도록
    만든다. assets가 1개면 기존과 완전히 동일하게 build_kenburns_clip을
    한 번만 호출한다(concatenate_videoclips 호출 없음 - 기존 렌더링
    경로를 그대로 재사용). assets가 여러 개면 각 asset마다 Ken Burns
    clip을 만들고 순서대로 이어 붙인다.
    """

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_single_asset_uses_kenburns_directly_without_concatenation(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        mock_clip = MagicMock()
        mock_build_kenburns_clip.return_value = mock_clip

        _build_scene_clip(["a.png"], 8.0)

        mock_build_kenburns_clip.assert_called_once_with("a.png", 8.0)
        mock_concatenate_videoclips.assert_not_called()

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_multiple_assets_builds_one_kenburns_clip_per_asset(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        mock_build_kenburns_clip.side_effect = (
            lambda path, duration, motion=None: MagicMock()
        )

        asset_paths = ["a.png", "b.png", "c.png", "d.png"]
        _build_scene_clip(asset_paths, 8.0)

        self.assertEqual(mock_build_kenburns_clip.call_count, 4)
        mock_concatenate_videoclips.assert_called_once()

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_multiple_assets_split_scene_duration_equally(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        # Sprint70-1 - 컷 사이 crossfade(overlap)가 생기면서, 마지막
        # 컷을 제외한 나머지는 렌더 길이가 overlap만큼 늘어난다(scene
        # 경계 crossfade와 동일한 방식) - 하지만 "할당"(균등 분배)
        # 자체는 여전히 2.0씩이라는 사실은 _resolve_cut_durations()로
        # 직접 검증되며(TestResolveCutDurations), 이 테스트는 실제
        # 렌더 호출값이 그 할당 + overlap 보정과 일치하는지 본다.
        mock_build_kenburns_clip.side_effect = (
            lambda path, duration, motion=None: MagicMock()
        )

        asset_paths = ["a.png", "b.png", "c.png", "d.png"]
        _build_scene_clip(asset_paths, 8.0)

        called_durations = [
            call_args.args[1] for call_args in mock_build_kenburns_clip.call_args_list
        ]
        overlap = min(ASSET_CROSSFADE_DURATION, 2.0 / 2)

        self.assertEqual(len(called_durations), 4)
        for duration in called_durations[:-1]:
            self.assertAlmostEqual(duration, 2.0 + overlap, places=6)
        self.assertAlmostEqual(called_durations[-1], 2.0, places=6)

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_multiple_assets_passed_to_concatenate_in_order(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        created_clips = []

        def _side_effect(path, duration, motion=None):
            clip = MagicMock(name=f"clip_for_{path}")
            created_clips.append(clip)
            return clip

        mock_build_kenburns_clip.side_effect = _side_effect

        asset_paths = ["a.png", "b.png"]
        _build_scene_clip(asset_paths, 4.0)

        concatenated_clips = mock_concatenate_videoclips.call_args.args[0]
        self.assertEqual(len(concatenated_clips), 2)

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_concatenate_called_with_negative_overlap_padding(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        mock_build_kenburns_clip.side_effect = (
            lambda path, duration, motion=None: MagicMock()
        )

        _build_scene_clip(["a.png", "b.png", "c.png", "d.png"], 8.0)

        overlap = min(ASSET_CROSSFADE_DURATION, 2.0 / 2)
        self.assertAlmostEqual(
            mock_concatenate_videoclips.call_args.kwargs["padding"], -overlap, places=6,
        )
        self.assertEqual(
            mock_concatenate_videoclips.call_args.kwargs["method"], "compose",
        )

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_cuts_receive_crossfade_effects_at_scene_internal_boundaries(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        created_clips = []

        def _side_effect(path, duration, motion=None):
            clip = MagicMock(name=f"clip_for_{path}")
            created_clips.append(clip)
            return clip

        mock_build_kenburns_clip.side_effect = _side_effect

        asset_paths = ["a.png", "b.png", "c.png"]
        _build_scene_clip(asset_paths, 6.0)

        overlap = min(ASSET_CROSSFADE_DURATION, 2.0 / 2)

        def _effects_applied(index):
            post_fps = created_clips[index].with_fps.return_value
            return post_fps.with_effects.call_args.args[0]

        first_effects = _effects_applied(0)
        self.assertEqual(len(first_effects), 1)
        self.assertIsInstance(first_effects[0], CrossFadeOut)
        self.assertAlmostEqual(first_effects[0].duration, overlap, places=6)

        middle_effects = _effects_applied(1)
        self.assertEqual(len(middle_effects), 2)
        self.assertIsInstance(middle_effects[0], CrossFadeIn)
        self.assertIsInstance(middle_effects[1], CrossFadeOut)

        last_effects = _effects_applied(2)
        self.assertEqual(len(last_effects), 1)
        self.assertIsInstance(last_effects[0], CrossFadeIn)
        self.assertAlmostEqual(last_effects[0].duration, overlap, places=6)

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_consecutive_cuts_use_different_motions(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        used_motions = []

        def _side_effect(path, duration, motion=None):
            used_motions.append(motion)
            return MagicMock()

        mock_build_kenburns_clip.side_effect = _side_effect

        asset_paths = ["a.png", "b.png", "c.png", "d.png"]
        _build_scene_clip(asset_paths, 8.0)

        self.assertEqual(len(used_motions), 4)
        self.assertEqual(len(set(used_motions)), 4)
        for motion in used_motions:
            self.assertIsNotNone(motion)


class TestResolveCutDurations(unittest.TestCase):
    """
    Sprint64-4 - role이 있는 asset에 한해 asset_usage_planner의 role
    가중 duration을 사용하고, 그 외에는 기존 균등 분배
    (_split_duration_equally)를 그대로 유지한다.
    """

    def test_all_roles_present_matches_asset_usage_planner(self):
        assets = [
            {"path": "a.png", "role": "environment"},
            {"path": "b.png", "role": "subject"},
            {"path": "c.png", "role": "detail"},
            {"path": "d.png", "role": "transition"},
        ]
        scene = {"scene": 1, "assets": assets}
        asset_paths = [asset["path"] for asset in assets]

        result = _resolve_cut_durations(scene, asset_paths, 8.0)
        expected = [
            entry["duration"]
            for entry in asset_usage_planner.plan_asset_usage(assets, 8.0)
        ]

        self.assertEqual(result, expected)
        # 균등 분배(2.0씩)와는 달라야 한다 - 실제로 role 가중이 적용됨.
        self.assertNotEqual(result, _split_duration_equally(8.0, 4))

    def test_no_role_falls_back_to_equal_split(self):
        assets = [
            {"path": "a.png"}, {"path": "b.png"},
            {"path": "c.png"}, {"path": "d.png"},
        ]
        scene = {"scene": 1, "assets": assets}
        asset_paths = [asset["path"] for asset in assets]

        result = _resolve_cut_durations(scene, asset_paths, 8.0)

        self.assertEqual(result, _split_duration_equally(8.0, 4))

    def test_no_assets_key_falls_back_to_equal_split(self):
        # 구버전 scene(assets 필드 자체가 없음)
        scene = {"scene": 1, "asset_path": "legacy.png"}
        asset_paths = ["a.png", "b.png"]

        result = _resolve_cut_durations(scene, asset_paths, 4.0)

        self.assertEqual(result, _split_duration_equally(4.0, 2))

    def test_scene_none_falls_back_to_equal_split(self):
        result = _resolve_cut_durations(None, ["a.png", "b.png"], 4.0)

        self.assertEqual(result, _split_duration_equally(4.0, 2))

    def test_length_mismatch_falls_back_to_equal_split(self):
        # 방어적 케이스: assets 개수와 asset_paths 개수가 다름(정상
        # 흐름에서는 발생하지 않지만 안전망으로 균등 분배를 써야 한다).
        assets = [
            {"path": "a.png", "role": "environment"},
            {"path": "b.png", "role": "subject"},
        ]
        scene = {"scene": 1, "assets": assets}
        asset_paths = ["a.png", "b.png", "c.png"]

        result = _resolve_cut_durations(scene, asset_paths, 6.0)

        self.assertEqual(result, _split_duration_equally(6.0, 3))

    def test_partial_role_still_uses_planner(self):
        # 일부만 role이 있어도(any) plan_asset_usage가 호출되어야
        # 한다 - 나머지는 planner 내부의 DEFAULT_ROLE_WEIGHT로 처리.
        assets = [
            {"path": "a.png", "role": "environment"},
            {"path": "b.png"},
        ]
        scene = {"scene": 1, "assets": assets}
        asset_paths = [asset["path"] for asset in assets]

        result = _resolve_cut_durations(scene, asset_paths, 4.0)
        expected = [
            entry["duration"]
            for entry in asset_usage_planner.plan_asset_usage(assets, 4.0)
        ]

        self.assertEqual(result, expected)


class TestBuildSceneClipWithScene(unittest.TestCase):
    """
    Sprint64-4 - _build_scene_clip()에 scene을 함께 넘기면 role 가중
    duration이 build_kenburns_clip에 그대로 전달된다. scene을 넘기지
    않으면(기본값 None) 기존 Sprint62-3 동작과 완전히 동일하다 -
    기존 4개 테스트(TestBuildSceneClip)가 이를 그대로 증명한다.
    """

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_role_weighted_durations_passed_to_kenburns(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        # Sprint70-1 - role 가중 "할당" 자체(_resolve_cut_durations)는
        # 그대로다(요구사항5) - 렌더 호출값은 그 위에 마지막 컷을 뺀
        # 나머지에 crossfade overlap이 더해진 값이어야 한다.
        mock_build_kenburns_clip.side_effect = (
            lambda path, duration, motion=None: MagicMock()
        )

        assets = [
            {"path": "a.png", "role": "environment"},
            {"path": "b.png", "role": "subject"},
            {"path": "c.png", "role": "detail"},
            {"path": "d.png", "role": "transition"},
        ]
        scene = {"scene": 1, "assets": assets}
        asset_paths = [asset["path"] for asset in assets]

        _build_scene_clip(asset_paths, 8.0, scene=scene)

        called_durations = [
            call_args.args[1] for call_args in mock_build_kenburns_clip.call_args_list
        ]
        allocations = [
            entry["duration"]
            for entry in asset_usage_planner.plan_asset_usage(assets, 8.0)
        ]
        overlap = min(ASSET_CROSSFADE_DURATION, min(allocations) / 2)
        expected = [d + overlap for d in allocations[:-1]] + [allocations[-1]]

        for actual, exp in zip(called_durations, expected):
            self.assertAlmostEqual(actual, exp, places=6)

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_no_role_scene_still_splits_equally(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        mock_build_kenburns_clip.side_effect = (
            lambda path, duration, motion=None: MagicMock()
        )

        assets = [{"path": "a.png"}, {"path": "b.png"}]
        scene = {"scene": 1, "assets": assets}

        _build_scene_clip(["a.png", "b.png"], 4.0, scene=scene)

        called_durations = [
            call_args.args[1] for call_args in mock_build_kenburns_clip.call_args_list
        ]
        overlap = min(ASSET_CROSSFADE_DURATION, 2.0 / 2)

        self.assertAlmostEqual(called_durations[0], 2.0 + overlap, places=6)
        self.assertAlmostEqual(called_durations[1], 2.0, places=6)

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_default_scene_none_behaves_exactly_like_before(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        mock_build_kenburns_clip.side_effect = (
            lambda path, duration, motion=None: MagicMock()
        )

        # scene 인자를 아예 넘기지 않는 기존 호출 방식 - 균등 분배
        # "할당"은 Sprint62-3 동작과 동일하고(_resolve_cut_durations로
        # 별도 검증됨), 여기서는 크로스페이드 보정까지 포함한 렌더
        # 호출값을 확인한다.
        _build_scene_clip(["a.png", "b.png", "c.png", "d.png"], 8.0)

        called_durations = [
            call_args.args[1] for call_args in mock_build_kenburns_clip.call_args_list
        ]
        overlap = min(ASSET_CROSSFADE_DURATION, 2.0 / 2)

        for duration in called_durations[:-1]:
            self.assertAlmostEqual(duration, 2.0 + overlap, places=6)
        self.assertAlmostEqual(called_durations[-1], 2.0, places=6)


if __name__ == "__main__":
    unittest.main()
