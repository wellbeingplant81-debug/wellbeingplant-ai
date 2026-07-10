import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.technical_validation_service import _check_scene_count


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x00")


class TestCheckSceneCount(unittest.TestCase):
    """
    Sprint66-2 - scene_count_consistency가 Sprint62-4 멀티에셋 추가
    파일(sceneN_2.png 등)을 별개 scene으로 잘못 세지 않아야 한다.
    Sprint65 실제 E2E("장내세균이 우울감과 기억력에 영향을 주는 이유",
    scene4가 AI 4-asset)에서 image_files=9 != scene_count=6으로 오탐한
    버그를 재현/수정 확인한다.
    """

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def _write_single_asset_scenes(self, scene_count):
        for index in range(1, scene_count + 1):
            _touch(os.path.join(self.project_path, "images", f"scene{index}.png"))
            _touch(os.path.join(self.project_path, "audio", "scenes", f"scene{index}.mp3"))

    # --- Sprint65 실제 재현 ---

    def test_multi_asset_scene_does_not_inflate_image_count(self):
        self._write_single_asset_scenes(6)
        # scene4는 AI 4-asset - 추가 파일 3개가 더 있다.
        _touch(os.path.join(self.project_path, "images", "scene4_2.png"))
        _touch(os.path.join(self.project_path, "images", "scene4_3.png"))
        _touch(os.path.join(self.project_path, "images", "scene4_4.png"))

        result = _check_scene_count(self.project_path, scene_count=6)

        self.assertTrue(result["passed"])
        self.assertEqual(result["image_files"], 6)
        self.assertEqual(result["audio_files"], 6)

    def test_multiple_multi_asset_scenes_still_count_correctly(self):
        self._write_single_asset_scenes(6)
        for scene in (2, 5):
            for suffix in ("_2", "_3", "_4"):
                _touch(os.path.join(self.project_path, "images", f"scene{scene}{suffix}.png"))

        result = _check_scene_count(self.project_path, scene_count=6)

        self.assertTrue(result["passed"])
        self.assertEqual(result["image_files"], 6)

    # --- 기존 단일 asset 동작 회귀 없음 ---

    def test_single_asset_scenes_pass_as_before(self):
        self._write_single_asset_scenes(6)

        result = _check_scene_count(self.project_path, scene_count=6)

        self.assertTrue(result["passed"])
        self.assertEqual(result["image_files"], 6)
        self.assertEqual(result["audio_files"], 6)
        self.assertEqual(result["script_scenes"], 6)

    # --- 진짜 결손은 계속 잡아야 함 ---

    def test_missing_image_file_still_fails(self):
        self._write_single_asset_scenes(6)
        os.remove(os.path.join(self.project_path, "images", "scene3.png"))

        result = _check_scene_count(self.project_path, scene_count=6)

        self.assertFalse(result["passed"])
        self.assertEqual(result["image_files"], 5)

    def test_missing_audio_file_still_fails(self):
        self._write_single_asset_scenes(6)
        os.remove(os.path.join(self.project_path, "audio", "scenes", "scene3.mp3"))

        result = _check_scene_count(self.project_path, scene_count=6)

        self.assertFalse(result["passed"])
        self.assertEqual(result["audio_files"], 5)

    def test_missing_image_file_not_masked_by_multi_asset_extras(self):
        # scene3의 1차 asset이 없어도, 다른 scene의 멀티에셋 추가
        # 파일들 때문에 총 개수가 우연히 맞아떨어져 통과해버리면 안 된다.
        self._write_single_asset_scenes(6)
        os.remove(os.path.join(self.project_path, "images", "scene3.png"))
        _touch(os.path.join(self.project_path, "images", "scene4_2.png"))

        result = _check_scene_count(self.project_path, scene_count=6)

        self.assertFalse(result["passed"])
        self.assertEqual(result["image_files"], 5)

    def test_empty_project_fails(self):
        result = _check_scene_count(self.project_path, scene_count=6)

        self.assertFalse(result["passed"])
        self.assertEqual(result["image_files"], 0)
        self.assertEqual(result["audio_files"], 0)


if __name__ == "__main__":
    unittest.main()
