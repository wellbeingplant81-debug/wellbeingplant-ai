"""
Sprint123 (GREEN) - Longform Audio/Video Sync. build_video()가 render_
profile=longform이면 _apply_duration_limits()의 클램프/재분배를 건너
뛰고 scene 각각의 Ken Burns 재생 길이를 그 scene의 실제 오디오 길이와
정확히 일치시킨다. Shorts(render_profile 없음/그 외 값)는 기존과
100% 동일하게 _apply_duration_limits()가 그대로 적용된다.

실제 write_videofile()은 무겁기 때문에, _build_scene_clip()과
concatenate_videoclips()를 mock해 build_video()가 각 scene에 실제로
어떤 clip_duration을 넘기는지만 가볍게 검증한다.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.render_profile import RenderProfile
from app.services.video_builder import (
    CROSSFADE_DURATION,
    MIN_SCENE_DURATION,
    _apply_duration_limits,
    build_video,
)


LONGFORM = RenderProfile.get("longform")

# 한 scene(scene2)만 MIN_SCENE_DURATION(2.0s)보다 훨씬 짧게(0.5s) 만들어
# _apply_duration_limits()의 클램프/재분배가 실제로 작동하게 만든다.
SCENE_DURATIONS_SECONDS = [3.0, 0.5, 3.0]


def _make_silent_mp3(path, duration):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-t", str(duration),
         "-i", "anullsrc=r=44100:cl=mono", "-c:a", "libmp3lame", path],
        capture_output=True, check=True,
    )


class TestBuildVideoLongformSync(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

        os.makedirs(os.path.join(self.project_path, "images"))
        os.makedirs(os.path.join(self.project_path, "audio", "scenes"))
        os.makedirs(os.path.join(self.project_path, "video"))

        scenes = []
        for i, duration in enumerate(SCENE_DURATIONS_SECONDS, start=1):
            scenes.append({"scene": i, "narration": f"n{i}", "image_prompt": f"p{i}"})
            image_path = os.path.join(self.project_path, "images", f"scene{i}.png")
            open(image_path, "wb").close()
            audio_path = os.path.join(self.project_path, "audio", "scenes", f"scene{i}.mp3")
            _make_silent_mp3(audio_path, duration)

        with open(os.path.join(self.project_path, "script.json"), "w", encoding="utf-8") as f:
            json.dump({"scenes": scenes}, f)

    def _captured_clip_durations(self, render_profile):
        captured = []

        def _fake_build_scene_clip(asset_paths, clip_duration, scene=None, render_profile=None):
            captured.append(clip_duration)
            fake_clip = MagicMock()
            fake_clip.with_fps.return_value = fake_clip
            fake_clip.with_effects.return_value = fake_clip
            return fake_clip

        with patch(
            "app.services.video_builder._build_scene_clip",
            side_effect=_fake_build_scene_clip,
        ), patch("app.services.video_builder.concatenate_videoclips") as mock_concat:
            mock_concat.return_value = MagicMock()
            build_video(self.project_path, render_profile=render_profile)

        return captured

    def test_shorts_still_applies_duration_limits(self):
        # 실측 오디오 길이(대략 [3.0, 0.5, 3.0], ffmpeg 인코딩 오차 감안)에
        # _apply_duration_limits()를 그대로 적용한 값과 일치해야 한다
        # (기존 동작 100% 보존).
        captured = self._captured_clip_durations(render_profile=None)

        # overlap 보정을 역산해 원래 클램프된 durations를 복원한다.
        last_index = len(captured) - 1
        clamped = [
            d if i == last_index else d - CROSSFADE_DURATION
            for i, d in enumerate(captured)
        ]

        # scene2(원래 ~0.5초)가 MIN_SCENE_DURATION(2.0초)까지 올라갔어야
        # 클램프가 실제로 작동한 것이다.
        self.assertAlmostEqual(clamped[1], MIN_SCENE_DURATION, delta=0.2)
        # 총합은 원본 audio 총합과 거의 동일하게 보존된다.
        self.assertAlmostEqual(sum(clamped), sum(SCENE_DURATIONS_SECONDS), delta=0.3)

    def test_longform_uses_exact_audio_durations_without_clamping(self):
        captured = self._captured_clip_durations(render_profile=LONGFORM)

        last_index = len(captured) - 1
        unclamped = [
            d if i == last_index else d - CROSSFADE_DURATION
            for i, d in enumerate(captured)
        ]

        # 클램프를 건너뛰므로 scene2는 실제 오디오 길이(~0.5초)를 그대로
        # 유지해야 한다 - MIN_SCENE_DURATION(2.0초)까지 부풀려지지 않는다.
        self.assertAlmostEqual(unclamped[1], 0.5, delta=0.2)
        for actual, expected in zip(unclamped, SCENE_DURATIONS_SECONDS):
            self.assertAlmostEqual(actual, expected, delta=0.2)


if __name__ == "__main__":
    unittest.main()
