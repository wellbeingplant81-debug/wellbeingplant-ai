"""
Sprint218 - 제작 방식과 과금 확인 (Epic 62).

이 스위트가 지키는 것
---------------------
    1. 두 갈래가 기존 모드 체계에서 유도된다     평행한 목록을 안 만든다
    2. 돈이 든다고 단정하지 않는다               "발생할 수 있습니다"
    3. 금액을 지어내지 않는다
    4. 확인 없이는 시작되지 않는다               **서버가 막는다**
    5. 취소는 아무 일도 일어나지 않는다
    6. 고른 갈래가 작업까지 전달된다
    7. 설명이 실제로 되는 것만 말한다            가짜 자동화 금지
"""

import os
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.production import creation_modes, production_modes, source_modes


def _page():
    from app.routers import studio as studio_router

    return studio_router.studio_page().body.decode("utf-8")


# ══ 1. 기존 모델에서 유도한다 ════════════════════════════════════════

class TheTwoBranchesAreDerivedTest(unittest.TestCase):

    def test_there_are_exactly_two_branches(self):
        self.assertEqual(sorted(creation_modes.CREATION_MODES),
                         sorted([creation_modes.FREE,
                                 creation_modes.FULL_AUTO]))

    def test_each_branch_points_at_a_real_production_mode(self):
        """새 모드를 만들지 않는다 - 있는 것을 가리킨다."""

        for mode in creation_modes.CREATION_MODES:
            with self.subTest(mode=mode):
                self.assertTrue(production_modes.is_production_mode(
                    creation_modes.production_mode_for(mode)))

    def test_full_auto_is_what_the_engine_actually_does(self):
        """
        AUTO_PREMIUM을 가리키면 화면은 "가장 좋은 것으로 만든다"고
        말하지만 엔진은 여전히 같은 일을 한다 - 그것이 가짜 자동화다.
        """

        self.assertEqual(
            creation_modes.production_mode_for(creation_modes.FULL_AUTO),
            production_modes.CURRENT_ENGINE_MODE)

    def test_an_unknown_branch_is_refused(self):
        with self.assertRaises(ValueError):
            creation_modes.require_creation_mode("turbo")

    def test_every_branch_has_a_label_and_a_description(self):
        for mode in creation_modes.CREATION_MODES:
            with self.subTest(mode=mode):
                self.assertTrue(creation_modes.LABELS[mode])
                self.assertTrue(creation_modes.DESCRIPTIONS[mode])

    def test_the_description_does_not_promise_topic_research(self):
        """
        이 저장소에 "소재 분석" 단계는 없다. 주제는 사람이 적고
        파이프라인은 그 주제로 대본부터 시작한다 - 있는 척하는 설명
        한 줄이 나머지 전부를 의심스럽게 만든다.
        """

        said = creation_modes.DESCRIPTIONS[creation_modes.FULL_AUTO]

        for promise in ("소재 분석", "소재를 분석", "트렌드", "주제 발굴"):
            with self.subTest(promise=promise):
                self.assertNotIn(promise, said)

    def test_the_description_only_names_things_the_pipeline_makes(self):
        """
        설명이 이름을 대는 것마다 실제로 그것을 만드는 단계 파일이
        있어야 한다.

        production/stages.LABELS 와 견주지 않는다 - 그 다섯은 **사용자가
        고를 수 있는** 단계이고, 파이프라인이 밟는 단계는 그보다 많다
        (자막·영상·썸네일은 고를 수 없지만 실제로 만들어진다). 견줄
        곳을 잘못 고르면 사실인 설명을 거짓으로 판정한다.
        """

        steps = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "steps")

        made = os.listdir(steps)

        # 설명이 대는 이름 -> 그것을 만드는 단계 파일의 표식
        BY = {
            "대본": "script", "장면": "scene_plan", "이미지": "image",
            "음성": "tts", "자막": "subtitle", "렌더링": "video",
        }

        said = creation_modes.DESCRIPTIONS[creation_modes.FULL_AUTO]

        for named, marker in BY.items():
            if named not in said:
                continue

            with self.subTest(named=named):
                self.assertTrue(
                    any(marker in name for name in made),
                    f"{named} 을 만드는 단계 파일이 없습니다({marker})")

    def test_the_description_names_nothing_the_pipeline_lacks(self):
        """
        반대 방향도 본다 - 없는 것을 적지 않았는가.

        이 저장소에는 번역·더빙·업스케일 단계가 없다.
        """

        said = creation_modes.DESCRIPTIONS[creation_modes.FULL_AUTO]

        for absent in ("번역", "더빙", "업스케일", "배경 제거", "자동 업로드"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, said)


# ══ 2·3. 돈이 든다고 단정하지 않는다 ════════════════════════════════

class TheCostPolicyIsHonestTest(unittest.TestCase):

    def test_free_calls_no_paid_api(self):
        self.assertFalse(creation_modes.calls_paid_api(creation_modes.FREE))

    def test_free_needs_no_confirmation(self):
        self.assertFalse(
            creation_modes.needs_cost_confirmation(creation_modes.FREE))

    def test_free_allows_no_api_calling_source_mode(self):
        """
        FREE가 API를 안 부른다는 사실의 출처는 이 모듈이 아니라
        허용 입력 목록이다 - 플래그를 따로 두면 어긋난다.
        """

        for mode in creation_modes.allowed_source_modes(creation_modes.FREE):
            with self.subTest(source_mode=mode):
                self.assertFalse(source_modes.calls_api(mode))

    def test_full_auto_may_cost_and_needs_confirmation(self):
        policy = creation_modes.cost_policy_for(creation_modes.FULL_AUTO)

        self.assertTrue(policy.may_cost)
        self.assertTrue(policy.requires_confirmation)

    def test_it_says_may_not_will(self):
        """"무조건 비용이 발생한다"고 단정하지 않는다."""

        said = creation_modes.cost_policy_for(
            creation_modes.FULL_AUTO).reason

        self.assertIn("있습니다", said)

        for absolute in ("반드시", "무조건", "항상 비용", "비용이 발생합니다"):
            with self.subTest(absolute=absolute):
                self.assertNotIn(absolute, said)

    def test_no_amount_is_invented_anywhere(self):
        """
        실제 비용을 모른다 - 단가를 아는 단계만 계산되고 모르는 단계가
        남는다(cost.py). 그러니 이 층은 금액을 한 글자도 적지 않는다.
        """

        for mode in creation_modes.CREATION_MODES:
            said = creation_modes.cost_policy_for(mode).reason

            with self.subTest(mode=mode):
                self.assertNotIn("$", said)
                self.assertNotIn("원", said)
                self.assertIsNone(
                    re.search(r"\d+\s*(달러|원|USD)", said), said)

    def test_the_api_stages_come_from_a_real_plan(self):
        """단계 이름을 지어내지 않는다 - 계획이 말하는 것만 옮긴다."""

        from app.production import stages

        found = creation_modes.api_stage_labels(creation_modes.FULL_AUTO)

        self.assertTrue(found, "API를 부르는 단계가 하나도 없습니다")

        for label in found:
            with self.subTest(label=label):
                self.assertIn(label, set(stages.LABELS.values()))

    def test_free_lists_no_api_stage(self):
        self.assertEqual(
            creation_modes.api_stage_labels(creation_modes.FREE), ())

    def test_a_broken_registry_still_answers(self):
        """
        계획을 못 세우는 자리에서도 안내는 떠야 한다 - 안내가 못 뜨면
        확인을 받을 수 없고, 그러면 시작할 방법이 없다.
        """

        with patch("app.production.production_plan.build_automatic_plan",
                   side_effect=RuntimeError("등록소가 비었다")):
            policy = creation_modes.cost_policy_for(creation_modes.FULL_AUTO)

        self.assertTrue(policy.requires_confirmation)
        self.assertTrue(policy.reason)
        self.assertEqual(policy.api_stages, ())


# ══ 4·5. 확인 없이는 시작되지 않는다 ════════════════════════════════

class TheServerIsTheGateTest(unittest.TestCase):
    """
    화면의 대화상자 하나로 끝내면 그것은 연극이다. 창을 새로 열어 같은
    요청을 보내면 그냥 시작된다.
    """

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.services import studio_jobs

        self.client = TestClient(app)
        studio_jobs.reset()
        self.addCleanup(studio_jobs.reset)

    def _post(self, **body):
        body.setdefault("topic", "혈관 건강을 지키는 아침 습관")

        return self.client.post("/studio/api/jobs", json=body)

    def test_full_auto_without_an_ack_is_refused(self):
        with patch("app.services.studio_jobs.start") as started:
            response = self._post(creation_mode="full_auto")

        self.assertEqual(response.status_code, 400)
        started.assert_not_called()

    def test_the_refusal_says_what_to_do(self):
        response = self._post(creation_mode="full_auto")
        said = response.json()["detail"]

        self.assertIn("확인", said)
        self.assertIn("확인하고 시작", said)

    def test_an_explicit_false_ack_is_refused(self):
        with patch("app.services.studio_jobs.start") as started:
            response = self._post(creation_mode="full_auto", cost_ack=False)

        self.assertEqual(response.status_code, 400)
        started.assert_not_called()

    def test_nothing_is_created_when_it_is_refused(self):
        """
        취소는 아무 일도 일어나지 않는다여야 한다 - 작업도 프로젝트도
        만들어지면 안 된다.
        """

        from app.services import studio_jobs

        before = len(studio_jobs.recent(limit=100))

        self._post(creation_mode="full_auto")

        self.assertEqual(len(studio_jobs.recent(limit=100)), before)

    def test_full_auto_with_an_ack_starts(self):
        with patch("app.services.studio_jobs.start",
                   return_value="job-1") as started:
            response = self._post(creation_mode="full_auto", cost_ack=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "job-1")
        started.assert_called_once()

    def test_free_starts_without_an_ack(self):
        """무료 갈래에 확인을 요구하면 그것은 겁주기다."""

        with patch("app.services.studio_jobs.start",
                   return_value="job-2") as started:
            response = self._post(creation_mode="free")

        self.assertEqual(response.status_code, 200)
        started.assert_called_once()

    def test_the_old_button_is_unchanged(self):
        """
        creation_mode를 안 보내면 예전과 똑같다. 기존 동작을 바꾸지
        않는 것이 이번 Sprint의 최우선이다.
        """

        with patch("app.services.studio_jobs.start",
                   return_value="job-3") as started:
            response = self._post()

        self.assertEqual(response.status_code, 200)
        started.assert_called_once()

    def test_an_unknown_branch_is_refused_by_http(self):
        with patch("app.services.studio_jobs.start") as started:
            response = self._post(creation_mode="turbo", cost_ack=True)

        self.assertEqual(response.status_code, 400)
        started.assert_not_called()

    def test_an_empty_topic_is_still_refused_first(self):
        response = self.client.post(
            "/studio/api/jobs",
            json={"topic": "  ", "creation_mode": "free"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("주제", response.json()["detail"])


# ══ 6. 고른 갈래가 작업까지 간다 ════════════════════════════════════

class TheBranchReachesTheJobTest(unittest.TestCase):

    def setUp(self):
        from app.services import studio_jobs

        self.jobs = studio_jobs
        studio_jobs.reset()
        self.addCleanup(studio_jobs.reset)

    def test_the_job_remembers_which_branch_started_it(self):
        with patch("app.services.studio_jobs.threading.Thread"):
            job_id = self.jobs.start("주제", "wellbeing", None, "full_auto")

        self.assertEqual(
            self.jobs.status(job_id)["creation_mode"], "full_auto")

    def test_a_job_without_a_branch_says_so(self):
        with patch("app.services.studio_jobs.threading.Thread"):
            job_id = self.jobs.start("주제")

        self.assertIsNone(self.jobs.status(job_id)["creation_mode"])

    def test_the_http_layer_passes_it_through(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with patch("app.services.studio_jobs.start",
                   return_value="j") as started:
            TestClient(app).post("/studio/api/jobs", json={
                "topic": "주제", "creation_mode": "full_auto",
                "cost_ack": True})

        self.assertIn("full_auto", started.call_args.args)


# ══ 7. HTTP 목록과 화면 ═════════════════════════════════════════════

class TheHttpSurfaceTest(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_it_lists_both_branches(self):
        body = self.client.get(
            "/studio/api/production/creation-modes").json()

        self.assertEqual(
            sorted(m["creation_mode"] for m in body["modes"]),
            sorted(creation_modes.CREATION_MODES))

    def test_each_branch_says_whether_it_may_cost(self):
        body = self.client.get(
            "/studio/api/production/creation-modes").json()

        by = {m["creation_mode"]: m for m in body["modes"]}

        self.assertFalse(by["free"]["may_cost"])
        self.assertFalse(by["free"]["requires_confirmation"])
        self.assertTrue(by["full_auto"]["may_cost"])
        self.assertTrue(by["full_auto"]["requires_confirmation"])

    def test_listing_them_starts_nothing(self):
        with patch("app.services.studio_jobs.start") as started:
            self.client.get("/studio/api/production/creation-modes")

        started.assert_not_called()


class TheScreenTest(unittest.TestCase):

    def test_both_cards_have_a_place(self):
        page = _page()

        self.assertIn('id="creationModes"', page)
        self.assertIn('id="cmFree"', page)
        self.assertIn('id="cmAuto"', page)

    def test_the_words_are_on_the_screen(self):
        page = _page()

        for word in ("무료로 만들기", "완전 자동으로 만들기",
                     "비용 발생 가능", "비용 없음"):
            with self.subTest(word=word):
                self.assertIn(word, page)

    def test_the_confirmation_sheet_exists_with_both_buttons(self):
        page = _page()

        self.assertIn('id="costSheet"', page)
        self.assertIn("취소", page)
        self.assertIn("확인하고 시작", page)

    def test_it_does_not_use_the_browser_confirm_for_the_cost_gate(self):
        """
        브라우저 기본 대화상자는 테마를 따르지 않고, 어느 단계가 API를
        부르는지를 담을 자리도 없다.
        """

        page = _page()
        at = page.index("function chooseFullAuto")
        block = page[at:at + 500]

        self.assertNotIn("confirm(", block)
        self.assertIn("openCostSheet()", block)

    def test_cancel_starts_nothing(self):
        """
        취소는 아무 일도 일어나지 않는다여야 한다 - 단계 선택도
        바꾸지 않는다.
        """

        page = _page()
        at = page.index("function cancelCostSheet")
        # 다음 함수 선언 전까지가 이 함수다. 고정 길이로 자르면 옆
        # 함수의 본문을 함께 읽는다(실제로 그렇게 걸렸다).
        block = page[at:page.index("function ", at + 20)]

        for forbidden in ("startGeneration", "createProject", "pickCostMode"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)

    def test_accept_is_the_only_path_that_starts(self):
        page = _page()
        at = page.index("function acceptCostSheet")
        block = page[at:at + 420]

        self.assertIn("startGeneration(\"full_auto\", true)", block)

    def test_the_handlers_are_declared(self):
        page = _page()

        for name in ("chooseFree", "chooseFullAuto", "openCostSheet",
                     "cancelCostSheet", "acceptCostSheet",
                     "startGeneration", "markCreationMode"):
            with self.subTest(name=name):
                self.assertIn(f"function {name}(", page)

    def test_the_free_branch_reuses_the_existing_wizard(self):
        """새 길을 만들지 않는다."""

        page = _page()
        at = page.index("function chooseFree")
        block = page[at:at + 420]

        self.assertIn("toggleFreeWizard()", block)
        self.assertIn("pickCostMode(true)", block)

    def test_nothing_that_was_there_was_deleted(self):
        page = _page()

        for word in ('id="wizToggle"', "무료 제작 시작",
                     "toggleFreeWizard", 'id="go"', "직접 고르기"):
            with self.subTest(word=word):
                self.assertIn(word, page)

    def test_the_old_button_sends_no_branch(self):
        page = _page()
        at = page.index('$("go").onclick')

        self.assertIn("startGeneration(null, false)", page[at:at + 120])


if __name__ == "__main__":
    unittest.main()
