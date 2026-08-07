"""
Sprint108 - 만들기 전에 무엇이 나올지 알려 준다 (Epic 54, Phase 7).

붙여넣은 대본으로 영상을 만들면 몇 초짜리가 되는지, scene과 이미지는
몇 개인지, 비용은 얼마인지를 생성 버튼을 누르기 전에 보여 준다.

PV-03에서 27.7초짜리가 나온 것이 계기다. 목표는 45초인데 그렇게 된
이유는 Duration Gate가 step01 안에 있어서 붙여넣은 대본은 그 게이트를
거치지 않기 때문이다. 그 사실 자체는 Sprint106의 설계대로다 - 사용자가
준 대본을 우리가 고치지 않는다. 다만 누르기 전에 알 수는 있어야 한다.

그래서 여기서 하는 일은 재는 것뿐이다.

    고치지 않는다. 늘리지 않는다. 요약하지 않는다. 다시 만들지 않는다.

새 계산도 만들지 않는다 - Duration Gate가 쓰는 그 estimator를 그대로
부른다. 두 곳이 다른 값을 내면 화면이 통과라고 한 대본이 게이트에서
걸리는 날이 온다.
"""

import ast
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import script_forecast
from app.services import duration_estimator, duration_gate


def _script(narrations, images=None):
    return {
        "title": "제목",
        "hook": "훅",
        "script": " ".join(narrations),
        "character": "인물",
        "scenes": [
            {
                "scene": index,
                "narration": text,
                "image_prompt": "a man walking",
            }
            for index, text in enumerate(narrations, start=1)
        ],
    }


def _at_target():
    """권장 범위에 들어가는 대본. estimator로 역산해 만든다 -
    숫자를 손으로 넣으면 상수가 바뀔 때 조용히 틀린다."""

    sentence = "저녁 식사 후에 천천히 열 분만 걸으면 혈당이 안정됩니다."
    scenes, narrations = [], []

    while True:
        narrations.append(sentence)
        scenes = _script(narrations)["scenes"]
        if duration_estimator.estimate_script_duration(scenes) >= 43.0:
            break

    return _script(narrations)


class TestItReusesTheEngineEstimator(unittest.TestCase):
    """새 계산을 만들지 않는다. 두 곳이 다른 값을 내면 화면이
    통과라고 한 대본이 게이트에서 걸린다."""

    def test_the_seconds_match_the_estimator_exactly(self):
        script = _script(["첫 문장입니다.", "둘째 문장입니다."])

        forecast = script_forecast.forecast(script)

        self.assertEqual(
            forecast["duration"]["seconds"],
            round(duration_estimator.estimate_script_duration(script["scenes"]), 2),
        )

    def test_the_recommended_range_comes_from_the_duration_gate(self):
        forecast = script_forecast.forecast(_script(["문장."]))

        self.assertEqual(
            forecast["duration"]["min_seconds"], duration_gate.MIN_ACCEPTABLE_SECONDS,
        )
        self.assertEqual(
            forecast["duration"]["max_seconds"], duration_gate.MAX_ACCEPTABLE_SECONDS,
        )

    def test_no_estimation_logic_of_its_own(self):
        """상수를 여기에 다시 적으면 두 곳이 갈라진다."""

        source = open(script_forecast.__file__, encoding="utf-8").read()

        self.assertNotIn("5.93", source)
        self.assertNotIn("43.0", source)
        self.assertNotIn("47.0", source)


class TestTheVerdict(unittest.TestCase):

    def test_a_script_in_range_passes(self):
        forecast = script_forecast.forecast(_at_target())

        self.assertEqual(forecast["duration"]["verdict"], script_forecast.PASS)
        self.assertEqual(forecast["warnings"], [])

    def test_a_short_script_warns_without_refusing(self):
        """PV-03에서 실제로 나온 경우다. 만들 수는 있다."""

        forecast = script_forecast.forecast(_script(["짧은 한 문장입니다."]))

        self.assertEqual(forecast["duration"]["verdict"], script_forecast.WARN)
        self.assertTrue(forecast["warnings"])
        self.assertIn("짧", forecast["warnings"][0])

    def test_a_long_script_warns_too(self):
        sentence = "저녁 식사 후에 천천히 열 분만 걸으면 혈당이 안정됩니다."
        narrations = []
        while True:
            narrations.append(sentence)
            if duration_estimator.estimate_script_duration(
                _script(narrations)["scenes"],
            ) > duration_gate.MAX_ACCEPTABLE_SECONDS:
                break

        forecast = script_forecast.forecast(_script(narrations))

        self.assertEqual(forecast["duration"]["verdict"], script_forecast.WARN)
        self.assertIn("깁니다", " ".join(forecast["warnings"]))

    def test_the_warning_says_generation_is_still_possible(self):
        forecast = script_forecast.forecast(_script(["짧은 문장."]))

        self.assertIn("생성", " ".join(forecast["warnings"]))


class TestCounts(unittest.TestCase):

    def test_scene_count(self):
        forecast = script_forecast.forecast(_script(["하나.", "둘.", "셋."]))

        self.assertEqual(forecast["scene_count"], 3)

    def test_image_count_is_one_per_scene(self):
        """지금 엔진은 scene마다 이미지 하나를 쓴다."""

        forecast = script_forecast.forecast(_script(["하나.", "둘."]))

        self.assertEqual(forecast["image_count"], 2)

    def test_the_tts_length_is_the_narration_characters(self):
        script = _script(["가나다.", "라마바."])

        forecast = script_forecast.forecast(script)

        self.assertEqual(
            forecast["tts_characters"],
            sum(len(s["narration"]) for s in script["scenes"]),
        )

    def test_per_scene_seconds_are_reported(self):
        """어느 scene이 짧은지 사람이 볼 수 있어야 고칠 수 있다."""

        forecast = script_forecast.forecast(_script(["하나.", "둘."]))

        self.assertEqual(len(forecast["scenes"]), 2)
        self.assertEqual(forecast["scenes"][0]["scene"], 1)
        self.assertGreater(forecast["scenes"][0]["seconds"], 0)


class TestCost(unittest.TestCase):

    def test_the_script_stage_is_free_because_it_was_pasted(self):
        """붙여넣은 대본은 우리가 API를 부르지 않았다."""

        forecast = script_forecast.forecast(_script(["문장."]))

        script_line = [
            e for e in forecast["cost"]["estimates"] if e["stage"] == "script"
        ][0]

        self.assertEqual(script_line["amount"], 0.0)

    def test_metadata_is_known_free_and_the_rest_unknown(self):
        forecast = script_forecast.forecast(_script(["문장."]))

        self.assertIn("image", forecast["cost"]["unknown_stages"])
        self.assertNotIn("script", forecast["cost"]["unknown_stages"])
        self.assertNotIn("metadata", forecast["cost"]["unknown_stages"])

    def test_it_never_invents_a_number(self):
        forecast = script_forecast.forecast(_script(["문장."]))

        self.assertFalse(forecast["cost"]["complete"])


class TestItNeverChangesTheScript(unittest.TestCase):
    """자동 재생성/추가/요약/수정 전부 금지."""

    def test_the_input_is_not_mutated(self):
        import copy

        script = _script(["하나.", "둘."])
        before = copy.deepcopy(script)

        script_forecast.forecast(script)

        self.assertEqual(script, before)

    def test_it_writes_nothing(self):
        tree = ast.parse(open(script_forecast.__file__, encoding="utf-8").read())

        called = {
            node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
        }

        for forbidden in ("open", "dump", "write", "makedirs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, called)

    def test_it_calls_no_ai(self):
        tree = ast.parse(open(script_forecast.__file__, encoding="utf-8").read())

        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")

        for forbidden in ("genai", "requests", "script_service",
                          "duration_gate.generate", "step01"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(any(forbidden in n for n in names), forbidden)


class TestEmptyAndBrokenInput(unittest.TestCase):

    def test_no_scenes_gives_zero_not_a_crash(self):
        forecast = script_forecast.forecast({"title": "t", "scenes": []})

        self.assertEqual(forecast["scene_count"], 0)
        self.assertEqual(forecast["duration"]["seconds"], 0.0)

    def test_a_missing_narration_is_counted_as_empty(self):
        forecast = script_forecast.forecast(
            {"title": "t", "scenes": [{"scene": 1}]},
        )

        self.assertEqual(forecast["scene_count"], 1)
        self.assertEqual(forecast["tts_characters"], 0)


class TestTheEndpointCarriesIt(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def _post(self, raw):
        return self.client.post(
            "/studio/api/production/import", json={"raw": raw, "topic": "주제"},
        )

    def test_the_import_preview_includes_the_forecast(self):
        raw = ('{"title":"t","scenes":[{"narration":"첫 문장입니다.",'
               '"subject":"a man","action":"walking"}]}')

        body = self._post(raw).json()

        self.assertIn("forecast", body)
        self.assertIn("duration", body["forecast"])
        self.assertEqual(body["forecast"]["scene_count"], 1)

    def test_a_short_paste_is_warned_about(self):
        raw = '{"title":"t","scenes":[{"narration":"짧은 문장."}]}'

        forecast = self._post(raw).json()["forecast"]

        self.assertEqual(forecast["duration"]["verdict"], "warn")
        self.assertTrue(forecast["warnings"])


class TestNothingElseChanged(unittest.TestCase):
    """Acceptance - Auto 결과 동일, Duration Gate/step01 수정 없음."""

    def test_the_duration_gate_is_untouched(self):
        source = open(duration_gate.__file__, encoding="utf-8").read()

        self.assertNotIn("forecast", source)
        self.assertEqual(duration_gate.MIN_ACCEPTABLE_SECONDS, 43.0)
        self.assertEqual(duration_gate.MAX_ACCEPTABLE_SECONDS, 47.0)

    def test_step01_is_untouched(self):
        from app.steps import step01_script

        tree = ast.parse(open(step01_script.__file__, encoding="utf-8").read())
        run = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )

        self.assertEqual(
            [n for n in ast.walk(run) if isinstance(n, ast.If)], [],
        )

    def test_the_pipeline_does_not_import_the_forecast(self):
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
                self.assertNotIn("script_forecast", name)

    def test_the_resolver_does_not_judge_length(self):
        """Resolver는 존재/형식/필수 필드만 본다(Sprint106). 예측이
        생겼다고 거기서 거절하게 만들지 않는다."""

        from app.steps import step01_script_resolve

        tree = ast.parse(
            open(step01_script_resolve.__file__, encoding="utf-8").read(),
        )

        # 원문을 훑지 않는다 - 설명 주석이 duration_estimator를
        # 언급한다(어느 필드를 누가 쓰는지 적느라).
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)

        for name in names:
            with self.subTest(imported=name):
                self.assertNotIn("forecast", name)
                self.assertNotIn("duration", name)


if __name__ == "__main__":
    unittest.main()
