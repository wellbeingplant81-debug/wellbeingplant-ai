"""
Sprint241 - 금지했으면 한 번도 부르지 않는다 (비용 안전장치).

이 파일 하나가 이번 Sprint 의 이유다
------------------------------------
2026-08-01~18 사이 이미지 생성으로 약 20만원이 나갔다. 지금 결제는
잠겨 있고, 그 잠긴 상태에서 배포된 EXE 가 이렇게 죽었다(실측).

    imagen-4.0-generate-001 -> 404 NOT_FOUND -> HTTP 500

"AI 안 씀" 이 예외 경로였기 때문이다. 스톡이 한 장 실패하자 곧바로
유료 모델로 넘어갔고, 그 모델에 닿지 못하자 제작 전체가 멈췄다.

세 갈래를 각각 잰다
-------------------
유료 모델로 가는 길은 셋이고 전부 _ai_result 로 모인다.

    visual_type 없음   스톡 실패/품질 미달 -> _ai_result
    visual_type real   스톡 실패           -> _ai_result
    visual_type ai     처음부터            -> _ai_result

셋 다 "한 번도 부르지 않았다" 를 확인한다. 하나라도 새면 돈이 나간다.

무엇을 감시하는가
-----------------
실제 유료 함수 자리를 감시한다 - 사이에 낀 계층이 아니라 **바깥으로
나가는 그 함수**다.

    image_service.generate_image        Vertex Imagen
    best_of_n_service.generate_candidates
    flux_provider.generate_image
    gpt_image_provider.generate_image

이들 중 하나라도 불리면 실패다. 부르지 않았다는 것을 mock 의 호출
횟수로 센다 - 실제 API 는 절대 부르지 않는다.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import asset_integration_service as assets
from app.services import media_policy


class _PaidWatch:
    """
    유료로 나가는 문 넷을 한꺼번에 지켜본다. 하나라도 열리면 안다.
    """

    DOORS = (
        ("app.services.image_service", "generate_image"),
        ("app.services.best_of_n_service", "generate_candidates"),
        ("app.providers.flux_provider", "generate_image"),
        ("app.providers.gpt_image_provider", "generate_image"),
    )

    def __init__(self):
        self.patches = []
        self.mocks = {}

    def __enter__(self):
        for module, name in self.DOORS:
            try:
                patched = patch(f"{module}.{name}")
                self.mocks[f"{module}.{name}"] = patched.start()
                self.patches.append(patched)
            except (ImportError, AttributeError, ModuleNotFoundError):
                # 없는 문은 셀 것도 없다.
                pass

        return self

    def __exit__(self, *rest):
        for patched in self.patches:
            patched.stop()

        return False

    @property
    def opened(self):
        return {name: m.call_count for name, m in self.mocks.items()
                if m.call_count}


def _downloads(candidate, staging_path, *rest, **kw):
    """내려받은 척이 아니라 실제로 파일을 놓는다 - 뒤 단계가 그것을 옮긴다."""

    os.makedirs(os.path.dirname(staging_path) or ".", exist_ok=True)

    with open(staging_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

    # 진짜 download_candidate 의 계약 그대로 - source · local_path ·
    # metadata 셋이다(asset_selector:306).
    return {"source": "pexels_image", "local_path": staging_path,
            "metadata": {"query": "knee stretching"}}


def _scene(visual_type=None):
    scene = {"scene": 1, "image_prompt": "knee stretching home",
             "narration": "무릎을 천천히 늘려 줍니다."}

    if visual_type:
        scene["visual_type"] = visual_type

    return scene


class NothingPaidIsCalledWhenForbiddenTest(unittest.TestCase):
    """
    세 갈래 전부. 스톡을 일부러 실패시켜 AI 로 갈 수밖에 없는 상황을
    만든 다음, 그래도 부르지 않는지 본다.
    """

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.staging = os.path.join(self.project, "scene1.png")

        # 이 프로젝트는 AI 를 쓰지 않기로 했다.
        media_policy.choose(self.project, media_policy.MODE_MINE_THEN_STOCK)

    def _integrate(self, scene, candidates=None):
        """스톡 후보를 우리가 정한다 - 바깥을 부르지 않는다."""

        with patch.object(assets, "get_candidates",
                          return_value=candidates or []), \
                patch.object(assets, "select_best_with_score",
                             return_value=(None, 0.0)), \
                _PaidWatch() as watch:
            try:
                assets.integrate_asset(scene, self.project,
                                       channel="wellbeing")
                failed = None
            except Exception as exc:
                failed = exc

        return watch.opened, failed

    def test_visual_type_없음_스톡_실패해도_안_부른다(self):
        opened, failed = self._integrate(_scene())

        self.assertEqual(opened, {}, f"유료 문이 열렸다: {opened}")
        self.assertIsInstance(failed, media_policy.AiNotAllowed)

    def test_visual_type_real_스톡_실패해도_안_부른다(self):
        opened, failed = self._integrate(_scene("real"))

        self.assertEqual(opened, {}, f"유료 문이 열렸다: {opened}")
        self.assertIsInstance(failed, media_policy.AiNotAllowed)

    def test_visual_type_ai_여도_안_부른다(self):
        """
        사람이 AI 를 고르지 않았는데 파이프라인이 ai 로 분류한 scene 이다.
        여기서 부르면 고르지 않은 돈이 나간다.
        """

        opened, _ = self._integrate(_scene("ai"))

        self.assertEqual(opened, {}, f"유료 문이 열렸다: {opened}")

    def test_visual_type_ai_는_스톡으로_강등되어_이어진다(self):
        """
        AI 를 고르지 않은 사람에게는 제작이 끝나는 쪽이 맞다.
        """

        candidate = {"provider": "pexels_image", "slug": "knee",
                     "download_url": "https://x/1.jpg"}

        with patch.object(assets, "get_candidates", return_value=[candidate]), \
                patch.object(assets, "select_best_with_score",
                             return_value=(candidate, 0.95)), \
                patch.object(assets, "download_candidate",
                             side_effect=_downloads), \
                _PaidWatch() as watch:
            found = assets.integrate_asset(_scene("ai"), self.project,
                                           channel="wellbeing")

        self.assertEqual(watch.opened, {})
        # integrate_asset 은 scene 을 불려 돌려준다 - 키는 provider 다.
        self.assertEqual(found["provider"], "pexels_image")

    def test_기본값만으로도_막힌다(self):
        """
        프로젝트가 아무것도 고르지 않은 경우. 전역 기본값이 금지다.
        """

        bare = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)

        with patch.object(assets, "get_candidates", return_value=[]), \
                patch.object(assets, "select_best_with_score",
                             return_value=(None, 0.0)), \
                _PaidWatch() as watch:
            try:
                assets.integrate_asset(_scene(), bare, channel="wellbeing")
            except Exception:
                pass

        self.assertEqual(watch.opened, {})


class TheStockPathStillWorksTest(unittest.TestCase):
    """
    막는 것이 목적이 아니다. 막고도 영상이 만들어져야 한다.
    """

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.staging = os.path.join(self.project, "scene1.png")

        media_policy.choose(self.project, media_policy.MODE_MINE_THEN_STOCK)

    def test_스톡이_있으면_그것으로_끝난다(self):
        candidate = {"provider": "pexels_image", "slug": "knee",
                     "download_url": "https://x/1.jpg"}

        with patch.object(assets, "get_candidates", return_value=[candidate]), \
                patch.object(assets, "select_best_with_score",
                             return_value=(candidate, 0.95)), \
                patch.object(assets, "download_candidate",
                             side_effect=_downloads), \
                _PaidWatch() as watch:
            found = assets.integrate_asset(_scene("real"), self.project,
                                           channel="wellbeing")

        self.assertEqual(watch.opened, {})
        # integrate_asset 은 scene 을 불려 돌려준다 - 키는 provider 다.
        self.assertEqual(found["provider"], "pexels_image")


class TheAllowedModeCanStillUseAiTest(unittest.TestCase):
    """
    고른 사람은 쓸 수 있어야 한다. 막기만 하는 것은 고장이다.
    """

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.staging = os.path.join(self.project, "scene1.png")

        media_policy.choose(self.project, media_policy.MODE_MINE_STOCK_AI)

    def test_허용하면_관문을_지나간다(self):
        """
        실제 유료 API 는 부르지 않는다 - 문 안쪽을 mock 으로 막고
        "관문을 지나갔는가" 만 본다.
        """

        with patch.object(assets, "get_candidates", return_value=[]), \
                patch.object(assets, "select_best_with_score",
                             return_value=(None, 0.0)), \
                _PaidWatch() as watch:
            try:
                assets.integrate_asset(_scene("real"), self.project,
                                       channel="wellbeing")
            except Exception:
                pass

        self.assertTrue(watch.opened,
                        "허용했는데 관문이 막았다 - 고른 사람이 못 쓴다")


class TheGateLivesInOnePlaceTest(unittest.TestCase):
    """
    목이 하나라는 사실 자체를 지킨다. 두 번째 길이 생기면 이 시험이
    아무것도 지키지 못하게 된다.
    """

    def test_유료_이미지는_한_함수에서만_불린다(self):
        with open(assets.__file__, encoding="utf-8") as f:
            doing = "\n".join(
                line for line in f.read().splitlines()
                if not line.lstrip().startswith("#"))

        # best_of_n / SINGLE_IMAGE_PROVIDERS 로 가는 자리는 _ai_result
        # 안에만 있어야 한다.
        at = doing.index("def _ai_result(")
        end = doing.index("\ndef ", at + 10)
        inside = doing[at:end]
        outside = doing[:at] + doing[end:]

        self.assertIn("best_of_n_service.generate_candidates", inside)
        self.assertNotIn("best_of_n_service.generate_candidates", outside)

    def test_관문이_그_함수_안에_있다(self):
        with open(assets.__file__, encoding="utf-8") as f:
            body = f.read()

        at = body.index("def _ai_result(")
        end = body.index("\ndef ", at + 10)

        self.assertIn("media_policy", body[at:end])


if __name__ == "__main__":
    unittest.main()
