import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from moviepy.video.fx.CrossFadeIn import CrossFadeIn
from moviepy.video.fx.CrossFadeOut import CrossFadeOut
from moviepy.video.fx.FadeIn import FadeIn
from moviepy.video.fx.FadeOut import FadeOut

from app.services import audio_policy
from app.services.video_builder import (
    _apply_duration_limits,
    _effects_for_clip,
    _intermediate_ffmpeg_params,
    _load_scenes,
    _resolve_asset_path,
    build_video,
    INTERMEDIATE_CRF,
    INTERMEDIATE_PRESET,
    MIN_SCENE_DURATION,
    MAX_SCENE_DURATION,
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


class TestApplyDurationLimits(unittest.TestCase):
    """Sprint55 - Adaptive Scene Timing. video_builder.py는 이미
    Sprint37-1부터 각 scene의 실제 narration(mp3) 길이를 그대로 Ken
    Burns clip 길이로 쓴다 - 이 테스트는 그 위에 추가되는 최소/최대
    duration 제한이, scene duration 합(=narration 총 길이)을 정확히
    보존하면서 동작하는지 검증한다."""

    def test_empty_list_returns_empty(self):
        self.assertEqual(_apply_duration_limits([]), [])

    def test_already_within_bounds_is_unchanged(self):
        raw = [5.0, 6.0, 7.0, 4.5]
        result = _apply_duration_limits(raw)

        for expected, actual in zip(raw, result):
            self.assertAlmostEqual(expected, actual, places=6)

    def test_sum_is_always_preserved(self):
        cases = [
            [5.0, 6.0, 7.0, 4.5],
            [0.5, 20.0, 3.0, 3.0, 3.0, 3.0],
            [1.0, 1.0, 1.0, 1.0, 1.0, 30.0],
            [8.0] * 6,
        ]

        for raw in cases:
            with self.subTest(raw=raw):
                result = _apply_duration_limits(raw)
                self.assertAlmostEqual(sum(raw), sum(result), places=6)

    def test_short_scene_is_raised_to_minimum(self):
        raw = [0.5, 8.0, 8.0, 8.0, 8.0, 8.0]

        result = _apply_duration_limits(raw)

        self.assertGreaterEqual(result[0], MIN_SCENE_DURATION)
        self.assertAlmostEqual(result[0], MIN_SCENE_DURATION, places=6)

    def test_long_scene_is_lowered_to_maximum(self):
        raw = [5.0, 5.0, 5.0, 5.0, 5.0, 30.0]

        result = _apply_duration_limits(raw)

        self.assertLessEqual(result[-1], MAX_SCENE_DURATION)
        self.assertAlmostEqual(result[-1], MAX_SCENE_DURATION, places=6)

    def test_other_scenes_absorb_the_deficit_from_a_short_scene(self):
        raw = [0.5, 8.0, 8.0, 8.0, 8.0, 8.0]

        result = _apply_duration_limits(raw)

        # 0.5 -> MIN_SCENE_DURATION로 올라간 만큼(deficit)을 나머지가
        # 나눠서 흡수해야 하므로, 나머지 scene들은 원래(8.0)보다 살짝
        # 줄어야 한다.
        for value in result[1:]:
            self.assertLess(value, 8.0)

    def test_all_results_respect_bounds_when_feasible(self):
        raw = [0.2, 0.3, 25.0, 6.0, 6.0, 6.0]

        result = _apply_duration_limits(raw)

        for value in result:
            self.assertGreaterEqual(value, MIN_SCENE_DURATION - 1e-6)
            self.assertLessEqual(value, MAX_SCENE_DURATION + 1e-6)

    def test_impossible_bounds_falls_back_to_preserving_sum_only(self):
        # 6개 scene 전부 MIN_SCENE_DURATION보다 훨씬 작은 총합이면,
        # 모두를 MIN까지 올리는 것 자체가 총합 보존과 근본적으로
        # 모순된다 - 이럴 땐 합 보존을 우선한다(요구사항: "scene
        # duration 합은 narration 길이와 동일"은 하드 요구사항).
        raw = [0.1] * 6

        result = _apply_duration_limits(raw)

        self.assertAlmostEqual(sum(raw), sum(result), places=6)

    def test_single_scene_unchanged_when_within_bounds(self):
        result = _apply_duration_limits([6.0])
        self.assertAlmostEqual(result[0], 6.0, places=6)

    def test_custom_bounds_are_respected(self):
        raw = [1.0, 1.0, 1.0, 1.0]

        result = _apply_duration_limits(raw, min_duration=0.5, max_duration=2.0)

        self.assertAlmostEqual(sum(raw), sum(result), places=6)
        for value in result:
            self.assertGreaterEqual(value, 0.5 - 1e-6)


class TestIntermediateEncodingParams(unittest.TestCase):
    """Sprint62 - Master Quality Render Pipeline.

    short.mp4는 final_video_service.py가 자막을 번인하면서 곧바로 다시
    인코딩하는 중간 산출물이다. 그런데 moviepy는 -crf를 전혀 넘기지
    않으므로(moviepy/video/io/ffmpeg_writer.py 참고) 아무것도 지정하지
    않으면 libx264 기본값 CRF 23으로 인코딩된다 - 2차 인코딩이 CRF
    18이어도 1차에서 이미 버린 디테일은 되살아나지 않는다.

    중간본은 즉시 버려지므로 압축 효율(파일 크기)은 의미가 없고,
    충실도와 렌더 속도만이 의미가 있다.
    """

    def test_crf_is_visually_lossless(self):
        self.assertLessEqual(INTERMEDIATE_CRF, 16)
        self.assertGreaterEqual(INTERMEDIATE_CRF, 0)

    def test_ffmpeg_params_pass_crf_explicitly(self):
        params = _intermediate_ffmpeg_params()

        self.assertIn("-crf", params)
        self.assertEqual(
            params[params.index("-crf") + 1],
            str(INTERMEDIATE_CRF),
        )

    def test_ffmpeg_params_do_not_set_bitrate(self):
        # CRF(품질 목표)와 -b:v(비트레이트 목표)를 동시에 주면 libx264는
        # 비트레이트를 우선해 CRF를 무시한다. 둘을 섞지 않는다.
        params = _intermediate_ffmpeg_params()

        self.assertNotIn("-b:v", params)
        self.assertNotIn("-b", params)

    def test_preset_is_declared(self):
        self.assertIsInstance(INTERMEDIATE_PRESET, str)
        self.assertTrue(INTERMEDIATE_PRESET)


class TestBuildVideoEncodingContract(unittest.TestCase):
    """Sprint62 - build_video()가 실제로 write_videofile에 명시적 품질
    파라미터를 넘기는지 검증한다. 상수만 선언해 두고 정작 넘기지 않는
    회귀를 막는 것이 목적이다."""

    def _make_project(self, tmp_dir, scene_count=2):

        os.makedirs(os.path.join(tmp_dir, "images"), exist_ok=True)
        os.makedirs(
            os.path.join(tmp_dir, "audio", "scenes"), exist_ok=True,
        )

        scenes = []

        for index in range(1, scene_count + 1):

            image_path = os.path.join(
                tmp_dir, "images", f"scene{index}.png",
            )
            audio_path = os.path.join(
                tmp_dir, "audio", "scenes",
                audio_policy.scene_audio_filename(index),
            )

            for path in (image_path, audio_path):
                with open(path, "wb") as f:
                    f.write(b"stub")

            scenes.append({"scene": index, "narration": "x"})

        with open(
            os.path.join(tmp_dir, "script.json"), "w", encoding="utf-8",
        ) as f:
            json.dump({"scenes": scenes}, f)

        return scenes

    def _run_build_video(self, tmp_dir):

        with patch(
            "app.services.video_builder.AudioFileClip"
        ) as mock_audio, patch(
            "app.services.video_builder.build_kenburns_clip"
        ) as mock_kenburns, patch(
            "app.services.video_builder.concatenate_videoclips"
        ) as mock_concat:

            mock_audio.return_value = MagicMock(duration=6.0)
            mock_kenburns.return_value = MagicMock()

            final = MagicMock()
            mock_concat.return_value = final

            build_video(tmp_dir)

            return final.write_videofile.call_args

    def test_write_videofile_receives_explicit_ffmpeg_params(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_project(tmp_dir)

            call_args = self._run_build_video(tmp_dir)

            self.assertEqual(
                call_args.kwargs.get("ffmpeg_params"),
                _intermediate_ffmpeg_params(),
            )

    def test_write_videofile_receives_declared_preset(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_project(tmp_dir)

            call_args = self._run_build_video(tmp_dir)

            self.assertEqual(
                call_args.kwargs.get("preset"),
                INTERMEDIATE_PRESET,
            )

    def test_output_contract_is_unchanged(self):
        # Sprint62는 인코딩 품질만 바꾼다 - 코덱/fps/무음 처리 등 나머지
        # 출력 계약은 그대로여야 한다(R5).
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_project(tmp_dir)

            call_args = self._run_build_video(tmp_dir)

            self.assertEqual(call_args.kwargs.get("codec"), "libx264")
            self.assertEqual(call_args.kwargs.get("fps"), 30)
            self.assertFalse(call_args.kwargs.get("audio"))
            self.assertEqual(
                call_args.args[0],
                os.path.join(tmp_dir, "video", "short.mp4"),
            )


if __name__ == "__main__":
    unittest.main()
