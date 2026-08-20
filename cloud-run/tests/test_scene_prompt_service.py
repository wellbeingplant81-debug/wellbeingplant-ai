"""
Sprint75 - Writer가 문장 하나가 아니라 요소를 내놓는다.

Writer는 이제 scene마다 subject/action/environment/camera/composition/
lighting을 따로 적는다. image_prompt는 그 요소들에서 파생된다 -
스톡 검색(extract_search_query)과 품질 평가가 계속 그 필드를 읽으므로
없앨 수 없고, 없앨 이유도 없다.

파생된 image_prompt에는 라벨을 붙이지 않는다. 라벨이 붙은 구조는
Imagen에 보내는 프롬프트의 형태이고, 검색 키워드 추출은 자연스러운
문장을 전제로 하기 때문이다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.prompts import prompt_elements as slots
from app.services import scene_prompt_service


class TestSceneElements(unittest.TestCase):

    def _scene(self, **overrides):
        scene = {
            "scene": 2,
            "narration": "물 한 잔이 시작입니다",
            "subject": "a 50s Korean man",
            "action": "drinking a glass of water",
            "environment": "a bright modern kitchen",
            "camera": "eye-level medium shot",
            "composition": "rule of thirds",
            "lighting": "gentle morning sunlight",
        }
        scene.update(overrides)
        return scene

    def test_the_element_fields_are_collected(self):
        elements = scene_prompt_service.scene_elements(self._scene())

        self.assertEqual(elements[slots.SUBJECT], "a 50s Korean man")
        self.assertEqual(elements[slots.CAMERA], "eye-level medium shot")

    def test_narration_and_scene_number_are_not_elements(self):
        elements = scene_prompt_service.scene_elements(self._scene())

        self.assertNotIn("narration", elements)
        self.assertNotIn("scene", elements)

    def test_empty_elements_are_dropped(self):
        elements = scene_prompt_service.scene_elements(
            self._scene(composition="", lighting=None),
        )

        self.assertNotIn(slots.COMPOSITION, elements)
        self.assertNotIn(slots.LIGHTING, elements)

    def test_a_legacy_scene_has_no_elements(self):
        legacy = {"scene": 1, "narration": "x", "image_prompt": "a bowl"}

        self.assertEqual(scene_prompt_service.scene_elements(legacy), {})


class TestDerivedImagePrompt(unittest.TestCase):

    def test_image_prompt_is_built_from_the_elements(self):
        scenes = scene_prompt_service.apply_prompt_elements([
            {
                "scene": 1,
                "subject": "a 50s Korean man",
                "action": "sitting up in bed",
                "environment": "a sunlit bedroom",
                "camera": "close-up",
                "lighting": "soft morning light",
            }
        ])

        prompt = scenes[0]["image_prompt"]

        self.assertIn("a 50s Korean man", prompt)
        self.assertIn("sitting up in bed", prompt)
        self.assertIn("close-up", prompt)

    def test_the_derived_prompt_carries_no_labels(self):
        """검색 키워드 추출이 읽는 필드다. "Subject:" 같은 라벨이
        들어가면 그것이 키워드가 된다."""

        scenes = scene_prompt_service.apply_prompt_elements([
            {"scene": 1, "subject": "a ceramic bowl of oatmeal",
             "camera": "top-down view"},
        ])

        prompt = scenes[0]["image_prompt"]

        for label in slots.LABELS.values():
            self.assertNotIn(f"{label}:", prompt)

    def test_an_existing_image_prompt_is_not_overwritten_when_no_elements(self):
        """구버전 대본은 그대로 돈다."""

        scenes = scene_prompt_service.apply_prompt_elements([
            {"scene": 1, "image_prompt": "a bowl of oatmeal, top-down"},
        ])

        self.assertEqual(
            scenes[0]["image_prompt"], "a bowl of oatmeal, top-down",
        )

    def test_the_input_scenes_are_not_mutated(self):
        original = {"scene": 1, "subject": "a bowl"}

        scene_prompt_service.apply_prompt_elements([original])

        self.assertNotIn("image_prompt", original)

    def test_a_scene_with_neither_elements_nor_prompt_is_left_alone(self):
        # Writer가 실패한 경우까지 여기서 막지는 않는다. 그것은
        # script_service가 판단할 일이고, 여기서 조용히 지어내면
        # 무엇이 잘못됐는지 가려진다.
        scenes = scene_prompt_service.apply_prompt_elements([{"scene": 1}])

        self.assertNotIn("image_prompt", scenes[0])


class TestCharacterReference(unittest.TestCase):
    """Reference 슬롯 - 인물 scene에만 앵커를 넣는다."""

    def test_a_character_scene_gets_the_reference(self):
        elements = scene_prompt_service.scene_elements(
            {"scene": 1, "subject": "the man", "character_scene": True},
            character="a 50s Korean man with short neat black hair",
        )

        self.assertEqual(
            elements[slots.REFERENCE],
            "a 50s Korean man with short neat black hair",
        )

    def test_a_non_character_scene_gets_no_reference(self):
        """오트밀 그릇에 인물 앵커를 붙이지 않는다."""

        elements = scene_prompt_service.scene_elements(
            {"scene": 4, "subject": "a ceramic bowl of oatmeal"},
            character="a 50s Korean man with short neat black hair",
        )

        self.assertNotIn(slots.REFERENCE, elements)



class TestCharacterAnchorReachesTheScene(unittest.TestCase):
    """Sprint75 실측 - Reference 슬롯을 만들어 놓고 아무도 채우지
    않았다.

    Writer에게 요소를 짧게 쓰라고 지시하면서 동시에 긴 외형 묘사를 매
    Scene 반복하라고 요구했다. Writer는 짧은 쪽을 택했고, 텍스트는
    Scene마다 동일했는데도 character_consistency가 40으로 떨어졌다
    (기존 방식 3회는 100/95/95).

    외형 묘사는 대본 최상위 character 한 곳에 두고, 인물 Scene에만
    Reference로 붙인다.
    """

    CHARACTER = ("a 50s Korean man with short salt-and-pepper hair, "
                 "thin rectangular glasses, clean-shaven, warm friendly face")

    def test_the_anchor_is_attached_to_character_scenes(self):
        scenes = scene_prompt_service.attach_character_reference(
            [
                {"scene": 1, "subject": "the same man", "character_scene": True},
                {"scene": 2, "subject": "a bowl of oatmeal"},
            ],
            self.CHARACTER,
        )

        self.assertEqual(
            scenes[0][scene_prompt_service.CHARACTER_REFERENCE_FIELD],
            self.CHARACTER,
        )
        self.assertNotIn(
            scene_prompt_service.CHARACTER_REFERENCE_FIELD, scenes[1],
        )

    def test_the_anchor_reaches_the_reference_slot(self):
        scenes = scene_prompt_service.attach_character_reference(
            [{"scene": 1, "subject": "the same man", "character_scene": True}],
            self.CHARACTER,
        )

        elements = scene_prompt_service.scene_elements(scenes[0])

        self.assertEqual(elements[slots.REFERENCE], self.CHARACTER)

    def test_no_character_in_the_script_changes_nothing(self):
        original = [{"scene": 1, "subject": "the same man",
                     "character_scene": True}]

        scenes = scene_prompt_service.attach_character_reference(original, "")

        self.assertNotIn(
            scene_prompt_service.CHARACTER_REFERENCE_FIELD, scenes[0],
        )

    def test_the_input_is_not_mutated(self):
        original = {"scene": 1, "subject": "x", "character_scene": True}

        scene_prompt_service.attach_character_reference(
            [original], self.CHARACTER,
        )

        self.assertNotIn(
            scene_prompt_service.CHARACTER_REFERENCE_FIELD, original,
        )



class TestThumbnailKeepsTheCharacter(unittest.TestCase):
    """Sprint75 실측 - 앵커를 대본 최상위로 옮기면서 썸네일이 인물을
    잃었다.

    예전에는 썸네일 프롬프트가 scene 1의 image_prompt를 통째로 품었고,
    거기에 인물 외형이 문장으로 들어 있었다. 이제 scene 1의 subject는
    "the same man"처럼 짧고 외형은 최상위 character에 있는데,
    thumbnail_service는 그 필드를 읽지 않았다.

    결과: 영상 속 인물 일관성은 95인데 썸네일만
    consistency_with_scene1 = 0 - "썸네일 속 인물이 영상의 주인공과
    완전히 다른 사람입니다".
    """

    def setUp(self):
        from app.services import thumbnail_service
        self.thumbnail_service = thumbnail_service

    def test_the_character_reference_reaches_the_reference_slot(self):
        from unittest.mock import patch

        captured = {}

        def fake_generate(prompt, output_file, channel="wellbeing",
                          is_hook_scene=False, image_style=None,
                          elements=None):
            captured["elements"] = elements
            return output_file

        # Sprint243 - 이 시험은 **AI 로 썸네일을 그릴 때** 인물 앵커가
        # 프롬프트에 닿는지를 잰다. 제품의 기본값은 AI 이미지 생성
        # 금지(결제 잠금)라, 그 전제를 적어야 그 경로로 들어간다.
        #
        # 경로가 "/tmp/p" 라 폴더가 없어 project.json 을 적을 수 없다.
        # 그래서 판정만 그 블록에서 허용으로 둔다 - assertion 은 한
        # 글자도 바뀌지 않는다.
        from app.services import media_policy

        with patch.object(media_policy, "ai_allowed", return_value=True):
            with patch.object(
                self.thumbnail_service, "generate_image",
                side_effect=fake_generate,
            ):
                self.thumbnail_service.create_thumbnail(
                    "제목", "주제", "/tmp/p", "wellbeing",
                    scene1_narration="나레이션",
                    scene1_image_prompt="the same man waking up",
                    character_reference=(
                        "a 50s Korean man with thin glasses"),
                )

        self.assertEqual(
            captured["elements"][slots.REFERENCE],
            "a 50s Korean man with thin glasses",
        )

    def test_no_character_means_no_reference_slot(self):
        from unittest.mock import patch

        captured = {}

        def fake_generate(prompt, output_file, channel="wellbeing",
                          is_hook_scene=False, image_style=None,
                          elements=None):
            captured["elements"] = elements
            return output_file

        # Sprint243 - 이 시험은 **AI 로 썸네일을 그릴 때** 인물 앵커가
        # 프롬프트에 닿는지를 잰다. 제품의 기본값은 AI 이미지 생성
        # 금지(결제 잠금)라, 그 전제를 적어야 그 경로로 들어간다.
        #
        # 경로가 "/tmp/p" 라 폴더가 없어 project.json 을 적을 수 없다.
        # 그래서 판정만 그 블록에서 허용으로 둔다 - assertion 은 한
        # 글자도 바뀌지 않는다.
        from app.services import media_policy

        with patch.object(media_policy, "ai_allowed", return_value=True):
            with patch.object(
                self.thumbnail_service, "generate_image",
                side_effect=fake_generate,
            ):
                self.thumbnail_service.create_thumbnail(
                    "제목", "주제", "/tmp/p", "wellbeing",
                    scene1_image_prompt="a bowl of oatmeal",
                )

        self.assertNotIn(slots.REFERENCE, captured["elements"] or {})


if __name__ == "__main__":
    unittest.main()
