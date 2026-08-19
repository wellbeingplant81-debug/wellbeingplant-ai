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
    _effects_for_clip,
    _intermediate_ffmpeg_params,
    _load_scenes,
    _resolve_asset_path,
    build_video,
    CROSSFADE_DURATION,
    INTERMEDIATE_CRF,
    INTERMEDIATE_PRESET,
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

    def _run_build_video(self, tmp_dir, durations=None, capture_kenburns=False):

        count = len(durations) if durations else 2
        values = durations or [6.0] * count

        by_path = {
            os.path.join(
                tmp_dir, "audio", "scenes",
                audio_policy.scene_audio_filename(index),
            ): value
            for index, value in enumerate(values, start=1)
        }

        with patch(
            "app.services.scene_timeline.get_audio_duration",
            lambda path: by_path[path],
        ), patch(
            "app.services.video_builder.build_kenburns_clip"
        ) as mock_kenburns, patch(
            "app.services.video_builder.concatenate_videoclips"
        ) as mock_concat:

            mock_kenburns.return_value = MagicMock()

            final = MagicMock()
            mock_concat.return_value = final

            build_video(tmp_dir)

            if capture_kenburns:
                return mock_kenburns.call_args_list

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


class TestBuildVideoFollowsSharedTimeline(unittest.TestCase):
    """Sprint64 - clip 길이가 공유 타임라인(=나레이션 오디오)을 그대로
    따르는지 확인한다. 마지막 scene을 뺀 나머지는 cross-dissolve 겹침
    (CROSSFADE_DURATION)만큼 길게 렌더되고, 그 겹침은 concatenate의
    padding=-overlap으로 정확히 상쇄된다 - 즉 scene이 화면을 점유하는
    구간 자체는 오디오 길이와 같다."""

    _make_project = TestBuildVideoEncodingContract._make_project
    _run_build_video = TestBuildVideoEncodingContract._run_build_video

    def test_clip_durations_match_audio_plus_crossfade_overlap(self):
        durations = [4.2, 7.9, 5.05]

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_project(tmp_dir, scene_count=len(durations))

            calls = self._run_build_video(
                tmp_dir, durations=durations, capture_kenburns=True,
            )

        actual = [call.args[1] for call in calls]

        expected = [
            durations[0] + CROSSFADE_DURATION,
            durations[1] + CROSSFADE_DURATION,
            durations[2],
        ]

        for index, (got, want) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(got, want, places=9, msg=f"scene {index + 1}")

    def test_a_very_short_scene_is_not_stretched(self):
        # Sprint55의 duration clamp는 0.8초짜리 scene을 2.0초로 늘렸고,
        # 그만큼 뒤쪽 경계가 전부 밀렸다. 이제는 늘리지 않는다.
        durations = [0.8, 8.0, 8.0]

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_project(tmp_dir, scene_count=len(durations))

            calls = self._run_build_video(
                tmp_dir, durations=durations, capture_kenburns=True,
            )

        self.assertAlmostEqual(
            calls[0].args[1], 0.8 + CROSSFADE_DURATION, places=9,
        )

    def test_total_occupied_time_equals_audio_total(self):
        durations = [0.8, 8.0, 20.0, 3.3]

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_project(tmp_dir, scene_count=len(durations))

            calls = self._run_build_video(
                tmp_dir, durations=durations, capture_kenburns=True,
            )

        # clip 길이 합에서 겹침(마지막 제외 n-1개)을 빼면 실제 영상 길이
        rendered = sum(call.args[1] for call in calls)
        occupied = rendered - CROSSFADE_DURATION * (len(durations) - 1)

        self.assertAlmostEqual(occupied, sum(durations), places=9)


class TheFootageSceneUsesTheFootageTest(unittest.TestCase):
    """
    Sprint223 - 받아 둔 스톡 영상이 있으면 그것이 이 scene 의 자산이다.
    """

    def test_the_footage_wins_when_it_is_really_there(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            where = os.path.join(tmp_dir, "videos", "scene1.mp4")
            os.makedirs(os.path.dirname(where))

            with open(where, "wb") as f:
                f.write(b"stub")

            scene = {
                "scene": 1,
                "asset_path": os.path.join(tmp_dir, "images", "scene1.png"),
                "footage_path": where,
            }

            self.assertEqual(_resolve_asset_path(tmp_dir, scene), where)

    def test_a_recorded_but_missing_footage_falls_back_to_the_picture(self):
        """
        사람이 videos/ 를 지웠다는 이유로 렌더가 멈추지 않는다 - 첫
        프레임은 언제나 함께 남는다.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            picture = os.path.join(tmp_dir, "images", "scene1.png")

            scene = {
                "scene": 1,
                "asset_path": picture,
                "footage_path": os.path.join(tmp_dir, "videos", "gone.mp4"),
            }

            self.assertEqual(_resolve_asset_path(tmp_dir, scene), picture)

    def test_a_scene_without_footage_is_untouched(self):
        scene = {"scene": 4}

        self.assertEqual(
            _resolve_asset_path("output/proj", scene),
            os.path.join("output/proj", "images", "scene4.png"),
        )


class TheMixedTimelinePicksTheRightBuilderTest(unittest.TestCase):
    """
    한 타임라인에 영상과 그림이 섞인다. 어느 쪽으로 가는지는 확장자
    하나로 갈리고, 그 갈림은 footage.is_footage 한 곳에서 정한다.
    """

    def _project(self, tmp_dir, footage_scenes):
        os.makedirs(os.path.join(tmp_dir, "images"), exist_ok=True)
        os.makedirs(os.path.join(tmp_dir, "videos"), exist_ok=True)
        os.makedirs(os.path.join(tmp_dir, "audio", "scenes"), exist_ok=True)

        scenes = []

        for index in (1, 2, 3):
            picture = os.path.join(tmp_dir, "images", f"scene{index}.png")
            audio = os.path.join(
                tmp_dir, "audio", "scenes",
                audio_policy.scene_audio_filename(index))

            for path in (picture, audio):
                with open(path, "wb") as f:
                    f.write(b"stub")

            scene = {"scene": index, "narration": "x"}

            if index in footage_scenes:
                where = os.path.join(tmp_dir, "videos", f"scene{index}.mp4")

                with open(where, "wb") as f:
                    f.write(b"stub")

                scene["footage_path"] = where

            scenes.append(scene)

        with open(
            os.path.join(tmp_dir, "script.json"), "w", encoding="utf-8",
        ) as f:
            json.dump({"scenes": scenes}, f)

    def _build(self, tmp_dir):
        by_path = {
            os.path.join(
                tmp_dir, "audio", "scenes",
                audio_policy.scene_audio_filename(index),
            ): 4.0
            for index in (1, 2, 3)
        }

        with patch(
            "app.services.scene_timeline.get_audio_duration",
            lambda path: by_path[path],
        ), patch(
            "app.services.video_builder.build_kenburns_clip"
        ) as mock_kenburns, patch(
            "app.services.video_builder.build_footage_clip"
        ) as mock_footage, patch(
            "app.services.video_builder.concatenate_videoclips"
        ) as mock_concat:

            mock_kenburns.return_value = MagicMock()
            mock_footage.return_value = MagicMock()
            mock_concat.return_value = MagicMock()

            build_video(tmp_dir)

            return mock_kenburns.call_args_list, mock_footage.call_args_list

    def test_each_kind_goes_to_its_own_builder(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._project(tmp_dir, footage_scenes={1, 3})

            kenburns, footage = self._build(tmp_dir)

        self.assertEqual(len(footage), 2)
        self.assertEqual(len(kenburns), 1)

    def test_the_still_scene_still_gets_ken_burns(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._project(tmp_dir, footage_scenes={1, 3})

            kenburns, _ = self._build(tmp_dir)

            self.assertEqual(
                kenburns[0].args[0],
                os.path.join(tmp_dir, "images", "scene2.png"),
            )

    def test_a_project_with_no_footage_never_calls_the_new_path(self):
        """예전 프로젝트는 예전 그대로 돈다."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._project(tmp_dir, footage_scenes=set())

            kenburns, footage = self._build(tmp_dir)

        self.assertEqual(footage, [])
        self.assertEqual(len(kenburns), 3)

    def test_both_kinds_are_asked_for_the_same_length(self):
        """
        겹침 계산은 자산의 종류를 몰라야 한다 - 두 builder 가 같은
        길이를 받는 것이 그 증거다.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._project(tmp_dir, footage_scenes={1, 3})

            kenburns, footage = self._build(tmp_dir)

        # scene 1·2 는 겹침만큼 더 길고, 마지막(scene 3)은 그대로다.
        self.assertAlmostEqual(
            footage[0].args[1], 4.0 + CROSSFADE_DURATION, places=9)
        self.assertAlmostEqual(
            kenburns[0].args[1], 4.0 + CROSSFADE_DURATION, places=9)
        self.assertAlmostEqual(footage[1].args[1], 4.0, places=9)


if __name__ == "__main__":
    unittest.main()
