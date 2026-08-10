"""
Sprint214 - 기억과 준비는 다른 것이다 (Epic 59, Phase 26).

Sprint213 실측에서 화면과 API가 다른 말을 했다.

    프로젝트에 자료를 이은 뒤
        화면    WORKSPACE_REQUIRED — 내 자료 폴더가 필요합니다
                이어갈 수 있는가  False
        제작    200 · 영상이 나옴

화면을 믿는 사람은 이미 이어 둔 자료를 두고 또 고르러 간다.

두 상태가 각각 무엇인가
-----------------------
free_workspace.remembered 는 편의 기억이다. 라이브러리를 훑을 때
root를 안 주면 쓰는 기본값이고, 주면 쳐다보지도 않는다.

    # Sprint152 - 주지 않았으면 정해 둔 폴더를 쓴다.
    #             프로젝트마다 같은 경로를 다시 적게 만들지 않는다.

훑은 결과는 프로젝트 안에 남는다 - local_library.json 이다. 제작이
기대는 것은 그쪽이고, Sprint213이 그것을 증명했다(전역 기억이 빈 채로
영상이 나왔다).

그래서 인정한다
---------------
프로젝트가 제 자료 목록을 갖고 있으면 그 걸음이 하려던 일은 이미
끝나 있다. 새 기준을 만드는 것이 아니라, local_library가 이미 아는
사실을 읽는 것이다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import runtime_paths
from app.services import free_workspace, local_library, onboarding_state

SCRIPT = {
    "title": "무릎 통증 완화 스트레칭",
    "hook": "무릎이 아프십니까",
    "script": "무릎 스트레칭 안내",
    "character": "편안한 옷차림의 사람",
    "scenes": [
        {"scene": 1, "narration": "다리를 천천히 펴 주십시오.",
         "image_prompt": "무릎을 펴고 앉은 사람"},
        {"scene": 2, "narration": "발목을 열 번 움직이십시오.",
         "image_prompt": "발목을 움직이는 발"},
    ],
}


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        self.store = os.path.join(self.home, "free_workspace.json")

        self.project = runtime_paths.ensure(
            os.path.join(self.home, "output", "20260810_214"))

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump(SCRIPT, f, ensure_ascii=False)

    def stuff(self, images=2, voices=2):
        """사람이 제 자료를 모아 둔 폴더."""

        root = os.path.join(self.home, "내자료")

        for name, many, suffix in (("images", images, ".png"),
                                   ("voices", voices, ".wav")):
            where = runtime_paths.ensure(os.path.join(root, name))

            for at in range(1, many + 1):
                with open(os.path.join(where, f"scene{at}{suffix}"),
                          "wb") as f:
                    f.write(b"x")

        return root

    def connect(self, root):
        """라우터가 하는 그대로 - 훑어서 프로젝트에 적는다."""

        local_library.save(self.project, local_library.scan(root))

    def now(self):
        return onboarding_state.build(self.store, self.project)


class TheScreenAgreesTest(Base):
    """1. 자료를 이어 두면 그 걸음을 넘어간다."""

    def test_before_connecting_it_asks_for_the_folder(self):
        found = self.now()

        self.assertEqual(found["state"],
                         onboarding_state.WORKSPACE_REQUIRED)

    def test_after_connecting_it_moves_on(self):
        """
        Sprint213에서 여기가 어긋났다 - 이어 두었는데도 계속
        "폴더가 필요합니다"라고 했다.
        """

        self.connect(self.stuff())

        self.assertNotEqual(self.now()["state"],
                            onboarding_state.WORKSPACE_REQUIRED)

    def test_the_first_step_is_marked_done(self):
        self.connect(self.stuff())

        steps = {row["key"]: row["done"] for row in self.now()["steps"]}

        self.assertIs(steps["workspace"], True)


class NothingElseMovedTest(Base):
    """2. 건드리지 않은 것."""

    def test_without_a_project_it_is_unchanged(self):
        """
        아직 아무것도 없는 사람에게는 예전 그대로다.
        """

        found = onboarding_state.build(self.store, None)

        self.assertEqual(found["state"], onboarding_state.FIRST_RUN)

    def test_remembering_a_folder_still_works(self):
        free_workspace.remember(self.store, self.stuff())

        self.assertNotEqual(self.now()["state"],
                            onboarding_state.WORKSPACE_REQUIRED)

    def test_an_empty_library_is_still_not_ready(self):
        """
        훑기는 했는데 자료가 하나도 없으면 그림도 목소리도 못 고른다.
        """

        self.connect(self.stuff(images=0, voices=0))

        self.assertEqual(self.now()["state"],
                         onboarding_state.WORKSPACE_REQUIRED)

    def test_the_memory_is_not_written_by_looking(self):
        """
        보는 것으로 기억이 생기면 안 된다. 사람이 고른 적이 없다.
        """

        self.connect(self.stuff())
        self.now()

        self.assertIsNone(
            free_workspace.remembered(self.store).get("root"))


class TheSayingIsUnchangedTest(Base):
    """3. 말은 그대로다."""

    def test_the_words_for_each_state_are_untouched(self):
        title, message, action, can = onboarding_state.SAYS[
            onboarding_state.WORKSPACE_REQUIRED]

        self.assertEqual(title, "내 자료 폴더가 필요합니다")
        self.assertEqual(action, "내 자료 폴더 선택")
        self.assertIs(can, False)

    def test_every_state_still_says_what_to_do(self):
        for state, (title, message, action, _) in \
                onboarding_state.SAYS.items():
            with self.subTest(state=state):
                self.assertTrue(title.strip())
                self.assertTrue(message.strip())
                self.assertTrue(action.strip())


if __name__ == "__main__":
    unittest.main()
