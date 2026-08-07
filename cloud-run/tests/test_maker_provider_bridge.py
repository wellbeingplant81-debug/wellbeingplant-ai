"""
Sprint139 - maker에서 고른 것이 끝까지 간다 (Epic 56, Phase 16).

Sprint132가 maker에 Provider 선택기를 놓고, 검토 경로에서는 프로젝트를
만든 직후 그 선택을 적게 했다. 그런데 두 곳이 끊겨 있었다.

    /plan          고른 것을 보내지 않아, 요약이 언제나 현재 엔진의
                   사실(인증·시간)을 말했다
    영상 생성      프로젝트를 작업 안에서 만들어, 고른 Provider가
                   적히기 전에 파이프라인이 돌았다

두 번째가 더 나쁘다. FLUX를 골라 놓고 눌렀는데 조용히 현재 엔진으로
만들어진다 - 화면이 거짓말을 하는 것이 아니라 결과가 다르다.

새 다리를 만들지 않는다
-----------------------
프로젝트를 만드는 자리(POST /api/review)도, 고른 것을 적는 자리
(PUT /api/review/{id}/providers)도 이미 있다. 순서를 바꿔 부르기만
한다.

    영상 생성 누름
      -> 고른 것이 있으면 먼저 빈 프로젝트를 만든다
      -> 그 프로젝트에 고른 것을 적는다
      -> 그 project_id로 작업을 시작한다(Sprint107이 이미 받는다)

계획도 사실을 말하게 된다
-------------------------
/plan이 고른 이름을 받으면 요약의 "필요한 인증"이 실제로 고른
Provider의 것이 된다. 그리고 제작 시간의 "측정 완료"는 현재 엔진을
잰 값이므로, 직접 호출을 고른 순간 그렇게 말할 수 없다.
"""

import ast
import json
import os
import re
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

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


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


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _plan(selections, providers=None):
    body = {"selections": selections}

    if providers is not None:
        body["providers"] = providers

    return _client().post("/studio/api/production/plan", json=body)


ALL_GENERATE = {"script": "generate", "image": "generate",
                "voice": "generate", "metadata": "generate"}


class TestThePlanCarriesTheChoice(unittest.TestCase):

    def _provider_of(self, response, stage):
        return response.json()["stages"][stage]["provider"]

    def test_without_a_choice_nothing_changes(self):
        """고르지 않으면 예전 그대로다."""

        response = _plan(ALL_GENERATE)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._provider_of(response, "script"), "current")

    def test_an_empty_choice_is_the_same_as_none(self):
        response = _plan(ALL_GENERATE, {})

        self.assertEqual(self._provider_of(response, "script"), "current")

    def test_the_chosen_script_provider_reaches_the_plan(self):
        response = _plan(ALL_GENERATE, {"script": "claude"})

        self.assertEqual(self._provider_of(response, "script"), "claude")

    def test_the_chosen_image_provider_reaches_the_plan(self):
        response = _plan(ALL_GENERATE, {"image": "flux"})

        self.assertEqual(self._provider_of(response, "image"), "flux")

    def test_the_chosen_voice_provider_reaches_the_plan(self):
        response = _plan(ALL_GENERATE, {"voice": "elevenlabs"})

        self.assertEqual(self._provider_of(response, "voice"), "elevenlabs")

    def test_choosing_one_stage_does_not_move_the_others(self):
        response = _plan(ALL_GENERATE, {"image": "gpt_image"})

        self.assertEqual(self._provider_of(response, "image"), "gpt_image")
        self.assertEqual(self._provider_of(response, "script"), "current")
        self.assertEqual(self._provider_of(response, "voice"), "current")

    def test_current_folds_back_to_the_existing_path(self):
        response = _plan(ALL_GENERATE, {"script": "current"})

        self.assertEqual(self._provider_of(response, "script"), "current")

    def test_a_name_nobody_knows_is_refused(self):
        """모르는 이름을 조용히 무시하면 고른 대로 만들어지지 않는다."""

        response = _plan(ALL_GENERATE, {"script": "그런거없음"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("그런거없음", response.json()["detail"])

    def test_a_provider_from_another_stage_is_refused(self):
        response = _plan(ALL_GENERATE, {"script": "flux"})

        self.assertEqual(response.status_code, 400)

    def test_an_unknown_stage_is_refused(self):
        response = _plan(ALL_GENERATE, {"음성": "elevenlabs"})

        self.assertEqual(response.status_code, 400)

    def test_a_stage_that_makes_nothing_ignores_the_choice(self):
        """가져오기는 API를 부르지 않는다 - 고를 Provider가 없다."""

        response = _plan(dict(ALL_GENERATE, script="import"),
                         {"script": "claude"})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self._provider_of(response, "script"))

    def test_the_same_rule_decides_here_and_in_review(self):
        """두 자리가 다른 이름을 받아 주면 고른 것이 도중에 바뀐다."""

        from app.routers import studio

        self.assertTrue(hasattr(studio, "_known_provider"))


class TestTheProjectGetsIt(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name

    def _put(self, providers):
        import app.routers.studio as studio_router

        with patch.object(studio_router, "_project_path",
                          lambda project_id: self.project):
            return _client().put("/studio/api/review/p1/providers",
                                 json={"providers": providers})

    def test_what_the_maker_chose_lands_in_project_json(self):
        chosen = {"script": "gemini", "image": "flux",
                  "voice": "elevenlabs"}

        self.assertEqual(self._put(chosen).status_code, 200)

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["script_provider"], "gemini")
        self.assertEqual(saved["image_provider"], "flux")
        self.assertEqual(saved["voice_provider"], "elevenlabs")

    def test_the_engine_reads_exactly_what_was_chosen(self):
        for stage, name in (("script", "claude"), ("image", "gpt_image"),
                            ("voice", "elevenlabs")):
            with self.subTest(stage=stage):
                self._put({stage: name})

                self.assertEqual(
                    provider_selection.selected(self.project, stage), name)

    def test_review_opens_with_the_same_choice(self):
        import app.routers.studio as studio_router

        self._put({"script": "openai", "image": "flux"})

        with patch.object(studio_router, "_project_path",
                          lambda project_id: self.project):
            state = _client().get("/studio/api/review/p1").json()

        self.assertEqual(state["providers"]["script"], "openai")
        self.assertEqual(state["providers"]["image"], "flux")
        self.assertEqual(state["providers"]["voice"], "current")


class TestTheGenerateButtonNoLongerDropsIt(unittest.TestCase):
    """FLUX를 골라 놓고 눌렀는데 현재 엔진으로 만들어지면 안 된다."""

    def test_there_is_one_helper_that_writes_the_choice(self):
        self.assertIn("async function saveMakerProviders(", _script())

    def test_it_uses_the_endpoint_that_already_exists(self):
        block = _function("saveMakerProviders")

        self.assertIn("/providers", block)
        self.assertIn('"PUT"', block)

    def test_it_does_nothing_when_nothing_was_chosen(self):
        """고르지 않았으면 예전 경로 그대로여야 한다."""

        block = _function("saveMakerProviders")

        self.assertIn("Object.keys(uiProvider).length", block)

    def test_the_generate_button_makes_the_project_first(self):
        script = _script()
        block = script[script.index('$("go").onclick'):]
        block = block[:block.index("async function pollJob")]

        # 만드는 자리도 적는 자리도 함수 하나씩이다 - 두 경로가 같은
        # 것을 쓰므로 한쪽만 고쳐지는 일이 없다.
        self.assertIn("createProject", block)
        self.assertIn("saveMakerProviders", block)

    def test_the_project_is_made_through_the_endpoint_that_exists(self):
        block = _function("createProject")

        self.assertIn("/studio/api/review", block)

    def test_the_review_button_uses_the_same_helper(self):
        self.assertIn("saveMakerProviders", _function("startReview"))

    def test_the_job_still_receives_a_project_id(self):
        """Sprint107이 이미 받는 자리다 - 새로 만들지 않는다."""

        script = _script()
        block = script[script.index('$("go").onclick'):]
        block = block[:block.index("async function pollJob")]

        self.assertIn("project_id", block)

    def test_no_new_api_path_was_invented(self):
        paths = set(re.findall(r'"/studio/api/review[^"`]*"', _page()))

        self.assertEqual(paths, {'"/studio/api/review"'})


class TestThePlanRequestCarriesIt(unittest.TestCase):

    def test_the_page_sends_what_was_chosen(self):
        block = _function("refreshPlan")

        self.assertIn("uiProvider", block)

    def test_the_request_model_accepts_it(self):
        from app.routers.studio import StagePlanRequest

        request = StagePlanRequest(selections={"script": "generate"})

        self.assertIn(request.providers, ({}, None))


class TestTheSummaryStopsOverclaiming(unittest.TestCase):
    """
    제작 시간의 "측정 완료"는 현재 엔진을 잰 값이다. 직접 호출을
    고르면 재 본 적이 없는 길로 가므로 그렇게 말할 수 없다.
    """

    def test_there_is_a_check(self):
        self.assertIn("function planTimeIsMeasured(", _script())

    def test_it_looks_at_the_chosen_provider(self):
        block = _function("planTimeIsMeasured")

        self.assertIn("provider", block)
        self.assertIn('"current"', block)

    def test_the_summary_uses_it(self):
        block = _function("expectedResult")

        self.assertIn("planTimeIsMeasured", block)
        self.assertIn("UNMEASURED", block)


class TestNothingBelowMoved(unittest.TestCase):

    def _constants(self, module):
        with open(module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        return {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_the_resolvers_did_not_change(self):
        from app.steps import (
            step01_script_resolve, step02_asset_resolve, step03_voice_resolve,
        )

        for module in (step01_script_resolve, step02_asset_resolve,
                       step03_voice_resolve):
            with self.subTest(module=module.__name__):
                constants = self._constants(module)

                self.assertNotIn("script_provider", constants)
                self.assertNotIn("image_provider", constants)
                self.assertNotIn("voice_provider", constants)

    def test_the_job_runner_did_not_learn_about_providers(self):
        """프로젝트를 먼저 만들어 적어 두므로 작업은 알 필요가 없다."""

        from app.services import studio_jobs

        self.assertNotIn(
            "provider_selection", self._constants(studio_jobs))

    def test_the_pipeline_did_not_change(self):
        import app.pipeline.pipeline as pipeline

        constants = self._constants(pipeline)

        for name in ("script_provider", "image_provider", "voice_provider"):
            with self.subTest(name=name):
                self.assertNotIn(name, constants)

    def test_no_environment_variable_is_touched(self):
        from app.routers import studio

        with open(studio.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        called = {
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        }

        self.assertNotIn("putenv", called)
        self.assertNotIn("setenv", called)


class TestTwoProjectsDoNotMix(unittest.TestCase):

    def test_concurrent_choices_stay_apart(self):
        import app.routers.studio as studio_router

        tmps = [tempfile.TemporaryDirectory() for _ in range(3)]
        for tmp in tmps:
            self.addCleanup(tmp.cleanup)

        chosen = ("claude", "gemini", "openai")
        errors = []

        # 세 스레드가 각자 patch를 걸면 서로의 patch를 덮어쓴다. 한 번만
        # 걸고 project_id로 갈라 준다 - 실제 서버가 하는 일과 같다.
        paths = {name: tmp.name for name, tmp in zip(chosen, tmps)}

        def run(path, name):
            try:
                _client().put(
                    f"/studio/api/review/{name}/providers",
                    json={"providers": {"script": name}})
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        patcher = patch.object(studio_router, "_project_path",
                               lambda project_id: paths[project_id])
        patcher.start()
        self.addCleanup(patcher.stop)

        threads = [threading.Thread(target=run, args=(t.name, n))
                   for t, n in zip(tmps, chosen)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])

        for tmp, name in zip(tmps, chosen):
            with self.subTest(name=name):
                self.assertEqual(
                    provider_selection.selected(tmp.name, "script"), name)


if __name__ == "__main__":
    unittest.main()
