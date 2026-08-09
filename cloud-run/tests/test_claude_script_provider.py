"""
Sprint134 - Claude를 대본 Provider로 붙인다 (Epic 56, Phase 11).

Sprint133의 Gemini에 이어 두 번째 실제 Script Provider다. 다리는
Sprint128에 놓였으므로 이번에 하는 일은 도착지 하나를 더 여는 것이다.

둘이 되면 복제가 시작된다
-------------------------
Sprint133은 Gemini 하나를 if로 받았고, 대본을 글에서 꺼내 검사하고
step01이 읽는 모양으로 싸는 일을 그 파일 안에서 했다. 여기에 하나를
더 얹으면 같은 일이 두 벌이 되고, 세 번째부터 조금씩 갈라진다 -
이 저장소가 반복해서 겪은 결함이다.

그래서 이번에 공용 자리를 만든다.

    app/providers/direct_script.py      글 -> 대본 · outcome 모양 · 예외
    app/production/providers/generated_script.py   등록소 목록(표 하나)

Gemini는 그 공용 자리를 쓰도록 옮겼다. 동작은 그대로다 - Sprint133의
시험이 전부 그대로 통과해야 한다.

current를 대체하지 않는다
-------------------------
current는 Writer(바이럴 템플릿·인물 일관성 규칙) · Duration Gate의
재생성 루프 · Topic Fidelity 판정 · 최대 3회 재시도가 붙은 엔진
전체다. 이쪽은 모델을 한 번 부르는 것뿐이다.

새 의존성을 더하지 않는다
-------------------------
anthropic 패키지는 이 저장소에 없다. FLUX·GPT Image가 그랬듯
requests로 Messages API를 직접 부른다 - 대본 하나를 만들자고
의존성을 늘릴 이유가 없다.

검증하지 못한 것 - 정직하게 적어 둔다
-------------------------------------
ANTHROPIC_API_KEY가 없어 실제 왕복을 확인하지 못했다. 아래 시험은
HTTP 계층만 세우고 그 위를 전부 진짜로 돌린다.
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
from app.providers import claude_script_provider as claude
from app.providers import direct_script
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

CONFIGURED = {"ANTHROPIC_API_KEY": "sk-ant-134",
              "PATH": os.environ.get("PATH", "")}


def _message(text=None, stop_reason="end_turn"):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "content": [] if text is None else [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 10, "output_tokens": 100},
    }


class _Response:

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        return self._payload


class _Transport:
    """Anthropic이 돌려줄 법한 응답. 한 번에 끝난다."""

    def __init__(self, payload=None, status_code=200, raises=None):
        self.status_code = status_code
        self._raises = raises
        self._payload = (
            payload if payload is not None
            else _message(json.dumps(SCRIPT, ensure_ascii=False)))
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "body": json, "headers": headers or {},
                           "timeout": timeout})

        if self._raises is not None:
            raise self._raises

        return _Response(self.status_code, self._payload)


def _run(transport=None, env=None, topic=TOPIC):
    transport = transport or _Transport()

    with patch.dict(os.environ, env or CONFIGURED, clear=True):
        with patch.object(claude, "requests", transport):
            return claude.generate_script(topic), transport


class TestItIsWiredNow(unittest.TestCase):

    def test_claude_is_wired(self):
        provider_selection.require_wired("script", "claude")

    def test_gemini_is_still_wired(self):
        """Sprint133이 붙인 것을 건드리지 않았다."""

        provider_selection.require_wired("script", "gemini")

    def test_both_are_listed(self):
        """Sprint135에서 OpenAI가 옆에 붙었다. 둘은 그대로다."""

        self.assertLessEqual(
            {"gemini", "claude"}, set(provider_selection.WIRED["script"]))

    def test_a_name_nobody_added_is_still_refused(self):
        for name in ("그런거없음",):
            with self.subTest(name=name):
                with self.assertRaises(ProviderNotWired):
                    provider_selection.require_wired("script", name)

    def test_the_bridge_table_matches_what_is_wired(self):
        """
        이름을 아는 자리와 부를 모듈을 아는 자리가 다르다. 어긋나면
        고를 수는 있는데 만들 때 깨진다.
        """

        self.assertEqual(
            set(step01_script.DIRECT_SCRIPT_PROVIDERS),
            set(provider_selection.WIRED["script"]))


class TestItCallsTheMessagesApi(unittest.TestCase):

    def test_it_posts_to_the_messages_endpoint(self):
        _, transport = _run()

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["url"],
                         "https://api.anthropic.com/v1/messages")

    def test_the_key_travels_in_the_x_api_key_header(self):
        _, transport = _run()

        self.assertEqual(transport.calls[0]["headers"]["x-api-key"],
                         "sk-ant-134")

    def test_it_names_the_api_version(self):
        """버전 머리말이 없으면 API가 거절한다."""

        _, transport = _run()

        self.assertTrue(transport.calls[0]["headers"]["anthropic-version"])

    def test_it_asks_one_user_turn_with_the_topic(self):
        _, transport = _run()

        body = transport.calls[0]["body"]
        messages = body["messages"]

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn(TOPIC, messages[0]["content"])

    def test_it_sets_a_token_ceiling(self):
        """max_tokens는 Messages API의 필수값이다."""

        _, transport = _run()

        self.assertGreater(transport.calls[0]["body"]["max_tokens"], 0)

    def test_the_model_is_a_current_generation_one(self):
        _, transport = _run()

        self.assertIn("claude", transport.calls[0]["body"]["model"])

    def test_the_model_can_be_changed_without_touching_code(self):
        env = dict(CONFIGURED, CLAUDE_SCRIPT_MODEL="claude-opus-5")

        _, transport = _run(env=env)

        self.assertEqual(transport.calls[0]["body"]["model"], "claude-opus-5")

    def test_the_address_can_be_changed_without_touching_code(self):
        env = dict(CONFIGURED, ANTHROPIC_API_URL="https://proxy.test")

        _, transport = _run(env=env)

        self.assertTrue(
            transport.calls[0]["url"].startswith("https://proxy.test/"))

    def test_it_does_not_wait_forever(self):
        _, transport = _run()

        self.assertIsNotNone(transport.calls[0]["timeout"])

    def test_it_does_not_change_the_environment(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            before = dict(os.environ)

            with patch.object(claude, "requests", _Transport()):
                claude.generate_script(TOPIC)

            self.assertEqual(dict(os.environ), before)


class TestTheOutputMatchesTheEngineContract(unittest.TestCase):

    def test_it_returns_what_the_writer_returns(self):
        result, _ = _run()

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_a_json_fence_is_stripped(self):
        fenced = "```json\n" + json.dumps(SCRIPT, ensure_ascii=False) + "\n```"

        result, _ = _run(_Transport(_message(fenced)))

        self.assertEqual(len(result["data"]["scenes"]), 6)

    def test_several_text_blocks_are_joined(self):
        payload = _message(json.dumps(SCRIPT, ensure_ascii=False))
        text = payload["content"][0]["text"]
        payload["content"] = [
            {"type": "text", "text": text[:40]},
            {"type": "text", "text": text[40:]},
        ]

        result, _ = _run(_Transport(payload))

        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_the_scene_fields_step02_reads_are_filled(self):
        result, _ = _run()

        for scene in result["data"]["scenes"]:
            with self.subTest(scene=scene["scene"]):
                self.assertTrue(scene.get("image_prompt"))

    def test_it_looks_exactly_like_the_gemini_result(self):
        """두 Provider가 다른 모양을 돌려주면 뒤 단계가 갈린다."""

        from app.providers import gemini_script_provider

        claude_result, _ = _run()

        from app.services import scene_prompt_service

        with patch.object(scene_prompt_service, "apply_prompt_elements",
                          side_effect=lambda s: s):
            gemini_data = direct_script.script_from_text(
                json.dumps(SCRIPT, ensure_ascii=False))

        self.assertEqual(set(claude_result), {"success", "data"})
        self.assertEqual(set(claude_result["data"]), set(gemini_data))
        self.assertTrue(hasattr(gemini_script_provider, "script_outcome"))


class TestItFailsHonestly(unittest.TestCase):

    def _fails_with(self, transport, expected=None):
        expected = expected or claude.ClaudeScriptError

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(claude, "requests", transport):
                with self.assertRaises(expected) as caught:
                    claude.generate_script(TOPIC)

        return str(caught.exception)

    def test_no_key_is_refused_by_name(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(
                    claude.ClaudeScriptUnavailable) as caught:
                claude.generate_script(TOPIC)

        self.assertIn("ANTHROPIC_API_KEY", str(caught.exception))

    def test_it_refuses_before_calling_anything(self):
        transport = _Transport()

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(claude, "requests", transport):
                with self.assertRaises(claude.ClaudeScriptUnavailable):
                    claude.generate_script(TOPIC)

        self.assertEqual(transport.calls, [])

    def test_an_empty_topic_never_reaches_the_model(self):
        transport = _Transport()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(claude, "requests", transport):
                with self.assertRaises(Exception):
                    claude.generate_script("   ")

        self.assertEqual(transport.calls, [])

    def test_a_refusal_is_told_apart_from_a_broken_call(self):
        """안전 거절은 키가 틀린 것과도, 서버가 죽은 것과도 다르다."""

        message = self._fails_with(
            _Transport(_message("", stop_reason="refusal")))

        self.assertIn("거절", message)

    def test_a_truncated_answer_says_so(self):
        """토큰 한도에 걸려 잘린 JSON을 '형식이 아니다'로 말하면
        사람이 프롬프트를 고치려 든다. 고칠 곳은 한도다."""

        message = self._fails_with(
            _Transport(_message('{"title": "잘린', stop_reason="max_tokens")))

        self.assertIn("max_tokens", message)

    def test_a_rejected_key_says_the_status(self):
        message = self._fails_with(_Transport(
            {"type": "error", "error": {"type": "authentication_error",
                                        "message": "invalid x-api-key"}},
            status_code=401))

        self.assertIn("401", message)

    def test_an_overloaded_server_says_the_status(self):
        message = self._fails_with(_Transport(
            {"type": "error", "error": {"type": "overloaded_error",
                                        "message": "Overloaded"}},
            status_code=529))

        self.assertIn("529", message)

    def test_a_network_failure_is_an_error(self):
        message = self._fails_with(
            _Transport(raises=OSError("connection reset")))

        self.assertIn("connection reset", message)

    def test_an_answer_without_text_is_an_error(self):
        self._fails_with(_Transport(_message(None)))

    def test_an_answer_that_is_not_json_is_an_error(self):
        self._fails_with(_Transport(_message("대본을 써 드릴까요?")))

    def test_a_script_without_scenes_is_an_error(self):
        self._fails_with(_Transport(_message('{"title": "x"}')))


class TestTheOutcomeLooksLikeTheGates(unittest.TestCase):

    def _make(self, transport=None):
        transport = transport or _Transport()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(claude, "requests", transport):
                return claude.script_outcome(TOPIC), transport

    def test_the_keys_are_the_ones_the_gate_returns(self):
        outcome, _ = self._make()

        for key in ("result", "estimated_seconds", "attempts",
                    "duration_passed", "topic_fidelity", "passed"):
            with self.subTest(key=key):
                self.assertIn(key, outcome)

    def test_it_says_it_tried_once(self):
        outcome, _ = self._make()

        self.assertEqual(outcome["attempts"], 1)

    def test_the_log_does_not_claim_the_gate_ran(self):
        outcome, _ = self._make()

        self.assertIn("게이트 없음", outcome["gate"])
        self.assertIn("Claude", outcome["gate"])

    def test_it_does_not_retry_when_the_script_is_off_target(self):
        short = {"title": "짧게", "scenes": [
            {"scene": 1, "narration": "짧다.", "image_prompt": "x"}]}

        outcome, transport = self._make(_Transport(
            _message(json.dumps(short, ensure_ascii=False))))

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(outcome["attempts"], 1)
        self.assertFalse(outcome["passed"])

    def test_the_bounds_come_from_the_gate_itself(self):
        with open(claude.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

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

    def test_current_runs_the_existing_engine_and_never_claude(self):
        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            gate.return_value = {
                "result": {"data": SCRIPT}, "estimated_seconds": 45.0,
                "attempts": 1, "duration_passed": True,
                "topic_fidelity": {"passed": True}, "passed": True,
            }
            with patch.object(claude, "script_outcome") as direct:
                step01_script.run(TOPIC, self.project)

        gate.assert_called_once()
        direct.assert_not_called()

    def test_choosing_claude_skips_the_existing_engine(self):
        provider_selection.save(self.project, {"script": "claude"})

        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            with patch.dict(os.environ, CONFIGURED, clear=True):
                with patch.object(claude, "requests", _Transport()):
                    data = step01_script.run(TOPIC, self.project)

        gate.assert_not_called()
        self.assertEqual(data["title"], SCRIPT["title"])

    def test_choosing_claude_never_calls_gemini(self):
        from app.providers import gemini_script_provider

        provider_selection.save(self.project, {"script": "claude"})

        with patch.object(gemini_script_provider,
                          "script_outcome") as gemini:
            with patch.dict(os.environ, CONFIGURED, clear=True):
                with patch.object(claude, "requests", _Transport()):
                    step01_script.run(TOPIC, self.project)

        gemini.assert_not_called()

    def test_it_writes_the_same_file_the_engine_writes(self):
        provider_selection.save(self.project, {"script": "claude"})

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(claude, "requests", _Transport()):
                step01_script.run(TOPIC, self.project)

        with open(os.path.join(self.project, "script.json"),
                  encoding="utf-8") as f:
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

        provider_selection.save(self.project, {"script": "claude"})

        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            with patch.dict(os.environ, CONFIGURED, clear=True):
                with patch.object(claude, "requests",
                                  _Transport()) as transport:
                    studio_review.generate_script(TOPIC, self.project)

        gate.assert_not_called()
        self.assertEqual(len(transport.calls), 1)


class TestTwoProjectsDoNotMix(unittest.TestCase):

    def test_the_choice_does_not_leak_between_threads(self):
        tmps = [tempfile.TemporaryDirectory() for _ in range(3)]
        for tmp in tmps:
            self.addCleanup(tmp.cleanup)

        provider_selection.save(tmps[0].name, {"script": "claude"})
        provider_selection.save(tmps[1].name, {"script": "gemini"})
        provider_selection.save(tmps[2].name, {"script": "current"})

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

        with patch.object(step01_script, "_generate_script", remember):
            threads = [
                threading.Thread(target=step01_script.run,
                                 args=(TOPIC, tmp.name), name=name)
                for name, tmp in zip("ABC", tmps)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(seen.get("A"), "claude")
        self.assertEqual(seen.get("B"), "gemini")
        self.assertIsNone(seen.get("C"))


class TestTheCatalogOffersIt(unittest.TestCase):

    def setUp(self):
        self.registry = StageProviderRegistry()
        bootstrap.register_current_providers(self.registry)

    def _provider(self, name="claude"):
        return self.registry.get(stages.SCRIPT, name)

    def test_it_is_no_longer_coming_soon(self):
        self.assertFalse(getattr(self._provider(), "coming_soon", False))

    def test_gemini_is_still_there(self):
        self.assertFalse(
            getattr(self._provider("gemini"), "coming_soon", False))

    def test_the_unwired_ones_are_still_coming_soon(self):
        # Sprint141 - 대본 자리는 하나도 남지 않았다.
        for provider in self.registry.for_stage(stages.SCRIPT):
            with self.subTest(name=provider.name):
                self.assertFalse(
                    getattr(provider, "coming_soon", False))

    def test_without_a_key_it_says_which(self):
        with patch.dict(os.environ, {}, clear=True):
            available, reason = self._provider().availability()

        self.assertFalse(available)
        self.assertIn("ANTHROPIC_API_KEY", reason)

    def test_with_a_key_it_is_available(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}, clear=True):
            available, reason = self._provider().availability()

        self.assertTrue(available)
        self.assertEqual(reason, "")

    def test_no_key_becomes_provider_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderUnavailable):
                self._provider().generate(StageRequest(topic=TOPIC))

    def test_an_api_error_becomes_a_stage_provider_error(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(claude, "requests",
                              _Transport(raises=OSError("boom"))):
                with self.assertRaises(StageProviderError):
                    self._provider().generate(StageRequest(topic=TOPIC))

    def test_it_needs_a_topic(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with self.assertRaises(ValueError):
                self._provider().generate(StageRequest())

    def test_it_reaches_the_same_module_the_bridge_uses(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(claude, "requests",
                              _Transport()) as transport:
                result = self._provider().generate(StageRequest(topic=TOPIC))

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_the_setting_name_matches_the_engine(self):
        from app.production.providers import generated_script

        names = {
            entry[0]: entry[3]
            for entry in generated_script.GENERATED_SCRIPT_PROVIDERS
        }

        self.assertEqual(names["claude"], claude.API_KEY_SETTING)

    def test_registering_does_not_wake_any_client_library(self):
        import subprocess

        code = (
            "import sys\n"
            "from app.production.providers import bootstrap\n"
            "from app.production.registry import StageProviderRegistry\n"
            "bootstrap.register_current_providers(StageProviderRegistry())\n"
            "print(len([m for m in sys.modules "
            "if m.startswith(('google.genai','anthropic'))]))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

        self.assertEqual(result.stdout.strip(), "0", result.stderr[-800:])


class TestTheSharedPlaceIsActuallyShared(unittest.TestCase):
    """복제하면 두 자리가 조금씩 갈라진다."""

    def test_both_providers_use_the_same_text_reader(self):
        from app.providers import gemini_script_provider

        for module in (claude, gemini_script_provider):
            with self.subTest(module=module.__name__):
                with open(module.__file__, encoding="utf-8") as f:
                    tree = ast.parse(f.read())

                imported = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        imported.add(node.module or "")

                self.assertIn("app.providers.direct_script", imported)

    def test_both_exceptions_share_a_base(self):
        from app.providers import gemini_script_provider

        self.assertTrue(issubclass(claude.ClaudeScriptUnavailable,
                                   direct_script.ScriptProviderUnavailable))
        self.assertTrue(issubclass(claude.ClaudeScriptError,
                                   direct_script.ScriptProviderError))
        self.assertTrue(issubclass(gemini_script_provider.GeminiScriptError,
                                   direct_script.ScriptProviderError))

    def test_the_catalog_holds_one_table_not_two_classes(self):
        from app.production.providers import generated_script

        names = {entry[0]
                 for entry in generated_script.GENERATED_SCRIPT_PROVIDERS}

        self.assertLessEqual({"gemini", "claude"}, names)


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
                self.assertNotIn("claude", self._constants(module))

    def test_the_gate_still_retries_three_times(self):
        from app.services import duration_gate

        self.assertEqual(duration_gate.MAX_ATTEMPTS, 3)

    def test_the_pipeline_does_not_know_this_provider(self):
        import app.pipeline.pipeline as pipeline

        self.assertNotIn("claude", self._constants(pipeline))

    def test_the_engine_layer_does_not_import_the_production_package(self):
        from app.providers import gemini_script_provider

        for module in (claude, direct_script, gemini_script_provider):
            with open(module.__file__, encoding="utf-8") as f:
                tree = ast.parse(f.read())

            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names.add(node.module or "")

            for name in names:
                with self.subTest(module=module.__name__, imported=name):
                    self.assertNotIn("app.production", name)


if __name__ == "__main__":
    unittest.main()
