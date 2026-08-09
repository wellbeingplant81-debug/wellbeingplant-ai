"""
Sprint178 - 어느 채팅창에 물어볼 것인가 (Epic 59, Phase 1).

무료 대본은 붙여넣기로 온다(chat_import, Sprint104). Sprint154가
"무엇을 물어야 하는가"를 만들어 줬는데, 그 요청문은 Gemini 하나만
보고 있었다.

이 파일이 지키는 것
-------------------
    셋 중 무엇을 고르든 파서가 읽는다
    Gemini는 Sprint154와 한 글자도 다르지 않다
    직접 입력은 예전 그대로다
    어느 쪽도 모델을 부르지 않는다

부르지 않는다는 것이 핵심이다
-----------------------------
이 층은 "어느 채팅창에 넣을 글인가"만 정한다. 우리가 대신 물어봐
주는 순간 돈이 들고, 그러면 무료 모드가 아니다.

app/providers/claude_script_provider.py 와 헷갈리지 않는다 - 그쪽은
Claude API를 실제로 부르는 자리이고, 여기는 사람이 제 손으로 붙여넣을
글을 만드는 자리다.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.production.stage_request import StageRequest
from app.services import script_prompt_builder, script_provider

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOPIC = "40대 무릎 통증 완화 스트레칭"


class ChoiceTest(unittest.TestCase):
    """1. 무엇을 고를 수 있는가."""

    def test_the_three_ways_are_declared(self):
        self.assertEqual(
            list(script_provider.PROVIDERS),
            [script_provider.CLAUDE, script_provider.GEMINI,
             script_provider.MANUAL])

    def test_the_default_is_what_sprint154_did(self):
        """
        고르지 않으면 예전 그대로다.

        예전 화면과 예전 요청이 그대로 들어와도 달라지는 것이 없어야
        한다.
        """

        self.assertEqual(script_provider.DEFAULT, script_provider.GEMINI)

    def test_an_unknown_way_is_refused(self):
        with self.assertRaises(ValueError):
            script_provider.build("chatgpt_chat", topic=TOPIC)

    def test_every_way_has_a_name_people_read(self):
        for name in script_provider.PROVIDERS:
            with self.subTest(name=name):
                self.assertTrue(script_provider.label(name))


class GeminiUnchangedTest(unittest.TestCase):
    """2. Gemini는 Sprint154 그대로."""

    def test_the_prompt_is_byte_for_byte_the_old_one(self):
        """
        한 글자라도 달라지면 무료로 만든 대본만 모양이 어긋난다.

        그 어긋남은 며칠 뒤 자막이나 이미지 단계에서 드러난다.
        """

        old = script_prompt_builder.build(TOPIC, style="차분하게",
                                          audience="40대")
        new = script_provider.build(script_provider.GEMINI, topic=TOPIC,
                                    style="차분하게", audience="40대")

        self.assertEqual(new["prompt"], old["prompt"])
        self.assertEqual(new["how_to_use"], old["how_to_use"])
        self.assertEqual(new["save_to"], old["save_to"])

    def test_it_says_which_way_it_was(self):
        found = script_provider.build(script_provider.GEMINI, topic=TOPIC)

        self.assertEqual(found["provider"], script_provider.GEMINI)


class ClaudeTest(unittest.TestCase):
    """3. Claude 요청문."""

    def setUp(self):
        self.found = script_provider.build(script_provider.CLAUDE,
                                           topic=TOPIC)

    def test_it_keeps_the_engine_template(self):
        """
        엔진이 쓰는 그 요청문 위에 얹는다.

        여기서 새로 쓰면 두 개의 규칙이 생기고, Claude로 만든 대본만
        다른 모양이 된다 - Sprint154가 Gemini에서 피한 그 일이다.
        """

        engine = script_prompt_builder.build(TOPIC)["prompt"]

        self.assertIn(engine, self.found["prompt"])

    def test_it_asks_for_the_shape_we_read(self):
        prompt = self.found["prompt"]

        for wanted in ("title", "hook", "script", "character", "scenes",
                       "narration", "image_prompt", "voice_prompt"):
            with self.subTest(wanted=wanted):
                self.assertIn(wanted, prompt)

    def test_it_tells_the_person_which_window(self):
        self.assertIn("Claude", self.found["how_to_use"])
        self.assertNotIn("Gemini", self.found["how_to_use"])

    def test_it_says_which_way_it_was(self):
        self.assertEqual(self.found["provider"], script_provider.CLAUDE)


class ManualTest(unittest.TestCase):
    """4. 직접 입력은 예전 그대로."""

    def test_there_is_nothing_to_ask(self):
        """
        직접 쓰는 사람에게는 물어볼 채팅창이 없다.

        빈 요청문을 만들어 주면 사람은 그것을 어딘가에 붙여넣으려
        한다.
        """

        found = script_provider.build(script_provider.MANUAL)

        self.assertEqual(found["provider"], script_provider.MANUAL)
        self.assertIsNone(found["prompt"])
        self.assertTrue(found["how_to_use"])

    def test_a_topic_is_not_required(self):
        """직접 쓰는데 주제를 내라고 막지 않는다."""

        script_provider.build(script_provider.MANUAL)

    def test_the_other_two_need_a_topic(self):
        for name in (script_provider.CLAUDE, script_provider.GEMINI):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    script_provider.build(name, topic="   ")


class SameParserTest(unittest.TestCase):
    """5. 셋이 같은 파서로 들어간다."""

    def _answer(self, with_voice: bool) -> str:
        """그 요청문을 받은 채팅창이 내놓을 법한 답."""

        scene = {
            "narration": "무릎을 천천히 펴 주세요.",
            "image_prompt": "무릎 스트레칭",
        }

        if with_voice:
            scene["voice_prompt"] = "차분하고 낮은 목소리로"

        return json.dumps({
            "title": "무릎 스트레칭 두 가지",
            "hook": "2분이면 됩니다",
            "script": "무릎을 펴고 숨을 고릅니다.",
            "character": "40대 남성",
            "scenes": [scene],
        }, ensure_ascii=False)

    def test_all_three_answers_reach_the_same_scenes(self):
        from app.production.providers.chat_import import (
            ChatImportScriptProvider,
        )

        provider = ChatImportScriptProvider()

        for with_voice in (True, False):
            with self.subTest(with_voice=with_voice):
                script = provider.import_content(
                    self._answer(with_voice), StageRequest(topic=TOPIC))

                self.assertEqual(len(script["scenes"]), 1)

                scene = script["scenes"][0]

                self.assertEqual(scene["narration"], "무릎을 천천히 펴 주세요.")
                self.assertEqual(scene["image_prompt"], "무릎 스트레칭")

    def test_the_voice_line_is_not_thrown_away(self):
        """
        달라고 해 놓고 버리지 않는다.

        Claude에게 voice_prompt를 내라고 하면서 파서가 그것을 버리면,
        우리는 사람에게 쓸모없는 일을 시킨 것이 된다. 아직 아무도
        읽지 않지만 적힌 대로 남긴다.
        """

        from app.production.providers.chat_import import (
            ChatImportScriptProvider,
        )

        script = ChatImportScriptProvider().import_content(
            self._answer(True), StageRequest(topic=TOPIC))

        self.assertEqual(script["scenes"][0]["voice_prompt"],
                         "차분하고 낮은 목소리로")

    def test_an_answer_without_it_has_no_empty_hole(self):
        from app.production.providers.chat_import import (
            ChatImportScriptProvider,
        )

        script = ChatImportScriptProvider().import_content(
            self._answer(False), StageRequest(topic=TOPIC))

        self.assertNotIn("voice_prompt", script["scenes"][0])


class NoApiTest(unittest.TestCase):
    """6. 아무것도 부르지 않는다."""

    def test_no_model_client_is_touched(self):
        """
        요청문을 만드는 동안 밖으로 나가는 길이 열리지 않는다.

        열리면 그 순간 돈이 들고, 무료 모드라는 말이 거짓이 된다.
        """

        import socket

        def refuse(*args, **kwargs):
            raise AssertionError("밖으로 나갔다")

        with patch.object(socket.socket, "connect", refuse), \
                patch.object(socket.socket, "connect_ex", refuse):

            for name in script_provider.PROVIDERS:
                with self.subTest(name=name):
                    script_provider.build(name, topic=TOPIC)

    def test_the_source_names_no_client(self):
        import re

        source = os.path.join(REPO, "app", "services", "script_provider.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for forbidden in ("anthropic", "genai", "vertexai", "requests",
                          "httpx", "openai"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class ScreenTest(unittest.TestCase):
    """7. 화면이 고른 것과 서버가 아는 것이 같다."""

    def test_the_screen_offers_exactly_these_three(self):
        from app.routers import studio

        page = studio.studio_page().body.decode("utf-8")

        for name in script_provider.PROVIDERS:
            with self.subTest(name=name):
                self.assertIn(name, page)
                self.assertIn(script_provider.label(name), page)

    def test_the_screen_asks_the_server_for_the_prompt(self):
        from app.routers import studio

        page = studio.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/script-prompt", page)

    def test_the_endpoint_takes_the_choice(self):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        answer = client.post("/studio/api/script-prompt",
                             json={"topic": TOPIC,
                                   "provider": script_provider.CLAUDE})

        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.json()["provider"], script_provider.CLAUDE)
        self.assertIn("voice_prompt", answer.json()["prompt"])

    def test_an_old_request_still_works(self):
        """
        고르지 않고 보내던 예전 화면이 그대로 돈다.

        묶어 보낸 프로그램에는 예전 화면이 들어 있을 수 있다.
        """

        from fastapi.testclient import TestClient

        from app.main import app

        answer = TestClient(app).post("/studio/api/script-prompt",
                                      json={"topic": TOPIC})

        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.json()["provider"], script_provider.GEMINI)
        self.assertEqual(answer.json()["prompt"],
                         script_prompt_builder.build(TOPIC)["prompt"])

    def test_an_unknown_choice_is_refused_with_a_readable_line(self):
        from fastapi.testclient import TestClient

        from app.main import app

        answer = TestClient(app).post("/studio/api/script-prompt",
                                      json={"topic": TOPIC,
                                            "provider": "chatgpt_chat"})

        self.assertEqual(answer.status_code, 400)
        self.assertIn("chatgpt_chat", answer.json()["detail"])


class NothingIsStoredTest(unittest.TestCase):
    """8. 아무것도 저장하지 않는다."""

    def test_building_a_prompt_writes_nothing(self):
        """
        로그인 정보도, 키도, 대본도, 채팅 내용도 남기지 않는다.

        이 층은 글자를 만들 뿐이다.
        """

        import re

        source = os.path.join(REPO, "app", "services", "script_provider.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for forbidden in ("open(", "atomic_write", "makedirs", "os.environ"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
