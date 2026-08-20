"""
Sprint225 - 고른 것으로 만든다 (Epic 66).

무엇이 잘못되어 있었나
----------------------
integrate_asset은 맨 위에서 이 프로젝트가 고른 Provider를 읽는다
(Sprint127). 그런데 그 값을 넘기는 곳이 두 갈래뿐이었다.

    visual_type == "real"   _select_real_first(..., provider=provider)
    visual_type == "ai"     _select_ai_first(..., provider=provider)
    visual_type 없음        _ai_result(...)              <- 빠져 있었다

그리고 apply_visual_type을 부르는 곳은 파이프라인 하나뿐이다. 검수
화면이 만드는 scene에는 그 값이 없다 - 대본을 쓰고 [이미지 만들기]를
누르는 그 길이다.

    검수 화면에서 "내 PC 자료"(무료)를 고른다
      -> visual_type이 없다
      -> 고른 것이 다리까지 가지 않는다
      -> 스톡 검색, 없으면 current 엔진(Imagen, 유료 Vertex)

무료로 만들겠다고 해 놓고 조용히 Imagen을 부르면 그때부터 돈이 든다.
이 저장소가 여러 곳에 적어 둔 규칙이고, 그 규칙이 이 경로에서만
지켜지지 않았다.

무엇을 바꾸지 않았는가
----------------------
고르는 순서를 바꾸지 않았다. 스톡을 먼저 보는 것도, 품질 게이트도,
폴백 정책도 그대로다. 달라지는 것은 "만들어야 할 때 무엇이 만드는가"
하나뿐이고 그것이 원래 이 값의 뜻이다.
"""

import json
from app.services import media_policy
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import runtime_paths
from app.services import asset_integration_service as bridge


REAL = {"scene": 1, "narration": "가", "image_prompt": "무릎",
        "visual_type": "real"}
AI = {"scene": 1, "narration": "가", "image_prompt": "무릎",
      "visual_type": "ai"}
PLAIN = {"scene": 1, "narration": "가", "image_prompt": "무릎"}

BRANCHES = (("real", REAL), ("ai", AI), ("없음", PLAIN))


class _Bridge(unittest.TestCase):
    """다리가 무엇을 받는지만 본다. 실제로 만들지 않는다."""

    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="sprint225_")
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        os.makedirs(os.path.join(self.project, "images"), exist_ok=True)

        # Sprint241 - 이 시험은 **유료 AI Provider 가 도는 것**을 잰다.
        #
        # 제품의 기본값은 AI 이미지 생성 금지다(결제 잠금). 그러니 AI
        # 경로를 재려면 그 전제를 적어야 한다 - 지금까지는 AI 를 쓰는
        # 세상이 유일해서 적을 필요가 없었을 뿐이다.
        #
        # 약하게 만드는 것이 아니라 숨어 있던 전제를 드러내는 것이다.
        media_policy.choose(self.project, media_policy.MODE_MINE_STOCK_AI)

        blocked = patch.object(bridge.asset_feedback_service, "record")
        blocked.start()
        self.addCleanup(blocked.stop)

    def _given(self, scene, chosen):
        """그 scene을 만들 때 _ai_result가 받은 provider."""

        seen = {}

        def spy(image_prompt, staging_path, channel, is_hook_scene,
                image_style=None, candidate_count=1, scene=None,
                provider=None, project_path=None):
  # Sprint241 - 진짜 _ai_result 가 project_path 를 받는다.
                # 대역도 같은 것을 받아야 그 자리에 설 수 있다.
            seen["provider"] = provider
            raise RuntimeError("여기까지만 본다")

        with patch.object(bridge, "_ai_result", spy), \
                patch.object(bridge.provider_selection, "selected",
                             lambda project_path, stage: chosen), \
                patch.object(bridge, "get_candidates", lambda *a, **k: []):
            try:
                bridge.integrate_asset(dict(scene), self.project)
            except Exception:
                pass

        return seen.get("provider", "부르지도 않았다")


class TheChoiceReachesEveryBranchTest(_Bridge):
    """세 갈래 전부에서 고른 것이 지켜진다."""

    def test_every_branch_carries_the_choice(self):
        for label, scene in BRANCHES:
            with self.subTest(visual_type=label):
                self.assertEqual(
                    self._given(scene, "local_stock"), "local_stock")

    def test_the_branch_that_was_missing_it(self):
        """
        이것이 이번에 고친 자리다. 나머지 둘은 Sprint127부터 되어
        있었고, 여기만 빠져 있었다.
        """

        self.assertEqual(self._given(PLAIN, "local_stock"), "local_stock")

    def test_any_chosen_provider_is_carried_not_just_one(self):
        for chosen in ("local_stock", "flux", "gpt_image"):
            with self.subTest(chosen=chosen):
                self.assertEqual(self._given(PLAIN, chosen), chosen)


class TheCurrentPathIsUnchangedTest(_Bridge):
    """고르지 않은 프로젝트는 예전 그대로다."""

    def test_no_choice_means_no_provider_in_every_branch(self):
        for label, scene in BRANCHES:
            with self.subTest(visual_type=label):
                self.assertIsNone(self._given(scene, None))


class TheFreeChoiceNeverCallsThePaidEngineTest(unittest.TestCase):
    """
    고른 것이 실패해도 다른 것으로 조용히 넘어가지 않는다.

    Sprint130이 정한 규칙이고, 이제 이 갈래에도 적용된다.
    """

    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="sprint225_free_")
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        os.makedirs(os.path.join(self.project, "images"), exist_ok=True)

        # Sprint241 - 이 시험은 **유료 AI Provider 가 도는 것**을 잰다.
        #
        # 제품의 기본값은 AI 이미지 생성 금지다(결제 잠금). 그러니 AI
        # 경로를 재려면 그 전제를 적어야 한다 - 지금까지는 AI 를 쓰는
        # 세상이 유일해서 적을 필요가 없었을 뿐이다.
        #
        # 약하게 만드는 것이 아니라 숨어 있던 전제를 드러내는 것이다.
        media_policy.choose(self.project, media_policy.MODE_MINE_STOCK_AI)

        blocked = patch.object(bridge.asset_feedback_service, "record")
        blocked.start()
        self.addCleanup(blocked.stop)

    def _run(self, scene):
        """내 자료가 비어 있는 채로 만들어 본다. 무엇이 불렸는지 돌려준다."""

        from app.providers import local_stock_provider
        from app.services import image_service

        with patch.object(bridge.provider_selection, "selected",
                          lambda project_path, stage: "local_stock"), \
                patch.object(bridge, "get_candidates", lambda *a, **k: []), \
                patch.object(bridge.best_of_n_service,
                             "generate_candidates") as imagen, \
                patch.object(image_service, "generate_image") as one_image:

            with self.assertRaises(local_stock_provider.LocalStockUnavailable):
                bridge.integrate_asset(dict(scene), self.project)

        return imagen, one_image

    def test_imagen_is_never_called_in_any_branch(self):
        for label, scene in BRANCHES:
            with self.subTest(visual_type=label):
                imagen, one_image = self._run(scene)

                imagen.assert_not_called()
                one_image.assert_not_called()

    def test_it_stops_instead_of_quietly_making_something_else(self):
        """
        스톡 사진을 대신 주면 사람은 무료를 골랐는데 다른 것을 받는다.
        """

        from app.providers import local_stock_provider

        with patch.object(bridge.provider_selection, "selected",
                          lambda project_path, stage: "local_stock"), \
                patch.object(bridge, "get_candidates", lambda *a, **k: []):

            with self.assertRaises(local_stock_provider.LocalStockUnavailable):
                bridge.integrate_asset(dict(PLAIN), self.project)

        self.assertFalse(os.path.exists(
            os.path.join(self.project, "images", "scene1.png")))


class TheScreenSaysWhatWasChosenTest(unittest.TestCase):
    """
    고른 것이 만들지 못했을 때 화면이 무엇을 고쳐야 하는지 말한다.

    지금까지 이 자리는 ReviewError만 받아서, 고른 Provider가 낸 것은
    그대로 빠져나가 500이 됐다 - 화면에는 "Internal Server Error"만
    떴고, 정작 사람이 할 수 있는 일이 적힌 문장은 사라졌다.
    """

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="sprint225_home_")
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        patched = patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)

        from app.services import project_service

        rooted = patch.object(
            project_service, "OUTPUT_ROOT",
            runtime_paths.ensure(os.path.join(self.home, "output")))
        rooted.start()
        self.addCleanup(rooted.stop)

        self.project_id = "20260819_120000"
        self.project = runtime_paths.ensure(
            os.path.join(project_service.OUTPUT_ROOT, self.project_id))

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": [dict(PLAIN)]}, f,
                      ensure_ascii=False)

    def _client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def _choose(self, provider):
        from app.services import provider_selection

        provider_selection.save(self.project, {"image": provider})

    def test_it_names_what_was_chosen(self):
        self._choose("local_stock")

        answer = self._client().post(
            f"/studio/api/review/{self.project_id}/images")

        self.assertEqual(answer.status_code, 400)
        self.assertIn("내 PC 자료", answer.json()["detail"])

    def test_it_says_why_it_could_not(self):
        self._choose("local_stock")

        answer = self._client().post(
            f"/studio/api/review/{self.project_id}/images")

        self.assertIn("내 PC 자료 목록이 비어 있습니다",
                      answer.json()["detail"])

    def test_it_says_what_the_person_can_do(self):
        self._choose("local_stock")

        answer = self._client().post(
            f"/studio/api/review/{self.project_id}/images")

        self.assertIn("바꾸십시오", answer.json()["detail"])

    def test_one_scene_at_a_time_says_the_same(self):
        self._choose("local_stock")

        answer = self._client().post(
            f"/studio/api/review/{self.project_id}/images/1")

        self.assertEqual(answer.status_code, 400)
        self.assertIn("내 PC 자료", answer.json()["detail"])

    def test_a_project_that_chose_nothing_is_left_as_it_was(self):
        """
        고르지 않은 사람의 화면은 이번에 건드리지 않는다 - 그 길은
        예전 그대로 500이다.
        """

        from app.services import best_of_n_service

        with patch.object(bridge, "get_candidates", lambda *a, **k: []), \
                patch.object(best_of_n_service, "generate_candidates",
                             side_effect=RuntimeError("엔진이 못 만들었다")):

            answer = self._client().post(
                f"/studio/api/review/{self.project_id}/images")

        self.assertEqual(answer.status_code, 500)


if __name__ == "__main__":
    unittest.main()
