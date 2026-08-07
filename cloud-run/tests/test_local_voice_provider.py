"""
Sprint151 - 내 PC 음성으로 만든다 (Epic 57, Phase 2).

무엇을 지키는가
---------------
    1. voice 폴더를 훑으면 길이·샘플레이트·채널이 적힌다
                                          test_local_voice_scan
    2. scene에 맞는 음성이 골라진다        test_local_voice_selected
    3. 그 길에서 TTS API를 부르지 않는다   test_free_mode_never_calls_tts_api
    4. 고른 것이 남는다                    test_voice_provider_saved
    5. 음성이 없으면 렌더가 막힌다         test_missing_voice_file_blocks_render

다섯 번째가 이 Sprint에서 가장 중요하다. 이미지가 없으면 검은 화면이
나오지만, 음성이 없으면 자막 시각이 통째로 어긋난다 - 조용히 넘어가면
안 되는 자리다.

왜 번호로 고르는가
------------------
그림은 낱말이 겹치는 것을 골라도 된다. 조금 안 맞는 그림은 어색할
뿐이다. 음성은 다르다 - 3번 scene에 2번 나레이션이 들어가면 자막과
소리가 서로 다른 말을 하고, 그것은 영상이 망가진 것이다.

그래서 나레이션 글로 닮은 파일을 찾지 않고, scene 번호가 이름에 있는
파일만 쓴다. 없으면 없다고 말한다.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.providers import local_voice_provider, tts_provider
from app.services import (
    audio_policy, local_library, provider_selection, scene_order,
    scene_tts_service,
)


def _tone(path, seconds=1.0, hz=440, rate=44100, channels=2):
    """진짜 소리 파일. 빈 파일이면 ffmpeg가 무엇을 하는지 알 수 없다."""

    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f={hz}:d={seconds}",
         "-ar", str(rate), "-ac", str(channels), path],
        capture_output=True, check=True,
    )


def _probe(path):
    """실제로 무엇이 들어 있는가. 파일이 말하게 한다."""

    result = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "stream=sample_rate,channels,codec_name"
         ":format=duration",
         "-of", "default=noprint_wrappers=1", path],
        capture_output=True, text=True,
    )

    found = {}

    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            found[key] = value

    return found


class LocalVoiceScanTest(unittest.TestCase):
    """1. voice 폴더를 훑으면 소리의 성질이 적힌다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_local_voice_scan(self):
        _tone(os.path.join(self.root, "voice", "scene1.wav"),
              seconds=1.5, rate=44100, channels=2)
        _tone(os.path.join(self.root, "voice", "scene2.mp3"),
              seconds=2.0, rate=24000, channels=1)

        index = local_library.scan(self.root)
        by_name = {item["name"]: item for item in index["items"]}

        self.assertEqual(local_library.counts(index)["voice"], 2)

        first = by_name["scene1.wav"]

        self.assertAlmostEqual(first["duration"], 1.5, places=1)
        self.assertEqual(first["sample_rate"], 44100)
        self.assertEqual(first["channels"], 2)
        self.assertGreater(first["size"], 0)
        self.assertIsNotNone(first["modified"])

        second = by_name["scene2.mp3"]

        self.assertAlmostEqual(second["duration"], 2.0, places=1)
        self.assertEqual(second["sample_rate"], 24000)
        self.assertEqual(second["channels"], 1)

    def test_a_file_that_is_not_audio_is_measured_as_unknown(self):
        """읽지 못하면 None이다. 0으로 적으면 길이가 0인 소리가 된다."""

        path = os.path.join(self.root, "voice", "가짜.wav")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "wb") as f:
            f.write(b"not audio at all")

        item = local_library.scan(self.root)["items"][0]

        self.assertIsNone(item["duration"])
        self.assertIsNone(item["sample_rate"])
        self.assertIsNone(item["channels"])

    def test_images_do_not_carry_audio_fields(self):
        """그림에 샘플레이트를 적지 않는다 - 없는 사실이다."""

        from PIL import Image

        path = os.path.join(self.root, "images", "a.png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Image.new("RGB", (8, 8)).save(path)

        item = local_library.scan(self.root)["items"][0]

        self.assertNotIn("duration", item)
        self.assertNotIn("sample_rate", item)


class LocalVoiceSelectionTest(unittest.TestCase):
    """2. scene 번호에 맞는 음성이 골라진다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def _library(self, names, **kwargs):
        for name in names:
            _tone(os.path.join(self.root, "voice", name), **kwargs)

        local_library.save(self.project, local_library.scan(self.root))

    def _target(self, number):
        return os.path.join(
            self.project, "audio", "scenes",
            audio_policy.scene_audio_filename(number),
        )

    def test_local_voice_selected(self):
        self._library(["scene1.wav", "scene2.wav", "scene3.wav"])

        picked = local_voice_provider.find(self.project, 2)

        self.assertIsNotNone(picked)
        self.assertEqual(picked["name"], "scene2.wav")

    def test_several_naming_habits_all_work(self):
        """사람마다 이름을 다르게 짓는다. 번호만 읽으면 된다."""

        for names, number, expected in (
            (["1.wav", "2.wav"], 2, "2.wav"),
            (["01_인사.wav", "02_본론.wav"], 1, "01_인사.wav"),
            (["scene 3.mp3"], 3, "scene 3.mp3"),
            (["나레이션-4.wav"], 4, "나레이션-4.wav"),
        ):
            with self.subTest(names=names):
                shutil.rmtree(os.path.join(self.root, "voice"),
                              ignore_errors=True)
                self._library(names, seconds=0.5)

                picked = local_voice_provider.find(self.project, number)

                self.assertIsNotNone(picked, f"{names}에서 {number}를 못 찾음")
                self.assertEqual(picked["name"], expected)

    def test_a_wrong_number_is_never_substituted(self):
        """
        2번 음성밖에 없을 때 3번을 달라고 하면 없다고 한다.

        여기서 아무거나 주면 자막과 소리가 다른 말을 한다.
        """

        self._library(["scene2.wav"], seconds=0.5)

        self.assertIsNone(local_voice_provider.find(self.project, 3))

    def test_the_placed_file_follows_the_audio_policy(self):
        """
        놓인 파일은 정책 포맷이다 - 24kHz mono PCM.

        밖에서 온 44.1kHz 스테레오를 그대로 두면 뒤 단계의 concat이
        전체를 리샘플한다(audio_policy가 있는 이유다).
        """

        self._library(["scene1.wav"], seconds=1.0, rate=44100, channels=2)

        target = self._target(1)
        local_voice_provider.generate_voice("무릎을 펴 주세요", target)

        found = _probe(target)

        self.assertEqual(int(found["sample_rate"]),
                         audio_policy.NARRATION_SAMPLE_RATE_HZ)
        self.assertEqual(int(found["channels"]), audio_policy.NARRATION_CHANNELS)
        self.assertEqual(found["codec_name"], "pcm_s16le")

        # 길이는 손대지 않는다.
        self.assertAlmostEqual(float(found["duration"]), 1.0, places=1)

    def test_mp3_is_supported(self):
        self._library(["scene1.mp3"], seconds=1.0)

        target = self._target(1)
        local_voice_provider.generate_voice("무릎", target)

        self.assertTrue(os.path.exists(target))
        self.assertEqual(_probe(target)["codec_name"], "pcm_s16le")

    def test_no_file_fails_and_says_which_scene(self):
        self._library(["scene1.wav"], seconds=0.5)

        target = self._target(2)

        with self.assertRaises(local_voice_provider.LocalVoiceUnavailable) as e:
            local_voice_provider.generate_voice("두 번째", target)

        self.assertIn("2", str(e.exception))
        self.assertFalse(os.path.exists(target))

    def test_an_unplayable_file_leaves_nothing_behind(self):
        """길이를 읽지 못하는 것을 놓으면 렌더가 죽는다. 먼저 막는다."""

        path = os.path.join(self.root, "voice", "scene1.wav")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "wb") as f:
            f.write(b"broken")

        local_library.save(self.project, local_library.scan(self.root))

        target = self._target(1)

        with self.assertRaises(local_voice_provider.LocalVoiceUnavailable):
            local_voice_provider.generate_voice("첫 번째", target)

        self.assertFalse(os.path.exists(target))


class FreeModeCallsNoTtsApiTest(unittest.TestCase):
    """3. 무료 모드에서는 TTS API가 불리지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def test_free_mode_never_calls_tts_api(self):
        """
        찾았을 때도, 못 찾았을 때도 유료 쪽은 한 번도 불리지 않는다.

        못 찾았을 때가 더 중요하다 - 그때 몰래 Google TTS로 넘어가면
        "비용 0원"이 거짓이 된다.
        """

        for number in (1, 2):
            _tone(os.path.join(self.root, "voice", f"scene{number}.wav"),
                  seconds=0.5)

        local_library.save(self.project, local_library.scan(self.root))

        scenes = [
            {"scene": 1, "narration": "첫 번째 문장입니다"},
            {"scene": 2, "narration": "두 번째 문장입니다"},
        ]

        with patch.object(
            tts_provider, "google_tts_provider",
        ) as google, patch.object(
            tts_provider, "elevenlabs_provider",
        ) as eleven:

            outputs = scene_tts_service.create_scene_tts(
                scenes, self.project, provider="local_voice",
            )

            for path in outputs:
                self.assertTrue(os.path.exists(path))

            # 세 번째 scene은 음성이 없다 - 여기서 폴백이 일어나면 안 된다.
            with self.assertRaises(
                local_voice_provider.LocalVoiceUnavailable
            ):
                scene_tts_service.create_scene_tts(
                    scenes + [{"scene": 3, "narration": "세 번째"}],
                    self.project, provider="local_voice",
                )

            google.generate_voice.assert_not_called()
            eleven.generate_voice.assert_not_called()

    def test_the_module_imports_no_paid_engine(self):
        """import만으로도 붙어 있으면 언젠가 누군가 부른다."""

        import ast

        with open(local_voice_provider.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        imported = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        forbidden = (
            "google", "elevenlabs", "requests", "vertexai",
            "app.providers.google_tts_provider",
            "app.providers.elevenlabs_provider",
        )

        for name in sorted(imported):
            for bad in forbidden:
                self.assertFalse(
                    name == bad or name.startswith(bad + "."),
                    f"local_voice_provider가 {name}을 import한다",
                )

    def test_the_paid_engines_were_not_touched(self):
        """
        이 Sprint는 Google TTS와 ElevenLabs를 건드리지 않았다.

        두 모듈이 local_voice를 알면 안 된다 - 알게 되는 순간 그쪽
        경로에도 이 Sprint의 결정이 새어 든다.
        """

        import ast

        from app.providers import elevenlabs_provider, google_tts_provider

        for module in (google_tts_provider, elevenlabs_provider):
            with open(module.__file__, encoding="utf-8") as f:
                tree = ast.parse(f.read())

            constants = {
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
            }

            with self.subTest(module=module.__name__):
                self.assertNotIn("local_voice", constants)


class VoiceProviderSavedTest(unittest.TestCase):
    """4. 고른 것이 프로젝트에 남는다."""

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        import json

        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"topic": "무릎 통증"}, f)

    def test_voice_provider_saved(self):
        import json

        provider_selection.save(self.project, {"voice": "local_voice"})

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["voice_provider"], "local_voice")

        self.assertEqual(
            provider_selection.selected(self.project, "voice"), "local_voice")
        self.assertEqual(
            provider_selection.all_selected(self.project)["voice"],
            "local_voice")

        # 다른 단계는 건드리지 않는다.
        self.assertNotIn("image_provider", saved)
        self.assertEqual(saved["topic"], "무릎 통증")

    def test_local_voice_is_a_wired_choice(self):
        self.assertIn("local_voice", provider_selection.WIRED["voice"])

        provider_selection.require_wired("voice", "local_voice")

    def test_the_paid_ones_are_still_wired(self):
        """이 Sprint가 기존 선택지를 빼앗지 않았다."""

        for name in ("google", "elevenlabs"):
            with self.subTest(name=name):
                provider_selection.require_wired("voice", name)

    def test_the_selection_reaches_the_engine(self):
        """
        프로젝트에 적힌 것이 실제로 그 Provider를 부른다.

        적히기만 하고 안 불리면 화면이 거짓말을 한다.
        """

        provider_selection.save(self.project, {"voice": "local_voice"})

        with patch.object(tts_provider, "generate_voice") as generate:
            scene_tts_service.create_scene_tts(
                [{"scene": 1, "narration": "n"}], self.project,
            )

        self.assertEqual(
            generate.call_args.kwargs["provider"], "local_voice")


class MissingVoiceBlocksRenderTest(unittest.TestCase):
    """5. 음성이 없으면 렌더가 막힌다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        from PIL import Image

        for number in (1, 2):
            path = os.path.join(self.project, "images", f"scene{number}.png")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            Image.new("RGB", (8, 8)).save(path)

        self.scenes = [
            {"scene": 1, "narration": "첫 번째"},
            {"scene": 2, "narration": "두 번째"},
        ]

    def test_missing_voice_file_blocks_render(self):
        """
        내 PC에 2번 음성이 없으면, 2번 wav가 안 생기고 렌더가 막힌다.

        Sprint145가 만든 검사를 그대로 쓴다 - 새 관문을 만들지 않는다.
        """

        _tone(os.path.join(self.root, "voice", "scene1.wav"), seconds=0.5)
        local_library.save(self.project, local_library.scan(self.root))

        with self.assertRaises(local_voice_provider.LocalVoiceUnavailable):
            scene_tts_service.create_scene_tts(
                self.scenes, self.project, provider="local_voice",
            )

        problems = scene_order.render_problems(self.project, self.scenes)

        self.assertIn("Scene 2 음성이 없습니다", problems)
        self.assertNotIn("Scene 1 음성이 없습니다", problems)

    def test_when_every_voice_is_there_nothing_blocks(self):
        for number in (1, 2):
            _tone(os.path.join(self.root, "voice", f"scene{number}.wav"),
                  seconds=0.5)

        local_library.save(self.project, local_library.scan(self.root))

        scene_tts_service.create_scene_tts(
            self.scenes, self.project, provider="local_voice",
        )

        self.assertEqual(
            scene_order.render_problems(self.project, self.scenes), [])

    def test_the_render_endpoint_refuses(self):
        """화면에서 눌러도 막힌다 - 검사는 라우터가 이미 부른다."""

        from fastapi.testclient import TestClient

        from app.main import app
        from app.routers import studio as studio_router

        _tone(os.path.join(self.root, "voice", "scene1.wav"), seconds=0.5)
        local_library.save(self.project, local_library.scan(self.root))

        import json

        script = os.path.join(self.project, "script.json")
        with open(script, "w", encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": self.scenes}, f)

        real = studio_router._project_path
        studio_router._project_path = lambda project_id: self.project

        try:
            response = TestClient(app).post("/studio/api/review/p1/render")
        finally:
            studio_router._project_path = real

        self.assertEqual(response.status_code, 400)
        self.assertIn("Scene 2 음성이 없습니다", str(response.json()))


class TheCatalogSaysItIsFreeTest(unittest.TestCase):
    """
    화면이 "API 비용 없음"이라고 말할 근거.

    지어내지 않는다 - ProviderCapabilities의 estimated_cost가 0.0일
    때만이고, 그 필드는 "0.0은 무료임을 안다는 뜻이고 None은 아직
    모른다는 뜻"이라고 이미 정해 두었다.
    """

    def _registry(self):
        from app.production.providers import bootstrap
        from app.production.registry import StageProviderRegistry

        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        return registry

    def test_local_voice_is_registered_and_free(self):
        from app.production import stages

        provider = self._registry().get(stages.VOICE, "local_voice")

        self.assertEqual(provider.capabilities.estimated_cost, 0.0)
        self.assertEqual(provider.capabilities.required_settings, ())
        self.assertEqual(provider.capabilities.authentication, "")

    def test_the_paid_ones_do_not_claim_to_be_free(self):
        """모르는 것은 모른다고 둔다. 0.0이라고 적으면 거짓이 된다."""

        from app.production import stages

        registry = self._registry()

        for name in ("current", "elevenlabs"):
            with self.subTest(name=name):
                cost = registry.get(stages.VOICE, name).capabilities.\
                    estimated_cost

                self.assertNotEqual(cost, 0.0)

    def test_local_stock_says_the_same_thing(self):
        """
        같은 이유로 무료인 것은 같은 말을 해야 한다.

        Sprint150의 내 PC 자료도 파일을 복사할 뿐이라 돈이 들지 않는다.
        한쪽만 "비용 없음"이라고 하면 화면이 둘을 다르게 말한다.
        """

        from app.production import stages

        provider = self._registry().get(stages.IMAGE, "local_stock")

        self.assertEqual(provider.capabilities.estimated_cost, 0.0)


if __name__ == "__main__":
    unittest.main()
