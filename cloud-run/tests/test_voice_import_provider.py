"""
Sprint112 - 사용자가 만든 음성을 쓴다 (Epic 54, Phase 11).

TTS를 부르지 않는다. 사용자가 준 파일을 엔진이 쓰는 자리에 놓는다.

엔진이 쓰는 자리는 audio_policy가 정한다 - tts.mp3가 아니라
audio/scenes/scene{N}.wav이고, 포맷은 24kHz mono PCM이다. 그 정책이
있는 이유가 "다른 소스가 섞여 들어와도 한 포맷으로 수렴한다"이므로,
받은 mp3/m4a는 그 포맷으로 맞춰 넣는다. 길이는 건드리지 않는다.

길이는 재기만 한다.

    고치지 않는다. 늘리지 않는다. 이어붙이지 않는다.

짧으면 경고하고, 만들지 말지는 사용자가 정한다 - Sprint108이 대본
길이에서 내린 것과 같은 결론이다.
"""

import ast
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import source_modes, stages
from app.production.providers.voice_import import (
    VOICE_IMPORT,
    VoiceImportError,
    VoiceImportProvider,
)
from app.production.stage_provider import StageProviderError
from app.production.stage_request import StageRequest
from app.services import audio_policy


def _has_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=20)
        return True
    except Exception:
        return False


HAS_FFMPEG = _has_ffmpeg()


class _Case(unittest.TestCase):
    """실제 인코딩은 ffmpeg가 한다. 대부분의 테스트는 그것을 세워 두고
    놓는 규칙만 본다 - 규칙이 틀린 것과 ffmpeg가 없는 것은 다른
    문제다."""

    SECONDS = 15.0

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = os.path.join(self._tmp.name, "20260101_000001")
        os.makedirs(self.project)
        self.source = os.path.join(self._tmp.name, "given")
        os.makedirs(self.source)

        import shutil

        from app.production.providers import voice_import

        normalize = patch.object(
            voice_import, "_normalize",
            side_effect=lambda src, dst: shutil.copyfile(src, dst),
        )
        normalize.start()
        self.addCleanup(normalize.stop)

        duration = patch.object(
            voice_import, "_duration", side_effect=lambda path: self.SECONDS,
        )
        duration.start()
        self.addCleanup(duration.stop)

    def _files(self, names):
        paths = []
        for name in names:
            path = os.path.join(self.source, name)
            with open(path, "wb") as f:
                f.write(b"RIFF____WAVEfmt ")
            paths.append(path)
        return paths

    def _zip(self, names):
        path = os.path.join(self._tmp.name, "voice.zip")
        with zipfile.ZipFile(path, "w") as archive:
            for name in names:
                archive.writestr(name, b"RIFF____WAVEfmt ")
        return path

    def _request(self, scenes=3):
        return StageRequest(
            project_path=self.project,
            scenes=[
                # 3 scene × 15초 = 45초. 기본값은 경고가 없는 상태다.
                {"scene": n, "narration": "안녕하세요 " * 20}
                for n in range(1, scenes + 1)
            ],
        )

    def _scene_path(self, number):
        return os.path.join(
            self.project, "audio", "scenes",
            audio_policy.scene_audio_filename(number),
        )


class TestTheContract(unittest.TestCase):

    def test_it_supports_import_and_manual_only(self):
        capabilities = VoiceImportProvider().capabilities

        self.assertEqual(
            sorted(capabilities.supported_source_modes),
            sorted([source_modes.IMPORT, source_modes.MANUAL]),
        )
        self.assertEqual(capabilities.stage, stages.VOICE)

    def test_generate_is_refused(self):
        """TTS를 부르지 않는다."""

        with self.assertRaises(StageProviderError):
            VoiceImportProvider().generate(StageRequest())

    def test_the_cost_is_zero(self):
        estimate = VoiceImportProvider().estimate_cost(
            StageRequest(), source_modes.MANUAL,
        )

        self.assertEqual(estimate.amount, 0.0)
        self.assertTrue(estimate.free)

    def test_it_calls_no_api(self):
        from app.production.providers import voice_import

        tree = ast.parse(open(voice_import.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")

        for forbidden in ("requests", "genai", "texttospeech",
                          "scene_tts_service", "step03"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(any(forbidden in n for n in names), forbidden)

    def test_it_is_registered_for_the_voice_stage(self):
        from app.production.providers import bootstrap
        from app.production.registry import StageProviderRegistry

        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        self.assertIn(
            VOICE_IMPORT,
            [p.name for p in registry.available(stages.VOICE,
                                                source_modes.MANUAL)],
        )
        self.assertNotIn(
            VOICE_IMPORT,
            [p.name for p in registry.available(stages.VOICE,
                                                source_modes.GENERATE)],
        )


class TestAcceptingFiles(_Case):

    def test_individual_files_in_order(self):
        paths = self._files(["a.wav", "b.wav", "c.wav"])

        result = VoiceImportProvider().accept_manual(paths, self._request(3))

        self.assertEqual(len(result["voices"]), 3)

    def test_a_folder(self):
        self._files(["0001.mp3", "0002.mp3", "0003.mp3"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(3),
        )

        self.assertEqual(len(result["voices"]), 3)

    def test_a_zip(self):
        archive = self._zip(["0001.wav", "0002.wav", "0003.wav"])

        result = VoiceImportProvider().accept_manual(archive, self._request(3))

        self.assertEqual(len(result["voices"]), 3)

    def test_a_zip_with_a_folder_inside(self):
        archive = self._zip(["voice/0001.wav", "voice/0002.wav",
                             "voice/0003.wav"])

        result = VoiceImportProvider().accept_manual(archive, self._request(3))

        self.assertEqual(len(result["voices"]), 3)

    def test_import_mode_works_the_same_way(self):
        paths = self._files(["a.wav", "b.wav", "c.wav"])

        result = VoiceImportProvider().import_content(paths, self._request(3))

        self.assertEqual(len(result["voices"]), 3)

    def test_every_supported_format(self):
        for suffix in (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"):
            with self.subTest(suffix=suffix):
                path = os.path.join(self.source, "one" + suffix)
                with open(path, "wb") as f:
                    f.write(b"RIFF____WAVEfmt ")

                result = VoiceImportProvider().accept_manual(
                    [path], self._request(1),
                )

                self.assertEqual(len(result["voices"]), 1)

    def test_numeric_names_sort_numerically(self):
        self._files(["2.wav", "10.wav", "1.wav"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(3),
        )

        self.assertEqual(
            [os.path.basename(v["source"]) for v in result["voices"]],
            ["1.wav", "2.wav", "10.wav"],
        )


class TestTheOutputMatchesTheEngine(_Case):
    """엔진이 쓰는 자리는 audio_policy가 정한다 - tts.mp3가 아니다."""

    def _result(self):
        self._files(["a.wav", "b.wav", "c.wav"])
        return VoiceImportProvider().accept_manual(
            self.source, self._request(3),
        )

    def test_the_files_land_where_step03_puts_them(self):
        self._result()

        for number in (1, 2, 3):
            with self.subTest(scene=number):
                self.assertTrue(os.path.exists(self._scene_path(number)))

    def test_the_filename_comes_from_the_policy(self):
        result = self._result()

        self.assertEqual(result["voices"][0]["voice_path"], self._scene_path(1))
        self.assertTrue(
            result["voices"][0]["voice_path"].endswith(
                audio_policy.NARRATION_EXTENSION,
            )
        )

    def test_the_keys_say_where_it_came_from(self):
        voice = self._result()["voices"][0]

        self.assertEqual(voice["asset_type"], "voice")
        self.assertEqual(voice["provider"], VOICE_IMPORT)
        self.assertEqual(voice["confidence"], 1.0)

    def test_it_does_not_use_the_image_slot(self):
        """asset_path/asset_type은 이미지 단계가 이미 쓰고 있다.

        같은 키에 음성을 쓰면 이미지 경로가 사라진다 - 이 저장소에서
        한 슬롯을 두 곳에서 쓰는 구조는 이미 여러 번 사고를 냈다."""

        voice = self._result()["voices"][0]

        self.assertNotIn("asset_path", voice)
        self.assertIn("voice_path", voice)

    def test_the_original_file_is_left_alone(self):
        paths = self._files(["a.wav"])
        before = open(paths[0], "rb").read()

        VoiceImportProvider().accept_manual(paths, self._request(1))

        self.assertEqual(open(paths[0], "rb").read(), before)

    def test_one_file_for_many_scenes_becomes_the_whole_narration(self):
        """자를 수 없다. 경계를 우리가 알 수 없고, 자르는 것은
        자동 수정이다."""

        paths = self._files(["whole.mp3"])

        result = VoiceImportProvider().accept_manual(paths, self._request(3))

        self.assertEqual(
            result["voice_path"],
            os.path.join(self.project, "audio", audio_policy.VOICE_FILENAME),
        )
        self.assertTrue(os.path.exists(result["voice_path"]))
        self.assertEqual(result["voices"], [])

    def test_one_file_for_one_scene_is_that_scene(self):
        paths = self._files(["only.wav"])

        result = VoiceImportProvider().accept_manual(paths, self._request(1))

        self.assertEqual(result["voices"][0]["voice_path"], self._scene_path(1))
        self.assertIsNone(result["voice_path"])


class TestDurationIsMeasuredNotFixed(_Case):
    """고치지 않는다. 늘리지 않는다. 이어붙이지 않는다."""

    def setUp(self):
        super().setUp()

        # 예상 길이는 대본 글자 수가 정한다. 여기서 보려는 것은 잰
        # 값과 예상값을 어떻게 비교하는가이므로, 예상값을 45초로
        # 세워 두고 잰 값만 움직인다.
        from app.services import duration_estimator

        estimate = patch.object(
            duration_estimator, "estimate_script_duration", return_value=45.0,
        )
        estimate.start()
        self.addCleanup(estimate.stop)

    def test_it_reports_measured_and_expected_seconds(self):
        self._files(["a.wav", "b.wav", "c.wav"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(3),
        )

        self.assertAlmostEqual(result["measured_seconds"], 45.0, places=2)
        self.assertGreater(result["expected_seconds"], 0)

    def test_a_short_voice_warns(self):
        self.SECONDS = 4.0
        self._files(["a.wav", "b.wav", "c.wav"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(3),
        )

        self.assertTrue(any("짧습니다" in w for w in result["warnings"]))

    def test_a_long_voice_warns(self):
        self.SECONDS = 90.0
        self._files(["a.wav", "b.wav", "c.wav"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(3),
        )

        self.assertTrue(any("깁니다" in w for w in result["warnings"]))

    def test_a_matching_length_has_no_duration_warning(self):
        self._files(["a.wav", "b.wav", "c.wav"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(3),
        )

        self.assertEqual(
            [w for w in result["warnings"] if "짧" in w or "깁" in w], [],
        )

    def test_it_never_changes_the_placed_audio(self):
        """경고가 나와도 파일은 그대로다."""

        self.SECONDS = 4.0
        self._files(["a.wav", "b.wav", "c.wav"])

        VoiceImportProvider().accept_manual(self.source, self._request(3))

        for number in (1, 2, 3):
            with self.subTest(scene=number):
                self.assertEqual(
                    open(self._scene_path(number), "rb").read(),
                    b"RIFF____WAVEfmt ",
                )

    def test_the_estimator_is_the_existing_one(self):
        """새 계산을 만들지 않는다 - Duration Gate가 쓰는 그것이다."""

        from app.production.providers import voice_import
        from app.services import duration_estimator

        self._files(["a.wav"])

        with patch.object(
            duration_estimator, "estimate_script_duration", return_value=33.0,
        ) as estimate:
            result = voice_import.VoiceImportProvider().accept_manual(
                self.source, self._request(1),
            )

        estimate.assert_called_once()
        self.assertEqual(result["expected_seconds"], 33.0)

    def test_an_unplayable_file_is_refused(self):
        """재생할 수 없는 파일은 길이도 0이다 - 놓아 봐야 렌더에서
        죽는다."""

        self.SECONDS = 0.0
        self._files(["broken.wav"])

        with self.assertRaises(VoiceImportError) as caught:
            VoiceImportProvider().accept_manual(self.source, self._request(1))

        self.assertIn("broken.wav", str(caught.exception))


class TestCountMismatchWarnsWithoutFixing(_Case):

    def test_too_few_names_the_missing_scenes(self):
        self._files(["a.wav", "b.wav"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(6),
        )

        self.assertTrue(any("6" in w for w in result["warnings"]))
        self.assertEqual(len(result["voices"]), 2)

    def test_too_many_says_which_are_unused(self):
        self._files(["a.wav", "b.wav", "c.wav", "d.wav"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(2),
        )

        self.assertTrue(result["warnings"])
        self.assertEqual(len(result["voices"]), 2)

    def test_the_counts_are_reported(self):
        self._files(["a.wav", "b.wav"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(5),
        )

        self.assertEqual(result["scene_count"], 5)
        self.assertEqual(result["voice_count"], 2)


class TestPreview(_Case):
    """파일명 · 재생시간 · Play."""

    def test_each_placed_file_reports_a_name_and_seconds(self):
        self._files(["intro.wav", "body.wav", "outro.wav"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(3),
        )

        for voice in result["voices"]:
            with self.subTest(scene=voice["scene"]):
                self.assertIn("name", voice)
                self.assertEqual(voice["seconds"], 15.0)

        self.assertEqual(
            [v["name"] for v in result["voices"]],
            ["body.wav", "intro.wav", "outro.wav"],
        )

    def test_the_whole_narration_reports_its_length_too(self):
        self._files(["whole.mp3"])

        result = VoiceImportProvider().accept_manual(
            self.source, self._request(3),
        )

        self.assertEqual(result["measured_seconds"], 15.0)


class TestRefusals(_Case):

    def test_an_unsupported_format_is_refused(self):
        path = os.path.join(self.source, "a.wma")
        with open(path, "wb") as f:
            f.write(b"x")

        with self.assertRaises(VoiceImportError) as caught:
            VoiceImportProvider().accept_manual([path], self._request(1))

        self.assertIn("wma", str(caught.exception).lower())

    def test_no_audio_at_all_is_refused(self):
        with self.assertRaises(VoiceImportError):
            VoiceImportProvider().accept_manual(self.source, self._request(1))

    def test_a_missing_path_is_refused(self):
        with self.assertRaises(VoiceImportError):
            VoiceImportProvider().accept_manual("/nope/here", self._request(1))

    def test_without_scenes_it_refuses(self):
        paths = self._files(["a.wav"])

        with self.assertRaises(ValueError):
            VoiceImportProvider().accept_manual(
                paths, StageRequest(project_path=self.project),
            )

    def test_a_refusal_places_nothing(self):
        path = os.path.join(self.source, "a.wma")
        with open(path, "wb") as f:
            f.write(b"x")

        with self.assertRaises(VoiceImportError):
            VoiceImportProvider().accept_manual([path], self._request(1))

        self.assertFalse(
            os.path.exists(os.path.join(self.project, "audio", "scenes",
                                        audio_policy.scene_audio_filename(1))),
        )


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg가 없으면 실제 변환을 볼 수 없다")
class TestRealConversion(unittest.TestCase):
    """정책 포맷으로 맞춰 넣는다. 길이는 건드리지 않는다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = os.path.join(self._tmp.name, "p")
        os.makedirs(self.project)

        # 실제로 디코딩되는 3초짜리 mp3를 만든다.
        self.given = os.path.join(self._tmp.name, "given.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "sine=frequency=440:duration=3", "-ac", "2", "-ar", "44100",
             self.given],
            capture_output=True, check=True,
        )

    def test_it_lands_as_policy_pcm(self):
        VoiceImportProvider().accept_manual(
            [self.given],
            StageRequest(project_path=self.project,
                         scenes=[{"scene": 1, "narration": "안녕하세요"}]),
        )

        placed = os.path.join(
            self.project, "audio", "scenes",
            audio_policy.scene_audio_filename(1),
        )

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_name,sample_rate,channels",
             "-of", "default=noprint_wrappers=1", placed],
            capture_output=True, text=True,
        ).stdout

        self.assertIn(audio_policy.NARRATION_PCM_CODEC, probe)
        self.assertIn(str(audio_policy.NARRATION_SAMPLE_RATE_HZ), probe)
        self.assertIn("channels=%d" % audio_policy.NARRATION_CHANNELS, probe)

    def test_the_length_is_not_changed(self):
        from app.production.providers import voice_import

        result = VoiceImportProvider().accept_manual(
            [self.given],
            StageRequest(project_path=self.project,
                         scenes=[{"scene": 1, "narration": "안녕하세요"}]),
        )

        self.assertAlmostEqual(
            result["voices"][0]["seconds"],
            voice_import._duration(self.given),
            places=1,
        )


class TestNothingWasWiredIn(unittest.TestCase):
    """Pipeline 연결은 Resolver 앞까지다."""

    def test_step03_was_not_touched(self):
        from app.steps import step03_tts

        source = open(step03_tts.__file__, encoding="utf-8").read()

        self.assertNotIn("voice_import", source)
        self.assertNotIn("resolve", source)

    def test_the_pipeline_does_not_know_about_it(self):
        import app.pipeline.pipeline as pipeline

        tree = ast.parse(open(pipeline.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)

        for name in names:
            with self.subTest(imported=name):
                self.assertNotIn("app.production", name)

        self.assertIn("step03_tts.run(", open(
            pipeline.__file__, encoding="utf-8").read())


class TestTheSharedCollectorIsSharedNotCopied(unittest.TestCase):
    """이미지와 음성이 같은 것을 각자 적어 두면 한쪽만 고쳐진다."""

    def test_both_providers_use_it(self):
        from app.production.providers import image_import, voice_import

        for module in (image_import, voice_import):
            with self.subTest(module=module.__name__):
                tree = ast.parse(open(module.__file__, encoding="utf-8").read())
                names = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        names.add(node.module or "")
                        names.update(a.name for a in node.names)

                self.assertTrue(
                    any("incoming_files" in n for n in names),
                    module.__name__,
                )

    def test_it_knows_nothing_about_stages(self):
        from app.production.providers import incoming_files

        source = open(incoming_files.__file__, encoding="utf-8").read()

        for word in ("image_import", "voice_import", "scene", "audio_policy"):
            with self.subTest(word=word):
                self.assertNotIn(word, source.split('"""')[-1])


if __name__ == "__main__":
    unittest.main()
