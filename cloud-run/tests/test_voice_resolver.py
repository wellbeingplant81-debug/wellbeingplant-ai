"""
Sprint113 - 음성을 어디서 가져올지 정한다 (Epic 54, Phase 12).

Sprint106(대본)·Sprint111(이미지)과 같은 자리, 같은 원칙이다. step03
앞에 서서 고르기만 하고, AUTO면 손대지 않은 step03을 그대로 부른다.

다만 이미지와 다른 사실이 하나 있고, 그것이 이 Resolver의 모양을
정한다. step02는 이미지를 놓는 것으로 끝나지만 step03은 넷을 한다.

    create_scene_tts      나레이션을 만든다
    optimize_scene_audio  마지막 scene 뒤에 무음을 붙여 45초에 맞춘다
    concat_scene_audio    scene들을 이어 voice.wav
    mix_audio             BGM을 섞어 final_audio.wav

final_video_service는 final_audio.wav로 최종 MP4를 만든다. 그래서
step03을 통째로 건너뛰면 사용자 음성을 놓고도 소리 없는 영상이 나온다.

Resolver는 앞의 둘만 건너뛴다. 만들지 않고(사용자가 이미 줬다),
늘리지 않는다(자동 늘리기 금지 - optimizer는 무음을 붙인다). 뒤의
둘은 엔진의 조립이고, AUTO가 하는 것과 같은 함수를 같은 인자로
부른다.
"""

import ast
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

from app.services import audio_policy, audio_service
from app.steps import step03_tts, step03_voice_resolve as resolver
from app.steps.step03_voice_resolve import VoiceResolveError

WAV = b"RIFF____WAVEfmt "


def _scenes(count=3):
    return [
        {"scene": n, "narration": f"{n}번"} for n in range(1, count + 1)
    ]


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name
        os.makedirs(os.path.join(self.project, "audio", "scenes"))

        # 조립은 ffmpeg가 한다. 여기서 보려는 것은 무엇을 어떤 인자로
        # 부르는가이지 인코딩이 아니다.
        for name in ("concat_scene_audio", "mix_audio"):
            patcher = patch.object(audio_service, name)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _place_scenes(self, numbers):
        for number in numbers:
            path = os.path.join(
                self.project, "audio", "scenes",
                audio_policy.scene_audio_filename(number),
            )
            with open(path, "wb") as f:
                f.write(WAV)

    def _place_whole(self):
        path = os.path.join(
            self.project, "audio", audio_policy.VOICE_FILENAME,
        )
        with open(path, "wb") as f:
            f.write(WAV)
        return path

    def _mark(self, source):
        with open(
            os.path.join(self.project, "project.json"), "w", encoding="utf-8",
        ) as f:
            json.dump({"project_id": "p", "voice_source": source}, f)

    def _scene_path(self, number):
        return os.path.join(
            self.project, "audio", "scenes",
            audio_policy.scene_audio_filename(number),
        )


class TestAutoIsUnchanged(_Case):
    """예전과 완전히 같아야 한다."""

    def test_it_calls_step03_with_the_same_arguments(self):
        scenes = _scenes()

        with patch.object(step03_tts, "run") as run:
            resolver.run(scenes, self.project)

        run.assert_called_once_with(scenes, self.project)

    def test_it_calls_step03_exactly_once(self):
        with patch.object(step03_tts, "run") as run:
            resolver.run(_scenes(), self.project)

        self.assertEqual(run.call_count, 1)

    def test_an_empty_audio_folder_means_auto(self):
        """create_project()는 audio/를 비운 채로 만든다."""

        self.assertEqual(resolver.detect_source(self.project), resolver.AUTO)

    def test_an_explicit_auto_ignores_placed_voice(self):
        self._place_scenes([1, 2, 3])

        with patch.object(step03_tts, "run") as run:
            resolver.run(_scenes(), self.project, source=resolver.AUTO)

        run.assert_called_once()

    def test_auto_does_not_assemble_by_itself(self):
        """step03이 concat/mix까지 한다 - 두 번 부르면 안 된다."""

        with patch.object(step03_tts, "run"):
            resolver.run(_scenes(), self.project)

        audio_service.concat_scene_audio.assert_not_called()
        audio_service.mix_audio.assert_not_called()


class TestPreparedVoiceSkipsGeneration(_Case):

    def test_step03_is_not_called(self):
        self._place_scenes([1, 2, 3])

        with patch.object(step03_tts, "run") as run:
            resolver.run(_scenes(), self.project)

        run.assert_not_called()

    def test_it_assembles_with_the_engines_own_functions(self):
        self._place_scenes([1, 2, 3])

        resolver.run(_scenes(), self.project)

        audio_service.concat_scene_audio.assert_called_once_with(
            [self._scene_path(1), self._scene_path(2), self._scene_path(3)],
            os.path.join(self.project, "audio", audio_policy.VOICE_FILENAME),
        )
        audio_service.mix_audio.assert_called_once_with(self.project)

    def test_the_scene_order_is_the_script_order(self):
        self._place_scenes([1, 2, 3])

        resolver.run(_scenes(), self.project)

        given = audio_service.concat_scene_audio.call_args[0][0]
        self.assertEqual(
            [os.path.basename(p) for p in given],
            ["scene1.wav", "scene2.wav", "scene3.wav"],
        )

    def test_it_never_stretches_the_users_audio(self):
        """optimize_scene_audio는 마지막 scene 뒤에 무음을 붙인다."""

        from app.services import duration_optimizer

        self._place_scenes([1, 2, 3])

        with patch.object(duration_optimizer, "optimize_scene_audio") as opt:
            resolver.run(_scenes(), self.project)

        opt.assert_not_called()

    def test_the_placed_files_are_left_alone(self):
        self._place_scenes([1, 2, 3])

        resolver.run(_scenes(), self.project)

        for number in (1, 2, 3):
            with self.subTest(scene=number):
                self.assertEqual(open(self._scene_path(number), "rb").read(),
                                 WAV)

    def test_manual_works_the_same_way(self):
        self._place_scenes([1, 2, 3])

        with patch.object(step03_tts, "run") as run:
            resolver.run(_scenes(), self.project, source=resolver.MANUAL)

        run.assert_not_called()
        audio_service.mix_audio.assert_called_once()

    def test_no_tts_module_is_imported(self):
        import subprocess

        self._place_scenes([1, 2, 3])

        code = (
            "import sys\n"
            "from app.steps import step03_voice_resolve as r\n"
            "print(len([m for m in sys.modules if 'scene_tts' in m "
            "or 'texttospeech' in m]))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertEqual(result.stdout.strip().splitlines()[-1], "0")


class TestWholeNarrationOnlyFallsBackToAuto(_Case):
    """voice.wav만 있으면 scene별 자막 시각을 낼 수 없다.

    subtitle_service는 scene 오디오 개수와 scene 개수가 다르면 예외를
    던진다 - 그대로 두면 자막 단계에서 죽는다."""

    def test_it_falls_back_to_step03(self):
        self._place_whole()

        with patch.object(step03_tts, "run") as run:
            resolver.run(_scenes(3), self.project)

        run.assert_called_once()

    def test_it_warns_before_falling_back(self):
        self._place_whole()

        with patch.object(step03_tts, "run"):
            with patch("builtins.print") as printed:
                resolver.run(_scenes(3), self.project)

        said = " ".join(str(c) for c in printed.call_args_list)
        self.assertIn("WARN", said)

    def test_it_does_not_assemble_the_lone_file(self):
        """자동 합치기 금지 - scene별 파일이 없으면 조립하지 않는다."""

        self._place_whole()

        with patch.object(step03_tts, "run"):
            resolver.run(_scenes(3), self.project)

        audio_service.concat_scene_audio.assert_not_called()

    def test_a_single_scene_project_uses_the_scene_file_not_this_path(self):
        self._place_scenes([1])

        with patch.object(step03_tts, "run") as run:
            resolver.run(_scenes(1), self.project)

        run.assert_not_called()


class TestCountMismatchIsRefused(_Case):
    """자동 수정 금지. 자동 분할 금지."""

    def test_a_partial_set_is_refused(self):
        self._place_scenes([1, 2])

        with self.assertRaises(VoiceResolveError) as caught:
            resolver.run(_scenes(6), self.project)

        message = str(caught.exception)
        self.assertIn("3", message)
        self.assertIn("6", message)

    def test_a_gap_in_the_middle_is_named(self):
        self._place_scenes([1, 3])

        with self.assertRaises(VoiceResolveError) as caught:
            resolver.run(_scenes(3), self.project)

        self.assertIn("2", str(caught.exception))

    def test_it_does_not_fall_back_when_some_are_present(self):
        """일부만 있는 것은 사용자가 아직 다 넣지 않았다는 뜻이다 -
        조용히 TTS로 덮으면 넣은 것이 사라진다."""

        self._place_scenes([1, 2])

        with patch.object(step03_tts, "run") as run:
            with self.assertRaises(VoiceResolveError):
                resolver.run(_scenes(3), self.project)

        run.assert_not_called()

    def test_nothing_is_created_to_fill_the_gap(self):
        self._place_scenes([1])

        with self.assertRaises(VoiceResolveError):
            resolver.run(_scenes(3), self.project)

        self.assertEqual(
            sorted(os.listdir(os.path.join(self.project, "audio", "scenes"))),
            ["scene1.wav"],
        )
        audio_service.concat_scene_audio.assert_not_called()

    def test_an_explicit_import_with_nothing_placed_is_refused(self):
        with self.assertRaises(VoiceResolveError):
            resolver.run(_scenes(3), self.project, source=resolver.IMPORT)


class TestSourceIsRecordedNotGuessed(_Case):

    def test_the_marked_source_wins_over_disk(self):
        self._mark("manual")

        self.assertEqual(resolver.detect_source(self.project), "manual")

    def test_disk_is_the_fallback(self):
        self._place_scenes([1])

        self.assertEqual(resolver.detect_source(self.project), resolver.IMPORT)

    def test_a_lone_voice_file_also_reads_as_prepared(self):
        self._place_whole()

        self.assertEqual(resolver.detect_source(self.project), resolver.IMPORT)

    def test_an_explicit_argument_wins_over_everything(self):
        self._mark("import")
        self._place_scenes([1, 2, 3])

        with patch.object(step03_tts, "run") as run:
            resolver.run(_scenes(), self.project, source=resolver.AUTO)

        run.assert_called_once()

    def test_an_unknown_source_is_refused(self):
        with self.assertRaises(VoiceResolveError):
            resolver.run(_scenes(), self.project, source="whatever")


class TestStep03WasNotTouched(unittest.TestCase):
    """"step03 안에 IMPORT 분기 금지"."""

    def test_step03_has_no_branch_on_existing_audio(self):
        tree = ast.parse(open(step03_tts.__file__, encoding="utf-8").read())

        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)

        for name in names:
            with self.subTest(imported=name):
                self.assertNotIn("resolve", name)
                self.assertNotIn("voice_import", name)

    def test_the_resolver_generates_no_audio(self):
        tree = ast.parse(open(resolver.__file__, encoding="utf-8").read())

        top_level = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                top_level.add(node.module or "")
                top_level.update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                top_level.update(a.name for a in node.names)

        for forbidden in ("scene_tts_service", "step03_tts", "texttospeech",
                          "app.production", "duration_optimizer"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in n for n in top_level), forbidden,
                )

    def test_it_writes_no_audio_itself(self):
        """조립은 엔진 함수가 한다 - Resolver가 직접 ffmpeg를 부르지
        않는다."""

        tree = ast.parse(open(resolver.__file__, encoding="utf-8").read())

        called = {
            node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
        }

        for forbidden in ("Popen", "copyfile", "remove", "rename"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, called)

        # ffmpeg를 직접 부르지 않는다 - 조립은 audio_service가 한다.
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")

        self.assertNotIn("subprocess", imported)


class TestThePipelineChangedInOnePlace(unittest.TestCase):

    def test_the_pipeline_calls_the_resolver_not_step03(self):
        import app.pipeline.pipeline as pipeline

        tree = ast.parse(open(pipeline.__file__, encoding="utf-8").read())

        called = {
            f"{node.func.value.id}.{node.func.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        }

        self.assertIn("step03_voice_resolve.run", called)
        self.assertNotIn("step03_tts.run", called)

    def test_the_other_steps_are_untouched(self):
        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        for call in ("step01_script_resolve.run(", "step02_asset_resolve.run(",
                     "step04_subtitle.run(", "step05_video.run(",
                     "step06_thumbnail.run(", "step07_quality.run("):
            with self.subTest(call=call):
                self.assertIn(call, source)


class TestTheThreeResolversAgree(unittest.TestCase):
    """Sprint114 공통화를 판단하려면 지금 무엇이 같은지 고정해 둬야
    한다."""

    MODULES = ("step01_script_resolve", "step02_asset_resolve",
               "step03_voice_resolve")

    def _module(self, name):
        import importlib

        return importlib.import_module(f"app.steps.{name}")

    def test_they_share_the_same_vocabulary(self):
        for name in self.MODULES:
            module = self._module(name)
            with self.subTest(module=name):
                self.assertEqual(module.AUTO, "auto")
                self.assertEqual(module.IMPORT, "import")
                self.assertEqual(module.MANUAL, "manual")
                self.assertEqual(
                    sorted(module.SOURCES), ["auto", "import", "manual"],
                )
                self.assertEqual(
                    sorted(module.PREPARED_SOURCES), ["import", "manual"],
                )

    def test_they_each_own_their_metadata_field(self):
        fields = {self._module(n).SOURCE_FIELD for n in self.MODULES}

        self.assertEqual(len(fields), len(self.MODULES))

    def test_they_all_answer_auto_for_an_empty_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in self.MODULES:
                with self.subTest(module=name):
                    self.assertEqual(
                        self._module(name).detect_source(tmp), "auto",
                    )

    def test_metadata_beats_disk_everywhere(self):
        for name in self.MODULES:
            module = self._module(name)
            with self.subTest(module=name):
                with tempfile.TemporaryDirectory() as tmp:
                    with open(os.path.join(tmp, "project.json"), "w",
                              encoding="utf-8") as f:
                        json.dump({module.SOURCE_FIELD: "manual"}, f)

                    self.assertEqual(module.detect_source(tmp), "manual")


if __name__ == "__main__":
    unittest.main()
