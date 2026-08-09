"""
Sprint180 - 지금 어디에서 막혔는가 (Epic 59, Phase 3).

처음 켠 사람은 화면에 있는 것들이 무엇을 뜻하는지 모른다. 자료 준비,
최종 확인, 출력 검사가 각각 제 이야기를 하는데, 그 셋을 이어 붙여
"그래서 지금 무엇을 해야 하는가"로 만드는 일은 사람이 해야 했다.

새로 판정하지 않는다
--------------------
이 파일이 지키는 가장 중요한 것이 그것이다. 상태는 전부 이미 있는
서비스가 낸 답을 이어 붙여 나온다.

    free_workspace.status      내 자료 폴더를 골랐는가
    studio_review.state        대본·이미지·음성·영상이 있는가
    script_quality_check       그 대본이 쓸 만한가
    final_check                지금 누르면 되는가
    output_check               나온 것이 쓸 만한가
    studio_jobs                지금 돌고 있는가

여기서 새 규칙을 하나라도 만들면, 화면이 "준비됨"이라는데 버튼을
누르면 막히는 일이 생긴다. 그때 사람은 둘 중 무엇을 믿어야 할지
모른다.

만들지 않는다
-------------
읽기만 한다. 상태를 물어봤다고 이미지가 생기거나 렌더가 시작되면,
사람은 화면을 여는 것조차 조심스러워진다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import studio as studio_router
from app.services import (
    final_check, free_workspace, onboarding_state, output_check,
    studio_review,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.root = os.path.join(self.home, "내자료")
        self.project = os.path.join(self.home, "프로젝트")
        self.store = os.path.join(self.home, "기억.json")

        os.makedirs(self.project)

        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def workspace(self):
        """내 자료 폴더를 고른 상태."""

        for kind in ("images", "voices"):
            os.makedirs(os.path.join(self.root, kind), exist_ok=True)

        free_workspace.remember(self.store, self.root)

    def script(self, count=2, narration=None):
        """
        대본이 있는 상태.

        길이를 눈대중으로 넣지 않는다 - 짧으면 품질 검사가 먼저
        걸려서, 자료 검사까지 가 보지도 못한다(실제로 그랬다).
        엔진의 추정기에게 물어 관문에 맞춘다.
        """

        from app.services import duration_estimator, duration_optimizer

        if narration is None:
            bodies = [f"{n}번째 동작입니다" for n in range(1, count + 1)]
            at = 0

            while sum(duration_estimator.estimate_duration(b)
                      for b in bodies)                     < duration_optimizer.TARGET_DURATION_SECONDS:
                bodies[at % count] += " 무릎을 천천히 펴 주세요"
                at += 1
        else:
            bodies = [narration] * count

        scenes = [
            {"scene": n,
             "narration": bodies[n - 1],
             "image_prompt": f"동작{n} 스트레칭"}
            for n in range(1, count + 1)
        ]

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "무릎 스트레칭", "hook": "2분",
                       "script": "본문", "character": "40대 남성",
                       "scenes": scenes}, f, ensure_ascii=False)

        return scenes

    def made(self, *kinds, count=2):
        """산출물을 그 자리에 놓는다. 엔진을 부르지 않는다."""

        for number in range(1, count + 1):
            if "image" in kinds:
                path = os.path.join(self.project, "images",
                                    f"scene{number}.png")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "wb").write(b"0" * 100)

            if "voice" in kinds:
                path = os.path.join(self.project, "audio", "scenes",
                                    f"scene{number}.wav")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "wb").write(b"0" * 100)

        if "video" in kinds:
            path = os.path.join(self.project, *output_check.VIDEO_RELATIVE)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").write(b"0" * 5000)

    def now(self, project_path=None):
        return onboarding_state.build(self.store, project_path)


class WhereAmITest(Base):
    """1. 상태."""

    def test_a_brand_new_user_is_at_the_start(self):
        found = self.now()

        self.assertEqual(found["state"], onboarding_state.FIRST_RUN)
        self.assertFalse(found["can_continue"])
        self.assertTrue(found["title"])
        self.assertTrue(found["next_action"])

    def test_without_a_workspace_it_asks_for_one(self):
        """
        프로젝트는 있는데 폴더를 안 골랐다.

        처음이 아니므로 "시작하십시오"가 아니라 "폴더를 고르십시오"다.
        """

        self.script()

        found = self.now(self.project)

        self.assertEqual(found["state"],
                         onboarding_state.WORKSPACE_REQUIRED)

    def test_with_a_workspace_but_no_script_it_asks_for_one(self):
        self.workspace()

        found = self.now(self.project)

        self.assertEqual(found["state"], onboarding_state.SCRIPT_REQUIRED)

    def test_a_script_that_needs_work_is_named(self):
        """
        대본이 있어도 쓸 만하지 않으면 거기서 멈춘다.

        판정은 script_quality_check가 한다 - 여기서 다시 세지 않는다.
        """

        self.workspace()
        self.script(count=1, narration="짧다")

        found = self.now(self.project)

        self.assertEqual(found["state"],
                         onboarding_state.SCRIPT_CHECK_REQUIRED)
        self.assertTrue(found["reasons"])

    def test_missing_assets_are_named(self):
        self.workspace()
        self.script()

        found = self.now(self.project)

        self.assertEqual(found["state"], onboarding_state.ASSET_REQUIRED)

    def test_ready_when_the_final_check_says_so(self):
        self.workspace()
        scenes = self.script()
        self.made("image", "voice")

        self.assertEqual(final_check.build(self.project, scenes)["state"],
                         free_workspace.READY)

        found = self.now(self.project)

        self.assertEqual(found["state"], onboarding_state.READY)
        self.assertTrue(found["can_continue"])

    def test_review_when_the_final_check_says_so(self):
        self.workspace()
        scenes = self.script()
        self.made("image", "voice")

        with patch.object(final_check, "build",
                          return_value={"state": free_workspace.REVIEW,
                                        "problems": [], "warnings": ["보라"]}):
            found = self.now(self.project)

        self.assertEqual(found["state"], onboarding_state.REVIEW_REQUIRED)
        self.assertTrue(found["can_continue"])

    def test_completed_when_the_output_check_says_so(self):
        self.workspace()
        self.script()
        self.made("image", "voice", "video")

        with patch.object(output_check, "build",
                          return_value={"state": output_check.READY,
                                        "issues": [], "video": {}}):
            found = self.now(self.project)

        self.assertEqual(found["state"], onboarding_state.COMPLETED)
        self.assertTrue(found["can_continue"])

    def test_failed_when_the_output_check_says_so(self):
        self.workspace()
        self.script()
        self.made("image", "voice", "video")

        with patch.object(output_check, "build",
                          return_value={"state": output_check.FAILED,
                                        "issues": [{"message": "영상 없음"}],
                                        "video": {}}):
            found = self.now(self.project)

        self.assertEqual(found["state"], onboarding_state.FAILED)
        self.assertTrue(found["reasons"])

    def test_rendering_while_the_job_runs(self):
        self.workspace()
        self.script()

        from app.services import studio_jobs

        with patch.object(studio_jobs, "recent", return_value=[
                {"job_id": "x", "state": "running",
                 "project_id": os.path.basename(self.project),
                 "kind": "generate"}]):
            found = self.now(self.project)

        self.assertEqual(found["state"], onboarding_state.RENDERING)
        self.assertFalse(found["can_continue"])


class AgreementTest(Base):
    """2. 기존 판정과 같은 말을 한다."""

    def test_it_never_disagrees_with_the_final_check(self):
        """
        여기서 READY라고 하면 final_check도 READY다.

        다르면 화면이 "만들 수 있다"는데 버튼이 막히고, 사람은 둘 중
        무엇을 믿어야 할지 모른다.
        """

        self.workspace()
        scenes = self.script()

        for made in ((), ("image",), ("image", "voice")):
            with self.subTest(made=made):
                self.made(*made)

                found = self.now(self.project)
                theirs = final_check.build(self.project, scenes)["state"]

                if found["state"] == onboarding_state.READY:
                    self.assertEqual(theirs, free_workspace.READY)

                if theirs == free_workspace.BLOCKED:
                    self.assertNotEqual(found["state"],
                                        onboarding_state.READY)

    def test_the_steps_come_from_the_same_answers(self):
        """
        여섯 줄은 이미 있는 답을 옮긴 것이다.

        화면이 제 나름대로 세면 줄과 상태가 어긋난다.
        """

        self.workspace()
        self.script()
        self.made("image")

        found = self.now(self.project)
        theirs = studio_review.state(self.project)["done"]

        steps = {step["key"]: step["done"] for step in found["steps"]}

        self.assertTrue(steps["workspace"])
        self.assertEqual(steps["script"], theirs[studio_review.SCRIPT])
        self.assertEqual(steps["image"], theirs[studio_review.IMAGE])
        self.assertEqual(steps["voice"], theirs[studio_review.VOICE])
        self.assertEqual(steps["video"], theirs[studio_review.VIDEO])

    def test_the_six_lines_are_the_declared_ones(self):
        found = self.now()

        self.assertEqual([step["label"] for step in found["steps"]],
                         ["자료 연결", "대본 준비", "이미지 준비",
                          "음성 준비", "영상 제작", "결과 확인"])


class MakesNothingTest(Base):
    """3. 물어봤다고 만들지 않는다."""

    def test_no_maker_is_called(self):
        """
        상태를 물어봤다고 이미지가 생기거나 렌더가 시작되면, 사람은
        화면을 여는 것조차 조심스러워진다.
        """

        from app.services import studio_jobs

        self.workspace()
        self.script()

        with patch.object(studio_review, "generate_script") as script, \
                patch.object(studio_review, "generate_images") as images, \
                patch.object(studio_review, "generate_voices") as voices, \
                patch.object(studio_review, "render") as render, \
                patch.object(studio_jobs, "start") as start:

            self.now(self.project)

            for maker in (script, images, voices, render, start):
                with self.subTest(maker=maker):
                    maker.assert_not_called()

    def test_nothing_new_is_written(self):
        self.workspace()
        self.script()

        before = sorted(os.listdir(self.project))

        self.now(self.project)

        self.assertEqual(sorted(os.listdir(self.project)), before)

    def test_the_source_judges_nothing_by_itself(self):
        """
        기준을 여기서 새로 적지 않는다.

        읽어야 할 서비스의 이름이 소스에 있는지 보고, 새 숫자가
        없는지 본다.
        """

        import re

        source = os.path.join(REPO, "app", "services",
                              "onboarding_state.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for wanted in ("free_workspace", "studio_review",
                       "script_quality_check", "final_check",
                       "output_check"):
            with self.subTest(wanted=wanted):
                self.assertIn(wanted, code)

        for forbidden in ("open(", "makedirs", "generate_", "os.walk"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class ApiTest(Base):
    """4. 서버가 내주는 것."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

        self._project = studio_router._project_path
        self._store = studio_router._workspace_store

        studio_router._project_path = lambda project_id: self.project
        studio_router._workspace_store = lambda: self.store

        self.addCleanup(self._restore)

    def _restore(self):
        studio_router._project_path = self._project
        studio_router._workspace_store = self._store

    def test_it_answers_with_the_declared_fields(self):
        answer = self.client.get("/studio/api/onboarding")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("state", "title", "message", "next_action",
                    "can_continue"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_state_moves_as_the_person_works(self):
        """
        폴더를 고르고, 대본을 넣고, 자료를 놓으면 상태가 따라 움직인다.
        """

        self.assertEqual(self.client.get("/studio/api/onboarding").json()
                         ["state"], onboarding_state.FIRST_RUN)

        self.workspace()

        self.assertEqual(
            self.client.get("/studio/api/onboarding?project_id=p1").json()
            ["state"], onboarding_state.SCRIPT_REQUIRED)

        self.script()

        self.assertEqual(
            self.client.get("/studio/api/onboarding?project_id=p1").json()
            ["state"], onboarding_state.ASSET_REQUIRED)

        self.made("image", "voice")

        self.assertEqual(
            self.client.get("/studio/api/onboarding?project_id=p1").json()
            ["state"], onboarding_state.READY)

    def test_an_unknown_project_does_not_blow_up(self):
        """
        없는 프로젝트를 물어도 화면은 떠 있어야 한다.

        여기서 404를 던지면 첫 화면이 통째로 비어 버린다.
        """

        studio_router._project_path = self._project

        answer = self.client.get("/studio/api/onboarding?project_id=없는것")

        self.assertEqual(answer.status_code, 200)
        self.assertIn("state", answer.json())


class ScreenTest(Base):
    """5. 화면."""

    def test_the_screen_shows_the_six_lines_and_asks_the_server(self):
        """
        여섯 줄의 이름은 화면에 적혀 있지 않다. 서버가 준 것을 그린다.

        처음에는 화면에서 글자를 찾으려 했는데, 그것은 이름이 두 곳에
        적혀 있어야 통과하는 검사다 - 그러면 어느 날 한쪽만 바뀐다.
        여기서는 "서버에 묻고, 받은 이름을 그린다"를 본다.
        """

        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/onboarding", page)
        self.assertIn("step.label", page)
        self.assertIn("found.steps", page)

        # 이름은 서버 한 곳에서만 온다.
        answered = self.now()

        self.assertEqual([step["label"] for step in answered["steps"]],
                         [label for _, label in onboarding_state.STEPS])

    def test_the_buttons_are_the_declared_ones(self):
        page = studio_router.studio_page().body.decode("utf-8")

        for word in ("영상 만들기", "결과 보기", "검토"):
            with self.subTest(word=word):
                self.assertIn(word, page)


if __name__ == "__main__":
    unittest.main()
