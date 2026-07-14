"""
Sprint100-2 - Video as First-Class Asset. _resolve_video_only_path()/
_build_video_only_clip()/_build_scene_clip()의 video_path 분기가
(a) 실제 mp4를 재생하고 오디오를 제거하는지, (b) video_path가
없거나(scene 없음/필드 없음/파일 없음) 재생 자체가 실패하면(손상된
mp4) 기존 asset_path(PNG) + Ken Burns 경로로 100% 폴백하는지 확인
한다. kenburns.py 테스트와 동일하게 실제 PIL 이미지/실제 ffmpeg로
만든 작은 mp4를 써서 렌더링 로직 자체를 검증한다(과도한 mock 없음).
"""

import os
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.kenburns import VIDEO_HEIGHT, VIDEO_WIDTH
from app.services.video_builder import (
    _build_scene_clip,
    _build_video_only_clip,
    _resolve_video_only_path,
)


def _make_test_video(path: str, duration: float = 2.0, size: str = "320x240"):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s={size}:d={duration}",
            "-pix_fmt", "yuv420p",
            path,
        ],
        capture_output=True,
        check=True,
    )


def _make_test_image(path: str, size=(320, 240)):
    Image.new("RGB", size, color=(80, 90, 100)).save(path)


class TestResolveVideoOnlyPath(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp_dir.cleanup)

    def test_none_when_scene_is_none(self):
        self.assertIsNone(_resolve_video_only_path(None))

    def test_none_when_scene_has_no_assets(self):
        self.assertIsNone(_resolve_video_only_path({"scene": 1}))

    def test_none_when_asset_has_no_video_path_key(self):
        scene = {"scene": 1, "assets": [{"path": "images/scene1.png"}]}
        self.assertIsNone(_resolve_video_only_path(scene))

    def test_none_when_video_path_file_does_not_exist(self):
        scene = {
            "scene": 1,
            "assets": [{"path": "images/scene1.png", "video_path": "does/not/exist.mp4"}],
        }
        self.assertIsNone(_resolve_video_only_path(scene))

    def test_returns_path_when_video_file_exists(self):
        video_path = os.path.join(self._tmp_dir.name, "scene1.mp4")
        _make_test_video(video_path, duration=1.0)

        scene = {
            "scene": 1,
            "assets": [{"path": "images/scene1.png", "video_path": video_path}],
        }
        self.assertEqual(_resolve_video_only_path(scene), video_path)


class TestBuildVideoOnlyClip(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp_dir.cleanup)

    def test_short_source_video_is_looped_to_requested_duration(self):
        video_path = os.path.join(self._tmp_dir.name, "short.mp4")
        _make_test_video(video_path, duration=1.0)

        clip = _build_video_only_clip(video_path, duration=3.0)
        self.addCleanup(clip.close)

        self.assertAlmostEqual(clip.duration, 3.0, delta=0.15)
        self.assertEqual(clip.size, (VIDEO_WIDTH, VIDEO_HEIGHT))
        self.assertIsNone(clip.audio)

    def test_long_source_video_is_trimmed_to_requested_duration(self):
        video_path = os.path.join(self._tmp_dir.name, "long.mp4")
        _make_test_video(video_path, duration=4.0)

        clip = _build_video_only_clip(video_path, duration=1.5)
        self.addCleanup(clip.close)

        self.assertAlmostEqual(clip.duration, 1.5, delta=0.15)
        self.assertEqual(clip.size, (VIDEO_WIDTH, VIDEO_HEIGHT))
        self.assertIsNone(clip.audio)


class TestBuildSceneClipVideoOnlyFallback(unittest.TestCase):
    """
    기존 이미지 경로(Ken Burns)가 video_path 도입 이후에도 100% 그대로
    동작하는지, 그리고 video_path가 있어도 재생 자체가 실패하면
    자동으로 Ken Burns로 폴백하는지 확인한다.
    """

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp_dir.cleanup)
        self.image_path = os.path.join(self._tmp_dir.name, "scene1.png")
        _make_test_image(self.image_path)

    def test_no_scene_uses_ken_burns_unchanged(self):
        # 기존 호출부(scene=None 기본값)는 완전히 기존과 동일한 경로다.
        clip = _build_scene_clip([self.image_path], clip_duration=1.0)
        self.addCleanup(clip.close)
        self.assertAlmostEqual(clip.duration, 1.0, delta=0.05)

    def test_scene_without_video_path_uses_ken_burns(self):
        scene = {
            "scene": 1,
            "assets": [{"path": self.image_path}],
        }
        clip = _build_scene_clip(
            [self.image_path], clip_duration=1.0, scene=scene,
        )
        self.addCleanup(clip.close)
        self.assertAlmostEqual(clip.duration, 1.0, delta=0.05)

    def test_scene_with_valid_video_path_uses_real_video(self):
        video_path = os.path.join(self._tmp_dir.name, "scene1.mp4")
        _make_test_video(video_path, duration=1.0)

        scene = {
            "scene": 1,
            "assets": [{"path": self.image_path, "video_path": video_path}],
        }
        clip = _build_scene_clip(
            [self.image_path], clip_duration=2.0, scene=scene,
        )
        self.addCleanup(clip.close)
        self.assertAlmostEqual(clip.duration, 2.0, delta=0.15)
        self.assertIsNone(clip.audio)

    def test_corrupt_video_path_falls_back_to_ken_burns(self):
        corrupt_video_path = os.path.join(self._tmp_dir.name, "corrupt.mp4")
        with open(corrupt_video_path, "wb") as f:
            f.write(b"not a real mp4 file")

        scene = {
            "scene": 1,
            "assets": [{"path": self.image_path, "video_path": corrupt_video_path}],
        }

        # 재생 자체가 실패해도 예외 없이 기존 Ken Burns 경로로 폴백
        # 하고, 요청된 duration을 그대로 지킨다.
        clip = _build_scene_clip(
            [self.image_path], clip_duration=1.0, scene=scene,
        )
        self.addCleanup(clip.close)
        self.assertAlmostEqual(clip.duration, 1.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()
