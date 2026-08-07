"""
Sprint127 - 고른 Image Provider를 생성 지점까지 잇는다 (Epic 56, Phase 4).

Sprint126이 음성에 놓은 다리를 이미지에도 놓는다. 방식은 같다 -
환경변수를 쓰지 않고 프로젝트에 적고, 프로젝트를 아는 자리가 읽는다.

    project.json {"image_provider": "flux"}
      -> asset_integration_service.integrate_asset이 읽는다
      -> _ai_result(provider="flux")

_ai_result를 고른 이유는 그 파일이 스스로 "Imagen을 부르는 유일한
지점"이라고 적어 둔 자리이기 때문이다. 다른 Provider가 붙는다면
거기 붙는다.

폴백을 조심해야 한다
--------------------
_select_ai_first는 Imagen이 실패하면 Pexels로 넘어간다. 그 except가
넓어서, 고른 Provider가 없다는 이유의 실패까지 삼키면 사용자는 FLUX를
골랐는데 스톡 사진을 받는다. 그것은 조용히 틀린 결과다. 그래서 "고른
Provider가 없다"는 폴백 대상이 아니라 밖으로 나가야 한다.

되는 척하지 않는다
------------------
이미지 쪽은 아직 붙은 Provider가 하나도 없다. imagen·gpt_image·flux·
ideogram은 Sprint124가 만든 빈 자리다. 그러니 다리는 이름을 끝까지
나르되, 도착지에서 정직하게 거절한다 - current(=고르지 않음)만 실제로
돈다.

특히 "imagen"이 current와 같은 것처럼 굴면 안 된다. 현재 엔진이
imagen-4.0을 쓰는 것은 맞지만, 그것은 파이프라인(Best-of-N·품질
게이트·폴백)을 거치는 경로이고 "imagen"은 모델을 직접 부르는 빈
자리다.
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

from app.services import provider_selection
from app.services.provider_selection import ProviderNotWired

ALLOWED = ("current", "imagen", "gpt_image", "flux", "ideogram")


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name
        os.makedirs(os.path.join(self.project, "images"))

    def _scene(self, number=1, visual_type="ai"):
        return {"scene": number, "narration": f"{number}번",
                "image_prompt": "a man", "visual_type": visual_type}


class TestTheSelectionIsStored(_Case):

    def test_every_allowed_value_can_be_saved(self):
        for name in ALLOWED:
            with self.subTest(name=name):
                provider_selection.save(self.project, {"image": name})
                stored = provider_selection.all_selected(self.project)
                self.assertEqual(stored["image"], name)

    def test_current_folds_to_nothing(self):
        provider_selection.save(self.project, {"image": "current"})

        self.assertIsNone(provider_selection.selected(self.project, "image"))

    def test_it_does_not_touch_the_source_field(self):
        """image_source는 어디서 가져오는가이고 image_provider는
        누가 만드는가다. 섞으면 안 된다."""

        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"image_source": "import"}, f)

        provider_selection.save(self.project, {"image": "flux"})

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["image_source"], "import")
        self.assertEqual(saved["image_provider"], "flux")

    def test_the_resolver_still_reads_only_its_own_field(self):
        from app.steps import step02_asset_resolve

        provider_selection.save(self.project, {"image": "flux"})

        self.assertEqual(
            step02_asset_resolve.detect_source(self.project), "auto")


class TestWhatIsActuallyWired(unittest.TestCase):
    """되는 척하지 않는다."""

    def test_nothing_is_wired_for_images_yet(self):
        self.assertEqual(provider_selection.WIRED["image"], ())

    def test_choosing_nothing_passes(self):
        provider_selection.require_wired("image", None)

    def test_choosing_anything_else_is_refused(self):
        for name in ("imagen", "gpt_image", "flux", "ideogram"):
            with self.subTest(name=name):
                with self.assertRaises(ProviderNotWired) as caught:
                    provider_selection.require_wired("image", name)
                self.assertIn(name, str(caught.exception))

    def test_imagen_is_not_treated_as_current(self):
        """현재 엔진이 imagen-4.0을 쓰지만 그것은 파이프라인을 거치는
        경로다. 같은 것으로 취급하면 지어내는 것이 된다."""

        with self.assertRaises(ProviderNotWired):
            provider_selection.require_wired("image", "imagen")

    def test_voice_defers_to_the_engine_that_knows(self):
        from app.providers import tts_provider

        self.assertEqual(
            tuple(provider_selection.WIRED["voice"]),
            tuple(tts_provider.PROVIDERS),
        )

        for name in tts_provider.PROVIDERS:
            with self.subTest(name=name):
                provider_selection.require_wired("voice", name)


class TestTheNameReachesTheGenerator(_Case):
    """다리가 실제로 이름을 나르는가."""

    def _run(self, visual_type="ai", scenes=3):
        from app.services import asset_integration_service

        seen = []

        def fake_ai(image_prompt, staging_path, channel, is_hook_scene,
                    image_style=None, candidate_count=1, scene=None,
                    provider=None):
            seen.append(provider)
            return {"source": "ai_image", "local_path": staging_path,
                    "asset_type": "image", "selection": None}

        with patch.object(asset_integration_service, "_ai_result", fake_ai):
            with patch.object(asset_integration_service,
                              "download_candidate", return_value="x"):
                for number in range(1, scenes + 1):
                    try:
                        asset_integration_service.integrate_asset(
                            self._scene(number, visual_type),
                            self.project, "wellbeing",
                        )
                    except Exception:
                        pass

        return seen

    def test_nothing_chosen_delivers_nothing(self):
        """기존 경로가 100% 그대로여야 한다."""

        self.assertEqual(self._run(), [None, None, None])

    def test_current_delivers_nothing_too(self):
        provider_selection.save(self.project, {"image": "current"})

        self.assertEqual(self._run(), [None, None, None])

    def test_each_chosen_name_arrives_at_every_scene(self):
        for name in ("imagen", "gpt_image", "flux", "ideogram"):
            with self.subTest(name=name):
                provider_selection.save(self.project, {"image": name})
                self.assertEqual(self._run(), [name] * 3)


class TestTheFallbackDoesNotSwallowIt(_Case):
    """FLUX를 골랐는데 스톡 사진이 나오면 안 된다."""

    def test_a_not_wired_provider_escapes_the_pexels_fallback(self):
        from app.services import asset_integration_service

        provider_selection.save(self.project, {"image": "flux"})

        with patch.object(asset_integration_service,
                          "get_candidates") as candidates:
            with self.assertRaises(ProviderNotWired):
                asset_integration_service.integrate_asset(
                    self._scene(1, "ai"), self.project, "wellbeing",
                )

        candidates.assert_not_called()

    def test_a_real_imagen_failure_still_falls_back(self):
        """엔진이 실패한 것과 Provider가 없는 것은 다른 일이다."""

        from app.services import asset_integration_service

        with patch.object(asset_integration_service, "_ai_result",
                          side_effect=Exception("Imagen 실패")):
            with patch.object(asset_integration_service, "get_candidates",
                              return_value=[]) as candidates:
                with self.assertRaises(Exception):
                    asset_integration_service.integrate_asset(
                        self._scene(1, "ai"), self.project, "wellbeing",
                    )

        candidates.assert_called()


class TestTheReviewRegenerationCarriesItToo(_Case):

    def test_regenerating_one_scene_delivers_the_choice(self):
        from app.services import asset_integration_service, studio_review

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": [self._scene(1), self._scene(2)]},
                      f, ensure_ascii=False)

        provider_selection.save(self.project, {"image": "flux"})
        seen = []

        def fake_ai(image_prompt, staging_path, channel, is_hook_scene,
                    image_style=None, candidate_count=1, scene=None,
                    provider=None):
            seen.append(provider)
            return {"source": "ai_image", "local_path": staging_path,
                    "asset_type": "image", "selection": None}

        with patch.object(asset_integration_service, "_ai_result", fake_ai):
            try:
                studio_review.regenerate_image(self.project, "wellbeing", 2)
            except Exception:
                pass

        self.assertEqual(seen, ["flux"])


class TestThreadsDoNotMix(unittest.TestCase):

    def test_three_projects_at_once_keep_their_own(self):
        from app.services import asset_integration_service

        seen = {}
        lock = threading.Lock()

        def fake_ai(image_prompt, staging_path, channel, is_hook_scene,
                    image_style=None, candidate_count=1, scene=None,
                    provider=None):
            with lock:
                seen.setdefault(os.path.dirname(staging_path), []).append(
                    provider)
            return {"source": "ai_image", "local_path": staging_path,
                    "asset_type": "image", "selection": None}

        chosen = ("imagen", "flux", "gpt_image")
        dirs = []
        tmps = [tempfile.TemporaryDirectory() for _ in chosen]
        self.addCleanup(lambda: [t.cleanup() for t in tmps])

        for tmp, name in zip(tmps, chosen):
            os.makedirs(os.path.join(tmp.name, "images"))
            provider_selection.save(tmp.name, {"image": name})
            dirs.append(tmp.name)

        def run(project):
            for number in (1, 2):
                try:
                    asset_integration_service.integrate_asset(
                        {"scene": number, "narration": "n",
                         "image_prompt": "p", "visual_type": "ai"},
                        project, "wellbeing",
                    )
                except Exception:
                    pass

        with patch.object(asset_integration_service, "_ai_result", fake_ai):
            threads = [threading.Thread(target=run, args=(d,)) for d in dirs]
            [t.start() for t in threads]
            [t.join() for t in threads]

        for project, name in zip(dirs, chosen):
            with self.subTest(provider=name):
                self.assertEqual(
                    seen[os.path.join(project, "images")], [name, name])


class TestNothingGlobalOrStructuralMoved(unittest.TestCase):

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_step02_is_untouched(self):
        """step02 계약을 바꾸지 않는다."""

        import inspect

        from app.steps import step02_assets

        signature = inspect.signature(step02_assets.collect_assets)

        self.assertEqual(
            list(signature.parameters), ["scenes", "project_path", "channel"])

        source = open(step02_assets.__file__, encoding="utf-8").read()
        self.assertNotIn("provider_selection", source)

    def test_the_resolver_is_untouched(self):
        from app.steps import step02_asset_resolve

        source = open(step02_asset_resolve.__file__, encoding="utf-8").read()

        self.assertNotIn("provider_selection", source)
        self.assertNotIn("image_provider", source)

    def test_the_pipeline_is_untouched(self):
        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        self.assertNotIn("provider_selection", source)
        self.assertNotIn("image_provider", source)

    def test_image_service_is_untouched(self):
        from app.services import image_service

        source = open(image_service.__file__, encoding="utf-8").read()

        self.assertNotIn("provider_selection", source)
        self.assertNotIn("provider=", source)

    def test_best_of_n_is_untouched(self):
        from app.services import best_of_n_service

        source = open(best_of_n_service.__file__, encoding="utf-8").read()

        self.assertNotIn("provider_selection", source)

    def test_nobody_mutates_the_environment(self):
        from app.services import asset_integration_service

        tree = ast.parse(open(asset_integration_service.__file__,
                              encoding="utf-8").read())
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        }

        self.assertNotIn("putenv", called)
        self.assertNotIn("setdefault", called)

        source = open(asset_integration_service.__file__,
                      encoding="utf-8").read()
        self.assertNotIn("IMAGE_PROVIDER", source)


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
                    json={"providers": {"image": name}},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["providers"]["image"], name)

    def test_an_unknown_name_is_refused(self):
        response = self.client.put(
            f"/studio/api/review/{self.pid}/providers",
            json={"providers": {"image": "그런거없음"}},
        )

        self.assertEqual(response.status_code, 400)

    def test_the_state_reports_it(self):
        self.client.put(
            f"/studio/api/review/{self.pid}/providers",
            json={"providers": {"image": "flux"}},
        )

        state = self.client.get(f"/studio/api/review/{self.pid}").json()

        self.assertEqual(state["providers"]["image"], "flux")


if __name__ == "__main__":
    unittest.main()
