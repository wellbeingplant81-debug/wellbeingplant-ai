"""
Sprint81 - Studio에서 재생성을 돌리는 orchestration 계층.

엔진 로직을 옮겨오지 않는다. 여기서 하는 일은 세 가지뿐이다.

  1. 재생성 전 이미지를 스냅샷한다 - Before/After를 보여 주려면 필요한데,
     엔진은 자기 백업을 사이클이 끝나면 지운다(그게 맞다. 엔진의 백업은
     되돌리기용이지 보여 주기용이 아니다).
  2. regeneration_service.run()을 부른다.
  3. 엔진이 남긴 regeneration_log.json과 quality_report.json을 읽어
     화면이 쓸 모양으로 바꾼다.

무엇을 재생성할지, 예산이 남았는지, 되돌릴지는 전부 엔진이 정한다.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import studio_regeneration, studio_service


def _report(scenes, regeneration=None):
    return {
        "ai_quality_evaluation": {
            "scores": {"overall_quality": 70, "image_realism": 80,
                       "composition": 75, "character_consistency": 90,
                       "hook_strength": 80, "scene1_quality": 80,
                       "thumbnail_quality": 80},
            "scenes": [
                {"scene": n, "realism_score": r, "composition_score": 70,
                 "regenerate": bad, "reason": reason}
                for n, r, bad, reason in scenes
            ],
        },
        "regeneration": regeneration or [],
    }


def _log(**overrides):
    payload = {
        "max_image_calls": 6,
        "max_retry_per_scene": 3,
        "min_improvement": 3.0,
        "cycles": [{
            "cycle": 1, "targeted": [2], "dropped_for_budget": [],
            "succeeded": [2], "failed": [], "rolled_back": [],
            "quality_before": 70.0, "quality_after": 80.0,
            "quality_delta": 10.0, "spent": 1,
        }],
        "stop_reason": "no_improvement",
        "stop_explanation": "더 돌려도 나아진다는 근거가 없습니다.",
        "total_image_calls": 1,
        "rendered": True,
    }
    payload.update(overrides)
    return payload


class _Project:
    def __init__(self, root, log=None, report=None):
        self.path = os.path.join(root, "p1")
        os.makedirs(os.path.join(self.path, "images"))

        for number in (1, 2):
            with open(os.path.join(self.path, "images",
                                   f"scene{number}.png"), "wb") as f:
                f.write(f"ORIGINAL{number}".encode())

        if report is not None:
            with open(os.path.join(self.path, "quality_report.json"),
                      "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False)

        if log is not None:
            with open(os.path.join(self.path, "regeneration_log.json"),
                      "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False)


class TestBeforeSnapshot(unittest.TestCase):
    """엔진의 백업은 되돌리기용이라 사이클이 끝나면 사라진다.
    화면에 Before를 보여 주려면 UI가 따로 떠 둬야 한다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = _Project(self._tmp.name)

    def test_the_current_image_is_copied(self):
        studio_regeneration.snapshot_before(self.project.path, [2])

        path = os.path.join(
            self.project.path, studio_regeneration.BEFORE_DIRNAME,
            "scene2.png",
        )

        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"ORIGINAL2")

    def test_only_the_named_scenes_are_snapshotted(self):
        studio_regeneration.snapshot_before(self.project.path, [2])

        directory = os.path.join(
            self.project.path, studio_regeneration.BEFORE_DIRNAME,
        )

        self.assertEqual(os.listdir(directory), ["scene2.png"])

    def test_a_missing_image_is_not_fatal(self):
        studio_regeneration.snapshot_before(self.project.path, [99])

    def test_the_snapshot_directory_is_hidden_from_scene_scans(self):
        """images/ 안에 두면 scene*.png를 훑는 다른 단계가 착각한다."""

        self.assertFalse(
            studio_regeneration.BEFORE_DIRNAME.startswith("images"),
        )


class TestRegenerationView(unittest.TestCase):
    """엔진이 남긴 것을 화면이 읽을 모양으로."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _build(self, log=None, report=None):
        return _Project(self._tmp.name, log=log, report=report).path

    def test_no_log_means_never_run(self):
        path = self._build(report=_report([(1, 90, False, None)]))

        view = studio_regeneration.regeneration_view(path)

        self.assertFalse(view["has_run"])
        self.assertEqual(view["cycles"], [])

    def test_the_decision_log_is_exposed(self):
        path = self._build(log=_log(),
                           report=_report([(2, 80, False, None)]))

        view = studio_regeneration.regeneration_view(path)

        self.assertTrue(view["has_run"])
        self.assertEqual(view["stop_reason"], "no_improvement")
        self.assertTrue(view["stop_explanation"])
        self.assertEqual(view["total_image_calls"], 1)
        self.assertEqual(view["max_image_calls"], 6)
        self.assertTrue(view["rendered"])

    def test_budget_remaining_is_reported(self):
        path = self._build(log=_log(total_image_calls=4),
                           report=_report([(2, 80, False, None)]))

        view = studio_regeneration.regeneration_view(path)

        self.assertEqual(view["budget_remaining"], 2)

    def test_rollback_is_surfaced_per_scene(self):
        path = self._build(
            log=_log(cycles=[{
                "cycle": 1, "targeted": [2], "dropped_for_budget": [],
                "succeeded": [2], "failed": [], "rolled_back": [2],
                "quality_before": 80.0, "quality_after": 60.0,
                "quality_delta": -20.0, "spent": 1,
            }], stop_reason="regressed", rendered=False),
            report=_report([(2, 40, True, "여전히 나쁨")]),
        )

        view = studio_regeneration.regeneration_view(path)

        self.assertEqual(view["rolled_back_scenes"], [2])
        self.assertEqual(view["stop_reason"], "regressed")

    def test_retry_counts_come_from_the_report(self):
        path = self._build(
            log=_log(),
            report=_report(
                [(2, 80, False, None)],
                regeneration=[{
                    "scene": 2,
                    "regeneration": {
                        "retry_count": 2, "final_status": "passed",
                        "retry_history": [
                            {"attempt": 1, "outcome": "rolled_back",
                             "reason": "되돌림", "timestamp": "t"},
                            {"attempt": 2, "outcome": "success",
                             "reason": None, "timestamp": "t"},
                        ],
                    },
                }],
            ),
        )

        view = studio_regeneration.regeneration_view(path)
        scene = view["scenes"][2]

        self.assertEqual(scene["retry_count"], 2)
        self.assertEqual(scene["final_status"], "passed")
        self.assertEqual(len(scene["history"]), 2)
        self.assertTrue(scene["was_rolled_back"])

    def test_a_scene_never_regenerated_has_zero_retries(self):
        path = self._build(log=_log(),
                           report=_report([(1, 90, False, None)]))

        view = studio_regeneration.regeneration_view(path)

        self.assertEqual(view["scenes"], {})


class TestOrchestrationDoesNotReimplementTheEngine(unittest.TestCase):
    """이 Epic의 수용 기준."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = _Project(
            self._tmp.name,
            report=_report([(2, 40, True, "프롬프트와 다름")]),
        )

    def test_regeneration_goes_through_the_existing_engine(self):
        with patch.object(
            studio_regeneration, "regeneration_service",
        ) as engine:
            studio_regeneration.regenerate(self.project.path, [2])

        engine.run.assert_called_once()
        _, kwargs = engine.run.call_args
        self.assertEqual(kwargs["only_scenes"], [2])

    def test_the_before_snapshot_happens_first(self):
        order = []

        with patch.object(
            studio_regeneration, "snapshot_before",
            side_effect=lambda *a, **k: order.append("snapshot"),
        ), patch.object(studio_regeneration, "regeneration_service") as engine:
            engine.run.side_effect = lambda *a, **k: order.append("engine")
            studio_regeneration.regenerate(self.project.path, [2])

        self.assertEqual(order, ["snapshot", "engine"])

    def test_regenerating_everything_passes_no_filter(self):
        """"실패 scene 전부"는 필터 없이 엔진에게 맡긴다 - 무엇이
        대상인지는 엔진이 이미 안다."""

        with patch.object(
            studio_regeneration, "regeneration_service",
        ) as engine:
            studio_regeneration.regenerate(self.project.path, None)

        _, kwargs = engine.run.call_args
        self.assertIsNone(kwargs["only_scenes"])

    def test_the_module_imports_nothing_it_could_duplicate(self):
        """원문 문자열을 훑으면 주석까지 걸린다 - 실제로 이 테스트가
        "generate_image는 원본을 덮어쓴다"는 설명 주석에 걸렸다.

        확인해야 할 것은 이 모듈이 엔진의 결정 도구를 손에 쥐고
        있느냐다. 정책이나 이미지 생성기를 import하지 않으면 그것들을
        다시 구현할 수도 없다.
        """

        import ast

        source = open(studio_regeneration.__file__, encoding="utf-8").read()
        tree = ast.parse(source)

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported.add(f"{node.module}.{alias.name}")

        for forbidden in ("app.services.regeneration_policy",
                          "app.services.image_service",
                          "app.services.regeneration_policy.policy"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, imported)

        for name in imported:
            with self.subTest(name=name):
                self.assertNotIn("image_service", name)
                self.assertNotIn("regeneration_policy", name)

    def test_the_module_defines_no_engine_constants(self):
        """예산이나 재시도 한도를 여기서 다시 정의하면, 엔진과 화면이
        서로 다른 숫자를 믿는 날이 온다."""

        for attribute in ("QUALITY_MAX_RETRY", "REGENERATION_MAX_IMAGE_CALLS",
                          "MIN_IMPROVEMENT", "STOCK_PROVIDERS"):
            with self.subTest(attribute=attribute):
                self.assertFalse(hasattr(studio_regeneration, attribute))


class TestBeforeMediaIsServable(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = _Project(self._tmp.name)
        studio_regeneration.snapshot_before(self.project.path, [2])

    def test_a_before_image_resolves(self):
        path = studio_service.media_path(self.project.path, "before", 2)

        self.assertTrue(path.endswith("scene2.png"))

    def test_a_non_numeric_before_scene_is_rejected(self):
        with self.assertRaises(ValueError):
            studio_service.media_path(self.project.path, "before", "../x")

    def test_a_missing_before_image_is_not_found(self):
        with self.assertRaises(FileNotFoundError):
            studio_service.media_path(self.project.path, "before", 1)


if __name__ == "__main__":
    unittest.main()
