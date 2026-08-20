"""
Sprint243 - 돈이 나가는 마지막 문 하나 (AI 이미지 비용 관문).

Sprint241 이 세운 관문은 하나였는데 문은 여럿이었다
----------------------------------------------------
그때 asset_integration_service._ai_result 의 주석을 읽고 "Imagen 을
부르는 유일한 지점" 이라고 믿었다. 그 주석은 **자산 통합 경로
안에서만** 참이었다.

실제 EXE 로 영상을 만들어 보니 썸네일이 다른 길로 나갔다(실측).

    [424s] 영상 완료
    [440s] 썸네일 -> FAILED
      404 NOT_FOUND. imagen-4.0-generate-001

이미지 6장은 관문에 막혀 스톡으로 갔는데, 썸네일 한 장이 곧장
유료 모델로 갔다. 저장소 전체를 뒤져 보니 부르는 자리가 아홉이었다.

    asset_integration_service   (SINGLE_IMAGE_PROVIDERS 경유)
    best_of_n_service           x2  <- Sprint241 이 막던 그 하나
    thumbnail_service               <- 이번에 터진 곳
    regeneration_service
    asset_selector
    step02_image
    routers/image
    production/providers/generated_image

그래서 관문을 목이 아니라 **문 자체**로 옮긴다
----------------------------------------------
image_service.generate_image 와 generate_image_candidates 가 유료
모델(imagen-4.0-generate-001)을 부르는 두 함수다. 거기에 관문을 두면
문이 몇 개든 전부 그 하나를 지난다.

무료 경로는 막지 않는다
-----------------------
같은 이름의 함수가 무료 쪽에도 있다.

    local_stock_provider.generate_image   내 PC 자료에서 고른다
    flux_provider.generate_image          다른 모듈(자기 열쇠)
    gpt_image_provider.generate_image     다른 모듈(자기 열쇠)

이들은 image_service 를 지나지 않으므로 이 관문과 무관하다. Pexels ·
Pixabay 도 마찬가지다 - 막으면 AI 금지 모드에서 아무것도 못 만든다.

어느 프로젝트의 결정을 따르는가
-------------------------------
image_service 는 project_path 를 받지 않는다. 아홉 자리와 그 대역들의
서명을 다 바꾸는 것은 Sprint241 에서 겪은 그 일을 더 크게 반복하는
것이다.

대신 **적을 파일이 어디인지**를 본다. 그 파일은 언제나 어느 프로젝트
안에 있고, 그 프로젝트의 결정은 project.json 에 적혀 있다. 못 찾으면
전역 기본값을 따른다 - 모르면 돈을 쓰지 않는다.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import image_service, media_policy


class _Watch:
    """유료 모델로 나가는 그 호출만 지켜본다."""

    def __enter__(self):
        self.patch = patch.object(image_service, "client")
        self.client = self.patch.start()

        return self

    def __exit__(self, *rest):
        self.patch.stop()

        return False

    @property
    def calls(self):
        return self.client.models.generate_images.call_count


class _WithProject(unittest.TestCase):

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.images = os.path.join(self.project, "images")
        os.makedirs(self.images, exist_ok=True)

        self.target = os.path.join(self.images, "scene1.png")

    def forbid(self):
        media_policy.choose(self.project, media_policy.MODE_MINE_THEN_STOCK)

    def allow(self):
        media_policy.choose(self.project, media_policy.MODE_MINE_STOCK_AI)


class TheGateIsAtTheDoorTest(_WithProject):
    """관문이 실제로 그 두 함수 안에 있는가."""

    def test_금지_모드에서_generate_image_는_던진다(self):
        self.forbid()

        with _Watch() as watch:
            with self.assertRaises(media_policy.AiNotAllowed):
                image_service.generate_image("무릎", self.target)

        self.assertEqual(watch.calls, 0, "유료 모델을 불렀다")

    def test_금지_모드에서_candidates_도_던진다(self):
        self.forbid()

        with _Watch() as watch:
            with self.assertRaises(media_policy.AiNotAllowed):
                image_service.generate_image_candidates(
                    "무릎", [self.target,
                            os.path.join(self.images, "scene1_b.png")])

        self.assertEqual(watch.calls, 0)

    def test_허용_모드에서는_지나간다(self):
        self.allow()

        with _Watch() as watch:
            try:
                image_service.generate_image("무릎", self.target)
            except media_policy.AiNotAllowed:
                self.fail("허용했는데 막았다")
            except Exception:
                # mock 이 진짜 응답 모양이 아니라 뒤에서 깨질 수 있다.
                # 여기서 재는 것은 **관문을 지나갔는가** 뿐이다.
                pass

        self.assertEqual(watch.calls, 1, "허용했는데 모델을 안 불렀다")

    def test_거절_문장이_사람_말이다(self):
        self.forbid()

        with _Watch():
            try:
                image_service.generate_image("무릎", self.target)
            except media_policy.AiNotAllowed as refused:
                said = str(refused)

        self.assertIn("AI", said)


class TheProjectIsFoundFromTheFileTest(_WithProject):
    """
    어느 프로젝트의 결정인가. 적을 파일에서 거슬러 올라가 찾는다.
    """

    def test_images_아래_파일에서_프로젝트를_찾는다(self):
        self.forbid()

        self.assertEqual(image_service.project_of(self.target), self.project)

    def test_더_깊은_자리도_찾는다(self):
        self.forbid()

        deep = os.path.join(self.project, "images", "candidates", "a.png")
        os.makedirs(os.path.dirname(deep), exist_ok=True)

        self.assertEqual(image_service.project_of(deep), self.project)

    def test_프로젝트_바로_아래도_찾는다(self):
        self.forbid()

        self.assertEqual(
            image_service.project_of(os.path.join(self.project, "thumb.png")),
            self.project)

    def test_못_찾으면_전역_기본값을_따른다(self):
        """
        모르면 돈을 쓰지 않는다. 전역 기본값은 AI 금지다.
        """

        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)

        self.assertIsNone(image_service.project_of(
            os.path.join(outside, "x.png")))

        with _Watch() as watch:
            with self.assertRaises(media_policy.AiNotAllowed):
                image_service.generate_image("무릎",
                                             os.path.join(outside, "x.png"))

        self.assertEqual(watch.calls, 0)

    def test_다른_프로젝트의_결정을_가져오지_않는다(self):
        self.forbid()

        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        media_policy.choose(other, media_policy.MODE_MINE_STOCK_AI)

        # 이 프로젝트는 금지다 - 옆 프로젝트가 허용해도 막혀야 한다.
        with _Watch() as watch:
            with self.assertRaises(media_policy.AiNotAllowed):
                image_service.generate_image("무릎", self.target)

        self.assertEqual(watch.calls, 0)


class EveryPathIsCoveredTest(_WithProject):
    """
    Sprint241 의 실수를 되풀이하지 않는다 - 자리 하나를 믿지 않고
    아홉을 각각 밟아 본다.
    """

    def test_썸네일이_유료로_새지_않는다(self):
        """이번 EXE E2E 에서 실제로 터진 그 자리다."""

        self.forbid()

        from app.services import thumbnail_service

        with _Watch() as watch:
            try:
                thumbnail_service.generate_thumbnail(
                    self.project, "무릎 통증", "wellbeing")
            except Exception:
                pass

        self.assertEqual(watch.calls, 0, "썸네일이 유료 모델을 불렀다")

    def test_재생성이_유료로_새지_않는다(self):
        self.forbid()

        from app.services import regeneration_service

        with _Watch() as watch:
            try:
                regeneration_service.regenerate_failed_scenes(
                    self.project, "wellbeing")
            except Exception:
                pass

        self.assertEqual(watch.calls, 0)

    def test_asset_selector_가_유료로_새지_않는다(self):
        self.forbid()

        from app.services import asset_selector

        with _Watch() as watch:
            try:
                asset_selector.select_asset(
                    "무릎", self.target, "wellbeing", scene={"scene": 1})
            except Exception:
                pass

        self.assertEqual(watch.calls, 0)

    def test_step02_가_유료로_새지_않는다(self):
        self.forbid()

        from app.steps import step02_image

        with _Watch() as watch:
            try:
                step02_image.create_images(
                    {"scenes": [{"scene": 1, "image_prompt": "무릎"}]},
                    self.project, "wellbeing")
            except Exception:
                pass

        self.assertEqual(watch.calls, 0)

    def test_best_of_n_이_유료로_새지_않는다(self):
        self.forbid()

        from app.services import best_of_n_service

        with _Watch() as watch:
            try:
                best_of_n_service.generate_candidates(
                    "무릎", self.target, 2, "wellbeing", False,
                    image_service.IMAGE_STYLE_DEFAULT)
            except Exception:
                pass

        self.assertEqual(watch.calls, 0)


class TheFreePathsAreNotTouchedTest(_WithProject):
    """
    막는 것이 목적이 아니다. 막고도 영상이 만들어져야 한다.
    """

    def test_local_stock_은_이_관문을_지나지_않는다(self):
        from app.providers import local_stock_provider

        self.assertIsNot(local_stock_provider.generate_image,
                         image_service.generate_image)

    def test_flux_는_다른_모듈이다(self):
        from app.providers import flux_provider

        self.assertIsNot(flux_provider.generate_image,
                         image_service.generate_image)

    def test_gpt_image_도_다른_모듈이다(self):
        from app.providers import gpt_image_provider

        self.assertIsNot(gpt_image_provider.generate_image,
                         image_service.generate_image)

    def test_관문은_무료_provider_를_모른다(self):
        """
        image_service 가 무료 쪽을 알기 시작하면 두 계층이 얽힌다.
        """

        import re

        # docstring 까지 걷는다. 무엇을 부르지 않는지 적어 둔 설명에
        # 그 이름이 들어가고, 그러면 가드가 제 설명에 걸린다 - 이
        # 저장소에서 여러 번 겪었고 여기서도 실제로 걸렸다.
        with open(image_service.__file__, encoding="utf-8") as f:
            text = re.sub(r'"""[\s\S]*?"""', "", f.read())

        doing = "\n".join(
            line.split("#")[0] for line in text.splitlines()
            if not line.lstrip().startswith("#"))

        for free in ("local_stock", "pexels", "pixabay"):
            with self.subTest(free=free):
                self.assertNotIn(free, doing.lower())


if __name__ == "__main__":
    unittest.main()
