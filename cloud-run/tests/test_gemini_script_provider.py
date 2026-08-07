"""
Sprint133 - Gemini를 대본 Provider로 붙인다 (Epic 56, Phase 10).

Sprint128이 놓은 다리에 처음으로 실제 Script Provider가 도착한다.
그전까지 script_provider는 이름만 날랐고 도착지에서 전부 거절했다.

current를 대체하지 않는다 - 대신 우회한다
-----------------------------------------
current는 Writer(바이럴 템플릿·인물 일관성 규칙) · Duration Gate의
재생성 루프 · Topic Fidelity 판정 · 최대 3회 재시도가 붙은 엔진
전체다. 이쪽은 모델을 한 번 부르는 것뿐이다.

같은 gemini-2.5-pro를 부르더라도 거치는 것이 다르므로 결과가 같지
않다. 그 사실을 감추지 않는다.

인증부터 다르다
---------------
current는 Vertex AI로 간다(genai.Client(vertexai=True, project=...)).
이쪽은 API 키로 모델을 직접 부른다 - "파이프라인을 거치지 않고 모델을
직접 부르는 쪽"이라는 말이 인증 경로에서부터 사실이다.

무엇을 가져다 쓰고 무엇을 안 쓰는가
-----------------------------------
    쓴다     SCRIPT_PROMPT       대본의 모양을 정하는 계약이다
             apply_prompt_elements  step02가 읽는 필드를 채운다
             validate_topic      빈 주제를 모델에 보내지 않는다
             estimate/check      만든 것을 재서 정직하게 보고한다
    안 쓴다  재생성 루프         한 번만 부른다
             바이럴 템플릿·인물 규칙  current의 품질 층이다

지어내지 않기 위해서다. 결과를 재는 것과 결과를 고쳐 만드는 것은
다른 일이고, 이 Provider는 앞엣것만 한다.

두 층으로 나눈다
----------------
app/providers는 엔진 층이고 app.production을 import하면 안 된다
(test_production_architecture가 강제한다). 그래서 실제 호출은 엔진
층에 두고, 등록소용 StageProvider가 그것을 감싼다 - Sprint132에서
이미지에 한 것과 같다.
"""

import ast
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import stages
from app.production.providers import bootstrap
from app.production.registry import StageProviderRegistry
from app.production.stage_provider import ProviderUnavailable, StageProviderError
from app.production.stage_request import StageRequest
from app.providers import gemini_script_provider
from app.services import provider_selection
from app.services.provider_selection import ProviderNotWired
from app.steps import step01_script

TOPIC = "무릎 통증에 좋은 스트레칭"

SCRIPT = {
    "title": "무릎 통증 스트레칭 3가지",
    "scenes": [
        {"scene": n,
         "narration": "무릎이 아플 때 이 동작을 천천히 따라 해 보십시오. "
                      "숨을 고르게 쉬면서 열 번씩 반복합니다.",
         "image_prompt": "a person stretching a knee"}
        for n in range(1, 7)
    ],
}

CONFIGURED = {"GOOGLE_API_KEY": "key-133",
              "PATH": os.environ.get("PATH", "")}


class _Response:

    def __init__(self, text=None, block_reason=None, finish_reason=None):
        self.text = text
        self.prompt_feedback = (
            _Feedback(block_reason) if block_reason else None)
        self.candidates = (
            [_Candidate(finish_reason)] if finish_reason else [])


class _Feedback:

    def __init__(self, block_reason):
        self.block_reason = block_reason
        self.block_reason_message = "요청이 안전 기준에 걸렸습니다."


class _Candidate:

    def __init__(self, finish_reason):
        self.finish_reason = finish_reason
        self.content = None


class _Models:

    def __init__(self, response, raises=None):
        self._response = response
        self._raises = raises
        self.calls = []

    def generate_content(self, model=None, contents=None):
        self.calls.append({"model": model, "prompt": contents})

        if self._raises is not None:
            raise self._raises

        return self._response


class _Client:

    def __init__(self, models):
        self.models = models


class _Genai:
    """genai를 세운다. 실제 API로는 한 발짝도 나가지 않는다."""

    def __init__(self, response=None, raises=None):
        if response is None:
            response = _Response(text=json.dumps(SCRIPT, ensure_ascii=False))

        self.models = _Models(response, raises)
        self.client_kwargs = []

    def Client(self, **kwargs):
        self.client_kwargs.append(kwargs)
        return _Client(self.models)


def _run(genai=None, env=None, topic=TOPIC):
    genai = genai or _Genai()

    with patch.dict(os.environ, env or CONFIGURED, clear=True):
        with patch.object(gemini_script_provider, "genai", genai):
            return gemini_script_provider.generate_script(topic), genai


class TestItIsWiredNow(unittest.TestCase):

    def test_gemini_is_wired(self):
        provider_selection.require_wired("script", "gemini")

    def test_it_is_wired(self):
        """Sprint134에서 Claude가 옆에 붙었다. Gemini는 그대로다."""

        self.assertIn("gemini", provider_selection.WIRED["script"])

    def test_the_others_are_still_refused(self):
        for name in ("openai", "deepseek"):
            with self.subTest(name=name):
                with self.assertRaises(ProviderNotWired):
                    provider_selection.require_wired("script", name)

    def test_current_still_passes(self):
        self.assertIsNone(provider_selection.require_wired("script", None))
        self.assertIsNone(
            provider_selection.require_wired("script", "current"))


class TestItCallsTheModelDirectly(unittest.TestCase):

    def test_it_authenticates_with_an_api_key_not_vertex(self):
        """current는 Vertex로 간다. 이쪽이 다른 길이라는 것이 요점이다."""

        _, genai = _run()

        self.assertEqual(genai.client_kwargs, [{"api_key": "key-133"}])

    def test_it_asks_the_model_once(self):
        _, genai = _run()

        self.assertEqual(len(genai.models.calls), 1)

    def test_the_default_model_is_the_one_the_repo_uses(self):
        _, genai = _run()

        self.assertEqual(genai.models.calls[0]["model"], "gemini-2.5-pro")

    def test_the_model_can_be_changed_without_touching_code(self):
        env = dict(CONFIGURED, GEMINI_SCRIPT_MODEL="gemini-3.0-pro")

        _, genai = _run(env=env)

        self.assertEqual(genai.models.calls[0]["model"], "gemini-3.0-pro")

    def test_the_prompt_carries_the_topic(self):
        _, genai = _run()

        self.assertIn(TOPIC, genai.models.calls[0]["prompt"])

    def test_it_does_not_change_the_environment(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            before = dict(os.environ)

            with patch.object(gemini_script_provider, "genai", _Genai()):
                gemini_script_provider.generate_script(TOPIC)

            self.assertEqual(dict(os.environ), before)


class TestTheOutputMatchesTheEngineContract(unittest.TestCase):

    def test_it_returns_what_the_writer_returns(self):
        result, _ = _run()

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_a_json_fence_is_stripped(self):
        fenced = "```json\n" + json.dumps(SCRIPT, ensure_ascii=False) + "\n```"

        result, _ = _run(_Genai(_Response(text=fenced)))

        self.assertEqual(len(result["data"]["scenes"]), 6)

    def test_the_scene_fields_step02_reads_are_filled(self):
        """apply_prompt_elements를 거치지 않으면 뒤 단계가 빈 칸을 읽는다."""

        result, _ = _run()

        for scene in result["data"]["scenes"]:
            with self.subTest(scene=scene["scene"]):
                self.assertTrue(scene.get("image_prompt"))

    def test_it_uses_the_same_element_service_the_engine_uses(self):
        from app.services import scene_prompt_service

        with patch.object(scene_prompt_service, "apply_prompt_elements",
                          side_effect=lambda s: s) as apply:
            _run()

        apply.assert_called_once()


class TestItFailsHonestly(unittest.TestCase):

    def test_no_key_is_refused_by_name(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(
                    gemini_script_provider.GeminiScriptUnavailable) as caught:
                gemini_script_provider.generate_script(TOPIC)

        self.assertIn("GOOGLE_API_KEY", str(caught.exception))

    def test_it_refuses_before_building_a_client(self):
        genai = _Genai()

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(gemini_script_provider, "genai", genai):
                with self.assertRaises(
                        gemini_script_provider.GeminiScriptUnavailable):
                    gemini_script_provider.generate_script(TOPIC)

        self.assertEqual(genai.client_kwargs, [])

    def test_an_empty_topic_never_reaches_the_model(self):
        """빈 주제를 받은 모델은 반드시 무언가를 지어낸다."""

        genai = _Genai()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gemini_script_provider, "genai", genai):
                with self.assertRaises(Exception):
                    gemini_script_provider.generate_script("   ")

        self.assertEqual(genai.models.calls, [])

    def test_a_blocked_prompt_says_what_to_do(self):
        genai = _Genai(_Response(text=None, block_reason="SAFETY"))

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gemini_script_provider, "genai", genai):
                with self.assertRaises(
                        gemini_script_provider.GeminiScriptError) as caught:
                    gemini_script_provider.generate_script(TOPIC)

        self.assertIn("주제", str(caught.exception))

    def test_a_safety_stop_is_told_apart_from_a_broken_call(self):
        genai = _Genai(_Response(text=None, finish_reason="SAFETY"))

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gemini_script_provider, "genai", genai):
                with self.assertRaises(
                        gemini_script_provider.GeminiScriptError) as caught:
                    gemini_script_provider.generate_script(TOPIC)

        self.assertIn("SAFETY", str(caught.exception))

    def test_an_api_error_is_an_error(self):
        genai = _Genai(raises=RuntimeError("503 backend unavailable"))

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gemini_script_provider, "genai", genai):
                with self.assertRaises(
                        gemini_script_provider.GeminiScriptError) as caught:
                    gemini_script_provider.generate_script(TOPIC)

        self.assertIn("503", str(caught.exception))

    def test_an_answer_that_is_not_json_is_an_error(self):
        genai = _Genai(_Response(text="대본을 써 드릴까요?"))

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gemini_script_provider, "genai", genai):
                with self.assertRaises(
                        gemini_script_provider.GeminiScriptError):
                    gemini_script_provider.generate_script(TOPIC)

    def test_an_empty_answer_is_an_error(self):
        genai = _Genai(_Response(text=""))

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gemini_script_provider, "genai", genai):
                with self.assertRaises(
                        gemini_script_provider.GeminiScriptError):
                    gemini_script_provider.generate_script(TOPIC)


class TestTheOutcomeLooksLikeTheGates(unittest.TestCase):
    """step01이 읽는 모양이다. 다르면 화면과 로그가 깨진다."""

    def _make(self, genai=None):
        genai = genai or _Genai()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gemini_script_provider, "genai", genai):
                return gemini_script_provider.script_outcome(TOPIC), genai

    def test_the_keys_are_the_ones_the_gate_returns(self):
        outcome, _ = self._make()

        for key in ("result", "estimated_seconds", "attempts",
                    "duration_passed", "topic_fidelity", "passed"):
            with self.subTest(key=key):
                self.assertIn(key, outcome)

    def test_the_log_does_not_claim_the_gate_ran(self):
        """숫자는 참이어도 머리말이 거짓이면 로그가 거짓말을 한다."""

        outcome, _ = self._make()

        self.assertIn("게이트 없음", outcome["gate"])

    def test_current_keeps_the_old_heading(self):
        """기본값은 예전 그대로다 - 게이트가 돌면 게이트라고 적는다."""

        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as project:
            with patch.object(step01_script,
                              "generate_script_within_duration") as gate:
                gate.return_value = {
                    "result": {"data": SCRIPT}, "estimated_seconds": 45.0,
                    "attempts": 2, "duration_passed": True,
                    "topic_fidelity": {"passed": True}, "passed": True,
                }
                out = io.StringIO()
                with redirect_stdout(out):
                    step01_script.run(TOPIC, project)

        self.assertIn("Duration Gate: passed=True", out.getvalue())

    def test_it_says_it_tried_once(self):
        """세 번 시도한 척하지 않는다."""

        outcome, _ = self._make()

        self.assertEqual(outcome["attempts"], 1)

    def test_the_seconds_are_measured_by_the_same_estimator(self):
        from app.services.duration_estimator import estimate_script_duration

        outcome, _ = self._make()

        self.assertAlmostEqual(
            outcome["estimated_seconds"],
            estimate_script_duration(outcome["result"]["data"]["scenes"]),
            places=4)

    def test_it_does_not_retry_when_the_script_is_off_target(self):
        """재생성은 current 엔진의 일이다. 여기서 흉내 내지 않는다."""

        short = {"title": "짧게", "scenes": [
            {"scene": 1, "narration": "짧다.", "image_prompt": "x"}]}
        genai = _Genai(_Response(
            text=json.dumps(short, ensure_ascii=False)))

        outcome, genai = self._make(genai)

        self.assertEqual(len(genai.models.calls), 1)
        self.assertFalse(outcome["passed"])
        self.assertEqual(outcome["attempts"], 1)

    def test_the_bounds_come_from_the_gate_itself(self):
        """범위를 여기 다시 적으면 한쪽만 바뀌는 날이 온다."""

        source = open(gemini_script_provider.__file__,
                      encoding="utf-8").read()
        tree = ast.parse(source)

        numbers = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, float)
        }

        self.assertNotIn(43.0, numbers)
        self.assertNotIn(47.0, numbers)


class TestTheBridgeReachesIt(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name

    def test_current_runs_the_existing_engine_and_never_gemini(self):
        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            gate.return_value = {
                "result": {"data": SCRIPT}, "estimated_seconds": 45.0,
                "attempts": 1, "duration_passed": True,
                "topic_fidelity": {"passed": True}, "passed": True,
            }
            with patch.object(gemini_script_provider,
                              "script_outcome") as direct:
                step01_script.run(TOPIC, self.project)

        gate.assert_called_once()
        direct.assert_not_called()

    def test_choosing_gemini_skips_the_existing_engine(self):
        provider_selection.save(self.project, {"script": "gemini"})

        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            with patch.dict(os.environ, CONFIGURED, clear=True):
                with patch.object(gemini_script_provider, "genai", _Genai()):
                    data = step01_script.run(TOPIC, self.project)

        gate.assert_not_called()
        self.assertEqual(data["title"], SCRIPT["title"])

    def test_it_writes_the_same_file_the_engine_writes(self):
        provider_selection.save(self.project, {"script": "gemini"})

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gemini_script_provider, "genai", _Genai()):
                step01_script.run(TOPIC, self.project)

        path = os.path.join(self.project, "script.json")

        self.assertTrue(os.path.exists(path))

        with open(path, encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(len(saved["scenes"]), 6)
        self.assertTrue(saved["scenes"][0]["image_prompt"])

    def test_the_step_contract_did_not_change(self):
        import inspect

        self.assertEqual(
            list(inspect.signature(step01_script.run).parameters),
            ["topic", "project_path"])

    def test_review_regeneration_uses_the_same_provider(self):
        from app.services import studio_review

        provider_selection.save(self.project, {"script": "gemini"})

        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            with patch.dict(os.environ, CONFIGURED, clear=True):
                with patch.object(gemini_script_provider,
                                  "genai", _Genai()) as genai:
                    studio_review.generate_script(TOPIC, self.project)

        gate.assert_not_called()
        self.assertEqual(len(genai.models.calls), 1)


class TestTwoProjectsDoNotMix(unittest.TestCase):

    def test_one_project_choosing_gemini_does_not_move_the_other(self):
        tmps = [tempfile.TemporaryDirectory() for _ in range(2)]
        for tmp in tmps:
            self.addCleanup(tmp.cleanup)

        provider_selection.save(tmps[0].name, {"script": "gemini"})
        provider_selection.save(tmps[1].name, {"script": "current"})

        seen = {}
        lock = threading.Lock()

        def remember(topic, provider=None):
            with lock:
                seen[threading.current_thread().name] = provider
            return {
                "result": {"data": SCRIPT}, "estimated_seconds": 45.0,
                "attempts": 1, "duration_passed": True,
                "topic_fidelity": {"passed": True}, "passed": True,
            }

        def run(path):
            step01_script.run(TOPIC, path)

        with patch.object(step01_script, "_generate_script", remember):
            threads = [
                threading.Thread(target=run, args=(tmps[0].name,), name="A"),
                threading.Thread(target=run, args=(tmps[1].name,), name="B"),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(seen.get("A"), "gemini")
        self.assertIsNone(seen.get("B"))


class TestTheCatalogOffersIt(unittest.TestCase):

    def setUp(self):
        self.registry = StageProviderRegistry()
        bootstrap.register_current_providers(self.registry)

    def _provider(self):
        return self.registry.get(stages.SCRIPT, "gemini")

    def test_it_is_no_longer_coming_soon(self):
        self.assertFalse(getattr(self._provider(), "coming_soon", False))

    def test_the_setting_name_matches_the_engine(self):
        """
        등록소는 엔진 모듈을 import하지 않고 이름을 적어 둔다 -
        import하면 google.genai가 딸려 와 목록을 그리는 것만으로
        무거운 모듈이 켜진다. 그래서 두 값이 어긋나지 않도록 잠근다.
        """

        from app.production.providers import generated_script

        names = {e[0]: e[3] for e in generated_script.GENERATED_SCRIPT_PROVIDERS}

        self.assertEqual(names["gemini"],
                         gemini_script_provider.API_KEY_SETTING)

    def test_registering_does_not_wake_the_model_library(self):
        import subprocess

        code = (
            "import sys\n"
            "from app.production.providers import bootstrap\n"
            "from app.production.registry import StageProviderRegistry\n"
            "bootstrap.register_current_providers(StageProviderRegistry())\n"
            "print(len([m for m in sys.modules "
            "if m.startswith('google.genai')]))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
        )

        self.assertEqual(result.stdout.strip(), "0", result.stderr[-800:])

    def test_the_unwired_ones_are_still_coming_soon(self):
        for name in ("openai", "deepseek"):
            with self.subTest(name=name):
                self.assertTrue(getattr(
                    self.registry.get(stages.SCRIPT, name),
                    "coming_soon", False))

    def test_without_a_key_it_says_which(self):
        with patch.dict(os.environ, {}, clear=True):
            available, reason = self._provider().availability()

        self.assertFalse(available)
        self.assertIn("GOOGLE_API_KEY", reason)

    def test_with_a_key_it_is_available(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "k"}, clear=True):
            available, reason = self._provider().availability()

        self.assertTrue(available)
        self.assertEqual(reason, "")

    def test_no_key_becomes_provider_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderUnavailable):
                self._provider().generate(StageRequest(topic=TOPIC))

    def test_an_api_error_becomes_a_stage_provider_error(self):
        genai = _Genai(raises=RuntimeError("500 internal"))

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gemini_script_provider, "genai", genai):
                with self.assertRaises(StageProviderError):
                    self._provider().generate(StageRequest(topic=TOPIC))

    def test_it_needs_a_topic(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with self.assertRaises(ValueError):
                self._provider().generate(StageRequest())

    def test_it_reaches_the_same_module_the_bridge_uses(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gemini_script_provider, "genai",
                              _Genai()) as genai:
                result = self._provider().generate(StageRequest(topic=TOPIC))

        self.assertEqual(len(genai.models.calls), 1)
        self.assertEqual(result["data"]["title"], SCRIPT["title"])


class TestTheCurrentEngineIsUntouched(unittest.TestCase):

    def _constants(self, module):
        with open(module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        return {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_the_writer_and_the_gate_do_not_know_this_provider(self):
        from app.services import duration_gate, script_service, topic_fidelity

        for module in (script_service, duration_gate, topic_fidelity):
            with self.subTest(module=module.__name__):
                self.assertNotIn("gemini", self._constants(module))

    def test_the_gate_still_retries_three_times(self):
        from app.services import duration_gate

        self.assertEqual(duration_gate.MAX_ATTEMPTS, 3)

    def test_the_pipeline_does_not_know_this_provider(self):
        import app.pipeline.pipeline as pipeline

        self.assertNotIn("gemini", self._constants(pipeline))

    def test_the_engine_layer_does_not_import_the_production_package(self):
        """test_production_architecture가 강제하는 경계다."""

        with open(gemini_script_provider.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")

        for name in names:
            with self.subTest(imported=name):
                self.assertNotIn("app.production", name)


if __name__ == "__main__":
    unittest.main()
