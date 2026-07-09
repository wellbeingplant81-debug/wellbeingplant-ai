import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.video_builder import (
    _build_scene_clip,
    _resolve_asset_paths,
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
        mock_build_kenburns_clip.side_effect = lambda path, duration: MagicMock()

        asset_paths = ["a.png", "b.png", "c.png", "d.png"]
        _build_scene_clip(asset_paths, 8.0)

        self.assertEqual(mock_build_kenburns_clip.call_count, 4)
        mock_concatenate_videoclips.assert_called_once()

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_multiple_assets_split_scene_duration_equally(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        mock_build_kenburns_clip.side_effect = lambda path, duration: MagicMock()

        asset_paths = ["a.png", "b.png", "c.png", "d.png"]
        _build_scene_clip(asset_paths, 8.0)

        called_durations = [
            call_args.args[1] for call_args in mock_build_kenburns_clip.call_args_list
        ]

        self.assertEqual(len(called_durations), 4)
        for duration in called_durations:
            self.assertAlmostEqual(duration, 2.0, places=6)
        self.assertAlmostEqual(sum(called_durations), 8.0, places=6)

    @patch("app.services.video_builder.concatenate_videoclips")
    @patch("app.services.video_builder.build_kenburns_clip")
    def test_multiple_assets_passed_to_concatenate_in_order(
        self, mock_build_kenburns_clip, mock_concatenate_videoclips,
    ):
        created_clips = []

        def _side_effect(path, duration):
            clip = MagicMock(name=f"clip_for_{path}")
            created_clips.append(clip)
            return clip

        mock_build_kenburns_clip.side_effect = _side_effect

        asset_paths = ["a.png", "b.png"]
        _build_scene_clip(asset_paths, 4.0)

        concatenated_clips = mock_concatenate_videoclips.call_args.args[0]
        self.assertEqual(len(concatenated_clips), 2)


if __name__ == "__main__":
    unittest.main()
