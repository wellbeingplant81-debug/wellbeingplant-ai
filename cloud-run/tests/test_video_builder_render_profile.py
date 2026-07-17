"""
Sprint122 (RED) - Render Size가 video_builder.py의 clip 빌더 함수들에
render_profile을 통해 분기한다.

build_video()가 render_profile(기본값 None)을 받으면 그 width/height를
_build_scene_clip()/_build_video_only_clip()에 그대로 흘려보낸다 - 이
두 함수 자체의 계약만 여기서 직접 검증한다(kenburns.py와 동일하게
실제 PIL 이미지/ffmpeg mp4로 렌더링하되, build_video() 전체(실제
write_videofile 인코딩)까지는 부담이 커 이 파일에서는 다루지 않는다 -
build_video()가 render_profile을 받아 그대로 전달하는 한 줄짜리
배선은 step05_video 단계 테스트(test_step_wrappers_render_profile.py)
에서 mock으로 얇게 커버한다).
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
from app.services.video_builder import _build_scene_clip, _build_video_only_clip
from app.services.render_profile import RenderProfile


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


LONGFORM = RenderProfile.get("longform")


class TestBuildVideoOnlyClipCustomCanvas(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp_dir.cleanup)

    def test_no_width_height_matches_existing_canvas(self):
        video_path = os.path.join(self._tmp_dir.name, "clip.mp4")
        _make_test_video(video_path, duration=1.0)

        clip = _build_video_only_clip(video_path, duration=1.0)
        self.addCleanup(clip.close)

        self.assertEqual(clip.size, (VIDEO_WIDTH, VIDEO_HEIGHT))

    def test_custom_width_height_produces_matching_canvas(self):
        video_path = os.path.join(self._tmp_dir.name, "clip.mp4")
        _make_test_video(video_path, duration=1.0)

        clip = _build_video_only_clip(
            video_path, duration=1.0,
            width=LONGFORM["width"], height=LONGFORM["height"],
        )
        self.addCleanup(clip.close)

        self.assertEqual(clip.size, (LONGFORM["width"], LONGFORM["height"]))


class TestBuildSceneClipRenderProfile(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp_dir.cleanup)
        self.image_path = os.path.join(self._tmp_dir.name, "scene1.png")
        _make_test_image(self.image_path)

    def test_no_render_profile_matches_existing_canvas(self):
        clip = _build_scene_clip([self.image_path], clip_duration=1.0)
        self.addCleanup(clip.close)
        self.assertEqual(clip.size, (VIDEO_WIDTH, VIDEO_HEIGHT))

    def test_render_profile_changes_single_asset_canvas(self):
        clip = _build_scene_clip(
            [self.image_path], clip_duration=1.0, render_profile=LONGFORM,
        )
        self.addCleanup(clip.close)
        self.assertEqual(clip.size, (LONGFORM["width"], LONGFORM["height"]))

    def test_render_profile_changes_multi_asset_canvas(self):
        second_image = os.path.join(self._tmp_dir.name, "scene1_2.png")
        _make_test_image(second_image)

        clip = _build_scene_clip(
            [self.image_path, second_image], clip_duration=2.0, render_profile=LONGFORM,
        )
        self.addCleanup(clip.close)
        self.assertEqual(clip.size, (LONGFORM["width"], LONGFORM["height"]))

    def test_render_profile_changes_video_only_canvas(self):
        video_path = os.path.join(self._tmp_dir.name, "scene1.mp4")
        _make_test_video(video_path, duration=1.0)

        scene = {
            "scene": 1,
            "assets": [{"path": self.image_path, "video_path": video_path}],
        }
        clip = _build_scene_clip(
            [self.image_path], clip_duration=1.5, scene=scene, render_profile=LONGFORM,
        )
        self.addCleanup(clip.close)
        self.assertEqual(clip.size, (LONGFORM["width"], LONGFORM["height"]))


if __name__ == "__main__":
    unittest.main()
