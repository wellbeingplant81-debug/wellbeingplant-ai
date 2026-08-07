"""
Sprint128 - 고른 Script Provider를 생성 지점까지 잇는다 (Epic 56, Phase 5).

Sprint126(음성)·127(이미지)이 놓은 다리를 대본에도 놓는다. 방식은 같다 -
환경변수를 쓰지 않고 프로젝트에 적고, 프로젝트를 아는 자리가 읽는다.

다만 대본은 자리가 다르다
-------------------------
음성은 scene_tts_service가, 이미지는 asset_integration_service가
project_path를 받고 있어서 step을 건드리지 않고도 읽을 수 있었다.
대본은 그렇지 않다 - step01_script.run(topic, project_path)이
generate_script_within_duration(topic=topic)을 부를 때 project_path를
내려보내지 않는다. 그 아래는 프로젝트를 모른다.

그래서 읽는 자리가 step01_script.run이 된다. 계약(인자 둘)은 그대로
두고, 안에서 프로젝트의 결정을 읽어 하나뿐인 생성 지점으로 넘긴다.
step02~07은 손대지 않는다.

current는 Gemini가 아니다
-------------------------
현재 엔진은 단순한 Gemini 호출이 아니다.

    Writer -> Duration Gate -> Topic Fidelity -> QA -> Retry

전부를 거친다. "gemini"는 그 파이프라인 없이 모델을 직접 부르는
장래의 자리이고 아직 비어 있다. 둘을 같게 취급하면 지어내는 것이
된다 - current는 None으로 접혀 기존 엔진이 한 글자도 다르지 않게
돌고, gemini는 정직하게 거절한다.
"""

import ast
import inspect
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

from app.services import provider_selection
from app.services.provider_selection import ProviderNotWired

ALLOWED = ("current", "gemini", "claude", "openai", "deepseek")

SCRIPT = {
    "title": "제목",
    "hook": "훅",
    "scenes": [
        {"scene": n, "narration": f"{n}번", "image_prompt": "p"}
        for n in range(1, 4)
    ],
}


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name


class TestTheSelectionIsStored(_Case):

    def test_every_allowed_value_can_be_saved(self):
        for name in ALLOWED:
            with self.subTest(name=name):
                provider_selection.save(self.project, {"script": name})
                self.assertEqual(
                    provider_selection.all_selected(self.project)["script"],
                    name,
                )

    def test_current_folds_to_nothing(self):
        provider_selection.save(self.project, {"script": "current"})

        self.assertIsNone(provider_selection.selected(self.project, "script"))

    def test_it_does_not_touch_the_source_field(self):
        """production_source는 어디서 가져오는가이고 script_provider는
        누가 만드는가다."""

        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"production_source": "import"}, f)

        provider_selection.save(self.project, {"script": "claude"})

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["production_source"], "import")
        self.assertEqual(saved["script_provider"], "claude")

    def test_the_resolver_still_reads_only_its_own_field(self):
        from app.steps import step01_script_resolve

        provider_selection.save(self.project, {"script": "claude"})

        self.assertEqual(
            step01_script_resolve.detect_source(self.project), "auto")


class TestWhatIsActuallyWired(_Case):

    def test_the_wired_script_providers(self):
        """Sprint133 Gemini, Sprint134 Claude, Sprint135 OpenAI."""

        self.assertEqual(set(provider_selection.WIRED["script"]),
                         {"gemini", "claude", "openai", "deepseek"})

    def test_choosing_nothing_passes(self):
        provider_selection.require_wired("script", None)

    def test_choosing_anything_else_is_refused(self):
        """
        Sprint141 - 대본 자리는 넷 다 붙었다. 이제 거절당하는 것은
        아무도 등록하지 않은 이름뿐이다.
        """

        for name in ("그런거없음",):
            with self.subTest(name=name):
                with self.assertRaises(ProviderNotWired) as caught:
                    provider_selection.require_wired("script", name)
                self.assertIn(name, str(caught.exception))

    def test_gemini_is_not_treated_as_current(self):
        """
        현재 엔진은 Writer·Duration Gate·Topic Fidelity·QA·Retry
        전부다. 모델 하나를 부르는 것이 아니다.

        Sprint133에서 gemini가 붙었지만 이 문장은 그대로다 - 붙었다는
        것은 "고를 수 있다"는 뜻이지 "같다"는 뜻이 아니다. 고르면
        현재 엔진은 아예 돌지 않는다.
        """

        from unittest.mock import patch

        from app.providers import gemini_script_provider
        from app.steps import step01_script

        provider_selection.save(self.project, {"script": "gemini"})

        with patch.object(step01_script,
                          "generate_script_within_duration") as engine:
            with patch.object(gemini_script_provider,
                              "script_outcome") as direct:
                direct.return_value = {
                    "result": {"data": {"title": "t", "scenes": []}},
                    "estimated_seconds": 45.0, "attempts": 1,
                    "duration_passed": True,
                    "topic_fidelity": {"passed": True}, "passed": True,
                }
                step01_script.run("주제", self.project)

        engine.assert_not_called()
        direct.assert_called_once()


class TestTheNameReachesTheGenerator(_Case):

    def _run(self, times=1):
        from app.steps import step01_script

        seen = []

        def fake(topic, provider=None):
            seen.append(provider)
            return {"result": {"data": dict(SCRIPT)}, "passed": True,
                    "attempts": 1, "estimated_seconds": 45.0,
                    "topic_fidelity": None}

        with patch.object(step01_script, "_generate_script", fake):
            for _ in range(times):
                try:
                    step01_script.run("주제", self.project)
                except Exception:
                    pass

        return seen

    def test_nothing_chosen_delivers_nothing(self):
        self.assertEqual(self._run(), [None])

    def test_current_delivers_nothing_too(self):
        provider_selection.save(self.project, {"script": "current"})

        self.assertEqual(self._run(), [None])

    def test_each_chosen_name_arrives(self):
        for name in ("gemini", "claude", "openai", "deepseek"):
            with self.subTest(name=name):
                provider_selection.save(self.project, {"script": name})
                self.assertEqual(self._run(times=3), [name] * 3)

    def test_the_generator_refuses_what_is_not_wired(self):
        from app.steps import step01_script

        provider_selection.save(self.project, {"script": "그런거없음"})

        with self.assertRaises(ProviderNotWired):
            step01_script.run("주제", self.project)

    def test_a_refusal_writes_no_script(self):
        from app.steps import step01_script

        provider_selection.save(self.project, {"script": "그런거없음"})

        with self.assertRaises(ProviderNotWired):
            step01_script.run("주제", self.project)

        self.assertFalse(
            os.path.exists(os.path.join(self.project, "script.json")))


class TestTheCurrentEngineIsUntouched(_Case):
    """Writer·Duration Gate·Topic Fidelity·QA·Retry 전부 그대로."""

    def test_the_gate_is_still_the_one_that_runs(self):
        """step01_script가 이미 바인딩한 이름을 잡아야 한다 - 모듈
        경로로 패치하면 진짜 Writer가 돈다."""

        from app.steps import step01_script

        with patch.object(step01_script, "generate_script_within_duration",
                          return_value={"result": {"data": dict(SCRIPT)},
                                        "passed": True, "attempts": 1,
                                        "estimated_seconds": 45.0}) as gate:
            step01_script.run("주제", self.project)

        gate.assert_called_once_with(topic="주제")

    def test_it_still_writes_the_script(self):
        from app.steps import step01_script

        with patch.object(step01_script, "generate_script_within_duration",
                          return_value={"result": {"data": dict(SCRIPT)},
                                        "passed": True, "attempts": 1,
                                        "estimated_seconds": 45.0}):
            data = step01_script.run("주제", self.project)

        self.assertEqual(data["title"], "제목")
        self.assertTrue(
            os.path.exists(os.path.join(self.project, "script.json")))

    def test_the_contract_did_not_change(self):
        from app.steps import step01_script

        signature = inspect.signature(step01_script.run)

        self.assertEqual(list(signature.parameters), ["topic", "project_path"])


class TestTheReviewStepCarriesIt(_Case):

    def test_step1_generation_delivers_the_choice(self):
        from app.services import studio_review
        from app.steps import step01_script

        provider_selection.save(self.project, {"script": "deepseek"})
        seen = []

        def fake(topic, provider=None):
            seen.append(provider)
            return {"result": {"data": dict(SCRIPT)}, "passed": True,
                    "attempts": 1, "estimated_seconds": 45.0}

        with patch.object(step01_script, "_generate_script", fake):
            try:
                studio_review.generate_script("주제", self.project)
            except Exception:
                pass

        self.assertEqual(seen, ["deepseek"])

    def test_the_review_service_needed_no_change(self):
        from app.services import studio_review

        source = open(studio_review.__file__, encoding="utf-8").read()

        self.assertNotIn("script_provider", source)
        self.assertNotIn('"script")', source)


class TestThreadsDoNotMix(unittest.TestCase):

    def test_three_projects_at_once_keep_their_own(self):
        from app.steps import step01_script

        seen = {}
        lock = threading.Lock()
        chosen = ("gemini", "claude", "deepseek")
        tmps = [tempfile.TemporaryDirectory() for _ in chosen]
        self.addCleanup(lambda: [t.cleanup() for t in tmps])

        for tmp, name in zip(tmps, chosen):
            provider_selection.save(tmp.name, {"script": name})

        current = threading.local()

        def fake(topic, provider=None):
            with lock:
                seen.setdefault(current.project, []).append(provider)
            return {"result": {"data": dict(SCRIPT)}, "passed": True,
                    "attempts": 1, "estimated_seconds": 45.0}

        def run(project):
            current.project = project
            for _ in range(3):
                try:
                    step01_script.run("주제", project)
                except Exception:
                    pass

        with patch.object(step01_script, "_generate_script", fake):
            threads = [threading.Thread(target=run, args=(t.name,))
                       for t in tmps]
            [t.start() for t in threads]
            [t.join() for t in threads]

        for tmp, name in zip(tmps, chosen):
            with self.subTest(provider=name):
                self.assertEqual(seen[tmp.name], [name] * 3)


class TestNothingGlobalOrStructuralMoved(unittest.TestCase):

    def test_no_environment_variable_is_used(self):
        from app.steps import step01_script

        import ast

        with open(step01_script.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        # Sprint134 - 환경변수 이름은 문자열로 쓰인다. 원문을 훑으면
        # DIRECT_SCRIPT_PROVIDERS 같은 식별자가 이 이름을 품고 있다는
        # 이유로 걸린다 - 묻고 싶은 것은 "그 이름을 값으로 쓰는가"다.
        written = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        called = {
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        }

        self.assertNotIn("SCRIPT_PROVIDER", written)
        self.assertNotIn("getenv", called)
        self.assertNotIn("putenv", called)

    def test_the_resolver_is_untouched(self):
        from app.steps import step01_script_resolve

        source = open(step01_script_resolve.__file__, encoding="utf-8").read()

        self.assertNotIn("provider_selection", source)
        self.assertNotIn("script_provider", source)

    def test_the_pipeline_is_untouched(self):
        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        self.assertNotIn("provider_selection", source)
        self.assertNotIn("script_provider", source)

    def test_steps_two_to_seven_are_untouched(self):
        from app.steps import (
            step02_assets, step03_tts, step04_subtitle, step05_video,
            step06_thumbnail, step07_quality,
        )

        for module in (step02_assets, step03_tts, step04_subtitle,
                       step05_video, step06_thumbnail, step07_quality):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("provider_selection", source)

    def test_the_writer_side_is_untouched(self):
        from app.services import duration_gate, script_service

        for module in (duration_gate, script_service):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("provider_selection", source)
                self.assertNotIn("provider=", source)


class TestTheScreenCanSetIt(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.services import project_service

        self.client = TestClient(app)
        self.project = project_service.create_project("주제", "wellbeing")
        self.pid = self.project["id"]
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(str(self.project["path"]), ignore_errors=True)

    def test_each_allowed_value_is_accepted(self):
        for name in ALLOWED:
            with self.subTest(name=name):
                response = self.client.put(
                    f"/studio/api/review/{self.pid}/providers",
                    json={"providers": {"script": name}},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["providers"]["script"], name)

    def test_an_unknown_name_is_refused(self):
        response = self.client.put(
            f"/studio/api/review/{self.pid}/providers",
            json={"providers": {"script": "그런거없음"}},
        )

        self.assertEqual(response.status_code, 400)

    def test_the_state_reports_it(self):
        self.client.put(
            f"/studio/api/review/{self.pid}/providers",
            json={"providers": {"script": "claude"}},
        )

        state = self.client.get(f"/studio/api/review/{self.pid}").json()

        self.assertEqual(state["providers"]["script"], "claude")


if __name__ == "__main__":
    unittest.main()
