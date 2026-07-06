import json
import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from moviepy.video.fx.CrossFadeIn import CrossFadeIn
from moviepy.video.fx.CrossFadeOut import CrossFadeOut
from moviepy.video.fx.FadeIn import FadeIn
from moviepy.video.fx.FadeOut import FadeOut

from app.services.video_builder import (
    _effects_for_clip,
    _load_scenes,
    _resolve_asset_path,
)


class TestResolveAssetPath(unittest.TestCase):

    def test_uses_asset_path_when_present(self):
        scene = {"scene": 1, "asset_path": "output/proj/images/custom.png"}
        result = _resolve_asset_path("output/proj", scene)
        self.assertEqual(result, "output/proj/images/custom.png")

    def test_falls_back_to_legacy_path_when_missing(self):
        scene = {"scene": 3}
        result = _resolve_asset_path("output/proj", scene)
        self.assertEqual(
            result,
            os.path.join("output/proj", "images", "scene3.png"),
        )

    def test_falls_back_when_asset_path_is_empty_string(self):
        scene = {"scene": 2, "asset_path": ""}
        result = _resolve_asset_path("output/proj", scene)
        self.assertEqual(
            result,
            os.path.join("output/proj", "images", "scene2.png"),
        )

    def test_falls_back_when_asset_path_is_none(self):
        scene = {"scene": 5, "asset_path": None}
        result = _resolve_asset_path("output/proj", scene)
        self.assertEqual(
            result,
            os.path.join("output/proj", "images", "scene5.png"),
        )


class TestLoadScenes(unittest.TestCase):

    def _write_script(self, project_path, scenes):
        with open(
            os.path.join(project_path, "script.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump({"scenes": scenes}, f)

    def test_scenes_sorted_by_scene_number(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_script(
                tmp_dir,
                [{"scene": 3}, {"scene": 1}, {"scene": 2}],
            )

            scenes = _load_scenes(tmp_dir)

            self.assertEqual([s["scene"] for s in scenes], [1, 2, 3])

    def test_preserves_scene_fields(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_script(
                tmp_dir,
                [{"scene": 1, "asset_path": "a.png", "provider": "ai_image"}],
            )

            scenes = _load_scenes(tmp_dir)

            self.assertEqual(scenes[0]["asset_path"], "a.png")
            self.assertEqual(scenes[0]["provider"], "ai_image")


class TestEffectsForClip(unittest.TestCase):

    def test_hook_scene_gets_fade_in_from_black(self):
        scene = {"scene": 1, "transition": "fade"}
        effects = _effects_for_clip(0, 3, scene, 5.0, overlap=0.35)

        self.assertIsInstance(effects[0], FadeIn)

    def test_non_first_non_last_scene_gets_cross_dissolve_both_sides(self):
        scene = {"scene": 2, "transition": "cross_dissolve"}
        effects = _effects_for_clip(1, 3, scene, 5.0, overlap=0.35)

        self.assertIsInstance(effects[0], CrossFadeIn)
        self.assertEqual(effects[0].duration, 0.35)
        self.assertIsInstance(effects[1], CrossFadeOut)
        self.assertEqual(effects[1].duration, 0.35)

    def test_last_scene_always_fades_out_to_black(self):
        scene = {"scene": 4, "transition": "cross_dissolve"}
        effects = _effects_for_clip(3, 3, scene, 5.0, overlap=0.35)

        self.assertIsInstance(effects[0], CrossFadeIn)
        self.assertIsInstance(effects[1], FadeOut)

    def test_single_scene_video_gets_fade_in_and_fade_out_only(self):
        scene = {"scene": 1, "transition": "fade"}
        effects = _effects_for_clip(0, 0, scene, 5.0, overlap=0.35)

        self.assertIsInstance(effects[0], FadeIn)
        self.assertIsInstance(effects[1], FadeOut)

    def test_missing_transition_field_defaults_to_cross_dissolve(self):
        scene = {"scene": 2}
        effects = _effects_for_clip(1, 3, scene, 5.0, overlap=0.35)

        self.assertIsInstance(effects[0], CrossFadeIn)


if __name__ == "__main__":
    unittest.main()
