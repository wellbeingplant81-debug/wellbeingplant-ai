"""
Sprint115 - 파이프라인이 실제로 사용자 음성을 쓰는가 (Epic 54, Phase 14).

배선은 Sprint113이 했다. 없던 것은 증거다.

기존 파이프라인 테스트는 전부 step03_voice_resolve를 통째로 mock한다.
그래서 "Resolver가 붙어 있다"는 것만 보고 "붙어 있는 Resolver가 실제로
step03을 건너뛴다"는 것은 아무도 보지 않았다. 그 사이에 사람이 하나
있으면(예: 파이프라인이 source를 잘못 넘긴다, project.json을 다른
칸에서 읽는다) 모든 테스트가 통과한 채로 사용자 음성이 버려진다.

여기서는 Resolver를 mock하지 않는다. 진짜 Resolver를 두고, 비싼
엔진들만 세운다. 그러면 세는 것은 하나다 - step03_tts.run()이 몇 번
불렸는가.

    AUTO     1회
    IMPORT   0회
    MANUAL   0회

Resolver의 정책은 여기서 바꾸지 않는다. voice.wav 단독 폴백도, scene
wav 우선순위도 Sprint113이 정한 그대로이고, 이 파일은 그것이 파이프라인
안에서도 같은지만 본다.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

import app.pipeline.pipeline as pipeline
from app.services import audio_policy
from app.steps import step03_tts

WAV = b"RIFF____WAVEfmt "

SCENES = [
    {"scene": n, "narration": f"{n}번 문장입니다", "image_prompt": "a man"}
    for n in range(1, 4)
]

SCRIPT = {"title": "제목", "hook": "훅", "scenes": SCENES}


class _PipelineCase(unittest.TestCase):
    """비싼 것만 세운다. Resolver는 진짜를 쓴다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name

        for relative in ("images", os.path.join("audio", "scenes"), "video",
                         "subtitle"):
            os.makedirs(os.path.join(self.project, relative), exist_ok=True)

        self.tts_calls = []
        self.assembled = []

        flags = patch.multiple(
            "app.pipeline.pipeline.config",
            ENABLE_SCENE_PLANNER=False,
            ENABLE_PROMPT_ENRICHMENT=False,
            ENABLE_PROMPT_EFFECTIVENESS=False,
            ENABLE_PROMPT_OPTIMIZATION=False,
            ENABLE_PROMPT_LEARNING=False,
            ENABLE_AI_DIRECTOR=False,
            ENABLE_VIRAL_WRITER=False,
            # scene을 그대로 흘려보낸다. Mock으로 세우면 MagicMock이
            # 빈 iterator를 돌려주면서 scene이 조용히 사라진다.
            ENABLE_CHARACTER_CONSISTENCY=False,
        )
        flags.start()
        self.addCleanup(flags.stop)

        # 비싼 엔진과 관측만 세운다. Resolver는 여기 없고,
        # scene을 다루는 순수 함수들도 진짜를 쓴다.
        for target in ("visual_consistency_engine", "regeneration_service",
                       "step04_subtitle", "step05_video", "step06_thumbnail",
                       "step07_quality", "metadata_service", "studio_upload",
                       "asset_observatory", "asset_dataset"):
            patcher = patch(f"app.pipeline.pipeline.{target}")
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            setattr(self, target, mock)

        self.visual_consistency_engine.apply_visual_consistency.side_effect = (
            lambda scenes, channel: scenes
        )

        # step01/step02는 각자의 Resolver를 통해 불린다. 대본과 이미지는
        # 이 파일의 관심사가 아니므로 미리 놓아 IMPORT로 흐르게 한다.
        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump(SCRIPT, f, ensure_ascii=False)

        for scene in SCENES:
            with open(os.path.join(self.project, "images",
                                   f"scene{scene['scene']}.png"), "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")

        tts = patch.object(
            step03_tts, "run",
            side_effect=lambda scenes, path: self.tts_calls.append(path),
        )
        tts.start()
        self.addCleanup(tts.stop)

        # Resolver가 IMPORT에서 부르는 엔진 조립. ffmpeg를 돌리지
        # 않는다 - 여기서 세는 것은 호출이다.
        from app.services import audio_service

        for name in ("concat_scene_audio", "mix_audio"):
            patcher = patch.object(
                audio_service, name,
                side_effect=lambda *a, **k: self.assembled.append(a),
            )
            patcher.start()
            self.addCleanup(patcher.stop)

    def _place_scene_audio(self, numbers):
        for number in numbers:
            path = os.path.join(
                self.project, "audio", "scenes",
                audio_policy.scene_audio_filename(number),
            )
            with open(path, "wb") as f:
                f.write(WAV)

    def _place_whole_voice(self):
        with open(os.path.join(self.project, "audio",
                               audio_policy.VOICE_FILENAME), "wb") as f:
            f.write(WAV)

    def _mark(self, **fields):
        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"project_id": "p", **fields}, f)

    def _run(self):
        return pipeline.run_pipeline(
            topic="주제", project_path=self.project, channel="wellbeing",
        )


class TestAuto(_PipelineCase):

    def test_step03_is_called_once(self):
        self._run()

        self.assertEqual(len(self.tts_calls), 1)

    def test_it_receives_the_project_path(self):
        self._run()

        self.assertEqual(self.tts_calls[0], self.project)

    def test_the_resolver_does_not_assemble(self):
        """step03이 concat/mix까지 한다 - 두 번 하면 안 된다."""

        self._run()

        self.assertEqual(self.assembled, [])

    def test_the_later_steps_still_run(self):
        self._run()

        self.step04_subtitle.run.assert_called_once()
        self.step05_video.run.assert_called_once()
        self.step06_thumbnail.run.assert_called_once()
        self.step07_quality.run.assert_called_once()


class TestImport(_PipelineCase):

    def test_step03_is_never_called(self):
        self._place_scene_audio([1, 2, 3])

        self._run()

        self.assertEqual(self.tts_calls, [])

    def test_the_users_audio_is_assembled_instead(self):
        self._place_scene_audio([1, 2, 3])

        self._run()

        self.assertEqual(len(self.assembled), 2)

    def test_the_placed_files_are_untouched(self):
        self._place_scene_audio([1, 2, 3])

        self._run()

        for number in (1, 2, 3):
            path = os.path.join(self.project, "audio", "scenes",
                                audio_policy.scene_audio_filename(number))
            with self.subTest(scene=number):
                self.assertEqual(open(path, "rb").read(), WAV)

    def test_the_later_steps_still_run(self):
        self._place_scene_audio([1, 2, 3])

        self._run()

        self.step04_subtitle.run.assert_called_once()
        self.step05_video.run.assert_called_once()
        self.step06_thumbnail.run.assert_called_once()
        self.step07_quality.run.assert_called_once()

    def test_metadata_and_upload_are_reached_the_same_way(self):
        """step04 이후는 한 줄도 달라지지 않는다."""

        self._place_scene_audio([1, 2, 3])

        self._run()

        self.metadata_service.generate_publish_package.assert_called_once()
        self.studio_upload.run_upload_quietly.assert_called_once()


class TestManual(_PipelineCase):

    def test_it_behaves_like_import(self):
        self._mark(voice_source="manual")
        self._place_scene_audio([1, 2, 3])

        self._run()

        self.assertEqual(self.tts_calls, [])
        self.assertEqual(len(self.assembled), 2)


class TestThePolicyIsUnchanged(_PipelineCase):
    """Sprint113이 정한 것을 파이프라인 안에서도 그대로 지키는가."""

    def test_a_lone_voice_file_still_falls_back_to_step03(self):
        self._place_whole_voice()

        self._run()

        self.assertEqual(len(self.tts_calls), 1)
        self.assertEqual(self.assembled, [])

    def test_a_partial_set_still_stops_the_pipeline(self):
        from app.steps.step03_voice_resolve import VoiceResolveError

        self._place_scene_audio([1])

        with self.assertRaises(VoiceResolveError):
            self._run()

        self.assertEqual(self.tts_calls, [])

    def test_an_explicit_auto_in_project_json_wins(self):
        self._mark(voice_source="auto")
        self._place_scene_audio([1, 2, 3])

        self._run()

        self.assertEqual(len(self.tts_calls), 1)

    def test_an_unknown_recorded_value_falls_through_to_disk(self):
        """NONE 같은 모르는 값은 적히지 않은 것과 같게 다룬다 -
        Sprint114 resolve_common이 SOURCES로 거른다."""

        self._mark(voice_source="none")
        self._place_scene_audio([1, 2, 3])

        self._run()

        self.assertEqual(self.tts_calls, [])

    def test_the_voice_field_is_the_one_it_reads(self):
        """대본/이미지 칸을 잘못 읽으면 사용자 음성이 조용히 버려진다."""

        self._mark(production_source="import", image_source="import",
                   voice_source="auto")
        self._place_scene_audio([1, 2, 3])

        self._run()

        self.assertEqual(len(self.tts_calls), 1)


class TestThePipelinePassesNoSource(unittest.TestCase):
    """파이프라인은 출처를 지시하지 않는다 - 디스크와 project.json이
    정한다. 넘기기 시작하면 화면의 선택과 두 곳에서 갈라진다."""

    def test_the_call_has_two_arguments(self):
        import ast

        source = open(pipeline.__file__, encoding="utf-8").read()

        for node in ast.walk(ast.parse(source)):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "run"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "step03_voice_resolve"):
                self.assertEqual(len(node.args), 2)
                self.assertEqual(node.keywords, [])
                return

        self.fail("파이프라인이 step03_voice_resolve.run을 부르지 않습니다.")


if __name__ == "__main__":
    unittest.main()
