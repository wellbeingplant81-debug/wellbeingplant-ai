"""
Sprint179 - 붙여넣기 전에 읽어 본다 (Epic 59, Phase 2).

채팅창이 내놓은 대본이 파서를 통과해도, 영상으로 만들다 보면 뒤에서
걸리는 것들이 있다. 그때는 이미 몇 분을 쓴 뒤이고, 그 자리의 문장은
사람이 읽어도 무엇을 고쳐야 하는지 알 수 없다.

그래서 붙여넣기 전에 한 번 본다.

고쳐 주지 않는다
----------------
읽고 말하기만 한다. 우리가 대신 고치면 사람은 무엇이 잘못됐는지
영영 모르고, 다음에도 같은 자리에서 걸린다. 다시 써 주지도 않고,
모델을 부르지도 않는다.

기준을 여기서 지어내지 않는다
-----------------------------
길이는 엔진이 이미 정해 둔 관문을 그대로 쓴다.

    duration_optimizer.MIN_ACCEPTABLE_SECONDS / MAX_ACCEPTABLE_SECONDS
    duration_optimizer.MAX_PAUSE_SECONDS / MAX_SPEAKING_RATE
    duration_estimator.estimate_duration

여기서 다른 숫자를 정하면 "여기서는 됐다는데 저기서 걸린다"가 된다.
그것은 검사가 없는 것보다 나쁘다.

낱말도 마찬가지다. 내 자료에서 그림을 고르는 규칙은
local_stock_provider._keywords 하나뿐이고, 여기서는 그것을 부른다.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import (
    duration_estimator, duration_optimizer, script_quality_check,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _checked(raw: str) -> dict:
    """
    라우터가 하는 그대로 - 파서에게 먼저 읽히고 나서 살펴본다.

    app.production 은 studio 라우터만 들인다(test_production_architecture).
    서비스가 직접 들이면 그 가드가 막는다 - Sprint166과 Sprint179가
    같은 자리에서 걸렸다. 테스트는 그 선 밖이라 부를 수 있다.
    """

    from app.production.chat_script_parser import ChatImportError
    from app.production.providers.chat_import import ChatImportScriptProvider
    from app.production.stage_request import StageRequest

    script, refused = None, None

    if (raw or "").strip():
        try:
            script = ChatImportScriptProvider().import_content(
                raw, StageRequest(topic=""))
        except ChatImportError as failed:
            refused = str(failed)

    return script_quality_check.check(script, refused=refused)


def _scene(narration, image="무릎 스트레칭", voice="차분하게"):
    scene = {"narration": narration, "image_prompt": image}

    if voice is not None:
        scene["voice_prompt"] = voice

    return scene


def _long_enough(count=6):
    """
    엔진의 관문 안에 들어오는 대본.

    문장을 지어 세지 않는다 - 추정기에게 물어 목표에 닿을 때까지
    한 낱말씩 돌아가며 늘린다. 관문 숫자가 바뀌면 이 도우미가
    따라간다.

    scene마다 목표를 채우면 합이 관문을 넘는다 - 실제로 한 번 그렇게
    58초가 나왔다. 그래서 합을 보고 멈춘다.
    """

    target = duration_optimizer.TARGET_DURATION_SECONDS
    bodies = [f"{n}번째 동작입니다" for n in range(1, count + 1)]

    at = 0

    while sum(duration_estimator.estimate_duration(b)
              for b in bodies) < target:
        bodies[at % count] += " 무릎을 천천히 펴 주세요"
        at += 1

    return [_scene(bodies[n - 1], image=f"동작{n} 스트레칭")
            for n in range(1, count + 1)]


def _raw(scenes=None, **changed):
    found = {
        "title": "무릎 스트레칭 두 가지",
        "hook": "일어나서 2분이면 됩니다",
        "script": "무릎을 펴고 숨을 고릅니다.",
        "character": "40대 남성, 회색 티셔츠",
        "scenes": scenes if scenes is not None else _long_enough(),
    }

    found.update(changed)

    for key, value in list(found.items()):
        if value is None:
            found.pop(key)

    return json.dumps(found, ensure_ascii=False)


class GoodScriptTest(unittest.TestCase):
    """1. 쓸 수 있는 대본은 통과한다."""

    def test_a_claude_answer_passes(self):
        """voice_prompt까지 있는 답 - Claude 요청문이 시키는 모양."""

        found = _checked(_raw())

        self.assertEqual(found["state"], script_quality_check.READY,
                         f"막혔다: {found['reasons']}")
        self.assertEqual(found["reasons"], [])
        self.assertEqual(found["scene_count"], 6)

    def test_a_gemini_answer_passes(self):
        """
        voice_prompt가 없는 답도 통과한다.

        Gemini 요청문은 그것을 달라고 하지 않는다. 없다고 막으면
        Sprint154부터 잘 쓰던 길이 오늘부터 막힌다.
        """

        scenes = [_scene(s["narration"], s["image_prompt"], voice=None)
                  for s in _long_enough()]

        found = _checked(_raw(scenes))

        self.assertEqual(found["state"], script_quality_check.READY,
                         f"막혔다: {found['reasons']}")

    def test_it_says_what_it_looked_at(self):
        found = _checked(_raw())

        self.assertEqual(found["scene_count"], 6)
        self.assertGreater(found["estimated_seconds"], 0)
        self.assertEqual(found["voice_prompt_scenes"], 6)


class StructureTest(unittest.TestCase):
    """2. 있어야 할 것이 있는가."""

    def test_a_broken_json_is_stopped(self):
        """
        파서가 못 읽는 것은 여기서 멈춘다.

        파서의 문장을 그대로 옮긴다 - 우리가 다시 쓰면 두 개의 설명이
        생기고, 사람은 어느 쪽을 믿어야 할지 모른다.
        """

        found = _checked("이건 JSON이 아니다")

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)
        self.assertTrue(found["reasons"])
        self.assertEqual(found["scene_count"], 0)

    def test_an_empty_paste_says_so(self):
        found = _checked("   ")

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)
        self.assertTrue(any("붙여넣" in reason
                            for reason in found["reasons"]))

    def test_a_missing_title_is_named(self):
        found = _checked(_raw(title=None))

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)
        self.assertTrue(any("title" in reason for reason in found["reasons"]),
                        found["reasons"])

    def test_the_character_is_asked_for_only_when_the_engine_wants_it(self):
        """
        인물 묘사를 요구할지는 엔진의 플래그가 정한다.

        여기서 always로 정하면, 그 플래그를 끈 사람의 멀쩡한 대본이
        오늘부터 막힌다.
        """

        from app import config

        with patch.object(config, "ENABLE_CHARACTER_CONSISTENCY", True):
            found = _checked(_raw(character=None))

            self.assertEqual(found["state"],
                             script_quality_check.NEEDS_WORK)
            self.assertTrue(any("character" in reason
                                for reason in found["reasons"]))

        with patch.object(config, "ENABLE_CHARACTER_CONSISTENCY", False):
            found = _checked(_raw(character=None))

            self.assertEqual(found["state"], script_quality_check.READY,
                             f"막혔다: {found['reasons']}")


class SceneTest(unittest.TestCase):
    """3. Scene 하나하나."""

    def test_no_scene_at_all_is_stopped(self):
        found = _checked(_raw(scenes=[]))

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)

    def test_an_empty_narration_is_named_with_its_number(self):
        scenes = _long_enough()
        scenes[2]["narration"] = "   "

        found = _checked(_raw(scenes))

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)
        self.assertTrue(any("3" in reason for reason in found["reasons"]),
                        found["reasons"])

    def test_a_missing_image_prompt_is_named(self):
        scenes = _long_enough()
        scenes[1]["image_prompt"] = ""

        found = _checked(_raw(scenes))

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)
        self.assertTrue(any("2" in reason for reason in found["reasons"]),
                        found["reasons"])

    def test_an_image_prompt_with_no_usable_word_is_named(self):
        """
        낱말을 하나도 못 뽑는 묘사는 내 자료에서 아무것도 못 고른다.

        고르는 규칙을 여기서 새로 만들지 않는다 - local_stock_provider가
        쓰는 그 함수에 물어본다.
        """

        scenes = _long_enough()
        scenes[0]["image_prompt"] = "2026 40"

        from app.providers import local_stock_provider

        self.assertEqual(
            local_stock_provider._keywords(scenes[0]["image_prompt"]), [])

        found = _checked(_raw(scenes))

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)
        self.assertTrue(any("낱말" in reason for reason in found["reasons"]),
                        found["reasons"])

    def test_the_same_line_twice_is_named(self):
        scenes = _long_enough()
        scenes[4]["narration"] = scenes[0]["narration"]

        found = _checked(_raw(scenes))

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)
        self.assertTrue(any("같은" in reason for reason in found["reasons"]),
                        found["reasons"])

    def test_the_same_image_twice_is_named(self):
        """
        같은 그림 묘사는 한 파일이 두 scene에 걸리게 만든다.

        Sprint155 실측에서 실제로 그랬다 - 파일 하나가 모든 scene의
        그림이 됐다.
        """

        scenes = _long_enough()
        scenes[3]["image_prompt"] = scenes[1]["image_prompt"]

        found = _checked(_raw(scenes))

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)
        self.assertTrue(any("그림" in reason for reason in found["reasons"]),
                        found["reasons"])


class DurationTest(unittest.TestCase):
    """4. 영상 길이에 맞는가."""

    def test_too_short_to_ever_reach_the_target(self):
        """
        늘려도 못 채우는 대본.

        엔진은 마지막에 정적을 조금 붙일 수 있다. 그것으로도 안 되면
        Duration Gate에서 걸린다 - 몇 분 뒤에 아는 것보다 지금 아는
        것이 낫다.
        """

        found = _checked(_raw([_scene("짧다")]))

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)
        self.assertTrue(any("짧" in reason for reason in found["reasons"]),
                        found["reasons"])

    def test_too_long_to_ever_fit(self):
        long_line = "무릎을 천천히 펴고 숨을 깊게 들이마십니다 " * 40

        found = _checked(
            _raw([_scene(long_line, image=f"동작{n}") for n in range(1, 4)]))

        self.assertEqual(found["state"], script_quality_check.NEEDS_WORK)
        self.assertTrue(any("깁니다" in reason
                            for reason in found["reasons"]),
                        found["reasons"])

    def test_the_window_comes_from_the_engine(self):
        """
        관문 숫자를 여기서 다시 적지 않는다.

        두 벌이 되면 "여기서는 됐다는데 저기서 걸린다"가 된다.
        """

        import re

        source = os.path.join(REPO, "app", "services",
                              "script_quality_check.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for invented in ("45", "43", "47", "2.0", "3.0"):
            with self.subTest(invented=invented):
                self.assertNotIn(invented, code)

        self.assertIn("duration_optimizer", code)


class NeverFixesTest(unittest.TestCase):
    """5. 고치지 않는다."""

    def test_the_paste_is_not_touched(self):
        raw = _raw()

        _checked(raw)

        self.assertEqual(raw, _raw())

    def test_it_writes_nothing_and_calls_nobody(self):
        import re
        import socket

        source = os.path.join(REPO, "app", "services",
                              "script_quality_check.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for forbidden in ("open(", "atomic_write", "makedirs",
                          "anthropic", "genai", "vertexai", "requests"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)

        def refuse(*args, **kwargs):
            raise AssertionError("밖으로 나갔다")

        with patch.object(socket.socket, "connect", refuse):
            _checked(_raw())


class ParserAgreementTest(unittest.TestCase):
    """6. 통과한 것은 파서가 읽는다."""

    def test_what_passes_here_the_parser_reads(self):
        """
        여기서 준비됐다고 한 것이 가져오기에서 막히면 안 된다.

        두 자리가 다른 말을 하면 사람은 어느 쪽을 믿어야 할지 모른다.
        """

        from app.production.providers.chat_import import (
            ChatImportScriptProvider,
        )
        from app.production.stage_request import StageRequest

        raw = _raw()

        self.assertEqual(_checked(raw)["state"],
                         script_quality_check.READY)

        script = ChatImportScriptProvider().import_content(
            raw, StageRequest(topic="무릎"))

        self.assertEqual(len(script["scenes"]), 6)


class ScreenTest(unittest.TestCase):
    """7. 화면과 서버."""

    def test_the_endpoint_answers(self):
        from fastapi.testclient import TestClient

        from app.main import app

        answer = TestClient(app).post("/studio/api/script-check",
                                      json={"raw": _raw()})

        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.json()["state"],
                         script_quality_check.READY)

    def test_a_bad_paste_is_answered_not_thrown(self):
        """
        못 읽는 대본은 오류가 아니라 답이다.

        400으로 던지면 화면은 "실패"라고만 하고, 무엇을 고쳐야 하는지는
        사라진다.
        """

        from fastapi.testclient import TestClient

        from app.main import app

        answer = TestClient(app).post("/studio/api/script-check",
                                      json={"raw": "이건 JSON이 아니다"})

        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.json()["state"],
                         script_quality_check.NEEDS_WORK)
        self.assertTrue(answer.json()["reasons"])

    def test_the_screen_has_the_button_and_the_two_words(self):
        from app.routers import studio

        page = studio.studio_page().body.decode("utf-8")

        self.assertIn("대본 품질 확인", page)
        self.assertIn("/studio/api/script-check", page)
        self.assertIn(script_quality_check.LABELS[
            script_quality_check.READY], page)
        self.assertIn(script_quality_check.LABELS[
            script_quality_check.NEEDS_WORK], page)

    def test_the_two_words_are_what_the_sprint_asked_for(self):
        self.assertEqual(
            script_quality_check.LABELS[script_quality_check.READY],
            "준비됨")
        self.assertEqual(
            script_quality_check.LABELS[script_quality_check.NEEDS_WORK],
            "수정 필요")


if __name__ == "__main__":
    unittest.main()
