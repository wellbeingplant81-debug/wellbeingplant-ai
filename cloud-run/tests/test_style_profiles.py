"""
Sprint75 - 채널 스타일 블록을 슬롯으로 분해한다.

기존 블록(WELLBEING_STYLE 등)은 한 문자열 안에 스타일, 인물 품질, 조명,
카메라, 구도, 부정어가 전부 섞여 있었고 그것이 모든 scene에 통째로
붙었다. 무엇이 어디서 왔는지 알 수 없었고, scene이 정한 값과 싸웠다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.prompts import prompt_elements as slots
from app.prompts import style_profiles
from app.services import image_service


class TestProfileShape(unittest.TestCase):

    def test_every_style_has_a_profile(self):
        for style in image_service.IMAGE_STYLES:
            with self.subTest(style=style):
                profile = style_profiles.resolve(
                    style, channel="wellbeing", is_hook_scene=False,
                )
                self.assertIn(slots.STYLE, profile)
                self.assertIn(slots.NEGATIVE, profile)

    def test_an_unknown_style_is_rejected(self):
        with self.assertRaises(ValueError):
            style_profiles.resolve("ai", channel="wellbeing",
                                   is_hook_scene=False)

    def test_a_profile_never_declares_a_camera(self):
        """카메라는 scene이 정한다. 프로필이 카메라를 들고 있으면
        같은 슬롯을 두 곳에서 쓰게 된다."""

        for style in image_service.IMAGE_STYLES:
            for channel in ("wellbeing", "foodbeat", "mindtail"):
                with self.subTest(style=style, channel=channel):
                    profile = style_profiles.resolve(
                        style, channel=channel, is_hook_scene=False,
                    )
                    self.assertFalse(profile.get(slots.CAMERA))

    def test_a_profile_never_puts_negation_in_a_positive_slot(self):
        for style in image_service.IMAGE_STYLES:
            profile = style_profiles.resolve(
                style, channel="wellbeing", is_hook_scene=False,
            )
            for slot in slots.POSITIVE_ORDER:
                value = profile.get(slot) or ""
                text = value if isinstance(value, str) else " ".join(value)
                with self.subTest(style=style, slot=slot):
                    self.assertNotIn("no ", text.lower())


class TestPersonTermsOnlyForPeople(unittest.TestCase):
    """이 Epic이 고치는 실측 결함."""

    PERSON_TERMS = (
        "korean people", "facial expression", "realistic eyes",
        "skin pores", "human anatomy", "realistic hands",
    )

    def _positive_text(self, style, channel="wellbeing"):
        profile = style_profiles.resolve(
            style, channel=channel, is_hook_scene=False,
        )
        parts = []
        for slot in slots.POSITIVE_ORDER:
            value = profile.get(slot) or ""
            parts.append(value if isinstance(value, str) else " ".join(value))
        return " ".join(parts).lower()

    def test_an_object_scene_is_never_told_to_draw_people(self):
        """오트밀 그릇에 "Korean people, Natural facial expression,
        Realistic eyes"를 요구하던 그 자리다.

        Sprint73에서 이 scene을 다시 그리자 프롬프트에 없던 젊은
        여성의 얼굴이 들어왔고 character_consistency가 95 -> 20으로
        무너졌다. 원인은 Imagen이 아니라 우리 프롬프트였다.
        """

        text = self._positive_text(image_service.IMAGE_STYLE_DEFAULT)

        for term in self.PERSON_TERMS:
            with self.subTest(term=term):
                self.assertNotIn(term, text)

    def test_a_character_scene_still_gets_the_person_quality_terms(self):
        """인물 scene에서는 이 표현들이 여전히 필요하다. 손가락과
        피부 질감은 인물 사진의 품질을 좌우한다."""

        text = self._positive_text(image_service.IMAGE_STYLE_CHARACTER)

        self.assertIn("realistic hands", text)
        self.assertIn("human anatomy", text)

    def test_the_medical_style_still_forbids_people_in_the_negative(self):
        profile = style_profiles.resolve(
            image_service.IMAGE_STYLE_MEDICAL, channel="wellbeing",
            is_hook_scene=False,
        )

        self.assertIn("person", profile[slots.NEGATIVE])


class TestHookScene(unittest.TestCase):

    def test_the_hook_adds_composition_not_a_camera(self):
        hook = style_profiles.resolve(
            image_service.IMAGE_STYLE_DEFAULT, channel="wellbeing",
            is_hook_scene=True,
        )
        plain = style_profiles.resolve(
            image_service.IMAGE_STYLE_DEFAULT, channel="wellbeing",
            is_hook_scene=False,
        )

        self.assertNotEqual(hook[slots.COMPOSITION], plain.get(slots.COMPOSITION))
        self.assertFalse(hook.get(slots.CAMERA))

    def test_the_medical_style_ignores_the_hook_boost(self):
        """Sprint60 - 혈관/세포 scene은 hook이어도 인물 사진 쪽으로
        끌려가면 안 된다."""

        hook = style_profiles.resolve(
            image_service.IMAGE_STYLE_MEDICAL, channel="wellbeing",
            is_hook_scene=True,
        )
        plain = style_profiles.resolve(
            image_service.IMAGE_STYLE_MEDICAL, channel="wellbeing",
            is_hook_scene=False,
        )

        self.assertEqual(hook, plain)


if __name__ == "__main__":
    unittest.main()
