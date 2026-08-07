"""
Sprint126 - 고른 Provider를 파이프라인까지 잇는다 (Epic 56, Phase 3).

Sprint125에서 ElevenLabs는 실제로 부를 수 있게 됐지만, 화면에서 고른
것이 파이프라인까지 가지는 못했다. 파이프라인은 TTS_PROVIDER 환경변수만
보고 있었다.

환경변수는 쓰지 않는다
----------------------
studio_jobs는 파이프라인을 스레드로 돌린다. 전역 설정을 잠깐 바꾸는
방법은 두 작업이 겹치는 순간 서로의 설정을 덮어쓴다. 그래서 고른 것을
프로젝트에 적는다 - project.json은 Resolver들이 이미 voice_source를
읽는 그 파일이고, 사람이 내린 결정만 저장한다는 Sprint84의 원칙과도
같다.

    project.json  {"voice_provider": "elevenlabs"}
      -> scene_tts_service가 그 프로젝트를 만들 때 읽는다
      -> tts_provider.generate_voice(provider="elevenlabs")

파이프라인도 Resolver도 step01~07도 바뀌지 않는다. 프로젝트를 아는
자리(scene_tts_service)가 프로젝트의 결정을 읽을 뿐이다.

"current"는 고르지 않은 것과 같다
---------------------------------
기존 동작을 100% 지키려면 "아무것도 고르지 않았다"가 확실히 예전
경로여야 한다. 그래서 current는 None으로 접히고, None이면
tts_provider가 예전처럼 TTS_PROVIDER를 읽는다.

이번 스프린트에서 실제로 도는 것은 음성뿐이다. 나머지 세 단계는
같은 방식으로 적히기만 하고 아직 아무도 읽지 않는다 - 읽는 척하지
않으려고 테스트로 그 사실을 적어 둔다.
"""

import ast
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

from app.services import provider_selection

SCENES = [
    {"scene": n, "narration": f"{n}번 문장입니다"} for n in range(1, 4)
]


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name
        os.makedirs(os.path.join(self.project, "audio", "scenes"))

    def _write(self, payload):
        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump(payload, f)

    def _read(self):
        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            return json.load(f)


class TestTheSelectionLivesOnTheProject(_Case):

    def test_nothing_chosen_reads_as_nothing(self):
        self.assertIsNone(provider_selection.selected(self.project, "voice"))

    def test_a_saved_choice_comes_back(self):
        provider_selection.save(self.project, {"voice": "elevenlabs"})

        self.assertEqual(
            provider_selection.selected(self.project, "voice"), "elevenlabs")

    def test_current_means_the_same_as_nothing(self):
        """기존 동작 100% - 고르지 않은 것과 같아야 한다."""

        provider_selection.save(self.project, {"voice": "current"})

        self.assertIsNone(provider_selection.selected(self.project, "voice"))

    def test_it_keeps_what_was_already_in_the_file(self):
        self._write({"project_id": "p", "topic": "주제",
                     "voice_source": "import"})

        provider_selection.save(self.project, {"voice": "elevenlabs"})

        saved = self._read()
        self.assertEqual(saved["topic"], "주제")
        self.assertEqual(saved["voice_source"], "import")
        self.assertEqual(saved["voice_provider"], "elevenlabs")

    def test_an_unknown_stage_is_refused(self):
        with self.assertRaises(ValueError):
            provider_selection.save(self.project, {"저녁": "elevenlabs"})

    def test_a_broken_project_file_is_not_an_error_to_read(self):
        with open(os.path.join(self.project, "project.json"), "w") as f:
            f.write("{not json")

        self.assertIsNone(provider_selection.selected(self.project, "voice"))

    def test_the_four_stages_have_a_field_each(self):
        self.assertEqual(
            sorted(provider_selection.FIELDS),
            ["image", "metadata", "script", "voice"],
        )

    def test_the_field_names_do_not_collide_with_the_source_fields(self):
        """Resolver가 읽는 image_source와 섞이면 안 된다."""

        from app.steps import (
            step01_script_resolve, step02_asset_resolve, step03_voice_resolve,
        )

        used = {
            step01_script_resolve.SOURCE_FIELD,
            step02_asset_resolve.SOURCE_FIELD,
            step03_voice_resolve.SOURCE_FIELD,
        }

        self.assertEqual(used & set(provider_selection.FIELDS.values()), set())

    def test_it_writes_nothing_when_only_reading(self):
        before = sorted(os.listdir(self.project))

        provider_selection.selected(self.project, "voice")

        self.assertEqual(sorted(os.listdir(self.project)), before)


class TestTheVoiceEngineFollowsIt(_Case):
    """실제로 도는 것은 음성뿐이다."""

    def _run(self):
        from app.providers import tts_provider
        from app.services import scene_tts_service

        seen = []

        def fake_voice(text, output_file, provider=None):
            seen.append(provider)
            with open(output_file, "wb") as f:
                f.write(b"RIFF____WAVEfmt ")
            return output_file

        with patch.object(tts_provider, "generate_voice", fake_voice):
            scene_tts_service.create_scene_tts(SCENES, self.project)

        return seen

    def test_without_a_choice_it_asks_for_nothing(self):
        """예전 그대로 - tts_provider가 환경변수를 읽는다."""

        self.assertEqual(self._run(), [None, None, None])

    def test_with_a_choice_it_asks_for_that_one(self):
        provider_selection.save(self.project, {"voice": "elevenlabs"})

        self.assertEqual(self._run(), ["elevenlabs"] * 3)

    def test_choosing_current_goes_back_to_the_old_path(self):
        provider_selection.save(self.project, {"voice": "current"})

        self.assertEqual(self._run(), [None, None, None])

    def test_google_can_be_asked_for_explicitly(self):
        provider_selection.save(self.project, {"voice": "google"})

        self.assertEqual(self._run(), ["google"] * 3)

    def test_an_explicit_argument_still_wins(self):
        from app.providers import tts_provider
        from app.services import scene_tts_service

        provider_selection.save(self.project, {"voice": "elevenlabs"})
        seen = []

        def fake_voice(text, output_file, provider=None):
            seen.append(provider)
            with open(output_file, "wb") as f:
                f.write(b"x")
            return output_file

        with patch.object(tts_provider, "generate_voice", fake_voice):
            scene_tts_service.create_scene_tts(
                SCENES, self.project, provider="google")

        self.assertEqual(seen, ["google"] * 3)


class TestTheReviewRegenerationFollowsItToo(_Case):

    def _script(self):
        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": SCENES}, f, ensure_ascii=False)

    def test_it_asks_for_the_chosen_one(self):
        from app.services import studio_review

        self._script()
        provider_selection.save(self.project, {"voice": "elevenlabs"})
        seen = []

        with patch.object(studio_review, "generate_voice",
                          side_effect=lambda t, p, provider=None:
                              seen.append(provider)):
            studio_review.regenerate_voice(self.project, 2)

        self.assertEqual(seen, ["elevenlabs"])

    def test_without_a_choice_it_is_the_old_call(self):
        from app.services import studio_review

        self._script()
        seen = []

        with patch.object(studio_review, "generate_voice",
                          side_effect=lambda t, p, provider=None:
                              seen.append(provider)):
            studio_review.regenerate_voice(self.project, 2)

        self.assertEqual(seen, [None])


class TestTheOtherThreeAreInterfaceOnly(_Case):
    """읽는 척하지 않는다."""

    def test_they_can_be_saved(self):
        provider_selection.save(self.project, {
            "script": "claude", "image": "flux", "metadata": "current"})

        self.assertEqual(
            provider_selection.selected(self.project, "script"), "claude")
        self.assertEqual(
            provider_selection.selected(self.project, "image"), "flux")

    def test_the_fields_are_never_read_by_name(self):
        """Sprint127~130이 셋 다 이었지만, 읽는 것은 언제나
        provider_selection.selected(stage)를 거친다 - 칸 이름을 여기저기
        적어 두면 이름이 바뀔 때 한쪽만 바뀐다."""

        import pathlib

        # 설명문에 이름이 나오는 것은 상관없다. 코드가 그 문자열을
        # 값으로 쓰는지만 본다 - 산문을 뒤지면 설명을 지워야 통과하는
        # 테스트가 된다.
        fields = set(provider_selection.FIELDS.values())
        root = pathlib.Path(provider_selection.__file__).parent.parent
        readers = []

        for path in root.rglob("*.py"):
            if "__pycache__" in str(path) or path.name == "provider_selection.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant)
                        and isinstance(node.value, str)
                        and node.value in fields):
                    readers.append(path.name)

        self.assertEqual(sorted(set(readers)), [])


class TestNothingGlobalWasTouched(unittest.TestCase):

    def test_nobody_mutates_the_environment(self):
        import pathlib

        from app.services import scene_tts_service

        for module in (provider_selection, scene_tts_service):
            tree = ast.parse(open(module.__file__, encoding="utf-8").read())
            called = {
                node.func.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
            }
            with self.subTest(module=module.__name__):
                self.assertNotIn("putenv", called)
                self.assertNotIn("setdefault", called)

    def test_the_pipeline_did_not_change(self):
        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        self.assertNotIn("provider_selection", source)
        self.assertNotIn("elevenlabs", source)

    def test_the_resolvers_did_not_change(self):
        from app.steps import (
            step01_script_resolve, step02_asset_resolve, step03_voice_resolve,
        )

        for module in (step01_script_resolve, step02_asset_resolve,
                       step03_voice_resolve):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("provider_selection", source)
                self.assertNotIn("elevenlabs", source)

    def test_the_engine_steps_did_not_change(self):
        from app.steps import step03_tts

        source = open(step03_tts.__file__, encoding="utf-8").read()

        self.assertNotIn("provider", source)

    def test_google_is_untouched(self):
        from app.providers import google_tts_provider

        source = open(google_tts_provider.__file__, encoding="utf-8").read()

        self.assertNotIn("provider_selection", source)
        self.assertNotIn("elevenlabs", source)


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

    def test_the_endpoint_saves_it(self):
        response = self.client.put(
            f"/studio/api/review/{self.pid}/providers",
            json={"providers": {"voice": "elevenlabs"}},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["providers"]["voice"], "elevenlabs")

    def test_an_unknown_provider_is_refused(self):
        response = self.client.put(
            f"/studio/api/review/{self.pid}/providers",
            json={"providers": {"voice": "그런거없음"}},
        )

        self.assertEqual(response.status_code, 400)

    def test_the_state_reports_what_is_chosen(self):
        self.client.put(
            f"/studio/api/review/{self.pid}/providers",
            json={"providers": {"voice": "elevenlabs"}},
        )

        state = self.client.get(f"/studio/api/review/{self.pid}").json()

        self.assertEqual(state["providers"]["voice"], "elevenlabs")

    def test_nothing_chosen_reports_current(self):
        state = self.client.get(f"/studio/api/review/{self.pid}").json()

        self.assertEqual(state["providers"]["voice"], "current")


if __name__ == "__main__":
    unittest.main()
