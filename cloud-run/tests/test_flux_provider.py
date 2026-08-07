"""
Sprint130 - FLUX를 실제로 붙인다 (Epic 56, Phase 7).

Sprint127이 놓은 다리에 처음으로 실제 Provider가 도착한다. 지금까지
image_provider는 이름만 날랐고 도착지에서 전부 거절했다.

current를 대체하지 않는다
-------------------------
current는 Best-of-N · 품질 게이트 · Pexels 폴백 · 재시도까지 붙은
엔진 전체다. FLUX는 이미지 한 장을 만드는 Provider다. 둘은 같은
것이 아니고, provider=None이면 예전 경로가 한 글자도 다르지 않게
돈다.

폴백에 대해
-----------
Imagen이 실패하면 Pexels로 넘어가는 것은 current 엔진의 성질이다.
사용자가 FLUX를 골랐는데 실패했다고 스톡 사진을 주면 조용히 틀린
결과가 된다. 그래서 고른 Provider가 있으면 폴백하지 않고 실패를
그대로 내보낸다.

출력 계약
---------
step02 뒤가 차이를 몰라야 한다. 파일은 scene{N}.png, scene에 붙는
키는 asset_path · asset_type · provider · confidence로 같다. AI가
프롬프트로 만든 것이므로 confidence는 ai_image와 같은 1.0이다 -
스톡의 0.8은 "검색으로 찾은 것"이라는 뜻이라 맞지 않는다.

후처리도 같은 것을 거친다. 현재 엔진은 생성한 이미지마다
image_service.enhance_image를 부르므로 FLUX 결과만 건너뛰면 같은
프로젝트 안에서 그림의 성격이 갈린다.

검증하지 못한 것 - 정직하게 적어 둔다
-------------------------------------
FLUX API 키가 없어 실제 왕복을 확인하지 못했다. 아래 테스트는 HTTP
계층을 세우고 그 위를 전부 진짜로 돌린다. 엔드포인트 모양이 실제와
다를 수 있으므로 주소·모델은 환경변수로 바꿀 수 있게 두었다.
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

from app.providers import flux_provider
from app.services import provider_selection
from app.services.provider_selection import ProviderNotWired

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

CONFIGURED = {"FLUX_API_KEY": "key-123"}


class _Transport:
    """FLUX가 돌려줄 법한 응답. 제출 -> 폴링 -> 내려받기."""

    def __init__(self, ready_after=1, status_code=200):
        self.ready_after = ready_after
        self.status_code = status_code
        self.polls = 0
        self.submitted = []
        self.downloaded = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.submitted.append({"url": url, "body": json,
                               "key": (headers or {}).get("x-key")})
        return _Response(self.status_code, {"id": "job-1"})

    def get(self, url, headers=None, params=None, timeout=None):
        if "get_result" in url:
            self.polls += 1
            if self.polls >= self.ready_after:
                return _Response(200, {
                    "status": "Ready",
                    "result": {"sample": "https://example.test/out.png"},
                })
            return _Response(200, {"status": "Pending"})

        self.downloaded.append(url)
        return _Response(200, None, content=PNG)


class _Response:

    def __init__(self, status_code, payload, content=b""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        return self._payload


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name
        os.makedirs(os.path.join(self.project, "images"))

    def _scene(self, number=1):
        return {"scene": number, "narration": f"{number}번",
                "image_prompt": "a calm man walking", "visual_type": "ai"}


class TestItIsWiredNow(unittest.TestCase):

    def test_flux_is_the_only_image_provider_that_is_wired(self):
        self.assertEqual(provider_selection.WIRED["image"], ("flux",))

    def test_choosing_flux_passes(self):
        provider_selection.require_wired("image", "flux")

    def test_the_others_are_still_refused(self):
        for name in ("imagen", "gpt_image", "ideogram"):
            with self.subTest(name=name):
                with self.assertRaises(ProviderNotWired):
                    provider_selection.require_wired("image", name)


class TestItRefusesWithoutSettings(_Case):

    def test_no_api_key_is_refused_by_name(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(flux_provider.FluxUnavailable) as caught:
                flux_provider.generate_image(
                    "prompt", os.path.join(self.project, "images", "x.raw"))

        self.assertIn("FLUX_API_KEY", str(caught.exception))

    def test_refusing_writes_nothing(self):
        target = os.path.join(self.project, "images", "x.raw")

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(flux_provider.FluxUnavailable):
                flux_provider.generate_image("prompt", target)

        self.assertFalse(os.path.exists(target))


class TestTheApiCall(_Case):

    def _generate(self, transport=None, env=None):
        transport = transport or _Transport()
        target = os.path.join(self.project, "images", "scene1.raw")

        with patch.dict(os.environ, {**CONFIGURED, **(env or {})}, clear=True):
            with patch.object(flux_provider, "requests", transport):
                with patch.object(flux_provider, "enhance_image") as enhance:
                    path = flux_provider.generate_image("a man", target)

        return path, transport, enhance

    def test_it_sends_the_prompt_with_the_key(self):
        _, transport, _ = self._generate()

        self.assertEqual(len(transport.submitted), 1)
        self.assertEqual(transport.submitted[0]["key"], "key-123")
        self.assertEqual(transport.submitted[0]["body"]["prompt"], "a man")

    def test_it_asks_for_the_shape_the_pipeline_uses(self):
        """세로 영상이다 - 9:16."""

        _, transport, _ = self._generate()

        body = transport.submitted[0]["body"]
        self.assertEqual(body["width"] * 16, body["height"] * 9)

    def test_it_waits_until_the_job_is_ready(self):
        _, transport, _ = self._generate(_Transport(ready_after=3))

        self.assertEqual(transport.polls, 3)

    def test_it_downloads_and_writes_the_image(self):
        path, transport, _ = self._generate()

        self.assertEqual(transport.downloaded, ["https://example.test/out.png"])
        self.assertTrue(os.path.exists(path))
        self.assertEqual(open(path, "rb").read(), PNG)

    def test_it_runs_the_same_post_processing(self):
        """현재 엔진은 생성한 이미지마다 enhance_image를 부른다."""

        path, _, enhance = self._generate()

        enhance.assert_called_once_with(path)

    def test_the_endpoint_and_model_can_be_changed(self):
        """실제 주소를 확인하지 못했으므로 바꿀 수 있어야 한다."""

        _, transport, _ = self._generate(env={
            "FLUX_API_URL": "https://other.test",
            "FLUX_MODEL": "flux-dev",
        })

        self.assertTrue(
            transport.submitted[0]["url"].startswith("https://other.test"))
        self.assertIn("flux-dev", transport.submitted[0]["url"])

    def test_a_rejected_submit_is_an_error(self):
        target = os.path.join(self.project, "images", "scene1.raw")

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(flux_provider, "requests",
                              _Transport(status_code=401)):
                with self.assertRaises(Exception):
                    flux_provider.generate_image("a man", target)

    def test_it_gives_up_instead_of_polling_forever(self):
        source = open(flux_provider.__file__, encoding="utf-8").read()

        self.assertIn("MAX_POLLS", source)


class TestTheOutputContractIsUnchanged(_Case):
    """step02 뒤가 차이를 몰라야 한다."""

    def _integrate(self, number=1):
        from app.services import asset_integration_service

        provider_selection.save(self.project, {"image": "flux"})

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(flux_provider, "requests", _Transport()):
                with patch.object(flux_provider, "enhance_image"):
                    return asset_integration_service.integrate_asset(
                        self._scene(number), self.project, "wellbeing")

    def test_the_file_lands_where_the_engine_puts_it(self):
        self._integrate(2)

        self.assertTrue(os.path.exists(
            os.path.join(self.project, "images", "scene2.png")))

    def test_the_scene_keys_are_the_ones_step02_writes(self):
        enriched = self._integrate(1)

        for key in ("asset_path", "asset_type", "provider", "confidence"):
            with self.subTest(key=key):
                self.assertIn(key, enriched)

    def test_the_provider_says_flux(self):
        enriched = self._integrate(1)

        self.assertEqual(enriched["provider"], "flux")
        self.assertEqual(enriched["asset_type"], "image")

    def test_the_confidence_is_the_ai_one(self):
        """프롬프트로 만든 것이다 - 스톡의 0.8이 아니다."""

        enriched = self._integrate(1)

        self.assertEqual(enriched["confidence"], 1.0)

    def test_the_original_scene_fields_survive(self):
        enriched = self._integrate(1)

        self.assertEqual(enriched["narration"], "1번")
        self.assertEqual(enriched["image_prompt"], "a calm man walking")


class TestCurrentIsUntouched(_Case):

    def test_none_still_runs_best_of_n(self):
        from app.services import asset_integration_service, best_of_n_service

        with patch.object(best_of_n_service, "generate_candidates",
                          return_value=["a"]) as generate:
            with patch.object(best_of_n_service, "select_best",
                              return_value=(0, None)):
                with patch.object(best_of_n_service, "discard_losers"):
                    with patch.object(asset_integration_service, "os"):
                        try:
                            asset_integration_service._ai_result(
                                "p", "s", "wellbeing", False)
                        except Exception:
                            pass

        generate.assert_called_once()

    def test_flux_never_runs_when_nothing_is_chosen(self):
        from app.services import asset_integration_service

        with patch.object(flux_provider, "generate_image") as flux:
            with patch.object(asset_integration_service, "get_candidates",
                              return_value=[]):
                try:
                    asset_integration_service.integrate_asset(
                        self._scene(1), self.project, "wellbeing")
                except Exception:
                    pass

        flux.assert_not_called()

    def test_the_current_engine_files_are_untouched(self):
        from app.services import best_of_n_service, image_service

        for module in (best_of_n_service, image_service):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("flux", source.lower())


class TestTheFallbackDoesNotSubstitute(_Case):
    """FLUX를 골랐는데 스톡 사진이 나오면 안 된다."""

    def test_a_flux_failure_is_not_replaced_by_stock(self):
        from app.services import asset_integration_service

        provider_selection.save(self.project, {"image": "flux"})

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(flux_provider, "generate_image",
                              side_effect=Exception("FLUX 실패")):
                with patch.object(asset_integration_service,
                                  "get_candidates") as candidates:
                    with self.assertRaises(Exception):
                        asset_integration_service.integrate_asset(
                            self._scene(1), self.project, "wellbeing")

        candidates.assert_not_called()

    def test_the_current_engine_still_falls_back(self):
        from app.services import asset_integration_service

        with patch.object(asset_integration_service, "_ai_result",
                          side_effect=Exception("Imagen 실패")):
            with patch.object(asset_integration_service, "get_candidates",
                              return_value=[]) as candidates:
                with self.assertRaises(Exception):
                    asset_integration_service.integrate_asset(
                        self._scene(1), self.project, "wellbeing")

        candidates.assert_called()


class TestTheReviewRegenerationUsesIt(_Case):

    def test_regenerating_one_scene_goes_to_flux(self):
        from app.services import studio_review

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t",
                       "scenes": [self._scene(1), self._scene(2)]},
                      f, ensure_ascii=False)

        provider_selection.save(self.project, {"image": "flux"})
        seen = []

        def fake(prompt, output_file):
            seen.append(os.path.basename(output_file))
            with open(output_file, "wb") as f:
                f.write(PNG)
            return output_file

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(flux_provider, "generate_image", fake):
                studio_review.regenerate_image(self.project, "wellbeing", 2)

        self.assertEqual(seen, ["scene2.raw"])
        self.assertTrue(os.path.exists(
            os.path.join(self.project, "images", "scene2.png")))


class TestThreadsDoNotMix(unittest.TestCase):

    def test_one_project_on_flux_and_one_on_current(self):
        from app.services import asset_integration_service

        seen = {}
        lock = threading.Lock()
        tmps = [tempfile.TemporaryDirectory() for _ in range(2)]
        self.addCleanup(lambda: [t.cleanup() for t in tmps])

        for tmp in tmps:
            os.makedirs(os.path.join(tmp.name, "images"))
        provider_selection.save(tmps[0].name, {"image": "flux"})

        def record(image_prompt, staging_path, channel, is_hook_scene,
                   image_style=None, candidate_count=1, scene=None,
                   provider=None):
            with lock:
                seen.setdefault(os.path.dirname(staging_path), []).append(
                    provider)
            return {"source": "ai_image", "local_path": staging_path,
                    "metadata": {"query": ""}, "candidate_count": 1,
                    "selected_candidate": 0, "selection": None}

        def run(project):
            for number in (1, 2, 3):
                try:
                    asset_integration_service.integrate_asset(
                        {"scene": number, "narration": "n",
                         "image_prompt": "p", "visual_type": "ai"},
                        project, "wellbeing")
                except Exception:
                    pass

        with patch.object(asset_integration_service, "_ai_result", record):
            threads = [threading.Thread(target=run, args=(t.name,))
                       for t in tmps]
            [t.start() for t in threads]
            [t.join() for t in threads]

        self.assertEqual(seen[os.path.join(tmps[0].name, "images")],
                         ["flux"] * 3)
        self.assertEqual(seen[os.path.join(tmps[1].name, "images")],
                         [None] * 3)


class TestNothingElseMoved(unittest.TestCase):

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_no_environment_variable_is_written(self):
        source = open(flux_provider.__file__, encoding="utf-8").read()

        self.assertNotIn("putenv", source)
        self.assertNotIn("environ[", source)

    def test_the_pipeline_and_resolver_are_untouched(self):
        import app.pipeline.pipeline as pipeline
        from app.steps import step02_asset_resolve, step02_assets

        for module in (pipeline, step02_asset_resolve, step02_assets):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("flux", source.lower())

    def test_the_review_workflow_is_untouched(self):
        from app.services import studio_review

        source = open(studio_review.__file__, encoding="utf-8").read()

        self.assertNotIn("flux", source.lower())

    def test_the_other_providers_still_refuse(self):
        from app.production.providers import bootstrap
        from app.production.registry import StageProviderRegistry
        from app.production.stage_provider import ProviderUnavailable
        from app.production.stage_request import StageRequest

        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        for name in ("imagen", "gpt_image", "ideogram"):
            with self.subTest(name=name):
                with self.assertRaises(ProviderUnavailable):
                    registry.get("image", name).generate(StageRequest())


if __name__ == "__main__":
    unittest.main()
