"""
Sprint125 - ElevenLabs를 Provider 자리에 올린다 (Epic 56, Phase 2).

시작 전에 확인한 사실 하나가 이 스프린트의 모양을 정했다.

    app/providers/elevenlabs_provider.py는 이미 있다.
    app/providers/tts_provider.py가 이미 그것을 부른다.
    TTS_PROVIDER=elevenlabs면 파이프라인 전체가 이미 ElevenLabs로 돈다.

실제 API 호출도, voice 이름 조회도(못 찾으면 다른 voice로 대체하지
않고 에러), 정책 포맷(24kHz mono PCM) 변환도 전부 되어 있다. 그래서
여기서 새로 만드는 것은 엔진이 아니라 *자리*다 - app.production의
StageProvider로 감싸고, 설정이 됐는지 판정하고, 화면이 그것을 말하게
한다.

한 가지를 바꿨다. tts_provider.generate_voice가 어느 Provider를 쓸지
환경변수에서만 읽었는데, 인자로도 받을 수 있게 했다. 기본값은 예전
그대로(환경변수)라 Google 경로는 한 글자도 달라지지 않는다. 인자를
더한 이유는 StageProvider가 환경변수를 잠깐 바꿔 쓰면 안 되기
때문이다 - studio_jobs는 파이프라인을 스레드로 돌리므로 두 작업이
겹치면 서로의 설정을 덮어쓴다.

출력은 step03과 같아야 한다. scene wav가 반드시 있어야 하고
(subtitle_service가 scene 오디오 개수를 센다), voice.wav는 그
scene들을 이어 만든다 - 새로 만들지 않고 엔진의 concat을 그대로
부른다.
"""

import ast
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import source_modes, stages
from app.production.providers import bootstrap
from app.production.providers.elevenlabs_voice import (
    ELEVENLABS,
    ElevenLabsVoiceProvider,
)
from app.production.registry import StageProviderRegistry
from app.production.stage_provider import ProviderUnavailable
from app.production.stage_request import StageRequest
from app.services import audio_policy

SCENES = [
    {"scene": n, "narration": f"{n}번 문장입니다"} for n in range(1, 4)
]

CONFIGURED = {
    "ELEVENLABS_API_KEY": "key-123",
    "ELEVENLABS_VOICE_ID": "voice-abc",
}


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name
        os.makedirs(os.path.join(self.project, "audio", "scenes"))

    def _request(self):
        return StageRequest(project_path=self.project, scenes=SCENES)


class TestTheContract(unittest.TestCase):

    def test_it_is_a_voice_generator(self):
        caps = ElevenLabsVoiceProvider().capabilities

        self.assertEqual(caps.stage, stages.VOICE)
        self.assertEqual(caps.supported_source_modes,
                         (source_modes.GENERATE,))

    def test_it_names_its_vendor(self):
        caps = ElevenLabsVoiceProvider().capabilities

        self.assertEqual(caps.display_name, "ElevenLabs")
        self.assertEqual(caps.vendor, "ElevenLabs")

    def test_it_is_no_longer_coming_soon(self):
        self.assertFalse(getattr(ElevenLabsVoiceProvider(), "coming_soon", False))

    def test_the_cost_is_still_unknown(self):
        """실측 금액 계산은 이번 범위가 아니다."""

        self.assertIsNone(ElevenLabsVoiceProvider().capabilities.estimated_cost)

    def test_it_replaces_the_coming_soon_stub(self):
        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        provider = registry.get(stages.VOICE, ELEVENLABS)

        self.assertIsInstance(provider, ElevenLabsVoiceProvider)


class TestItRefusesWithoutSettings(_Case):

    def test_no_api_key_is_refused_by_name(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderUnavailable) as caught:
                ElevenLabsVoiceProvider().generate(self._request())

        self.assertIn("ELEVENLABS_API_KEY", str(caught.exception))

    def test_no_voice_is_refused_by_name(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k"}, clear=True):
            with self.assertRaises(ProviderUnavailable) as caught:
                ElevenLabsVoiceProvider().generate(self._request())

        self.assertIn("ELEVENLABS_VOICE_ID", str(caught.exception))

    def test_a_voice_name_is_enough(self):
        env = {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_NAME": "Brandon"}

        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(ElevenLabsVoiceProvider().is_configured())

    def test_it_says_why_it_cannot_run(self):
        with patch.dict(os.environ, {}, clear=True):
            available, reason = ElevenLabsVoiceProvider().availability()

        self.assertFalse(available)
        self.assertIn("ELEVENLABS_API_KEY", reason)

    def test_it_is_available_once_configured(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            available, reason = ElevenLabsVoiceProvider().availability()

        self.assertTrue(available)
        self.assertEqual(reason, "")

    def test_refusing_writes_nothing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderUnavailable):
                ElevenLabsVoiceProvider().generate(self._request())

        self.assertEqual(
            os.listdir(os.path.join(self.project, "audio", "scenes")), [])


class TestTheOutputMatchesStep03(_Case):
    """subtitle_service가 차이를 몰라야 한다."""

    def _run(self):
        from app.providers import tts_provider
        from app.services import audio_service

        made = []

        def fake_voice(text, output_file, provider=None):
            made.append((text, output_file, provider))
            with open(output_file, "wb") as f:
                f.write(b"RIFF____WAVEfmt ")
            return output_file

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(tts_provider, "generate_voice", fake_voice):
                with patch.object(audio_service, "concat_scene_audio") as concat:
                    result = ElevenLabsVoiceProvider().generate(self._request())

        return result, made, concat

    def test_it_makes_one_wav_per_scene(self):
        self._run()

        self.assertEqual(
            sorted(os.listdir(os.path.join(self.project, "audio", "scenes"))),
            ["scene1.wav", "scene2.wav", "scene3.wav"],
        )

    def test_the_filenames_come_from_the_policy(self):
        _, made, _ = self._run()

        for index, (_, path, _) in enumerate(made, start=1):
            with self.subTest(index=index):
                self.assertTrue(path.endswith(
                    audio_policy.scene_audio_filename(index)))

    def test_it_numbers_them_the_same_way_step03_does(self):
        """create_scene_tts는 목록의 순서로 정한다 - 같아야 한다."""

        from app.services import scene_tts_service

        source = open(scene_tts_service.__file__, encoding="utf-8").read()

        self.assertIn("start=1", source)

        _, made, _ = self._run()
        self.assertEqual(len(made), 3)

    def test_it_asks_for_elevenlabs_explicitly(self):
        """환경변수를 잠깐 바꿔 쓰지 않는다 - 스레드가 겹친다."""

        _, made, _ = self._run()

        for text, path, provider in made:
            with self.subTest(path=path):
                self.assertEqual(provider, "elevenlabs")

    def test_voice_wav_is_made_by_the_engines_own_concat(self):
        _, _, concat = self._run()

        concat.assert_called_once()
        paths, target = concat.call_args[0]
        self.assertEqual(len(paths), 3)
        self.assertTrue(target.endswith(audio_policy.VOICE_FILENAME))

    def test_it_never_makes_only_the_joined_file(self):
        """scene wav 없이 voice.wav만 만들면 자막이 죽는다."""

        from app.production.providers import elevenlabs_voice

        source = open(elevenlabs_voice.__file__, encoding="utf-8").read()

        self.assertIn("scene_audio_filename", source)


class TestTheSelectionIsExplicitNotGlobal(unittest.TestCase):

    def test_the_tts_provider_takes_an_argument_now(self):
        import inspect

        from app.providers import tts_provider

        signature = inspect.signature(tts_provider.generate_voice)

        self.assertIn("provider", signature.parameters)

    def test_the_default_is_still_the_environment(self):
        """Google 경로는 한 글자도 달라지지 않는다."""

        from app.providers import google_tts_provider, tts_provider

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(google_tts_provider, "generate_voice",
                              return_value="ok") as google:
                tts_provider.generate_voice("문장", "/tmp/x.wav")

        google.assert_called_once()

    def test_asking_for_google_explicitly_works_too(self):
        from app.providers import google_tts_provider, tts_provider

        with patch.dict(os.environ,
                        {"TTS_PROVIDER": "elevenlabs"}, clear=True):
            with patch.object(google_tts_provider, "generate_voice",
                              return_value="ok") as google:
                tts_provider.generate_voice("문장", "/tmp/x.wav",
                                            provider="google")

        google.assert_called_once()

    def test_nobody_mutates_the_environment(self):
        from app.production.providers import elevenlabs_voice

        tree = ast.parse(open(elevenlabs_voice.__file__,
                              encoding="utf-8").read())
        assigned = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        }

        self.assertNotIn("setdefault", assigned)
        self.assertNotIn("putenv", assigned)


class TestTheModelIsConfigurable(unittest.TestCase):

    def test_the_env_overrides_the_default(self):
        from app.providers import elevenlabs_provider

        with patch.dict(os.environ,
                        {"ELEVENLABS_MODEL": "eleven_turbo_v2_5"}, clear=True):
            self.assertEqual(elevenlabs_provider.model_id(),
                             "eleven_turbo_v2_5")

    def test_without_it_the_default_stays(self):
        from app.providers import elevenlabs_provider

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(elevenlabs_provider.model_id(),
                             elevenlabs_provider.DEFAULT_MODEL_ID)


class TestTheScreenIsToldTheTruth(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def _voice_row(self):
        rows = self.client.get("/studio/api/production/stages").json()["stages"]
        return [r for r in rows if r["stage"] == "voice"][0]

    def test_elevenlabs_is_listed_with_its_status(self):
        entry = [p for p in self._voice_row()["provider_list"]
                 if p["name"] == ELEVENLABS][0]

        self.assertFalse(entry["coming_soon"])
        for key in ("available", "unavailable_reason"):
            with self.subTest(key=key):
                self.assertIn(key, entry)

    def test_it_says_the_key_is_missing_when_it_is(self):
        with patch.dict(os.environ, {}, clear=True):
            entry = [p for p in self._voice_row()["provider_list"]
                     if p["name"] == ELEVENLABS][0]

        self.assertFalse(entry["available"])
        self.assertIn("ELEVENLABS_API_KEY", entry["unavailable_reason"])

    def test_the_engine_facts_name_whoever_actually_runs(self):
        """TTS_PROVIDER가 무엇이든 화면은 실제로 도는 것을 말해야 한다."""

        with patch.dict(os.environ,
                        {"TTS_PROVIDER": "elevenlabs"}, clear=True):
            row = self._voice_row()

        self.assertIn("ElevenLabs", row["engine"]["name"])

    def test_google_is_named_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            row = self._voice_row()

        self.assertIn("Google", row["engine"]["name"])


class TestNothingElseMoved(unittest.TestCase):

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_the_google_provider_is_untouched(self):
        from app.providers import google_tts_provider

        source = open(google_tts_provider.__file__, encoding="utf-8").read()

        for word in ("elevenlabs", "ElevenLabs", "app.production"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)

    def test_the_engine_steps_are_untouched(self):
        from app.steps import step03_tts

        source = open(step03_tts.__file__, encoding="utf-8").read()

        self.assertNotIn("elevenlabs", source)
        self.assertNotIn("app.production", source)

    def test_scene_tts_service_is_untouched(self):
        from app.services import scene_tts_service

        source = open(scene_tts_service.__file__, encoding="utf-8").read()

        self.assertNotIn("elevenlabs", source)
        self.assertNotIn("provider=", source)

    def test_the_pipeline_and_resolvers_are_untouched(self):
        import app.pipeline.pipeline as pipeline
        from app.steps import step03_voice_resolve

        for module in (pipeline, step03_voice_resolve):
            for name in self._imports(module):
                with self.subTest(module=module.__name__, imported=name):
                    self.assertNotIn("app.production", name)
                    self.assertNotIn("elevenlabs", name)

    def test_the_review_workflow_is_untouched(self):
        from app.services import studio_review

        source = open(studio_review.__file__, encoding="utf-8").read()

        self.assertNotIn("elevenlabs", source)
        self.assertNotIn("app.production", source)


if __name__ == "__main__":
    unittest.main()
