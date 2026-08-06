"""
Sprint71 - Provider Routing과 Visual Style의 책임 분리.

scene["visual_type"]("real"/"ai")이 두 가지를 동시에 뜻하고 있었다.

  1. 어느 provider를 먼저 시도할지 (asset_integration_service)
  2. Imagen에 어떤 스타일을 줄지 (image_service)

Sprint60에서 "ai"는 혈관/세포처럼 스톡으로 못 찍는 주제였으니 두 뜻이
같은 방향이었다. 그런데 Character Consistency가 인물 scene을 Imagen으로
보내면서 갈라졌다 - 라우팅으로는 "ai"가 맞지만 스타일로는 의료
일러스트가 아니라 인물이어야 한다.

실측으로 확인한 결과: "the same 60s Korean man ... pours steaming water
into a glass mug" 프롬프트가 사람 없는 해부학 단면도로 렌더됐다.

그래서 필드를 나눈다. 라우팅은 visual_type이, 스타일은 image_style이
정한다. 한 필드가 두 의미를 지고 있으면 한쪽을 바꿀 때마다 다른 쪽이
조용히 따라 바뀐다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_integration_service, image_service
from app.services.character_consistency_engine import CHARACTER_SCENE_FIELD
from app.services.visual_type_classifier import VISUAL_TYPE_AI, VISUAL_TYPE_REAL


class TestImageStyleConstants(unittest.TestCase):

    def test_every_style_has_a_name(self):
        for name in (
            image_service.IMAGE_STYLE_DEFAULT,
            image_service.IMAGE_STYLE_MEDICAL,
            image_service.IMAGE_STYLE_CHARACTER,
            image_service.IMAGE_STYLE_THUMBNAIL,
        ):
            self.assertIsInstance(name, str)
            self.assertTrue(name)

    def test_styles_are_distinct(self):
        names = {
            image_service.IMAGE_STYLE_DEFAULT,
            image_service.IMAGE_STYLE_MEDICAL,
            image_service.IMAGE_STYLE_CHARACTER,
            image_service.IMAGE_STYLE_THUMBNAIL,
        }
        self.assertEqual(len(names), 4)


class TestStyleResolution(unittest.TestCase):
    """어느 scene이 어떤 스타일을 받는지. 순수 함수라 API 없이 확인된다."""

    def test_a_character_scene_gets_the_character_style(self):
        scene = {
            "scene": 1,
            "visual_type": VISUAL_TYPE_AI,
            CHARACTER_SCENE_FIELD: True,
        }

        self.assertEqual(
            asset_integration_service.resolve_image_style(scene),
            image_service.IMAGE_STYLE_CHARACTER,
        )

    def test_an_ai_scene_without_a_character_gets_the_medical_style(self):
        # 혈관/세포 장면. Sprint60이 만든 동작을 그대로 유지한다.
        scene = {"scene": 2, "visual_type": VISUAL_TYPE_AI}

        self.assertEqual(
            asset_integration_service.resolve_image_style(scene),
            image_service.IMAGE_STYLE_MEDICAL,
        )

    def test_a_real_scene_gets_the_default_style(self):
        scene = {"scene": 3, "visual_type": VISUAL_TYPE_REAL}

        self.assertEqual(
            asset_integration_service.resolve_image_style(scene),
            image_service.IMAGE_STYLE_DEFAULT,
        )

    def test_a_character_scene_wins_even_over_an_ai_routing(self):
        # 인물 scene은 라우팅상 "ai"지만 스타일은 절대 의료 일러스트가
        # 아니다. 이 우선순위가 이번 수정의 핵심이다.
        scene = {
            "scene": 1,
            "visual_type": VISUAL_TYPE_AI,
            CHARACTER_SCENE_FIELD: True,
        }

        self.assertNotEqual(
            asset_integration_service.resolve_image_style(scene),
            image_service.IMAGE_STYLE_MEDICAL,
        )


class TestGenerateImagePicksStyleByName(unittest.TestCase):
    """generate_image()가 라우팅 값이 아니라 스타일 이름으로 분기하는지."""

    def _captured_prompt(self, **kwargs):
        captured = {}

        class _Image:
            image_bytes = b"png"

        class _Generated:
            image = _Image()

        class _Response:
            generated_images = [_Generated()]

        def fake_generate_images(model, prompt, config):
            captured["prompt"] = prompt
            captured["negative"] = config.negative_prompt
            return _Response()

        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch.object(
                 image_service.client.models, "generate_images",
                 fake_generate_images,
             ), \
             patch.object(image_service, "enhance_image", lambda path: None):

            image_service.generate_image(
                "a prompt", os.path.join(tmp_dir, "out.png"), **kwargs,
            )

        return captured

    def test_character_style_never_uses_the_medical_illustration_style(self):
        captured = self._captured_prompt(
            image_style=image_service.IMAGE_STYLE_CHARACTER,
        )

        # Sprint75 - 통짜 블록이 사라져서 예전 assertNotIn은 무조건
        # 참이 된다. 실제로 확인할 것은 의료 어휘가 인물 scene에
        # 새어 들어오지 않는다는 것이다.
        self.assertNotIn("medical illustration", captured["prompt"])
        self.assertNotIn("anatomy diagram", captured["prompt"])

    def test_medical_style_still_uses_the_medical_illustration_style(self):
        captured = self._captured_prompt(
            image_style=image_service.IMAGE_STYLE_MEDICAL,
        )

        # Sprint75 - 통짜 블록 대신 Style 슬롯.
        self.assertIn("medical illustration", captured["prompt"])
        self.assertNotIn("Korean people", captured["prompt"])

    def test_thumbnail_style_uses_the_thumbnail_style(self):
        captured = self._captured_prompt(
            image_style=image_service.IMAGE_STYLE_THUMBNAIL,
        )

        self.assertIn("professional photography", captured["prompt"])
        self.assertIn("bright color grading", captured["prompt"])

    def test_default_style_uses_the_channel_style(self):
        captured = self._captured_prompt(
            image_style=image_service.IMAGE_STYLE_DEFAULT, channel="wellbeing",
        )

        self.assertIn("editorial photography", captured["prompt"])

    def test_a_character_hook_scene_still_gets_the_hook_boost(self):
        # scene 1은 썸네일 역할을 겸하므로 인물이어도 hook 강조가
        # 살아 있어야 한다.
        captured = self._captured_prompt(
            image_style=image_service.IMAGE_STYLE_CHARACTER,
            is_hook_scene=True,
        )

        # Sprint75 - hook 강조는 Composition/Lighting 슬롯으로 간다.
        # 카메라는 건드리지 않는다 - 그것은 scene이 정한다.
        self.assertIn("large clear subject filling the frame",
                      captured["prompt"])
        self.assertIn("strong dramatic lighting", captured["prompt"])

    def test_routing_values_are_not_accepted_as_styles(self):
        # "ai"/"real"은 라우팅 어휘다. 스타일 인자로 새어 들어오면
        # 조용히 기본값으로 처리되는 대신 즉시 드러나야 한다.
        for routing_value in (VISUAL_TYPE_AI, VISUAL_TYPE_REAL):
            with self.subTest(value=routing_value):
                with self.assertRaises(ValueError):
                    self._captured_prompt(image_style=routing_value)


if __name__ == "__main__":
    unittest.main()
