"""
Sprint154 - Gemini 채팅에 붙여넣을 요청문을 만든다 (Epic 57, Phase 5).

무료 모드의 대본은 붙여넣기로 온다(chat_import, Sprint104). 그런데
"무엇을 물어봐야 쓸 만한 답이 오는가"는 사람이 알아서 해야 했다.
잘못 물으면 답이 와도 파서가 못 읽는다.

무엇을 지키는가
---------------
    1. 요청문이 만들어진다            test_prompt_builder
    2. 그 요청문이 옳은 것을 요구한다  test_prompt_copy_content
    3. 만드는 동안 밖으로 안 나간다    test_no_external_api_call
    4. 그 답이 실제로 읽힌다          test_script_import_flow

넷째가 이 Sprint의 값어치다. 요청문을 지어내면 사람이 그대로 물어도
돌아온 답을 우리가 못 읽는다 - Sprint153에서 경로를 지어내면 안 됐던
것과 같은 이야기다.

그래서 새로 쓰지 않는다
-----------------------
엔진이 Gemini API에 보내는 그 프롬프트를 그대로 준다. 같은 것을
물으니 같은 모양이 오고, 같은 모양이니 이미 있는 파서가 읽는다.
"""

import ast
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import script_prompt_builder


class PromptBuilderTest(unittest.TestCase):
    """1. 요청문이 만들어진다."""

    def test_prompt_builder(self):
        built = script_prompt_builder.build("40대 허리 건강 운동")

        self.assertIn("40대 허리 건강 운동", built["prompt"])
        self.assertGreater(len(built["prompt"]), 200)

        # 무엇으로 만든 요청문인지 되돌려 준다 - 화면이 그대로 보여
        # 줄 수 있어야 한다.
        self.assertEqual(built["topic"], "40대 허리 건강 운동")
        self.assertEqual(built["scene_count"],
                         script_prompt_builder.DEFAULT_SCENE_COUNT)
        self.assertEqual(built["target_duration"],
                         script_prompt_builder.DEFAULT_TARGET_DURATION)

    def test_the_defaults_come_from_the_engine(self):
        """
        숫자를 여기서 새로 정하지 않는다.

        엔진이 Writer에게 요구하는 값과 다르면, 무료로 만든 대본만
        길이가 어긋난다.
        """

        import inspect

        from app.services import duration_estimator, script_service

        signature = inspect.signature(script_service.generate_script)

        self.assertEqual(
            script_prompt_builder.DEFAULT_SCENE_COUNT,
            signature.parameters["scene_count"].default,
        )
        self.assertEqual(
            script_prompt_builder.DEFAULT_TARGET_DURATION,
            int(duration_estimator.TARGET_DURATION_SECONDS),
        )

    def test_the_numbers_can_be_changed(self):
        built = script_prompt_builder.build(
            "주제", target_duration=60, scene_count=8,
        )

        self.assertIn("8", built["prompt"])
        self.assertIn("60", built["prompt"])
        self.assertEqual(built["scene_count"], 8)

    def test_style_and_audience_are_added_only_when_given(self):
        """
        안 적은 것을 지어내지 않는다.

        "전 연령 대상"이라고 멋대로 적으면 그것은 사용자가 하지 않은
        말이고, 대본이 그쪽으로 끌려간다.
        """

        plain = script_prompt_builder.build("주제")

        # 안 적었으면 그 칸 자체가 없다.
        self.assertNotIn("이번 영상의 추가 조건", plain["prompt"])
        self.assertEqual(plain["style"], "")
        self.assertEqual(plain["audience"], "")

        detailed = script_prompt_builder.build(
            "주제", style="차분한 설명체", audience="40대 직장인",
        )

        self.assertIn("이번 영상의 추가 조건", detailed["prompt"])
        self.assertIn("차분한 설명체", detailed["prompt"])
        self.assertIn("40대 직장인", detailed["prompt"])

        # 하나만 적으면 그 하나만 붙는다.
        only_style = script_prompt_builder.build("주제", style="차분한")

        self.assertIn("차분한", only_style["prompt"])
        self.assertNotIn("보는 사람", only_style["prompt"])

    def test_an_empty_topic_is_refused(self):
        """주제가 없으면 물어볼 것이 없다."""

        with self.assertRaises(ValueError):
            script_prompt_builder.build("   ")

    def test_where_to_save_the_answer(self):
        """
        받은 답을 어디에 두면 되는지 말한다.

        경로는 여기서 정한다 - 아직 아무도 그 폴더를 훑지 않으므로
        local_library에 새 종류를 만들지 않는다.
        """

        built = script_prompt_builder.build("주제")

        self.assertEqual(built["save_to"], "scripts/script.txt")


class PromptContentTest(unittest.TestCase):
    """2. 요청문이 옳은 것을 요구한다."""

    def setUp(self):
        self.prompt = script_prompt_builder.build("40대 허리 건강 운동")["prompt"]

    def test_prompt_copy_content(self):
        """파서가 읽을 수 있는 모양을 요구한다."""

        # JSON을 달라고 한다 - 파서가 가장 믿는 길이다.
        self.assertIn("JSON", self.prompt)

        # 파서가 반드시 있어야 한다고 하는 것들.
        for key in ("title", "scenes", "narration"):
            with self.subTest(key=key):
                self.assertIn(key, self.prompt)

    def test_it_is_the_engine_prompt_not_a_new_one(self):
        """
        엔진이 Gemini에게 보내는 그 프롬프트다.

        따로 쓰면 두 개의 규칙이 생기고, 무료로 만든 대본만 다른
        모양이 된다.
        """

        from app.prompts.script_prompt import SCRIPT_PROMPT

        engine = SCRIPT_PROMPT.substitute(
            topic="40대 허리 건강 운동",
            target_duration=script_prompt_builder.DEFAULT_TARGET_DURATION,
            scene_count=script_prompt_builder.DEFAULT_SCENE_COUNT,
        )

        # 엔진 프롬프트가 통째로 들어 있다(뒤에 덧붙는 것은 있을 수
        # 있지만, 빼거나 고치지 않는다).
        self.assertIn(engine.strip(), self.prompt)

    def test_the_character_rule_follows_the_engine_flag(self):
        """
        인물 일관성 규칙은 엔진이 붙일 때 같이 붙는다.

        한쪽만 붙으면 무료로 만든 대본에서 인물이 scene마다 달라진다.
        """

        from app import config
        from app.prompts.character_consistency_rules import with_character_rules

        marker = with_character_rules("")

        if config.ENABLE_CHARACTER_CONSISTENCY:
            self.assertIn(marker.strip()[:40], self.prompt)
        else:
            self.assertNotIn(marker.strip()[:40], self.prompt)

    def test_it_tells_the_person_what_to_do_with_the_answer(self):
        """받은 답을 어떻게 하라는 말이 있다."""

        built = script_prompt_builder.build("주제")

        self.assertIn("붙여넣", built["how_to_use"])
        self.assertIn(built["save_to"], built["how_to_use"])

    def test_it_never_promises_to_call_gemini(self):
        """
        우리가 대신 물어봐 주겠다고 하지 않는다.

        이 자리는 요청문을 만들 뿐이다 - 부르는 순간 돈이 든다.
        """

        built = script_prompt_builder.build("주제")

        for word in ("자동으로", "대신 요청", "API로"):
            with self.subTest(word=word):
                self.assertNotIn(word, built["how_to_use"])


class NoExternalCallTest(unittest.TestCase):
    """3. 만드는 동안 밖으로 안 나간다."""

    def test_no_external_api_call(self):
        import requests

        with patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            built = script_prompt_builder.build("주제", style="차분한")

            get.assert_not_called()
            post.assert_not_called()

        self.assertIn("주제", built["prompt"])

    def test_the_module_never_imports_a_model_client(self):
        """
        import만으로도 붙어 있으면 언젠가 누군가 부른다.

        script_service는 모듈을 들이는 것만으로 Vertex 클라이언트를
        만든다 - 그것을 여기서 들이면 안 된다.
        """

        with open(script_prompt_builder.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        imported = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        forbidden = (
            "google", "requests", "openai", "anthropic", "vertexai",
            "app.services.script_service",
        )

        for name in sorted(imported):
            for bad in forbidden:
                self.assertFalse(
                    name == bad or name.startswith(bad + "."),
                    f"script_prompt_builder가 {name}을 import한다",
                )

    def test_the_existing_import_provider_did_not_change(self):
        """chat_import는 그대로다. 이 Sprint는 앞쪽만 더한다."""

        from app.production.providers import chat_import

        with open(chat_import.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn("script_prompt_builder", source)


class ScriptImportFlowTest(unittest.TestCase):
    """
    4. 그 요청문에 대한 답이 실제로 읽힌다.

    이 Sprint의 값어치가 여기 있다.
    """

    def test_script_import_flow(self):
        """
        요청문이 요구한 모양 그대로 답이 오면, 파서가 읽는다.

        아래 답은 요청문이 적어 준 JSON 뼈대를 그대로 채운 것이다 -
        모양을 우리가 따로 지어내지 않았다.
        """

        import json
        import re

        from app.production.chat_script_parser import parse_script

        built = script_prompt_builder.build("40대 허리 건강 운동",
                                            scene_count=3)

        # 요청문에 적힌 JSON 뼈대를 그대로 꺼내 채운다.
        skeleton = re.search(r"\{\s*\"title\".*?\n\}", built["prompt"],
                             re.DOTALL)
        self.assertIsNotNone(skeleton, "요청문에 JSON 뼈대가 없다")

        shape = json.loads(skeleton.group(0))

        self.assertIn("title", shape)
        self.assertIn("scenes", shape)
        self.assertIn("narration", shape["scenes"][0])

        answer = json.dumps({
            "title": "40대 허리, 이 동작 하나면 됩니다",
            "hook": "허리가 아프신가요?",
            "script": "전체 대본",
            "character": "40대 남성",
            "scenes": [
                {"scene": n, "narration": f"{n}번째 문장입니다.",
                 "subject": "40대 남성", "action": "허리를 편다",
                 "environment": "거실", "camera": "미디엄 샷",
                 "composition": "중앙", "lighting": "자연광"}
                for n in (1, 2, 3)
            ],
        }, ensure_ascii=False)

        script = parse_script(answer)

        self.assertEqual(script["title"], "40대 허리, 이 동작 하나면 됩니다")
        self.assertEqual(len(script["scenes"]), 3)

        for scene in script["scenes"]:
            with self.subTest(scene=scene["scene"]):
                self.assertTrue(scene["narration"])
                # image_prompt는 요소에서 파생된다 - 무료 경로에서도
                # 이미지 단계가 쓸 것이 있어야 한다.
                self.assertTrue(scene.get("image_prompt"))

    def test_a_fenced_answer_is_read_too(self):
        """
        Gemini는 ```json 으로 감싸서 답하는 일이 잦다.

        요청문이 "JSON만"이라고 해도 그렇다 - 파서가 그것도 읽는다는
        것을 여기서 확인해 둔다.
        """

        from app.production.chat_script_parser import parse_script

        answer = (
            "물론입니다!\n\n```json\n"
            '{"title": "제목", "scenes": ['
            '{"scene": 1, "narration": "문장"}]}\n'
            "```\n도움이 되었길 바랍니다."
        )

        script = parse_script(answer)

        self.assertEqual(script["title"], "제목")
        self.assertEqual(len(script["scenes"]), 1)

    def test_the_endpoint_builds_and_the_import_endpoint_reads(self):
        """화면이 쓰는 두 자리가 실제로 이어진다."""

        import json

        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        built = client.post("/studio/api/script-prompt",
                            json={"topic": "40대 허리 건강 운동",
                                  "scene_count": 2}).json()

        self.assertIn("40대 허리 건강 운동", built["prompt"])

        answer = json.dumps({
            "title": "제목",
            "scenes": [
                {"scene": 1, "narration": "첫 문장", "subject": "사람",
                 "action": "선다", "environment": "실내", "camera": "미디엄",
                 "composition": "중앙", "lighting": "자연광"},
                {"scene": 2, "narration": "둘째 문장", "subject": "사람",
                 "action": "앉는다", "environment": "실내", "camera": "미디엄",
                 "composition": "중앙", "lighting": "자연광"},
            ],
        }, ensure_ascii=False)

        read = client.post("/studio/api/production/import",
                           json={"raw": answer, "topic": "40대 허리 건강 운동"})

        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.json()["scene_count"], 2)

    def test_a_bad_topic_is_refused_by_the_endpoint(self):
        from fastapi.testclient import TestClient

        from app.main import app

        response = TestClient(app).post("/studio/api/script-prompt",
                                        json={"topic": "  "})

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
