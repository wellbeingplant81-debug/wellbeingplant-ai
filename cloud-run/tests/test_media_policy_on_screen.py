"""
Sprint242 - 사람이 화면에서 고른다 (Media Policy UI).

Sprint241 이 정책을 만들었지만 고를 자리가 없었다
--------------------------------------------------
다섯 갈래와 관문과 상한이 다 있는데, 그것을 바꾸려면 코드를 고쳐야
했다. 사장님이 코드를 여는 일은 일어나지 않는다 - 그러니 그 정책은
있어도 없는 것이었다.

이 Sprint 의 완료 조건은 하나다.

    화면에서 고른 것이 프로젝트에 적히고, 만들 때 그 자리가 그것을
    읽는다.

무엇을 새로 만들지 않았는가
---------------------------
    정책      media_policy 그대로 (다섯 갈래 · 관문 · 상한 · 상태)
    저장      project.json - provider_selection 이 사는 그 파일
    화면      자료 관리 센터 옆. 새 마법사를 세우지 않는다

기본값은 화면에서도 안전 쪽이다
-------------------------------
아무것도 고르지 않은 사람에게 AI 가 켜져 있으면 안 된다. 결제가
잠겨 있고, 잠긴 채로 유료 모델을 부르면 제작이 통째로 멈춘다 -
실제로 그렇게 죽은 EXE 가 있었다.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import media_policy

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _page() -> str:
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _markup() -> str:
    """주석을 걷어낸 화면. 설명이 가드를 속이지 않게 한다."""

    page = re.sub(r"(?m)^[ \t]*//.*$", "", _page())

    return re.sub(r"/\*.*?\*/", "", page, flags=re.S)


class TheHttpDoorTest(unittest.TestCase):
    """화면이 부르는 자리."""

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        patched = patch("app.routers.studio._project_path",
                        return_value=self.project)
        patched.start()
        self.addCleanup(patched.stop)

    def _get(self):
        return self.client.get("/studio/api/review/p1/media-policy")

    def _put(self, mode, scenes=None):
        body = {"mode": mode}

        if scenes is not None:
            body["scene_count"] = scenes

        return self.client.put("/studio/api/review/p1/media-policy", json=body)

    # ── 읽기 ────────────────────────────────────────────────────────
    def test_고른_적이_없으면_안전한_기본값을_준다(self):
        r = self._get()

        self.assertEqual(r.status_code, 200, r.text)

        found = r.json()

        self.assertEqual(found["mode"], media_policy.DEFAULT_MODE)
        self.assertFalse(found["ai_allowed"],
                         "고른 적 없는 사람에게 AI 가 켜져 있다")

    def test_다섯_갈래를_모두_알려_준다(self):
        found = self._get().json()

        self.assertEqual([m["mode"] for m in found["modes"]],
                         list(media_policy.MODES))

        for row in found["modes"]:
            with self.subTest(mode=row["mode"]):
                self.assertTrue(row["label"], row)

    def test_지금_무엇으로_만드는지_사람_말로_적는다(self):
        found = self._get().json()

        self.assertEqual(found["label"],
                         media_policy.LABELS[media_policy.DEFAULT_MODE])

    # ── 쓰기 ────────────────────────────────────────────────────────
    def test_고르면_적힌다(self):
        for mode in media_policy.MODES:
            with self.subTest(mode=mode):
                r = self._put(mode)

                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.json()["mode"], mode)

    def test_적힌_것이_프로젝트에_남는다(self):
        self._put(media_policy.MODE_STOCK)

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            found = json.load(f)

        self.assertEqual(found[media_policy.PROJECT_FIELD],
                         media_policy.MODE_STOCK)

    def test_새로고침해도_그대로다(self):
        """화면을 다시 열면 서버에 다시 묻는다 - 그때도 같아야 한다."""

        self._put(media_policy.MODE_MINE_ONLY)

        self.assertEqual(self._get().json()["mode"],
                         media_policy.MODE_MINE_ONLY)

    def test_프로젝트를_다시_열어도_그대로다(self):
        """
        같은 프로젝트를 다른 요청으로 다시 여는 것. 파일에 적혔으니
        서버가 다시 떠도 살아 있다.
        """

        self._put(media_policy.MODE_MINE_STOCK_AI)

        self.assertEqual(media_policy.mode_for(self.project),
                         media_policy.MODE_MINE_STOCK_AI)

    def test_모르는_갈래는_받지_않는다(self):
        r = self._put("아무거나")

        self.assertEqual(r.status_code, 400)
        self.assertIn("제작 방식", r.json()["detail"])

    def test_다른_칸을_지우지_않는다(self):
        with open(os.path.join(self.project, "project.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"topic": "무릎", "channel": "wellbeing"}, f)

        self._put(media_policy.MODE_STOCK)

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            found = json.load(f)

        self.assertEqual(found["topic"], "무릎")
        self.assertEqual(found["channel"], "wellbeing")


class TheProviderStatesReachTheScreenTest(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        patched = patch("app.routers.studio._project_path",
                        return_value=self.project)
        patched.start()
        self.addCleanup(patched.stop)

    def _providers(self, mode):
        self.client.put("/studio/api/review/p1/media-policy",
                        json={"mode": mode})

        return self.client.get(
            "/studio/api/review/p1/media-policy").json()["providers"]

    def test_AI_금지_모드에서는_전부_DISABLED(self):
        for name, row in self._providers(media_policy.MODE_MINE_THEN_STOCK).items():
            with self.subTest(name=name):
                self.assertEqual(row["state"], "DISABLED")
                self.assertFalse(row["choosable"],
                                 f"{name} 을 고를 수 있게 내놓았다")

    def test_네_가지_상태만_쓴다(self):
        for row in self._providers(media_policy.MODE_MINE_STOCK_AI).values():
            with self.subTest(state=row["state"]):
                self.assertIn(row["state"], media_policy.STATES)

    def test_쓸_수_없는_것은_고를_수_없다(self):
        found = self._providers(media_policy.MODE_MINE_STOCK_AI)

        for name, row in found.items():
            with self.subTest(name=name):
                if row["state"] != "AVAILABLE":
                    self.assertFalse(row["choosable"],
                                     f"{name}({row['state']}) 을 고를 수 있다")

    def test_금액을_지어내지_않는다(self):
        for name, row in self._providers(media_policy.MODE_MINE_STOCK_AI).items():
            with self.subTest(name=name):
                self.assertIn(row.get("cost"), (None, 0, 0.0))


class TheCostSheetReachesTheScreenTest(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        patched = patch("app.routers.studio._project_path",
                        return_value=self.project)
        patched.start()
        self.addCleanup(patched.stop)

    def _plan(self, mode, scenes=6):
        """
        장수는 요청마다 달라진다 - 대본이 아직 없을 수도 있고, 고친
        뒤일 수도 있다. 그래서 저장하지 않고 물을 때 함께 보낸다.
        PUT 의 답에도 같은 값으로 실려 온다.
        """

        put = self.client.put("/studio/api/review/p1/media-policy",
                              json={"mode": mode, "scene_count": scenes})

        self.assertEqual(put.status_code, 200, put.text)

        got = self.client.get(
            "/studio/api/review/p1/media-policy"
            f"?scene_count={scenes}").json()["plan"]

        # 두 자리가 같은 답을 주어야 한다.
        self.assertEqual(got, put.json()["plan"])

        return got

    def test_AI_금지면_0장_0회다(self):
        found = self._plan(media_policy.MODE_MINE_THEN_STOCK)

        self.assertEqual(found["ai_max_images"], 0)
        self.assertEqual(found["ai_max_calls"], 0)

    def test_AI_허용이면_상한_안에서_센다(self):
        found = self._plan(media_policy.MODE_MINE_STOCK_AI, scenes=6)

        self.assertEqual(found["ai_max_images"], 6)
        self.assertLessEqual(found["ai_max_images"],
                             media_policy.AI_IMAGE_HARD_LIMIT)

    def test_비용은_확인_불가다(self):
        found = self._plan(media_policy.MODE_AI_FIRST)

        self.assertIsNone(found["estimated_cost"])
        self.assertTrue(found["cost_unknown"])


class TheScreenShowsTheChoiceTest(unittest.TestCase):
    """화면 쪽 계약. 사람이 보는 자리다."""

    def _block(self) -> str:
        page = _markup()
        at = page.index("function renderMediaPolicy(")

        return page[at:at + 3000]

    def test_자리가_있다(self):
        self.assertIn('id="mediaPolicy"', _markup())

    def test_다섯_갈래를_서버에서_받아_그린다(self):
        """
        처음에 이 시험은 화면에 MEDIA_MODES 상수가 있기를 요구했다.
        그런데 바로 아래 시험은 화면이 갈래 이름을 적지 말라고 한다 -
        두 요구가 서로 모순이었다.

        옳은 쪽은 아래다. 목록을 두 곳이 들면 어느 날 한쪽만 늘어난다.
        그래서 여기서는 **서버가 준 목록을 돌려 그리는가**를 잰다.
        """

        block = self._block()

        self.assertIn("now.modes", block)
        self.assertIn("row.mode", block)
        self.assertIn("row.label", block)

    def test_서버가_준_것을_쓴다(self):
        """
        화면이 제 나름대로 갈래를 짓지 않는다 - 두 곳이 목록을 들면
        어느 날 한쪽만 늘어난다.
        """

        block = self._block()

        self.assertIn("mediaPolicy", block)
        self.assertNotIn("mine_only", block,
                         "화면이 갈래 이름을 다시 적고 있다")

    def test_지금_무엇으로_만드는지_보여_준다(self):
        self.assertIn("policyLabel", _markup())

    def test_AI_금지_모드에서는_Provider_를_내놓지_않는다(self):
        block = self._block()

        self.assertIn("ai_allowed", block)

    def test_고를_수_없는_것은_잠근다(self):
        page = _markup()
        at = page.index("function mediaProviderRow(")
        block = page[at:at + 1200]

        self.assertIn("choosable", block)
        self.assertIn("disabled", block)

    def test_바깥을_직접_부르지_않는다(self):
        block = self._block()

        for outside in ("googleapis", "openai.com", "generativelanguage"):
            with self.subTest(outside=outside):
                self.assertNotIn(outside, block)

    def test_기존_마법사를_깨지_않는다(self):
        """7걸음은 그대로다 - 여기에 여섯 번째 갈래를 만들지 않는다."""

        page = _markup()

        at = page.index("const WIZ_STEPS = [")
        block = page[at:page.index("];", at)]

        self.assertEqual(block.count("label:"), 7)

    def test_자료_관리_센터가_그대로다(self):
        page = _markup()

        self.assertIn('id="mediaLibrary"', page)
        self.assertIn("function renderMediaLibrary(", page)


if __name__ == "__main__":
    unittest.main()
