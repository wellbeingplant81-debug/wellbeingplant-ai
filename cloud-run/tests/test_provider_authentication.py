"""
Sprint138 - 인증을 실제와 같게 적는다 (Epic 56, Phase 15).

Sprint136에서 비교 표를 만들 때 current의 인증 칸이 "필요 없음"으로
나왔다. required_settings가 비어 있었기 때문인데, 실제로는 자격이
필요하다. 화면이 사실이 아닌 말을 하고 있었다.

무엇이 실제로 필요한가 - 코드에서 확인한 것
-------------------------------------------
    script  current   genai.Client(vertexai=True, project=...)
                      -> Vertex AI ADC
    image   current   같은 클라이언트 -> Vertex AI ADC
    voice   current   texttospeech.TextToSpeechClient()
                      -> Google Cloud ADC
    metadata current  규칙 기반. 부르는 API가 없다 -> 인증 없음

    직접 호출         환경변수 이름 그대로
    가져오기          사람이 준 파일을 읽는다 -> 인증 없음

환경변수 이름으로 담을 수 없는 것이 있다
----------------------------------------
ADC는 환경변수 하나가 아니라 자격을 얻는 방식이다. required_settings에
억지로 밀어 넣으면 "그 이름을 넣으면 된다"는 뜻이 되어 또 틀린 말이
된다. 그래서 칸을 따로 둔다.

    authentication      환경변수가 아닌 방식(ADC 같은 것)
    required_settings   환경변수 이름

둘 다 비어 있으면 정말로 인증이 없는 것이다.

세 곳이 같은 말을 한다
----------------------
Provider Card · Summary · 비교 표가 같은 함수로 같은 문장을 만든다.
"""

import ast
import os
import re
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import stages
from app.production.providers import bootstrap
from app.production.registry import StageProviderRegistry

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)

VERTEX = "Vertex AI ADC"
GOOGLE_CLOUD = "Google Cloud ADC"
NONE = "인증 없음"

# 짐작해서 적는 말들.
BANNED = ("로그인 필요", "추천", "쉬움", "복잡", "간단", "어려움")


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _script():
    page = _page()
    return page[page.index("<script>"):]


def _function(name):
    script = _script()
    block = script[script.index(f"function {name}("):]
    end = block.find("\nfunction ", 1)

    return block if end < 0 else block[:end]


def _without_comments(block):
    return re.sub(r"//.*", "", block)


def _registry():
    registry = StageProviderRegistry()
    bootstrap.register_current_providers(registry)
    return registry


class TestTheCapabilityCarriesIt(unittest.TestCase):

    def test_there_is_a_place_for_it(self):
        from app.production import stage_provider

        caps = stage_provider.ProviderCapabilities(name="x", stage="script")

        self.assertEqual(caps.authentication, "")

    def test_it_is_separate_from_the_environment_names(self):
        """
        ADC는 환경변수 하나가 아니다. 같은 칸에 넣으면 "그 이름을
        넣으면 된다"는 뜻이 되어 또 틀린 말이 된다.
        """

        from app.production import stage_provider

        caps = stage_provider.ProviderCapabilities(
            name="x", stage="script", authentication=VERTEX)

        self.assertEqual(caps.required_settings, ())
        self.assertEqual(caps.authentication, VERTEX)


class TestTheCurrentEngineSaysWhatItActuallyUses(unittest.TestCase):

    def setUp(self):
        self.registry = _registry()

    def _current(self, stage):
        return self.registry.get(stage, "current").capabilities

    def test_script_goes_through_vertex(self):
        self.assertEqual(self._current(stages.SCRIPT).authentication, VERTEX)

    def test_image_goes_through_vertex(self):
        self.assertEqual(self._current(stages.IMAGE).authentication, VERTEX)

    def test_voice_uses_the_cloud_client(self):
        """genai가 아니라 texttospeech.TextToSpeechClient()다."""

        self.assertEqual(
            self._current(stages.VOICE).authentication, GOOGLE_CLOUD)

    def test_metadata_calls_nothing(self):
        """규칙 기반이다. 부르는 API가 없다."""

        self.assertEqual(self._current(stages.METADATA).authentication, "")
        self.assertEqual(self._current(stages.METADATA).required_settings, ())

    def test_no_current_provider_pretends_to_need_an_env_name(self):
        for stage in (stages.SCRIPT, stages.IMAGE, stages.VOICE,
                      stages.METADATA):
            with self.subTest(stage=stage):
                self.assertEqual(self._current(stage).required_settings, ())

    def test_what_it_says_matches_what_the_engine_imports(self):
        """적어 둔 말이 실제 코드와 맞는지 본다."""

        from app.services import image_service, script_service

        for module in (script_service, image_service):
            with open(module.__file__, encoding="utf-8") as f:
                source = f.read()
            with self.subTest(module=module.__name__):
                self.assertIn("vertexai=True", source)

        from app.providers import google_tts_provider

        with open(google_tts_provider.__file__, encoding="utf-8") as f:
            voice = f.read()

        self.assertIn("texttospeech", voice)
        self.assertNotIn("vertexai", voice)


class TestTheOthersAreUnchanged(unittest.TestCase):

    def setUp(self):
        self.registry = _registry()

    def test_direct_providers_still_name_their_env_variable(self):
        expected = {
            (stages.SCRIPT, "gemini"): "GOOGLE_API_KEY",
            (stages.SCRIPT, "claude"): "ANTHROPIC_API_KEY",
            (stages.SCRIPT, "openai"): "OPENAI_API_KEY",
            (stages.IMAGE, "flux"): "FLUX_API_KEY",
            (stages.IMAGE, "gpt_image"): "OPENAI_API_KEY",
            (stages.VOICE, "elevenlabs"): "ELEVENLABS_API_KEY",
        }

        for (stage, name), setting in expected.items():
            with self.subTest(name=name):
                caps = self.registry.get(stage, name).capabilities

                self.assertIn(setting, caps.required_settings)
                # 환경변수로 다 말할 수 있으므로 따로 적을 것이 없다.
                self.assertEqual(caps.authentication, "")

    def test_import_providers_need_nothing(self):
        for stage, name in ((stages.SCRIPT, "chat_import"),
                            (stages.IMAGE, "image_import"),
                            (stages.VOICE, "voice_import")):
            with self.subTest(name=name):
                caps = self.registry.get(stage, name).capabilities

                self.assertEqual(caps.required_settings, ())
                self.assertEqual(caps.authentication, "")


class TestTheRouterCarriesIt(unittest.TestCase):

    def _row(self, stage="script"):
        from fastapi.testclient import TestClient

        from app.main import app

        payload = TestClient(app).get(
            "/studio/api/production/stages").json()

        return next(s for s in payload["stages"] if s["stage"] == stage)

    def test_every_provider_row_has_the_field(self):
        for stage in ("script", "image", "voice"):
            for provider in self._row(stage)["provider_list"]:
                with self.subTest(stage=stage, provider=provider["name"]):
                    self.assertIn("authentication", provider)

    def test_the_current_row_says_vertex(self):
        current = [p for p in self._row()["provider_list"]
                   if p["name"] == "current"][0]

        self.assertEqual(current["authentication"], VERTEX)

    def test_the_voice_current_row_says_the_cloud_client(self):
        current = [p for p in self._row("voice")["provider_list"]
                   if p["name"] == "current"][0]

        self.assertEqual(current["authentication"], GOOGLE_CLOUD)


class TestTheScreenSaysTheSameThing(unittest.TestCase):

    def test_there_is_one_function_that_words_it(self):
        """세 곳이 각자 문장을 만들면 조금씩 갈라진다."""

        self.assertIn("function providerAuth(", _script())

    def test_the_rule_is_the_three_cases(self):
        block = _function("providerAuth")

        self.assertIn("authentication", block)
        self.assertIn("required_settings", block)
        self.assertIn("NO_AUTH", block)

    def test_the_no_auth_word_is_declared_once(self):
        script = _without_comments(_script())

        self.assertIn('const NO_AUTH = "인증 없음"', _script())
        self.assertEqual(script.count('"인증 없음"'), 1)

    def test_the_old_wording_is_gone(self):
        """
        그 말은 인증이 없다는 뜻이 아니라 키가 없다는 뜻이다. current는
        키를 쓰지 않지만 자격이 필요하므로 둘을 섞으면 틀린 말이 된다.

        왜 그 말을 쓰지 않는지 적어 두려면 그 말을 적어야 한다 -
        설명이 아니라 화면에 나가는 글만 본다.
        """

        self.assertNotIn("필요 없음", _without_comments(_page()))

    def test_the_compare_table_asks_for_authentication(self):
        block = _function("providerCompare")

        self.assertIn("인증", block)
        self.assertIn("providerAuth", block)
        self.assertNotIn("API Key", block)

    def test_the_card_shows_it(self):
        self.assertIn("providerAuth", _function("providerCard"))

    def test_the_summary_shows_it(self):
        self.assertIn("planAuth", _script())
        self.assertIn("planAuth", _function("summaryCards"))

    def test_nothing_is_guessed(self):
        block = _without_comments(
            _function("providerAuth") + _function("planAuth"))

        for word in BANNED:
            with self.subTest(word=word):
                self.assertNotIn(word, block)


class TestNothingElseMoved(unittest.TestCase):

    def _constants(self, module):
        with open(module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        return {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_no_engine_learned_a_new_word(self):
        import app.pipeline.pipeline as pipeline
        from app.services import (
            image_service, provider_selection, script_service, studio_review,
        )
        from app.steps import step01_script

        for module in (pipeline, provider_selection, studio_review,
                       step01_script, script_service, image_service):
            with self.subTest(module=module.__name__):
                constants = self._constants(module)

                self.assertNotIn(VERTEX, constants)
                self.assertNotIn(NONE, constants)

    def test_the_engine_call_did_not_change(self):
        """적어 둔 말만 늘었다 - 부르는 방식은 그대로다."""

        from app.services import script_service

        with open(script_service.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn('project="wellbeingplant-ai"', source)
        self.assertIn('location="global"', source)


class TestTheHandlersStillLineUp(unittest.TestCase):

    def test_every_handler_the_markup_calls_is_declared(self):
        page = _page()
        script = _script()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
