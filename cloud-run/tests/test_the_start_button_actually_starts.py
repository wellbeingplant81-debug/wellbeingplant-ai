"""
Sprint232 - [영상 생성]이 실제로 시작한다 (Sprint231 E2E 후속).

무엇이 있었나
-------------
실제 영상 1편 E2E 에서 STEP7 이 열리지 않았다. 화면에는 "시작하지
못했습니다" 여섯 글자만 떴고 이유가 없었다. 서버 로그도 없었다 -
핸들러에 닿기 전에 거절되었기 때문이다.

    POST /studio/api/jobs -> 422
    creation_mode: Input should be a valid string (input: null)

왜 테스트가 못 잡았나
---------------------
pydantic v2 에서 `creation_mode: str = None` 은 "없어도 되는 문자열"이
아니다. **문자열인데 기본값이 None** 이다. 그래서

    키를 뺀다        지나간다   <- 기존 시험이 하던 것
    null 을 싣는다   422        <- 브라우저가 늘 하는 것

두 가지가 갈린다. studio.html 은 `creation_mode: creationMode || null`
로 언제나 후자를 한다. 같은 뜻인데 전선 위의 모양이 다르고, 시험은
앞의 모양만 재고 있었다.

라우터 안에는 `if request.creation_mode is None: return` 가지가 있다.
그 가지를 지나가라고 쓴 코드가 그 가지에 닿지 못했다 - 검사기가 먼저
막았다.

그래서 여기서는 **전선 위의 모양 그대로** 잰다. 모델을 파이썬으로
불러 재면 이 구멍이 다시 열려도 모른다.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _page() -> str:
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


class TheWireShapeTheBrowserActuallySendsTest(unittest.TestCase):
    """브라우저가 보내는 그 모양으로 잰다."""

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.services import studio_jobs

        self.client = TestClient(app)
        studio_jobs.reset()
        self.addCleanup(studio_jobs.reset)

    def _post(self, body):
        """json= 로 보낸다 - 없는 키와 null 인 키를 구별하기 위해서다."""

        with patch("app.services.studio_jobs.start", return_value="j") as go:
            response = self.client.post("/studio/api/jobs", json=body)

        return response, go

    def test_필드가_없으면_시작한다(self):
        """예전 동작. 이것이 깨지면 안 된다."""

        response, go = self._post({"topic": "주제"})

        self.assertEqual(response.status_code, 200, response.text)
        go.assert_called_once()

    def test_creation_mode_가_null_이어도_시작한다(self):
        """화면의 [영상 생성]이 하는 그것. 이것이 422 였다."""

        response, go = self._post({"topic": "주제", "creation_mode": None})

        self.assertEqual(response.status_code, 200, response.text)
        go.assert_called_once()

    def test_project_id_가_null_이어도_시작한다(self):
        response, go = self._post({"topic": "주제", "project_id": None})

        self.assertEqual(response.status_code, 200, response.text)
        go.assert_called_once()

    def test_화면이_보내는_그대로_보내도_시작한다(self):
        """studio.html 의 startGeneration 이 만드는 본문 그대로."""

        response, go = self._post({
            "topic": "주제", "channel": "wellbeing",
            "project_id": None, "creation_mode": None, "cost_ack": False,
        })

        self.assertEqual(response.status_code, 200, response.text)
        go.assert_called_once()

    def test_문자열_갈래는_예전과_똑같다(self):
        """full_auto 는 확인을 받아야 지나간다 - 그 문이 열리면 안 된다."""

        response, go = self._post({"topic": "주제", "creation_mode": "full_auto"})

        self.assertEqual(response.status_code, 400, response.text)
        go.assert_not_called()

        response, go = self._post({"topic": "주제", "creation_mode": "full_auto",
                                   "cost_ack": True})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("full_auto", go.call_args.args)

    def test_모르는_갈래는_여전히_막힌다(self):
        response, go = self._post({"topic": "주제", "creation_mode": "없는갈래"})

        self.assertEqual(response.status_code, 400, response.text)
        go.assert_not_called()


class TheScreenIsSpecificAboutOptionalFieldsTest(unittest.TestCase):
    """
    같은 모양(`X: str = None`)이 이 라우터에 더 있다. 화면이 지금
    null 을 싣지 않는 자리라서 이번에 고치지 않았지만, 고쳐야 할 두
    자리는 못 박아 둔다 - 다음에 누가 이 모양을 다시 쓰면 걸린다.
    """

    def test_화면이_null_을_싣는_필드는_Optional_이다(self):
        from typing import Optional

        from app.routers.studio import GenerateRequest

        for name in ("project_id", "creation_mode"):
            with self.subTest(field=name):
                found = GenerateRequest.model_fields[name]

                self.assertEqual(found.annotation, Optional[str],
                                 f"{name} 이 null 을 받지 못한다")

    def test_화면은_여전히_null_을_싣는다(self):
        """
        고친 곳이 맞는지 화면 쪽에서도 확인한다. 화면이 언젠가 키를
        빼도록 바뀌면 이 시험이 알려 준다 - 그때는 서버 쪽 이유가
        사라진 것이 아니라 재는 자리가 옮겨간 것이다.
        """

        page = _page()

        self.assertIn("creation_mode: creationMode || null", page)


class TheRefusalTellsWhyTest(unittest.TestCase):
    """
    거절당했을 때 이유가 보여야 한다.

    422 의 detail 은 **배열**이다. 그런데 배열도 typeof 는 "object" 라
    객체 가지로 그냥 들어갔고, message 도 reasons 도 없어서 제목만 남은
    빈 상자가 떴다 - 실제로 그 빈 상자를 보았다.
    """

    def test_배열도_따로_받는다(self):
        page = _page()

        at = page.index("function showScriptRefused(")
        block = page[at:at + 700]

        self.assertIn("Array.isArray(found)", block,
                      "배열을 객체보다 먼저 갈라야 한다")

        self.assertLess(block.index("Array.isArray(found)"),
                        block.index('typeof found !== "object"'),
                        "객체 가지가 배열을 먼저 삼킨다")

    def test_어느_값이_문제인지_적는다(self):
        page = _page()

        at = page.index("function refusalSentence(")
        block = page[at:at + 700]

        self.assertIn("입력값을 확인해주세요", block)
        self.assertIn("item.loc", block, "loc 에서 필드 이름을 꺼내야 한다")

    def test_실제_422_모양으로_문장이_나온다(self):
        """
        서버가 주는 그 모양을 그대로 넣어 본다. 화면 코드를 브라우저
        없이 재는 자리라, 함수 본문을 꺼내 파이썬에서 흉내 낸다 -
        모양이 바뀌면 위의 두 시험이 먼저 걸린다.
        """

        from fastapi.testclient import TestClient

        from app.main import app

        # 진짜 422 를 받아 온다. 모양을 손으로 적지 않는다.
        response = TestClient(app).post(
            "/studio/api/jobs", json={"topic": None})

        self.assertEqual(response.status_code, 422)

        detail = response.json()["detail"]

        self.assertIsInstance(detail, list)

        fields = [
            ".".join(part for part in item.get("loc", [])
                     if isinstance(part, str) and part != "body")
            for item in detail
        ]

        self.assertIn("topic", fields,
                      "loc 에서 사람이 읽을 이름이 나와야 한다")


if __name__ == "__main__":
    unittest.main()
