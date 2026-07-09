import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.video_builder import _resolve_asset_path


PROJECT_PATH = "/project"


class TestResolveAssetPathWithAssetsStructure(unittest.TestCase):
    """
    Sprint62-2 - video_builder가 scene["assets"]를 이해하도록 만든다.
    우선순위: assets[0].path -> asset_path(하위 호환) -> 레거시 파일명
    규칙. 이번 스프린트는 assets[0]만 읽고 나머지 항목은 순회하지 않는다.
    """

    # --- assets가 있으면 assets[0].path 사용 ---

    def test_uses_first_asset_path_when_assets_present(self):
        scene = {
            "scene": 2,
            "asset_path": "/project/images/scene2.png",
            "assets": [
                {"type": "image", "path": "/project/images/scene2_v2.png", "prompt": "p"},
            ],
        }

        result = _resolve_asset_path(PROJECT_PATH, scene)

        self.assertEqual(result, "/project/images/scene2_v2.png")

    def test_only_reads_first_asset_when_multiple_present(self):
        # 이번 스프린트는 assets[0]만 읽는다 - 순회하지 않는다.
        scene = {
            "scene": 3,
            "assets": [
                {"type": "image", "path": "/project/images/first.png", "prompt": "p1"},
                {"type": "image", "path": "/project/images/second.png", "prompt": "p2"},
            ],
        }

        result = _resolve_asset_path(PROJECT_PATH, scene)

        self.assertEqual(result, "/project/images/first.png")

    # --- assets가 없으면 기존 asset_path 사용(하위 호환) ---

    def test_falls_back_to_asset_path_when_assets_key_absent(self):
        scene = {
            "scene": 2,
            "asset_path": "/project/images/scene2.png",
        }

        result = _resolve_asset_path(PROJECT_PATH, scene)

        self.assertEqual(result, "/project/images/scene2.png")

    def test_falls_back_to_asset_path_when_assets_is_empty_list(self):
        scene = {
            "scene": 2,
            "asset_path": "/project/images/scene2.png",
            "assets": [],
        }

        result = _resolve_asset_path(PROJECT_PATH, scene)

        self.assertEqual(result, "/project/images/scene2.png")

    # --- 레거시 파일명 규칙 폴백(기존 동작 유지) ---

    def test_falls_back_to_legacy_filename_when_neither_assets_nor_asset_path(self):
        scene = {"scene": 5}

        result = _resolve_asset_path(PROJECT_PATH, scene)

        self.assertEqual(result, os.path.join(PROJECT_PATH, "images", "scene5.png"))

    # --- Sprint62-1 산출물(assets[0].path == asset_path)도 그대로 동작 ---

    def test_sprint62_1_output_where_assets_and_asset_path_match(self):
        shared_path = "/project/images/scene2.png"
        scene = {
            "scene": 2,
            "asset_path": shared_path,
            "assets": [{"type": "image", "path": shared_path, "prompt": "p"}],
        }

        result = _resolve_asset_path(PROJECT_PATH, scene)

        self.assertEqual(result, shared_path)


if __name__ == "__main__":
    unittest.main()
