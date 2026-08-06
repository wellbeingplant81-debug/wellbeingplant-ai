"""
Sprint75 - Prompt Intelligence v2.

지금까지 이미지 프롬프트는 문장 하나에 채널 스타일 블록을 통째로
이어붙여 만들었다. 그 블록이 무엇을 담고 있었는지 실측한 것이 이
Epic의 출발점이다.

오트밀 그릇 한 장을 그리려고 Imagen에 보낸 프롬프트는 이렇게 시작했다.

    Ultra realistic, Photorealistic, ...
    Korean people, Natural facial expression, Realistic eyes,
    Natural skin pores, Healthy skin, Correct human anatomy,
    Realistic hands, Correct fingers,
    ...
    85mm portrait photography, Professional depth of field,
    ...
    No text, No watermark, No logo, ...

    A beautifully styled top-down view of a ceramic bowl filled with
    creamy oatmeal...

세 가지가 한꺼번에 잘못돼 있다.

1. 사물 scene에 사람을 요구한다. Sprint73에서 이 scene을 다시 그렸을
   때 프롬프트에 없던 젊은 여성의 얼굴이 그릇 위로 들어왔고
   character_consistency가 95에서 20으로 무너졌다. 그때는 "Imagen이
   사람을 그려 넣는다"고 적었는데, 실제로는 우리가 사람을 달라고 했다.

2. 카메라를 두 곳에서 쓴다. 스타일 블록의 "85mm portrait photography"가
   scene이 요구한 "top-down view"와 정면으로 싸운다. Sprint74에서 후보
   두 장이 똑같이 'wide shot'을 구현하지 못한 것도 같은 이유다 - 후보
   추첨의 문제가 아니라 프롬프트 안의 충돌이었다.

3. 부정을 긍정문에 넣는다. "No text"가 positive prompt에 들어가 있고,
   같은 내용이 negative_prompt로도 따로 간다. 확산 모델은 긍정문의
   부정을 잘 처리하지 못한다.

이 저장소에서 반복된 결함 유형 그대로다 - 한 슬롯을 두 곳에서 쓴다.
Composer는 슬롯을 하나씩만 채우게 만든다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.prompts import prompt_elements as slots
from app.services import prompt_composer


class TestSlotVocabulary(unittest.TestCase):

    def test_the_ten_elements_are_declared(self):
        self.assertEqual(
            set(slots.ELEMENTS),
            {
                slots.SUBJECT, slots.ACTION, slots.ENVIRONMENT,
                slots.CAMERA, slots.COMPOSITION, slots.LIGHTING,
                slots.STYLE, slots.NEGATIVE, slots.REFERENCE,
                slots.CONSTRAINTS,
            },
        )

    def test_negative_is_not_a_positive_slot(self):
        """부정은 negative_prompt로만 간다."""

        self.assertNotIn(slots.NEGATIVE, slots.POSITIVE_ORDER)

    def test_every_positive_slot_has_a_label(self):
        for slot in slots.POSITIVE_ORDER:
            with self.subTest(slot=slot):
                self.assertTrue(slots.LABELS[slot])


class TestCompose(unittest.TestCase):

    def _full(self):
        return {
            slots.SUBJECT: "a 50s Korean man",
            slots.ACTION: "drinking a glass of water",
            slots.ENVIRONMENT: "a bright modern kitchen",
            slots.CAMERA: "eye-level medium shot",
            slots.COMPOSITION: "rule of thirds",
            slots.LIGHTING: "soft morning sunlight",
            slots.STYLE: "editorial photography",
            slots.REFERENCE: "short neat black hair, kind face",
            slots.CONSTRAINTS: "vertical 9:16",
            slots.NEGATIVE: "text, watermark",
        }

    def test_the_order_is_fixed_regardless_of_dict_order(self):
        forward = prompt_composer.compose(self._full())

        reversed_input = dict(reversed(list(self._full().items())))
        backward = prompt_composer.compose(reversed_input)

        self.assertEqual(forward.positive, backward.positive)

    def test_slots_appear_in_the_declared_order(self):
        composed = prompt_composer.compose(self._full())

        positions = [
            composed.positive.index(slots.LABELS[slot])
            for slot in slots.POSITIVE_ORDER
        ]

        self.assertEqual(positions, sorted(positions))

    def test_the_negative_never_reaches_the_positive_prompt(self):
        composed = prompt_composer.compose(self._full())

        self.assertNotIn("text, watermark", composed.positive)
        self.assertEqual(composed.negative, "text, watermark")

    def test_an_empty_slot_is_omitted_entirely(self):
        elements = self._full()
        elements[slots.REFERENCE] = ""
        del elements[slots.COMPOSITION]

        composed = prompt_composer.compose(elements)

        self.assertNotIn(slots.LABELS[slots.REFERENCE], composed.positive)
        self.assertNotIn(slots.LABELS[slots.COMPOSITION], composed.positive)
        self.assertIn(slots.LABELS[slots.SUBJECT], composed.positive)

    def test_a_list_slot_is_joined(self):
        elements = self._full()
        elements[slots.STYLE] = ["editorial photography", "ultra detailed"]

        composed = prompt_composer.compose(elements)

        self.assertIn("editorial photography, ultra detailed", composed.positive)

    def test_a_subject_is_required(self):
        """피사체 없는 프롬프트는 버그다. 조용히 넘기지 않는다."""

        elements = self._full()
        del elements[slots.SUBJECT]

        with self.assertRaises(ValueError):
            prompt_composer.compose(elements)

    def test_an_unknown_slot_is_rejected(self):
        """Sprint71의 교훈 - 모르는 값은 조용히 기본값으로 처리하지
        않고 즉시 거부한다. 오타가 소리 없이 사라지면 다음에 같은
        혼선이 또 생긴다."""

        elements = self._full()
        elements["camara"] = "top-down"

        with self.assertRaises(ValueError):
            prompt_composer.compose(elements)

    def test_no_negation_words_survive_in_the_positive_prompt(self):
        elements = self._full()
        elements[slots.STYLE] = ["editorial photography", "No text", "no logo"]

        composed = prompt_composer.compose(elements)

        for banned in ("No text", "no logo"):
            self.assertNotIn(banned, composed.positive)

        # 버리지 않고 negative로 옮긴다.
        self.assertIn("text", composed.negative)
        self.assertIn("logo", composed.negative)


class TestOneSlotOneSource(unittest.TestCase):
    """이 Epic의 핵심 계약."""

    def test_the_scene_camera_wins_over_a_profile_default(self):
        """카메라를 두 곳에서 쓰지 않는다.

        스타일 블록의 "85mm portrait photography"가 scene의 "top-down
        view"와 싸워서, Sprint74의 후보 두 장이 똑같이 요구된 앵글을
        구현하지 못했다.
        """

        merged = prompt_composer.merge(
            profile={slots.CAMERA: "85mm portrait photography",
                     slots.STYLE: "editorial photography"},
            scene={slots.SUBJECT: "a ceramic bowl of oatmeal",
                   slots.CAMERA: "top-down view"},
        )

        self.assertEqual(merged[slots.CAMERA], "top-down view")
        self.assertEqual(merged[slots.STYLE], "editorial photography")

    def test_the_profile_fills_only_what_the_scene_left_empty(self):
        merged = prompt_composer.merge(
            profile={slots.LIGHTING: "golden hour lighting"},
            scene={slots.SUBJECT: "a bowl", slots.LIGHTING: ""},
        )

        self.assertEqual(merged[slots.LIGHTING], "golden hour lighting")

    def test_negatives_from_both_sides_are_combined(self):
        merged = prompt_composer.merge(
            profile={slots.NEGATIVE: "text, watermark"},
            scene={slots.SUBJECT: "a bowl", slots.NEGATIVE: "people"},
        )

        self.assertIn("text", merged[slots.NEGATIVE])
        self.assertIn("people", merged[slots.NEGATIVE])


if __name__ == "__main__":
    unittest.main()
