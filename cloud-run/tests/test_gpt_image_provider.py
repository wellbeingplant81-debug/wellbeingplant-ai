"""
Sprint131 - GPT Image를 실제로 붙인다 (Epic 56, Phase 8).

Sprint130의 FLUX에 이어 두 번째 실제 이미지 Provider다. 다리는 이미
Sprint127에 놓였으므로 이번에 하는 일은 도착지 하나를 더 여는 것뿐이다.

FLUX와 다른 점
--------------
FLUX는 비동기다 - 제출하고, 준비될 때까지 묻고, 받는다. GPT Image는
한 번에 끝난다. 그래서 폴링이 없고, 대신 한 번의 응답을 오래 기다린다.

이미지도 주소가 아니라 응답 안에 base64로 담겨 온다. 내려받을 곳이
없다는 뜻이다.

크기를 고를 수 없다
-------------------
FLUX는 가로·세로를 숫자로 정할 수 있었지만 OpenAI는 정해진 값 중에서만
고른다. 세로 중 가장 큰 것이 1024x1536이고 이것은 2:3이다 - 파이프라인의
9:16이 아니다.

늘어나지는 않는다. kenburns._fit_scale이 1080x1920을 덮는 배율로 키운
뒤 넘치는 만큼 잘라내기 때문이다(cover). 다만 얼마나 잘리는지는 다르다.

    현재 엔진 768x1408 -> 1081x1982   세로 3.1% 잘림
    GPT Image 1024x1536 -> 1281x1922  가로 15.7% 잘림

가로 15.7%는 적지 않다. 인물이 가운데 있지 않으면 팔이나 어깨가
잘릴 수 있다. OpenAI가 세로로 주는 가장 큰 값이라 피할 방법이 없으므로
숨기지 않고 적어 둔다. 크기는 환경변수로 바꿀 수 있다.

current를 대체하지 않는다
-------------------------
current는 Best-of-N · 품질 게이트 · Pexels 폴백 · 재시도까지 붙은 엔진
전체다. GPT Image는 이미지 한 장을 만드는 Provider다. provider=None이면
예전 경로가 한 글자도 다르지 않게 돈다.

검증하지 못한 것 - 정직하게 적어 둔다
-------------------------------------
OPENAI_API_KEY가 없어 실제 왕복을 확인하지 못했다. 아래 테스트는 HTTP
계층만 세우고 그 위(응답 해석 · base64 해제 · 파일 쓰기 · 후처리 ·
출력 계약)를 전부 진짜로 돌린다. 주소·모델·크기는 환경변수로 바꿀 수
있게 두었으므로 실제 모양이 달라도 코드를 고치지 않아도 된다.
"""

import ast
import base64
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

from app.providers import gpt_image_provider
from app.services import provider_selection
from app.services.provider_selection import ProviderNotWired

def _png_bytes():
    """
    진짜로 열리는 PNG. 손으로 적은 상수를 쓰면 후처리를 세우지 않고
    돌려 보는 시험에서 PIL이 열지 못한다.
    """

    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 120, 200)).save(buffer, format="PNG")

    return buffer.getvalue()


PNG = _png_bytes()

CONFIGURED = {"OPENAI_API_KEY": "key-123", "PATH": os.environ.get("PATH", "")}


def _string_constants(path):
    """
    그 파일이 문자열로 '쓰는' 값들. 설명문에 이름이 나오는 것과
    실제로 그 이름을 쓰는 것은 다르다 - 그래서 정확히 같은 값만 본다.
    """

    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


class _Transport:
    """OpenAI가 돌려줄 법한 응답. 한 번에 끝난다 - 폴링이 없다."""

    def __init__(self, status_code=200, payload=None, error=None):
        self.status_code = status_code
        self.requested = []
        self.downloaded = []
        self._error = error
        self._payload = payload if payload is not None else {
            "data": [{"b64_json": base64.b64encode(PNG).decode()}]
        }

    def post(self, url, headers=None, json=None, timeout=None):
        self.requested.append({
            "url": url,
            "body": json,
            "authorization": (headers or {}).get("Authorization"),
            "timeout": timeout,
        })

        if self._error is not None:
            return _Response(self.status_code, self._error)

        return _Response(self.status_code, self._payload)

    def get(self, url, timeout=None):
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

    def _target(self, name="scene1.raw"):
        return os.path.join(self.project, "images", name)


class TestItIsWiredNow(unittest.TestCase):

    def test_gpt_image_is_wired(self):
        provider_selection.require_wired("image", "gpt_image")

    def test_flux_is_still_wired(self):
        """Sprint130이 붙인 것을 건드리지 않았다."""

        provider_selection.require_wired("image", "flux")

    def test_both_are_listed(self):
        """
        둘 다 목록에 있다.

        Sprint150까지는 "정확히 이 둘뿐"이었다. 그 뒤로 local_stock이
        붙었으므로 목록 전체를 못 박지 않는다 - 여기서 지킬 것은 이
        Sprint가 붙인 둘이 사라지지 않았다는 사실이고, 아직 안 붙은
        것이 섞여 들지 않는다는 것은 아래
        test_only_gpt_image_was_removed_from_the_refused가 지킨다.
        """

        self.assertLessEqual(
            {"flux", "gpt_image"}, set(provider_selection.WIRED["image"]))

    def test_only_gpt_image_was_removed_from_the_refused(self):
        for name in ("imagen", "ideogram"):
            with self.subTest(name=name):
                with self.assertRaises(ProviderNotWired):
                    provider_selection.require_wired("image", name)

    def test_the_other_stages_did_not_move(self):
        """이미지 단계만 바뀌었다."""

        self.assertEqual(provider_selection.WIRED["metadata"], ("manual",))

        with self.assertRaises(ProviderNotWired):
            provider_selection.require_wired("script", "그런거없음")


class TestItRefusesWithoutSettings(_Case):

    def test_no_api_key_is_refused_by_name(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(
                    gpt_image_provider.GptImageUnavailable) as caught:
                gpt_image_provider.generate_image("prompt", self._target())

        self.assertIn("OPENAI_API_KEY", str(caught.exception))

    def test_refusing_writes_nothing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(gpt_image_provider.GptImageUnavailable):
                gpt_image_provider.generate_image("prompt", self._target())

        self.assertFalse(os.path.exists(self._target()))

    def test_it_refuses_before_calling_anything(self):
        transport = _Transport()

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(gpt_image_provider, "requests", transport):
                with self.assertRaises(
                        gpt_image_provider.GptImageUnavailable):
                    gpt_image_provider.generate_image("p", self._target())

        self.assertEqual(transport.requested, [])


class TestItAsksOpenAiCorrectly(_Case):

    def _generate(self, transport=None, env=None):
        transport = transport or _Transport()

        with patch.dict(os.environ, env or CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests", transport):
                with patch.object(gpt_image_provider, "enhance_image"):
                    gpt_image_provider.generate_image(
                        "a calm man walking", self._target())

        return transport

    def test_it_posts_to_the_images_endpoint(self):
        transport = self._generate()

        self.assertEqual(len(transport.requested), 1)
        self.assertEqual(
            transport.requested[0]["url"],
            "https://api.openai.com/v1/images/generations")

    def test_the_key_travels_as_a_bearer_token(self):
        transport = self._generate()

        self.assertEqual(
            transport.requested[0]["authorization"], "Bearer key-123")

    def test_it_asks_for_one_image_of_the_prompt(self):
        body = self._generate().requested[0]["body"]

        self.assertEqual(body["prompt"], "a calm man walking")
        self.assertEqual(body["n"], 1)
        self.assertEqual(body["model"], "gpt-image-1")

    def test_it_asks_for_a_portrait(self):
        """세로 영상이다. 가로로 받으면 절반이 잘린다."""

        body = self._generate().requested[0]["body"]
        width, height = (int(n) for n in body["size"].split("x"))

        self.assertGreater(height, width)

    def test_it_does_not_wait_forever(self):
        self.assertIsNotNone(self._generate().requested[0]["timeout"])

    def test_the_address_can_be_changed_without_touching_code(self):
        env = dict(CONFIGURED, OPENAI_API_URL="https://proxy.test")

        transport = self._generate(env=env)

        self.assertTrue(
            transport.requested[0]["url"].startswith("https://proxy.test/"))

    def test_the_model_can_be_changed_without_touching_code(self):
        env = dict(CONFIGURED, GPT_IMAGE_MODEL="gpt-image-2")

        transport = self._generate(env=env)

        self.assertEqual(transport.requested[0]["body"]["model"],
                         "gpt-image-2")

    def test_the_size_can_be_changed_without_touching_code(self):
        env = dict(CONFIGURED, GPT_IMAGE_SIZE="1024x1024")

        transport = self._generate(env=env)

        self.assertEqual(transport.requested[0]["body"]["size"], "1024x1024")

    def test_it_does_not_change_the_environment(self):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            before = dict(os.environ)

            with patch.object(gpt_image_provider, "requests", _Transport()):
                with patch.object(gpt_image_provider, "enhance_image"):
                    gpt_image_provider.generate_image("p", self._target())

            self.assertEqual(dict(os.environ), before)


class TestItWritesTheImage(_Case):

    def test_the_bytes_from_the_answer_land_on_disk(self):
        target = self._target()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests", _Transport()):
                with patch.object(gpt_image_provider, "enhance_image"):
                    gpt_image_provider.generate_image("p", target)

        with open(target, "rb") as f:
            self.assertEqual(f.read(), PNG)

    def test_it_returns_where_it_wrote(self):
        target = self._target()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests", _Transport()):
                with patch.object(gpt_image_provider, "enhance_image"):
                    written = gpt_image_provider.generate_image("p", target)

        self.assertEqual(written, target)

    def test_it_goes_through_the_same_polish_as_the_current_engine(self):
        """여기만 건너뛰면 같은 프로젝트 안에서 그림의 성격이 갈린다."""

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests", _Transport()):
                with patch.object(gpt_image_provider,
                                  "enhance_image") as polish:
                    gpt_image_provider.generate_image("p", self._target())

        polish.assert_called_once_with(self._target())

    def test_a_real_png_survives_the_real_polish(self):
        """후처리를 세우지 않고 진짜로 돌려 본다."""

        from PIL import Image

        target = self._target()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests", _Transport()):
                gpt_image_provider.generate_image("p", target)

        self.assertEqual(Image.open(target).size, (4, 4))

    def test_a_missing_folder_is_created(self):
        target = os.path.join(self.project, "새폴더", "scene1.raw")

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests", _Transport()):
                with patch.object(gpt_image_provider, "enhance_image"):
                    gpt_image_provider.generate_image("p", target)

        self.assertTrue(os.path.exists(target))

    def test_an_answer_that_carries_a_link_is_downloaded(self):
        """모델을 바꾸면 주소로 올 수도 있다. 둘 다 받는다."""

        transport = _Transport(
            payload={"data": [{"url": "https://cdn.test/o.png"}]})
        target = self._target()

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests", transport):
                with patch.object(gpt_image_provider, "enhance_image"):
                    gpt_image_provider.generate_image("p", target)

        self.assertEqual(transport.downloaded, ["https://cdn.test/o.png"])

        with open(target, "rb") as f:
            self.assertEqual(f.read(), PNG)


class TestItFailsHonestly(_Case):

    def _fails_with(self, transport):
        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests", transport):
                with self.assertRaises(
                        gpt_image_provider.GptImageUnavailable) as caught:
                    gpt_image_provider.generate_image("p", self._target())

        return str(caught.exception)

    def test_a_rejected_key_says_so(self):
        message = self._fails_with(_Transport(
            status_code=401,
            error={"error": {"message": "Incorrect API key provided"}}))

        self.assertIn("401", message)

    def test_a_blocked_prompt_says_what_to_do(self):
        """
        OpenAI는 프롬프트를 거절한다. 키가 틀린 것과 전혀 다른 일이고,
        사람이 할 일도 다르다 - 프롬프트를 고쳐야 한다.
        """

        message = self._fails_with(_Transport(
            status_code=400,
            error={"error": {"code": "moderation_blocked",
                             "message": "blocked by our safety system"}}))

        self.assertIn("프롬프트", message)

    def test_an_empty_answer_is_a_failure(self):
        message = self._fails_with(_Transport(payload={"data": []}))

        self.assertTrue(message)

    def test_an_answer_without_an_image_is_a_failure(self):
        message = self._fails_with(_Transport(payload={"data": [{}]}))

        self.assertTrue(message)

    def test_failure_leaves_no_half_written_file(self):
        """반쯤 남으면 뒤 단계가 그것을 완성된 것으로 읽는다."""

        self._fails_with(_Transport(payload={"data": []}))

        self.assertFalse(os.path.exists(self._target()))

    def test_a_failed_download_is_a_failure(self):
        transport = _Transport(
            payload={"data": [{"url": "https://cdn.test/o.png"}]})
        transport.get = lambda url, timeout=None: _Response(404, None)

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests", transport):
                with self.assertRaises(
                        gpt_image_provider.GptImageUnavailable):
                    gpt_image_provider.generate_image("p", self._target())


class TestTheOutputContractIsUnchanged(_Case):
    """step02 뒤가 차이를 몰라야 한다."""

    def _integrate(self, number=1):
        from app.services import asset_integration_service

        provider_selection.save(self.project, {"image": "gpt_image"})

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests", _Transport()):
                with patch.object(gpt_image_provider, "enhance_image"):
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

    def test_the_provider_says_gpt_image(self):
        enriched = self._integrate(1)

        self.assertEqual(enriched["provider"], "gpt_image")
        self.assertEqual(enriched["asset_type"], "image")

    def test_the_confidence_is_the_ai_one(self):
        """프롬프트로 만든 것이다 - 스톡의 0.8이 아니다."""

        enriched = self._integrate(1)

        self.assertEqual(enriched["confidence"], 1.0)

    def test_the_original_scene_fields_survive(self):
        enriched = self._integrate(1)

        self.assertEqual(enriched["narration"], "1번")
        self.assertEqual(enriched["image_prompt"], "a calm man walking")

    def test_it_looks_exactly_like_the_flux_result(self):
        """
        두 Provider가 다른 모양을 돌려주면 뒤 단계가 갈린다. 같은
        자리에서 만들어지는지 확인한다.
        """

        from app.providers import flux_provider
        from app.services import asset_integration_service

        with patch.object(gpt_image_provider, "generate_image"):
            gpt = asset_integration_service._ai_result(
                "p", self._target(), "wellbeing", False, provider="gpt_image")

        with patch.object(flux_provider, "generate_image"):
            flux = asset_integration_service._ai_result(
                "p", self._target(), "wellbeing", False, provider="flux")

        self.assertEqual(set(gpt), set(flux))
        self.assertEqual(gpt["source"], "gpt_image")
        self.assertEqual(flux["source"], "flux")


class TestCurrentIsUntouched(_Case):

    def test_gpt_image_never_runs_when_nothing_is_chosen(self):
        from app.services import asset_integration_service

        with patch.object(gpt_image_provider, "generate_image") as generate:
            with patch.object(asset_integration_service, "get_candidates",
                              return_value=[]):
                try:
                    asset_integration_service.integrate_asset(
                        self._scene(1), self.project, "wellbeing")
                except Exception:
                    pass

        generate.assert_not_called()

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

    def test_the_current_engine_files_do_not_know_the_name(self):
        from app.services import best_of_n_service, image_service

        for module in (best_of_n_service, image_service):
            with self.subTest(module=module.__name__):
                self.assertNotIn(
                    "gpt_image", _string_constants(module.__file__))

    def test_the_pipeline_and_resolver_do_not_know_the_name(self):
        from app.steps import step02_asset_resolve, step02_assets

        for module in (step02_assets, step02_asset_resolve):
            with self.subTest(module=module.__name__):
                self.assertNotIn(
                    "gpt_image", _string_constants(module.__file__))


class TestTheFallbackDoesNotSubstitute(_Case):
    """GPT Image를 골랐는데 스톡 사진이 나오면 안 된다."""

    def test_a_failure_does_not_become_a_stock_photo(self):
        from app.services import asset_integration_service

        provider_selection.save(self.project, {"image": "gpt_image"})

        with patch.dict(os.environ, {"PATH": os.environ.get("PATH", "")},
                        clear=True):
            with patch.object(asset_integration_service,
                              "get_candidates") as search:
                with self.assertRaises(Exception):
                    asset_integration_service.integrate_asset(
                        self._scene(1), self.project, "wellbeing")

        search.assert_not_called()


class TestReviewUsesTheSameProvider(_Case):

    def test_regenerating_one_scene_goes_to_gpt_image(self):
        from app.services import studio_review

        provider_selection.save(self.project, {"image": "gpt_image"})

        scenes = [self._scene(1), self._scene(2), self._scene(3)]

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"scenes": scenes}, f, ensure_ascii=False)

        with patch.dict(os.environ, CONFIGURED, clear=True):
            with patch.object(gpt_image_provider, "requests",
                              _Transport()) as transport:
                with patch.object(gpt_image_provider, "enhance_image"):
                    studio_review.regenerate_image(self.project,
                                                   "wellbeing", 2)

        self.assertEqual(len(transport.requested), 1)
        self.assertTrue(os.path.exists(
            os.path.join(self.project, "images", "scene2.png")))
        self.assertFalse(os.path.exists(
            os.path.join(self.project, "images", "scene1.png")))


class TestTwoProjectsDoNotMix(_Case):

    def test_one_project_choosing_gpt_image_does_not_move_the_other(self):
        from app.services import asset_integration_service

        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        os.makedirs(os.path.join(other.name, "images"))

        provider_selection.save(self.project, {"image": "gpt_image"})
        provider_selection.save(other.name, {"image": "current"})

        seen = {}
        lock = threading.Lock()

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
                        self._scene(number), project, "wellbeing")
                except Exception:
                    pass

        with patch.object(asset_integration_service, "_ai_result", record):
            threads = [
                threading.Thread(target=run, args=(self.project,)),
                threading.Thread(target=run, args=(other.name,)),
            ]

            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(seen[os.path.join(self.project, "images")],
                         ["gpt_image"] * 3)
        self.assertEqual(seen[os.path.join(other.name, "images")],
                         [None] * 3)


if __name__ == "__main__":
    unittest.main()
