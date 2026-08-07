"""
Sprint135 - OpenAI를 대본 Provider로 붙인다 (Epic 56, Phase 12).

세 번째 실제 Script Provider다. Sprint134가 공용 자리를 만들어 둔
덕분에 이번에 새로 쓰는 것은 "어떻게 부르는가" 하나뿐이다.

    새로 쓴다   openai_script_provider.py   주소 · 머리말 · 응답 읽기
    가져다 쓴다 direct_script                글->대본 · outcome · 예외 뿌리
                generated_script 표          등록소 목록 한 줄
                DIRECT_SCRIPT_PROVIDERS 표   다리 한 줄

세 번째가 두 줄로 끝나는 것이 Sprint134에서 표로 모아 둔 이유다.

Responses API를 쓴다
--------------------
이 저장소는 이미 OpenAI를 부른다 - Sprint131의 GPT Image가 같은
호스트에 같은 Bearer 인증으로 간다. 그래서 대본도 그 옆으로 붙이는
것이 가장 자연스럽다.

    POST {base}/v1/responses

답의 모양이 Claude와 다르다. 글은 output 배열 안 message 항목의
output_text에 들어 있고, 거절은 별도 content 종류(refusal)로 오며,
잘림은 status="incomplete"와 incomplete_details.reason으로 온다.
추론 모델은 output에 reasoning 항목도 함께 넣는다 - message가 아닌
것을 걸러내지 않으면 대본이 아닌 것을 읽게 된다.

current를 대체하지 않는다
-------------------------
current는 Writer(바이럴 템플릿·인물 일관성 규칙) · Duration Gate의
재생성 루프 · Topic Fidelity 판정 · 최대 3회 재시도가 붙은 엔진
전체다. 이쪽은 모델을 한 번 부르는 것뿐이다.

검증하지 못한 것 - 정직하게 적어 둔다
-------------------------------------
OPENAI_API_KEY가 없어 실제 왕복을 확인하지 못했다. 아래 시험은 HTTP
계층만 세우고 그 위를 전부 진짜로 돌린다. 모델 이름과 주소는
환경변수로 바꿀 수 있게 두었다.
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
from app.production.providers import generated_script
from app.production.registry import StageProviderRegistry
from app.production.stage_provider import ProviderUnavailable, StageProviderError
from app.production.stage_request import StageRequest
from app.providers import direct_script
from app.providers import openai_script_provider as openai
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

CONFIGURED = {"OPENAI_API_KEY": "sk-openai-135",
              "PATH": os.environ.get("PATH", "")}


def _answer(text=None, status="completed", reason=None, refusal=None,
            with_reasoning=False):
    """Responses API가 돌려줄 법한 몸통."""

    content = []

    if text is not None:
        content.append({"type": "output_text", "text": text})

    if refusal is not None:
        content.append({"type": "refusal", "refusal": refusal})

    output = []

    if with_reasoning:
        # 추론 모델이 함께 넣는 항목. 대본이 아니다.
        output.append({"type": "reasoning", "id": "rs_1", "summary": []})

    output.append({"type": "message", "role": "assistant",
                   "content": content})

    payload = {"id": "resp_1", "object": "response", "status": status,
               "model": "gpt-5", "output": output}

    if reason is not None:
        payload["incomplete_details"] = {"reason": reason}

    return payload


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
        with patch.object(openai, "requests", transport):
            return openai.generate_script(topic), transport


class TestItIsWiredNow(unittest.TestCase):

    def test_openai_is_wired(self):
        provider_selection.require_wired("script", "openai")

    def test_the_earlier_ones_are_still_wired(self):
        for name in ("gemini", "claude"):
            with self.subTest(name=name):
                provider_selection.require_wired("script", name)

    def test_all_three_are_listed(self):
        """Sprint141에서 DeepSeek가 넷째로 붙었다. 셋은 그대로다."""

        self.assertLessEqual({"gemini", "claude", "openai"},
                             set(provider_selection.WIRED["script"]))

    def test_a_name_nobody_added_is_still_refused(self):
        with self.assertRaises(ProviderNotWired):
            provider_selection.require_wired("script", "그런거없음")

    def test_current_still_passes(self):
        self.assertIsNone(provider_selection.require_wired("script", None))
        self.assertIsNone(
            provider_selection.require_wired("script", "current"))

    def test_the_bridge_table_matches_what_is_wired(self):
        self.assertEqual(
            set(step01_script.DIRECT_SCRIPT_PROVIDERS),
            set(provider_selection.WIRED["script"]))

    def test_the_catalog_table_matches_too(self):
        names = {entry[0]
                 for entry in generated_script.GENERATED_SCRIPT_PROVIDERS}

        self.assertEqual(names, set(provider_selection.WIRED["script"]))


class TestItCallsTheResponsesApi(unittest.TestCase):

    def test_it_posts_to_the_responses_endpoint(self):
        _, transport = _run()

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["url"],
                         "https://api.openai.com/v1/responses")

    def test_the_key_travels_as_a_bearer_token(self):
        _, transport = _run()

        self.assertEqual(transport.calls[0]["headers"]["Authorization"],
                         "Bearer sk-openai-135")

    def test_the_topic_travels_in_the_input(self):
        _, transport = _run()

        body = transport.calls[0]["body"]

        self.assertIn(TOPIC, json.dumps(body["input"], ensure_ascii=False))

    def test_the_model_can_be_changed_without_touching_code(self):
        env = dict(CONFIGURED, OPENAI_SCRIPT_MODEL="gpt-5-mini")

        _, transport = _run(env=env)

        self.assertEqual(transport.calls[0]["body"]["model"], "gpt-5-mini")

    def test_the_address_can_be_changed_without_touching_code(self):
        env = dict(CONFIGURED, OPENAI_API_URL="https://proxy.test")

        _, transport = _run(env=env)

        self.assertTrue(
            transport.calls[0]["url"].startswith("https://proxy.test/"))

    def test_it_does_not_wait_forever(self):
        _, transport = _run()

        self.assertIsNotNone(transport.calls[0]["timeout"])

    def test_it_shares_the_key_with_the_image_provider(self):
        """
        같은 회사 키다. 두 이름을 쓰면 하나만 넣고 나머지가 왜 안 되는지
        모르게 된다.
        """

        from app.providers import gpt_image_provider

        self.assertEqual(openai.API_KEY_SETTING,
                         gpt_image_provider.API_KEY_SETTING)

    def test_it_does_not_change_the_environment(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            before = dict(os.environ)

            with patch.object(openai, "requests", _Transport()):
                openai.generate_script(TOPIC)

            self.assertEqual(dict(os.environ), before)


class TestItReadsTheAnswerShape(unittest.TestCase):

    def test_it_returns_what_the_writer_returns(self):
        result, _ = _run()

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_a_json_fence_is_stripped(self):
        fenced = "```json\n" + json.dumps(SCRIPT, ensure_ascii=False) + "\n```"

        result, _ = _run(_Transport(_answer(fenced)))

        self.assertEqual(len(result["data"]["scenes"]), 6)

    def test_reasoning_items_are_not_mistaken_for_the_script(self):
        """추론 모델은 output에 reasoning 항목도 넣는다."""

        result, _ = _run(_Transport(_answer(
            json.dumps(SCRIPT, ensure_ascii=False), with_reasoning=True)))

        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_several_text_parts_are_joined(self):
        text = json.dumps(SCRIPT, ensure_ascii=False)
        payload = _answer(text)
        payload["output"][0]["content"] = [
            {"type": "output_text", "text": text[:40]},
            {"type": "output_text", "text": text[40:]},
        ]

        result, _ = _run(_Transport(payload))

        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_the_scene_fields_step02_reads_are_filled(self):
        result, _ = _run()

        for scene in result["data"]["scenes"]:
            with self.subTest(scene=scene["scene"]):
                self.assertTrue(scene.get("image_prompt"))


class TestItFailsHonestly(unittest.TestCase):

    def _fails_with(self, transport, expected=None):
        expected = expected or openai.OpenAIScriptError

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(openai, "requests", transport):
                with self.assertRaises(expected) as caught:
                    openai.generate_script(TOPIC)

        return str(caught.exception)

    def test_no_key_is_refused_by_name(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(
                    openai.OpenAIScriptUnavailable) as caught:
                openai.generate_script(TOPIC)

        self.assertIn("OPENAI_API_KEY", str(caught.exception))

    def test_it_refuses_before_calling_anything(self):
        transport = _Transport()

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(openai, "requests", transport):
                with self.assertRaises(openai.OpenAIScriptUnavailable):
                    openai.generate_script(TOPIC)

        self.assertEqual(transport.calls, [])

    def test_an_empty_topic_never_reaches_the_model(self):
        transport = _Transport()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(openai, "requests", transport):
                with self.assertRaises(Exception):
                    openai.generate_script("   ")

        self.assertEqual(transport.calls, [])

    def test_a_refusal_is_told_apart_from_a_broken_call(self):
        message = self._fails_with(_Transport(
            _answer(refusal="I can't help with that.")))

        self.assertIn("거절", message)

    def test_the_refusal_text_is_shown(self):
        """모델이 왜 거절했는지는 사람이 읽어야 고칠 수 있다."""

        message = self._fails_with(_Transport(
            _answer(refusal="정책에 어긋납니다")))

        self.assertIn("정책에 어긋납니다", message)

    def test_a_content_filter_stop_says_so(self):
        message = self._fails_with(_Transport(_answer(
            "", status="incomplete", reason="content_filter")))

        self.assertIn("content_filter", message)

    def test_a_truncated_answer_points_at_the_ceiling(self):
        message = self._fails_with(_Transport(_answer(
            '{"title": "잘린', status="incomplete",
            reason="max_output_tokens")))

        self.assertIn("max_output_tokens", message)

    def test_a_rejected_key_says_the_status(self):
        message = self._fails_with(_Transport(
            {"error": {"type": "invalid_request_error",
                       "message": "Incorrect API key provided"}},
            status_code=401))

        self.assertIn("401", message)

    def test_a_rate_limit_says_the_status(self):
        message = self._fails_with(_Transport(
            {"error": {"type": "rate_limit_error",
                       "message": "Rate limit reached"}},
            status_code=429))

        self.assertIn("429", message)

    def test_a_network_failure_is_an_error(self):
        message = self._fails_with(
            _Transport(raises=OSError("connection reset")))

        self.assertIn("connection reset", message)

    def test_an_answer_without_text_is_an_error(self):
        self._fails_with(_Transport(_answer(None)))

    def test_an_answer_that_is_not_json_is_an_error(self):
        self._fails_with(_Transport(_answer("대본을 써 드릴까요?")))

    def test_a_script_without_scenes_is_an_error(self):
        self._fails_with(_Transport(_answer('{"title": "x"}')))


class TestTheOutcomeLooksLikeTheGates(unittest.TestCase):

    def _make(self, transport=None):
        transport = transport or _Transport()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(openai, "requests", transport):
                return openai.script_outcome(TOPIC), transport

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
        self.assertIn("OpenAI", outcome["gate"])

    def test_it_does_not_retry_when_the_script_is_off_target(self):
        short = {"title": "짧게", "scenes": [
            {"scene": 1, "narration": "짧다.", "image_prompt": "x"}]}

        outcome, transport = self._make(_Transport(
            _answer(json.dumps(short, ensure_ascii=False))))

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(outcome["attempts"], 1)
        self.assertFalse(outcome["passed"])

    def test_the_bounds_come_from_the_gate_itself(self):
        with open(openai.__file__, encoding="utf-8") as f:
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

    def test_current_runs_the_existing_engine_and_never_openai(self):
        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            gate.return_value = {
                "result": {"data": SCRIPT}, "estimated_seconds": 45.0,
                "attempts": 1, "duration_passed": True,
                "topic_fidelity": {"passed": True}, "passed": True,
            }
            with patch.object(openai, "script_outcome") as direct:
                step01_script.run(TOPIC, self.project)

        gate.assert_called_once()
        direct.assert_not_called()

    def test_choosing_openai_skips_the_existing_engine(self):
        provider_selection.save(self.project, {"script": "openai"})

        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            with patch.dict(os.environ, CONFIGURED, clear=True):
                with patch.object(openai, "requests", _Transport()):
                    data = step01_script.run(TOPIC, self.project)

        gate.assert_not_called()
        self.assertEqual(data["title"], SCRIPT["title"])

    def test_choosing_openai_never_calls_the_other_two(self):
        from app.providers import claude_script_provider, gemini_script_provider

        provider_selection.save(self.project, {"script": "openai"})

        with patch.object(gemini_script_provider,
                          "script_outcome") as gemini:
            with patch.object(claude_script_provider,
                              "script_outcome") as claude:
                with patch.dict(os.environ, CONFIGURED, clear=True):
                    with patch.object(openai, "requests", _Transport()):
                        step01_script.run(TOPIC, self.project)

        gemini.assert_not_called()
        claude.assert_not_called()

    def test_it_writes_the_same_file_the_engine_writes(self):
        provider_selection.save(self.project, {"script": "openai"})

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(openai, "requests", _Transport()):
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

        provider_selection.save(self.project, {"script": "openai"})

        with patch.object(step01_script,
                          "generate_script_within_duration") as gate:
            with patch.dict(os.environ, CONFIGURED, clear=True):
                with patch.object(openai, "requests",
                                  _Transport()) as transport:
                    studio_review.generate_script(TOPIC, self.project)

        gate.assert_not_called()
        self.assertEqual(len(transport.calls), 1)


class TestFourProjectsDoNotMix(unittest.TestCase):

    def test_the_choice_does_not_leak_between_threads(self):
        tmps = [tempfile.TemporaryDirectory() for _ in range(4)]
        for tmp in tmps:
            self.addCleanup(tmp.cleanup)

        chosen = ("openai", "claude", "gemini", "current")
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
                for name, tmp in zip("ABCD", tmps)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(seen.get("A"), "openai")
        self.assertEqual(seen.get("B"), "claude")
        self.assertEqual(seen.get("C"), "gemini")
        self.assertIsNone(seen.get("D"))


class TestTheCatalogOffersIt(unittest.TestCase):

    def setUp(self):
        self.registry = StageProviderRegistry()
        bootstrap.register_current_providers(self.registry)

    def _provider(self, name="openai"):
        return self.registry.get(stages.SCRIPT, name)

    def test_it_is_no_longer_coming_soon(self):
        self.assertFalse(getattr(self._provider(), "coming_soon", False))

    def test_the_earlier_two_are_still_there(self):
        for name in ("gemini", "claude"):
            with self.subTest(name=name):
                self.assertFalse(
                    getattr(self._provider(name), "coming_soon", False))

    def test_no_script_place_is_empty_anymore(self):
        """Sprint141 - 대본 자리는 하나도 남지 않았다."""

        for provider in self.registry.for_stage(stages.SCRIPT):
            with self.subTest(name=provider.name):
                self.assertFalse(
                    getattr(provider, "coming_soon", False))

    def test_without_a_key_it_says_which(self):
        with patch.dict(os.environ, {}, clear=True):
            available, reason = self._provider().availability()

        self.assertFalse(available)
        self.assertIn("OPENAI_API_KEY", reason)

    def test_with_a_key_it_is_available(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}, clear=True):
            available, reason = self._provider().availability()

        self.assertTrue(available)
        self.assertEqual(reason, "")

    def test_no_key_becomes_provider_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderUnavailable):
                self._provider().generate(StageRequest(topic=TOPIC))

    def test_an_api_error_becomes_a_stage_provider_error(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(openai, "requests",
                              _Transport(raises=OSError("boom"))):
                with self.assertRaises(StageProviderError):
                    self._provider().generate(StageRequest(topic=TOPIC))

    def test_it_needs_a_topic(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with self.assertRaises(ValueError):
                self._provider().generate(StageRequest())

    def test_it_reaches_the_same_module_the_bridge_uses(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(openai, "requests",
                              _Transport()) as transport:
                result = self._provider().generate(StageRequest(topic=TOPIC))

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result["data"]["title"], SCRIPT["title"])

    def test_the_setting_name_matches_the_engine(self):
        names = {
            entry[0]: entry[3]
            for entry in generated_script.GENERATED_SCRIPT_PROVIDERS
        }

        self.assertEqual(names["openai"], openai.API_KEY_SETTING)

    def test_registering_does_not_wake_any_client_library(self):
        import subprocess

        code = (
            "import sys\n"
            "from app.production.providers import bootstrap\n"
            "from app.production.registry import StageProviderRegistry\n"
            "bootstrap.register_current_providers(StageProviderRegistry())\n"
            "print(len([m for m in sys.modules "
            "if m.startswith(('google.genai','anthropic','openai'))]))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
        )

        self.assertEqual(result.stdout.strip(), "0", result.stderr[-800:])


class TestTheSharedPlaceIsStillShared(unittest.TestCase):

    def test_it_uses_the_common_reader(self):
        with open(openai.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        imported = {
            node.module or "" for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }

        self.assertIn("app.providers.direct_script", imported)

    def test_its_exceptions_share_the_base(self):
        self.assertTrue(issubclass(openai.OpenAIScriptUnavailable,
                                   direct_script.ScriptProviderUnavailable))
        self.assertTrue(issubclass(openai.OpenAIScriptError,
                                   direct_script.ScriptProviderError))

    def test_adding_the_third_did_not_add_a_third_branch(self):
        """
        Sprint134가 표로 모아 둔 이유다. 세 번째 Provider가 step01에
        분기를 하나 더 만들었다면 그 정리가 헛일이 된다.
        """

        with open(step01_script.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        branches = [node for node in ast.walk(tree)
                    if isinstance(node, ast.If)]

        self.assertLessEqual(len(branches), 2)


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
                self.assertNotIn("openai", self._constants(module))

    def test_the_gate_still_retries_three_times(self):
        from app.services import duration_gate

        self.assertEqual(duration_gate.MAX_ATTEMPTS, 3)

    def test_the_pipeline_does_not_know_this_provider(self):
        import app.pipeline.pipeline as pipeline

        self.assertNotIn("openai", self._constants(pipeline))

    def test_the_engine_layer_does_not_import_the_production_package(self):
        with open(openai.__file__, encoding="utf-8") as f:
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
