"""
Sprint141 - DeepSeek를 대본 Provider로 붙인다 (Epic 56, Phase 18).

네 번째이자 마지막 직접 호출 대본 Provider다. 이것이 붙으면 대본
단계에 "자리만 있는" 것이 하나도 남지 않는다.

Sprint134가 공용 자리를 만들어 둔 덕분에 새로 쓰는 것은 "어떻게
부르고 어떻게 읽는가" 하나뿐이다.

    새로 쓴다   deepseek_script_provider.py   주소 · 머리말 · 응답 읽기
    가져다 쓴다 direct_script                 글->대본 · outcome · 예외 뿌리
                generated_script 표           등록소 목록 한 줄
                DIRECT_SCRIPT_PROVIDERS 표    다리 한 줄

Chat Completions를 쓴다
-----------------------
DeepSeek는 OpenAI와 같은 모양의 API를 준다.

    POST {base}/chat/completions
    Authorization: Bearer

답은 choices[0].message.content에 있다. 추론 모델(deepseek-reasoner)을
고르면 reasoning_content가 함께 오는데 그것은 대본이 아니다 - content만
읽는다.

멈춘 이유를 구분한다
--------------------
    content_filter                 안전 기준으로 막혔다
    length                         한도에 걸려 잘렸다
    insufficient_system_resource   서버가 도중에 멈췄다
    stop                           정상

잘린 JSON을 "형식이 아니다"로 말하면 사람이 프롬프트를 고치려 든다.
고칠 곳이 다르므로 글보다 먼저 본다.

검증하지 못한 것 - 정직하게 적어 둔다
-------------------------------------
DEEPSEEK_API_KEY가 없어 실제 왕복을 확인하지 못했다. 아래 시험은 HTTP
계층만 세우고 그 위를 전부 진짜로 돌린다.
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
from app.production.providers import bootstrap, generated_script
from app.production.providers.coming_soon import COMING_SOON
from app.production.registry import StageProviderRegistry
from app.production.stage_provider import ProviderUnavailable, StageProviderError
from app.production.stage_request import StageRequest
from app.providers import deepseek_script_provider as deepseek
from app.providers import direct_script
from app.services import provider_selection
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

CONFIGURED = {"DEEPSEEK_API_KEY": "sk-deepseek-141",
              "PATH": os.environ.get("PATH", "")}

ALL_SCRIPT_PROVIDERS = ("gemini", "claude", "openai", "deepseek")


def _answer(content=None, finish_reason="stop", reasoning=None):
    message = {"role": "assistant"}

    if content is not None:
        message["content"] = content

    if reasoning is not None:
        message["reasoning_content"] = reasoning

    return {
        "id": "chat-1",
        "object": "chat.completion",
        "model": "deepseek-chat",
        "choices": [{"index": 0, "message": message,
                     "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 700},
    }


class _Response:

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        return self._payload


class _Transport:

    def __init__(self, payload=None, status_code=200, raises=None):
        self.status_code = status_code
        self._raises = raises
        self._payload = (
            payload if payload is not None
            else _answer(json.dumps(SCRIPT, ensure_ascii=False)))
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
        with patch.object(deepseek, "requests", transport):
            return deepseek.generate_script(topic), transport


class TestNothingIsLeftAsAStub(unittest.TestCase):
    """대본 단계에 "자리만 있는" 것이 하나도 남지 않는다."""

    def test_all_four_are_wired(self):
        self.assertEqual(set(provider_selection.WIRED["script"]),
                         set(ALL_SCRIPT_PROVIDERS))

    def test_the_coming_soon_table_has_no_script_left(self):
        script_entries = [e[0] for e in COMING_SOON if e[1] == stages.SCRIPT]

        self.assertEqual(script_entries, [])

    def test_the_registry_offers_five_ways_to_make_a_script(self):
        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        usable = sorted(
            p.name for p in registry.for_stage(stages.SCRIPT)
            if not getattr(p, "coming_soon", False)
            and p.capabilities.supports_generate
        )

        self.assertEqual(usable, ["claude", "current", "deepseek",
                                  "gemini", "openai"])

    def test_the_three_tables_agree(self):
        catalog = {e[0] for e in generated_script.GENERATED_SCRIPT_PROVIDERS}

        self.assertEqual(catalog, set(ALL_SCRIPT_PROVIDERS))
        self.assertEqual(set(step01_script.DIRECT_SCRIPT_PROVIDERS),
                         set(ALL_SCRIPT_PROVIDERS))

    def test_a_name_nobody_added_is_still_refused(self):
        from app.services.provider_selection import ProviderNotWired

        with self.assertRaises(ProviderNotWired):
            provider_selection.require_wired("script", "그런거없음")

    def test_current_still_passes(self):
        self.assertIsNone(provider_selection.require_wired("script", None))
        self.assertIsNone(
            provider_selection.require_wired("script", "current"))


class TestItCallsChatCompletions(unittest.TestCase):

    def test_it_posts_to_the_chat_endpoint(self):
        _, transport = _run()

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["url"],
                         "https://api.deepseek.com/chat/completions")

    def test_the_key_travels_as_a_bearer_token(self):
        _, transport = _run()

        self.assertEqual(transport.calls[0]["headers"]["Authorization"],
                         "Bearer sk-deepseek-141")

    def test_it_asks_one_user_turn_with_the_topic(self):
        body = _run()[1].calls[0]["body"]

        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(body["messages"][0]["role"], "user")
        self.assertIn(TOPIC, body["messages"][0]["content"])

    def test_it_does_not_ask_for_a_stream(self):
        """조각으로 오면 대본을 이어 붙이는 일이 새로 생긴다."""

        body = _run()[1].calls[0]["body"]

        self.assertFalse(body.get("stream", False))

    def test_the_default_model_is_the_chat_one(self):
        body = _run()[1].calls[0]["body"]

        self.assertEqual(body["model"], "deepseek-chat")

    def test_the_model_can_be_changed_without_touching_code(self):
        env = dict(CONFIGURED, DEEPSEEK_SCRIPT_MODEL="deepseek-reasoner")

        body = _run(env=env)[1].calls[0]["body"]

        self.assertEqual(body["model"], "deepseek-reasoner")

    def test_the_address_can_be_changed_without_touching_code(self):
        env = dict(CONFIGURED, DEEPSEEK_API_URL="https://proxy.test")

        transport = _run(env=env)[1]

        self.assertTrue(
            transport.calls[0]["url"].startswith("https://proxy.test/"))

    def test_it_waits_the_same_as_the_others(self):
        self.assertEqual(deepseek.REQUEST_TIMEOUT_SECONDS, 180)
        self.assertEqual(_run()[1].calls[0]["timeout"], 180)

    def test_it_does_not_change_the_environment(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            before = dict(os.environ)

            with patch.object(deepseek, "requests", _Transport()):
                deepseek.generate_script(TOPIC)

            self.assertEqual(dict(os.environ), before)


class TestItReadsTheAnswer(unittest.TestCase):

    def test_it_returns_what_the_writer_returns(self):
        result, _ = _run()

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_a_json_fence_is_stripped(self):
        fenced = "```json\n" + json.dumps(SCRIPT, ensure_ascii=False) + "\n```"

        result, _ = _run(_Transport(_answer(fenced)))

        self.assertEqual(len(result["data"]["scenes"]), 6)

    def test_the_thinking_is_not_mistaken_for_the_script(self):
        """deepseek-reasoner는 reasoning_content를 함께 보낸다."""

        payload = _answer(json.dumps(SCRIPT, ensure_ascii=False),
                          reasoning="사용자가 무릎 스트레칭을 원한다…")

        result, _ = _run(_Transport(payload))

        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_the_scene_fields_step02_reads_are_filled(self):
        result, _ = _run()

        for scene in result["data"]["scenes"]:
            with self.subTest(scene=scene["scene"]):
                self.assertTrue(scene.get("image_prompt"))


class TestItFailsHonestly(unittest.TestCase):

    def _fails_with(self, transport, expected=None):
        expected = expected or deepseek.DeepSeekScriptError

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(deepseek, "requests", transport):
                with self.assertRaises(expected) as caught:
                    deepseek.generate_script(TOPIC)

        return str(caught.exception)

    def test_no_key_is_refused_by_name(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(
                    deepseek.DeepSeekScriptUnavailable) as caught:
                deepseek.generate_script(TOPIC)

        self.assertIn("DEEPSEEK_API_KEY", str(caught.exception))

    def test_it_refuses_before_calling_anything(self):
        transport = _Transport()

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(deepseek, "requests", transport):
                with self.assertRaises(deepseek.DeepSeekScriptUnavailable):
                    deepseek.generate_script(TOPIC)

        self.assertEqual(transport.calls, [])

    def test_an_empty_topic_never_reaches_the_model(self):
        transport = _Transport()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(deepseek, "requests", transport):
                with self.assertRaises(Exception):
                    deepseek.generate_script("   ")

        self.assertEqual(transport.calls, [])

    def test_a_bad_key_says_the_status(self):
        message = self._fails_with(_Transport(
            {"error": {"message": "Authentication Fails",
                       "type": "authentication_error"}}, status_code=401))

        self.assertIn("401", message)

    def test_a_rate_limit_says_the_status(self):
        message = self._fails_with(_Transport(
            {"error": {"message": "Rate limit reached"}}, status_code=429))

        self.assertIn("429", message)

    def test_a_network_failure_is_an_error(self):
        message = self._fails_with(
            _Transport(raises=OSError("connection reset")))

        self.assertIn("connection reset", message)

    def test_a_safety_stop_says_what_to_do(self):
        message = self._fails_with(
            _Transport(_answer("", finish_reason="content_filter")))

        self.assertIn("content_filter", message)

    def test_a_truncated_answer_points_at_the_ceiling(self):
        message = self._fails_with(_Transport(
            _answer('{"title": "잘린', finish_reason="length")))

        self.assertIn("length", message)

    def test_a_server_that_gave_up_is_told_apart(self):
        message = self._fails_with(_Transport(_answer(
            "", finish_reason="insufficient_system_resource")))

        self.assertIn("insufficient_system_resource", message)

    def test_an_answer_without_choices_is_an_error(self):
        self._fails_with(_Transport({"id": "x", "choices": []}))

    def test_an_empty_answer_is_an_error(self):
        self._fails_with(_Transport(_answer("")))

    def test_thinking_without_a_script_is_an_error(self):
        """추론만 오고 대본이 없으면 대본이 없는 것이다."""

        self._fails_with(_Transport(_answer("", reasoning="생각만 했다")))

    def test_an_answer_that_is_not_json_is_an_error(self):
        self._fails_with(_Transport(_answer("대본을 써 드릴까요?")))

    def test_a_script_without_scenes_is_an_error(self):
        self._fails_with(_Transport(_answer('{"title": "x"}')))


class TestTheOutcomeLooksLikeTheGates(unittest.TestCase):

    def _make(self, transport=None):
        transport = transport or _Transport()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(deepseek, "requests", transport):
                return deepseek.script_outcome(TOPIC), transport

    def test_the_keys_are_the_ones_the_gate_returns(self):
        outcome, _ = self._make()

        for key in ("result", "estimated_seconds", "attempts",
                    "duration_passed", "topic_fidelity", "passed"):
            with self.subTest(key=key):
                self.assertIn(key, outcome)

    def test_it_says_it_tried_once(self):
        self.assertEqual(self._make()[0]["attempts"], 1)

    def test_the_log_does_not_claim_the_gate_ran(self):
        outcome, _ = self._make()

        self.assertIn("게이트 없음", outcome["gate"])
        self.assertIn("DeepSeek", outcome["gate"])

    def test_it_does_not_retry_when_the_script_is_off_target(self):
        short = {"title": "짧게", "scenes": [
            {"scene": 1, "narration": "짧다.", "image_prompt": "x"}]}

        outcome, transport = self._make(_Transport(
            _answer(json.dumps(short, ensure_ascii=False))))

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(outcome["attempts"], 1)
        self.assertFalse(outcome["passed"])

    def test_the_bounds_come_from_the_gate_itself(self):
        with open(deepseek.__file__, encoding="utf-8") as f:
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

    def test_current_runs_the_existing_engine_and_never_deepseek(self):
        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            gate.return_value = {
                "result": {"data": SCRIPT}, "estimated_seconds": 45.0,
                "attempts": 1, "duration_passed": True,
                "topic_fidelity": {"passed": True}, "passed": True,
            }
            with patch.object(deepseek, "script_outcome") as direct:
                step01_script.run(TOPIC, self.project)

        gate.assert_called_once()
        direct.assert_not_called()

    def test_choosing_deepseek_skips_the_existing_engine(self):
        provider_selection.save(self.project, {"script": "deepseek"})

        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            with patch.dict(os.environ, CONFIGURED, clear=True):
                with patch.object(deepseek, "requests", _Transport()):
                    data = step01_script.run(TOPIC, self.project)

        gate.assert_not_called()
        self.assertEqual(data["title"], SCRIPT["title"])

    def test_choosing_deepseek_never_calls_the_other_three(self):
        from app.providers import (
            claude_script_provider, gemini_script_provider,
            openai_script_provider,
        )

        provider_selection.save(self.project, {"script": "deepseek"})

        others = (gemini_script_provider, claude_script_provider,
                  openai_script_provider)

        with patch.object(others[0], "script_outcome") as a:
            with patch.object(others[1], "script_outcome") as b:
                with patch.object(others[2], "script_outcome") as c:
                    with patch.dict(os.environ, CONFIGURED, clear=True):
                        with patch.object(deepseek, "requests", _Transport()):
                            step01_script.run(TOPIC, self.project)

        for mock in (a, b, c):
            mock.assert_not_called()

    def test_it_writes_the_same_file_the_engine_writes(self):
        provider_selection.save(self.project, {"script": "deepseek"})

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(deepseek, "requests", _Transport()):
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

    def test_step01_did_not_grow_a_branch(self):
        """표에 한 줄을 더한 것뿐이다."""

        with open(step01_script.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        branches = [n for n in ast.walk(tree) if isinstance(n, ast.If)]

        self.assertLessEqual(len(branches), 2)

    def test_review_regeneration_uses_the_same_provider(self):
        from app.services import studio_review

        provider_selection.save(self.project, {"script": "deepseek"})

        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            with patch.dict(os.environ, CONFIGURED, clear=True):
                with patch.object(deepseek, "requests",
                                  _Transport()) as transport:
                    studio_review.generate_script(TOPIC, self.project)

        gate.assert_not_called()
        self.assertEqual(len(transport.calls), 1)


class TestFiveProjectsDoNotMix(unittest.TestCase):

    def test_every_choice_stays_with_its_project(self):
        chosen = ("deepseek", "openai", "claude", "gemini", "current")
        tmps = [tempfile.TemporaryDirectory() for _ in chosen]
        for tmp in tmps:
            self.addCleanup(tmp.cleanup)

        for tmp, name in zip(tmps, chosen):
            provider_selection.save(tmp.name, {"script": name})

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
                for name, tmp in zip("ABCDE", tmps)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(seen.get("A"), "deepseek")
        self.assertEqual(seen.get("B"), "openai")
        self.assertEqual(seen.get("C"), "claude")
        self.assertEqual(seen.get("D"), "gemini")
        self.assertIsNone(seen.get("E"))


class TestTheCatalogOffersIt(unittest.TestCase):

    def setUp(self):
        self.registry = StageProviderRegistry()
        bootstrap.register_current_providers(self.registry)

    def _provider(self, name="deepseek"):
        return self.registry.get(stages.SCRIPT, name)

    def test_it_is_no_longer_coming_soon(self):
        self.assertFalse(getattr(self._provider(), "coming_soon", False))

    def test_without_a_key_it_says_which(self):
        with patch.dict(os.environ, {}, clear=True):
            available, reason = self._provider().availability()

        self.assertFalse(available)
        self.assertIn("DEEPSEEK_API_KEY", reason)

    def test_with_a_key_it_is_available(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "k"}, clear=True):
            self.assertTrue(self._provider().availability()[0])

    def test_no_key_becomes_provider_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderUnavailable):
                self._provider().generate(StageRequest(topic=TOPIC))

    def test_an_api_error_becomes_a_stage_provider_error(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(deepseek, "requests",
                              _Transport(raises=OSError("boom"))):
                with self.assertRaises(StageProviderError):
                    self._provider().generate(StageRequest(topic=TOPIC))

    def test_it_reaches_the_same_module_the_bridge_uses(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(deepseek, "requests",
                              _Transport()) as transport:
                result = self._provider().generate(StageRequest(topic=TOPIC))

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_the_setting_name_matches_the_engine(self):
        names = {
            entry[0]: entry[3]
            for entry in generated_script.GENERATED_SCRIPT_PROVIDERS
        }

        self.assertEqual(names["deepseek"], deepseek.API_KEY_SETTING)


class TestTheSharedPlaceIsStillShared(unittest.TestCase):

    def test_it_uses_the_common_reader(self):
        with open(deepseek.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        imported = {
            node.module or "" for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }

        self.assertIn("app.providers.direct_script", imported)

    def test_its_exceptions_share_the_base(self):
        self.assertTrue(issubclass(deepseek.DeepSeekScriptUnavailable,
                                   direct_script.ScriptProviderUnavailable))
        self.assertTrue(issubclass(deepseek.DeepSeekScriptError,
                                   direct_script.ScriptProviderError))

    def test_the_engine_layer_does_not_import_the_production_package(self):
        with open(deepseek.__file__, encoding="utf-8") as f:
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
                self.assertNotIn("deepseek", self._constants(module))

    def test_the_gate_still_retries_three_times(self):
        from app.services import duration_gate

        self.assertEqual(duration_gate.MAX_ATTEMPTS, 3)

    def test_the_pipeline_and_resolver_do_not_know_it(self):
        import app.pipeline.pipeline as pipeline
        from app.steps import step01_script_resolve

        for module in (pipeline, step01_script_resolve):
            with self.subTest(module=module.__name__):
                self.assertNotIn("deepseek", self._constants(module))


if __name__ == "__main__":
    unittest.main()
