"""
Sprint129 - 고른 Metadata Provider를 생성 지점까지 잇는다 (Epic 56, Phase 6).

Sprint126(음성)·127(이미지)·128(대본)이 놓은 다리를 메타데이터에도
놓는다. 방식은 같다 - 환경변수를 쓰지 않고 프로젝트에 적고, 프로젝트를
아는 자리가 읽는다.

metadata_service.generate_publish_package(project_path)는 이미
project.json을 읽고 있다(topic을 거기서 가져온다). 그래서 읽는 자리를
새로 만들 필요가 없었다.

manual이 무엇인가
-----------------
앞의 셋과 다르다. 대본·이미지·음성의 gemini·flux·elevenlabs는 "아직
안 붙은 자리"였지만, 메타데이터의 manual은 이미 뜻이 정해져 있다 -
사람이 직접 쓴다는 것이고, 그러면 엔진이 만들지 않는 것이 맞다.

없는 엔진을 새로 만들지 않는다. manual은 publish_package.json을
사람이 놓아 두는 경로이고, 코드가 할 일은 그것을 덮어쓰지 않는
것뿐이다.

    current  기존 엔진이 script.json을 읽어 만든다(한 글자도 안 바뀜)
    manual   만들지 않는다. 놓여 있으면 그대로 쓰고, 없으면 없는 대로

없는 대로 두어도 되는 이유는 업로드가 publish_package.json이 없으면
script.json의 제목으로 돌아가기 때문이다(Sprint91~93).
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

from app.services import metadata_service, provider_selection
from app.services.provider_selection import ProviderNotWired

ALLOWED = ("current", "manual")

SCRIPT = {
    "title": "저녁 10분 걷기",
    "hook": "훅",
    "scenes": [
        {"scene": n, "narration": f"{n}번 문장입니다", "image_prompt": "p"}
        for n in range(1, 4)
    ],
}


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump(SCRIPT, f, ensure_ascii=False)

    def _package_path(self):
        return os.path.join(self.project, metadata_service.PACKAGE_FILENAME)

    def _write_package(self, payload):
        with open(self._package_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)


class TestTheSelectionIsStored(_Case):

    def test_both_allowed_values_can_be_saved(self):
        for name in ALLOWED:
            with self.subTest(name=name):
                provider_selection.save(self.project, {"metadata": name})
                self.assertEqual(
                    provider_selection.all_selected(self.project)["metadata"],
                    name,
                )

    def test_current_folds_to_nothing(self):
        provider_selection.save(self.project, {"metadata": "current"})

        self.assertIsNone(
            provider_selection.selected(self.project, "metadata"))

    def test_it_does_not_touch_a_source_field(self):
        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"topic": "주제", "metadata_source": "manual"}, f)

        provider_selection.save(self.project, {"metadata": "manual"})

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["metadata_source"], "manual")
        self.assertEqual(saved["metadata_provider"], "manual")
        self.assertEqual(saved["topic"], "주제")


class TestWhatIsWiredForMetadata(unittest.TestCase):
    """앞의 셋과 다르다 - manual은 이미 뜻이 정해져 있다."""

    def test_manual_is_wired(self):
        self.assertEqual(provider_selection.WIRED["metadata"], ("manual",))

        provider_selection.require_wired("metadata", "manual")

    def test_nothing_chosen_passes(self):
        provider_selection.require_wired("metadata", None)

    def test_an_unwired_name_is_still_refused(self):
        with self.assertRaises(ProviderNotWired):
            provider_selection.require_wired("metadata", "gemini")


class TestTheNameReachesTheGenerator(_Case):

    def _run(self, times=1):
        seen = []

        def fake(project_path, provider=None):
            seen.append(provider)
            return {"title": "x"}

        with patch.object(metadata_service, "_package_for", fake):
            for _ in range(times):
                metadata_service.generate_publish_package(self.project)

        return seen

    def test_nothing_chosen_delivers_nothing(self):
        self.assertEqual(self._run(), [None])

    def test_current_delivers_nothing_too(self):
        provider_selection.save(self.project, {"metadata": "current"})

        self.assertEqual(self._run(), [None])

    def test_manual_arrives(self):
        provider_selection.save(self.project, {"metadata": "manual"})

        self.assertEqual(self._run(times=3), ["manual"] * 3)

    def test_an_explicit_argument_wins(self):
        provider_selection.save(self.project, {"metadata": "manual"})

        seen = []

        def fake(project_path, provider=None):
            seen.append(provider)
            return None

        with patch.object(metadata_service, "_package_for", fake):
            metadata_service.generate_publish_package(
                self.project, provider="current")

        self.assertEqual(seen, ["current"])


class TestCurrentIsUnchanged(_Case):
    """기존 생성 결과가 한 글자도 달라지면 안 된다."""

    def test_it_still_builds_from_the_script(self):
        with patch.object(metadata_service, "build_package",
                          return_value={"title": "만든 것"}) as build:
            package = metadata_service.generate_publish_package(self.project)

        build.assert_called_once()
        self.assertEqual(package["title"], "만든 것")

    def test_it_still_writes_the_file(self):
        metadata_service.generate_publish_package(self.project)

        self.assertTrue(os.path.exists(self._package_path()))

    def test_the_output_is_identical_with_and_without_the_field(self):
        first = metadata_service.generate_publish_package(self.project)

        provider_selection.save(self.project, {"metadata": "current"})
        second = metadata_service.generate_publish_package(self.project)

        self.assertEqual(first, second)

    def test_no_script_still_makes_nothing(self):
        os.remove(os.path.join(self.project, "script.json"))

        self.assertIsNone(
            metadata_service.generate_publish_package(self.project))

    def test_the_contract_still_accepts_one_argument(self):
        import inspect

        signature = inspect.signature(
            metadata_service.generate_publish_package)

        self.assertEqual(list(signature.parameters),
                         ["project_path", "provider"])
        self.assertIsNone(signature.parameters["provider"].default)


class TestManualDoesNotGenerate(_Case):
    """사람이 직접 쓴다 - 엔진이 덮어쓰지 않는다."""

    def test_it_calls_no_engine(self):
        provider_selection.save(self.project, {"metadata": "manual"})

        with patch.object(metadata_service, "build_package") as build:
            metadata_service.generate_publish_package(self.project)

        build.assert_not_called()

    def test_it_keeps_what_the_person_put_there(self):
        provider_selection.save(self.project, {"metadata": "manual"})
        self._write_package({"title": "사람이 쓴 제목"})

        package = metadata_service.generate_publish_package(self.project)

        self.assertEqual(package["title"], "사람이 쓴 제목")

        with open(self._package_path(), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["title"], "사람이 쓴 제목")

    def test_nothing_there_stays_nothing(self):
        """없는 대로 두어도 된다 - 업로드가 script.json 제목으로
        돌아간다(Sprint91~93)."""

        provider_selection.save(self.project, {"metadata": "manual"})

        self.assertIsNone(
            metadata_service.generate_publish_package(self.project))
        self.assertFalse(os.path.exists(self._package_path()))

    def test_no_new_engine_was_written(self):
        source = open(metadata_service.__file__, encoding="utf-8").read()

        for forbidden in ("genai", "requests", "openai"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class TestThePipelineCarriesIt(_Case):

    def test_the_pipeline_call_is_unchanged(self):
        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        self.assertIn(
            "metadata_service.generate_publish_package(project_path)", source)
        self.assertNotIn("provider_selection", source)

    def test_the_render_path_picks_the_choice_up(self):
        """STEP4는 파이프라인을 그대로 돌린다 - 그 안에서 읽힌다."""

        provider_selection.save(self.project, {"metadata": "manual"})
        seen = []

        def fake(project_path, provider=None):
            seen.append(provider)
            return None

        with patch.object(metadata_service, "_package_for", fake):
            metadata_service.generate_publish_package(self.project)

        self.assertEqual(seen, ["manual"])

    def test_the_review_service_needed_no_change(self):
        from app.services import studio_review

        source = open(studio_review.__file__, encoding="utf-8").read()

        self.assertNotIn("metadata_provider", source)


class TestThreadsDoNotMix(unittest.TestCase):

    def test_two_projects_at_once_keep_their_own(self):
        seen = {}
        lock = threading.Lock()
        chosen = ("current", "manual")
        tmps = [tempfile.TemporaryDirectory() for _ in chosen]
        self.addCleanup(lambda: [t.cleanup() for t in tmps])

        for tmp, name in zip(tmps, chosen):
            with open(os.path.join(tmp.name, "script.json"), "w",
                      encoding="utf-8") as f:
                json.dump(SCRIPT, f, ensure_ascii=False)
            provider_selection.save(tmp.name, {"metadata": name})

        def fake(project_path, provider=None):
            with lock:
                seen.setdefault(project_path, []).append(provider)
            return None

        def run(project):
            for _ in range(3):
                metadata_service.generate_publish_package(project)

        with patch.object(metadata_service, "_package_for", fake):
            threads = [threading.Thread(target=run, args=(t.name,))
                       for t in tmps]
            [t.start() for t in threads]
            [t.join() for t in threads]

        self.assertEqual(seen[tmps[0].name], [None] * 3)
        self.assertEqual(seen[tmps[1].name], ["manual"] * 3)


class TestNothingGlobalOrStructuralMoved(unittest.TestCase):

    def test_no_environment_variable_is_used(self):
        source = open(metadata_service.__file__, encoding="utf-8").read()

        self.assertNotIn("METADATA_PROVIDER", source)
        self.assertNotIn("putenv", source)
        self.assertNotIn("getenv", source)

    def test_no_metadata_resolver_was_created(self):
        import pathlib

        from app.steps import step01_script_resolve

        steps = pathlib.Path(step01_script_resolve.__file__).parent

        self.assertEqual(
            sorted(p.name for p in steps.glob("*_resolve.py")),
            ["step01_script_resolve.py", "step02_asset_resolve.py",
             "step03_voice_resolve.py"],
        )

    def test_the_engine_steps_are_untouched(self):
        from app.steps import (
            step01_script, step02_assets, step03_tts, step04_subtitle,
            step05_video, step06_thumbnail, step07_quality,
        )

        for module in (step02_assets, step03_tts, step04_subtitle,
                       step05_video, step06_thumbnail, step07_quality):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("metadata_provider", source)

        source = open(step01_script.__file__, encoding="utf-8").read()
        self.assertNotIn("metadata", source)

    def test_every_stage_now_has_a_bridge(self):
        """네 단계 모두 같은 방식으로 전달된다."""

        self.assertEqual(
            sorted(provider_selection.FIELDS),
            ["image", "metadata", "script", "voice"],
        )


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

    def test_both_values_are_accepted(self):
        for name in ALLOWED:
            with self.subTest(name=name):
                response = self.client.put(
                    f"/studio/api/review/{self.pid}/providers",
                    json={"providers": {"metadata": name}},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json()["providers"]["metadata"], name)

    def test_the_state_reports_it(self):
        self.client.put(
            f"/studio/api/review/{self.pid}/providers",
            json={"providers": {"metadata": "manual"}},
        )

        state = self.client.get(f"/studio/api/review/{self.pid}").json()

        self.assertEqual(state["providers"]["metadata"], "manual")


if __name__ == "__main__":
    unittest.main()
