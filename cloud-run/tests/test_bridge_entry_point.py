"""AI Bridge 진입점 감싸개.

이 제품의 진입점은 **영상 한 편을 만드는 일 전체**이고 그 마지막이 업로드다.
그래서 여기 테스트가 지키는 것은 기능이 아니라 **부르지 않음**이다:

* 배송 기본값에서 파이프라인 호출이 **0**
* 파이프라인을 import 하지 않고 주입받는다(import 만으로 77줄이 필요해진다)
* `topic`/`project_path`/`channel` 을 **지어내지 않는다**
* `ai_bridge` 를 import 하지 않는다
"""

import ast
import importlib.util
import os
import unittest

CLOUD_RUN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(CLOUD_RUN, "app", "bridge", "entry_point.py")

# ⚠ **파일 경로로 직접 불러온다** -- `from app.bridge import …` 로 부르면
# `app/__init__.py` 가 먼저 돌고 그것이 `dotenv` 를 부른다. 감싸개는 제품
# 의존성을 하나도 쓰지 않으므로 그것 없이 불릴 수 있어야 하고, 이렇게 부르는
# 것 자체가 그 사실의 증명이다. (이 환경에는 제품 의존성이 설치되어 있지
# 않아 나머지 스위트 228 파일은 원래 돌지 않는다 -- 이 감싸개와 무관한
# 기존 상태다.)
_spec = importlib.util.spec_from_file_location("_bridge_entry_point", SOURCE)
entry_point_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entry_point_module)

STATUS_BLOCKED = entry_point_module.STATUS_BLOCKED
STATUS_FAILED = entry_point_module.STATUS_FAILED
STATUS_NEVER_RAN = entry_point_module.STATUS_NEVER_RAN
STATUS_SUCCEEDED = entry_point_module.STATUS_SUCCEEDED
VideoEntryPoint = entry_point_module.VideoEntryPoint
VideoRequest = entry_point_module.VideoRequest

TOPIC = "혈관을 청소하는 아침 습관"
PROJECT = "/tmp/a-project"
CHANNEL = "wellbeing"


class _RecordingPipeline:
    """진짜 `run_pipeline` 자리에 서는 대역. **아무것도 만들지 않는다.**"""

    def __init__(self, answer=None, boom=None):
        self.calls = []
        self._answer = answer if answer is not None else {"title": "만든 척"}
        self._boom = boom

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self._boom is not None:
            raise self._boom
        return self._answer


def _request(**overrides):
    values = {"topic": TOPIC, "project_path": PROJECT, "channel": CHANNEL}
    values.update(overrides)
    return VideoRequest(**values)


def _source_tree():
    with open(SOURCE, encoding="utf-8") as handle:
        return ast.parse(handle.read())


def _imports():
    found = set()
    for node in ast.walk(_source_tree()):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


class FlagTest(unittest.TestCase):
    def test_the_shipped_default_is_off(self):
        self.assertIs(entry_point_module.ENABLE_REAL_VIDEO_PIPELINE, False)

    def test_with_the_flag_off_the_pipeline_is_never_called(self):
        """**이 파일의 중심 증명.** 부를 수 있는 것과 불러도 되는 것은 다르다."""
        pipeline = _RecordingPipeline()

        result = VideoEntryPoint(pipeline=pipeline).execute(_request())

        self.assertEqual(result.status, STATUS_NEVER_RAN)
        self.assertEqual(pipeline.calls, [])
        self.assertIsNone(result.value)

    def test_nothing_in_this_module_turns_the_flag_on(self):
        for node in ast.walk(_source_tree()):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "ENABLE_REAL_VIDEO_PIPELINE"
                    ):
                        self.assertIs(node.value.value, False)


class InjectionTest(unittest.TestCase):
    def setUp(self):
        self._saved = entry_point_module.ENABLE_REAL_VIDEO_PIPELINE
        entry_point_module.ENABLE_REAL_VIDEO_PIPELINE = True

    def tearDown(self):
        entry_point_module.ENABLE_REAL_VIDEO_PIPELINE = self._saved

    def test_without_an_injected_pipeline_it_refuses(self):
        result = VideoEntryPoint().execute(_request())

        self.assertEqual(result.status, STATUS_BLOCKED)

    def test_it_passes_exactly_what_was_declared(self):
        pipeline = _RecordingPipeline()

        result = VideoEntryPoint(pipeline=pipeline).execute(_request())

        self.assertEqual(result.status, STATUS_SUCCEEDED)
        self.assertEqual(
            pipeline.calls,
            [{"topic": TOPIC, "project_path": PROJECT, "channel": CHANNEL}],
        )
        self.assertEqual(result.value, {"title": "만든 척"})

    def test_a_missing_value_is_refused_not_guessed(self):
        """`project_path` 를 추측하면 남의 폴더에 쓰고, `channel` 을 추측하면
        엉뚱한 채널로 올라간다."""
        for field in ("topic", "project_path", "channel"):
            with self.subTest(field=field):
                pipeline = _RecordingPipeline()

                result = VideoEntryPoint(pipeline=pipeline).execute(
                    _request(**{field: "   "})
                )

                self.assertEqual(result.status, STATUS_BLOCKED)
                self.assertEqual(pipeline.calls, [])

    def test_a_foreign_request_raises_instead_of_being_folded(self):
        with self.assertRaises(TypeError):
            VideoEntryPoint(pipeline=_RecordingPipeline()).execute(
                {"topic": TOPIC, "project_path": PROJECT, "channel": CHANNEL}
            )

    def test_a_failing_pipeline_is_recorded_not_swallowed(self):
        pipeline = _RecordingPipeline(boom=RuntimeError("TTS 자격증명이 없다"))

        result = VideoEntryPoint(pipeline=pipeline).execute(_request())

        self.assertEqual(result.status, STATUS_FAILED)
        self.assertIn("TTS 자격증명이 없다", result.reasons[0])

    def test_it_satisfies_the_contract_structurally(self):
        self.assertTrue(callable(getattr(VideoEntryPoint(), "execute", None)))

    def test_it_loaded_with_no_product_dependency_at_all(self):
        """이 파일이 여기까지 온 것 자체가 증명이다 -- `dotenv` 도 `moviepy` 도
        설치되어 있지 않은 인터프리터에서 감싸개가 불렸다."""
        self.assertIsNone(importlib.util.find_spec("dotenv"))
        self.assertTrue(callable(VideoEntryPoint().execute))


class BoundaryTest(unittest.TestCase):
    def test_it_never_imports_ai_bridge(self):
        self.assertFalse(
            [one for one in _imports() if one.split(".")[0] == "ai_bridge"],
            _imports(),
        )

    def test_it_never_imports_the_pipeline_or_the_uploader(self):
        """import 만으로 requirements 77줄이 필요해진다 -- 그래서 주입받는다."""
        forbidden = ("app.pipeline", "app.services", "app.main", "moviepy", "google")
        for one in _imports():
            self.assertFalse(
                any(one == bad or one.startswith(bad + ".") for bad in forbidden),
                one,
            )

    def test_the_word_upload_appears_only_in_prose(self):
        """업로드를 **부르는** 코드가 없다는 것을 이름 검색이 아니라 AST 로 본다."""
        called = set()
        for node in ast.walk(_source_tree()):
            if isinstance(node, ast.Call):
                target = node.func
                name = (
                    target.attr
                    if isinstance(target, ast.Attribute)
                    else getattr(target, "id", "")
                )
                called.add(name)
        self.assertFalse([one for one in called if "upload" in one.lower()], called)


if __name__ == "__main__":
    unittest.main()
