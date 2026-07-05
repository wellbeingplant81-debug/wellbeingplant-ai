import json
import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.video_builder import _load_scenes, _resolve_asset_path


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


if __name__ == "__main__":
    unittest.main()
