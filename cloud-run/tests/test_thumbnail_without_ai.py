"""
Sprint243 - 썸네일이 영상을 죽이지 않는다.

무엇이 실제로 있었나
--------------------
새 EXE 로 영상을 만들어 보니 이렇게 끝났다(실측).

    [  4s] 이미지 완료      <- 6장 전부 스톡으로 (AI 0회)
    [ 36s] 음성 완료
    [424s] 영상 완료
    [440s] 썸네일 -> FAILED
      404 NOT_FOUND. imagen-4.0-generate-001

영상은 다 만들어졌는데 썸네일 한 장 때문에 제작 전체가 실패로 끝났다.

두 가지가 겹쳤다
----------------
1. thumbnail_service 는 image_service.generate_image 를 곧장 부른다 -
   자산 쪽과 달리 스톡으로 내려가는 길이 없다.
2. pipeline 이 그 단계만 보호하지 않는다. 바로 아래 step07_quality 는
   try/except 로 감싸 두었다 - 같은 함수 안에 대조가 있다.

하류는 이미 견딘다
------------------
    publishing/resolve_thumbnail_path   없으면 None
    youtube_upload_provider             if thumbnail_path: 조건부
    step07_quality                      getsize(...) if ... 조건부

썸네일이 없어도 올리는 데 지장이 없다는 뜻이다. 그러니 비치명적으로
다루어도 되는 계약이다.

그런데 없는 것보다 있는 것이 낫다
---------------------------------
첫 장면 그림이 이미 프로젝트에 있다(images/scene1.png). 스톡에서 받은
것이든 AI 로 만든 것이든, 그 영상의 그림이다. 그것을 쓰면 돈이 들지
않고 결과도 늘 같다.

Sprint241 이 정한 계약이 "AI 이미지 사용 안 함은 예외가 아니라 정상
경로" 다. 정상 경로는 반쪽짜리가 아니라 완성품을 내야 한다.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import image_service, media_policy, thumbnail_service

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200


class _WithProject(unittest.TestCase):

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.images = os.path.join(self.project, "images")
        os.makedirs(self.images, exist_ok=True)

        with open(os.path.join(self.images, "scene1.png"), "wb") as f:
            f.write(PNG)

        self.thumb = os.path.join(self.project, "thumbnail.png")

    def forbid(self):
        media_policy.choose(self.project, media_policy.MODE_MINE_THEN_STOCK)

    def allow(self):
        media_policy.choose(self.project, media_policy.MODE_MINE_STOCK_AI)

    def make(self):
        return thumbnail_service.create_thumbnail(
            "무릎 통증", "무릎", self.project, "wellbeing",
            "첫 장면 내레이션", "knee stretch")


class TheThumbnailFallsBackToTheFirstSceneTest(_WithProject):
    """
    AI 를 쓰지 않기로 했으면 이미 있는 그림을 쓴다. 돈이 들지 않고
    결과도 늘 같다.
    """

    def test_금지_모드에서도_썸네일이_생긴다(self):
        self.forbid()

        with patch.object(image_service, "client") as client:
            self.make()

        self.assertTrue(os.path.isfile(self.thumb), "썸네일이 없다")
        self.assertEqual(client.models.generate_images.call_count, 0)

    def test_첫_장면_그림을_쓴다(self):
        self.forbid()

        with patch.object(image_service, "client"):
            self.make()

        with open(self.thumb, "rb") as f:
            made = f.read()

        with open(os.path.join(self.images, "scene1.png"), "rb") as f:
            scene1 = f.read()

        self.assertEqual(made, scene1)

    def test_원본을_옮기지_않고_베낀다(self):
        """첫 장면 그림은 영상이 쓰는 것이다 - 사라지면 안 된다."""

        self.forbid()

        with patch.object(image_service, "client"):
            self.make()

        self.assertTrue(
            os.path.isfile(os.path.join(self.images, "scene1.png")))

    def test_같은_입력이면_같은_결과다(self):
        self.forbid()

        with patch.object(image_service, "client"):
            self.make()

            first = open(self.thumb, "rb").read()

            self.make()

            second = open(self.thumb, "rb").read()

        self.assertEqual(first, second)

    def test_첫_장면_그림도_없으면_던지지_않는다(self):
        """
        그때는 썸네일이 없는 채로 둔다 - 하류가 이미 견딘다.
        """

        self.forbid()

        os.remove(os.path.join(self.images, "scene1.png"))

        with patch.object(image_service, "client") as client:
            self.make()

        self.assertFalse(os.path.isfile(self.thumb))
        self.assertEqual(client.models.generate_images.call_count, 0)


class TheAiPathIsUnchangedTest(_WithProject):
    """고른 사람은 예전 그대로 쓴다."""

    def test_허용_모드에서는_AI_로_만든다(self):
        self.allow()

        with patch.object(image_service, "client") as client, \
                patch.object(image_service, "enhance_image", lambda p: None):
            try:
                self.make()
            except Exception:
                # mock 응답이 진짜 모양이 아니라 뒤에서 깨질 수 있다.
                # 여기서 재는 것은 **모델을 불렀는가** 뿐이다.
                pass

        self.assertEqual(client.models.generate_images.call_count, 1,
                         "허용했는데 AI 를 부르지 않았다")

    def test_허용_모드에서_첫_장면을_베끼지_않는다(self):
        self.allow()

        with patch.object(image_service, "client"), \
                patch.object(image_service, "enhance_image", lambda p: None):
            try:
                self.make()
            except Exception:
                pass

        if os.path.isfile(self.thumb):
            with open(self.thumb, "rb") as f:
                made = f.read()

            self.assertNotEqual(made, PNG, "AI 를 고른 사람에게 사본을 줬다")


class TheRenderSurvivesAThumbnailFailureTest(_WithProject):
    """
    영상은 다 만들어졌는데 썸네일 한 장 때문에 제작 전체가 실패로
    끝나면 안 된다. 바로 아래 품질 단계는 이미 그렇게 보호받는다.
    """

    def test_파이프라인이_썸네일_실패를_삼킨다(self):
        import re

        from app.pipeline import pipeline

        with open(pipeline.__file__, encoding="utf-8") as f:
            source = f.read()

        at = source.index("step06_thumbnail.run(")

        # 그 호출을 감싸는 try 가 위에 있어야 한다.
        before = source[:at]
        opened = before.rfind("    try:")
        closed = before.rfind("    timings[")

        self.assertGreater(opened, closed,
                           "썸네일 호출이 try 로 감싸여 있지 않다")

    def test_삼키되_조용하지_않다(self):
        from app.pipeline import pipeline

        with open(pipeline.__file__, encoding="utf-8") as f:
            source = f.read()

        at = source.index("step06_thumbnail.run(")
        block = source[at:at + 900]

        self.assertIn("except Exception", block)
        self.assertIn("print(", block, "무슨 일이 있었는지 남겨야 한다")


class TheFreePathDoesNotKnowTheProviderLayerTest(_WithProject):
    """
    thumbnail_service 가 정책만 보고 provider 계층을 알지 않게 한다.
    """

    def test_무료_provider_이름을_적지_않는다(self):
        import re

        with open(thumbnail_service.__file__, encoding="utf-8") as f:
            text = re.sub(r'"""[\s\S]*?"""', "", f.read())

        doing = "\n".join(
            line.split("#")[0] for line in text.splitlines()
            if not line.lstrip().startswith("#"))

        for name in ("pexels", "pixabay", "local_stock"):
            with self.subTest(name=name):
                self.assertNotIn(name, doing.lower())


if __name__ == "__main__":
    unittest.main()
