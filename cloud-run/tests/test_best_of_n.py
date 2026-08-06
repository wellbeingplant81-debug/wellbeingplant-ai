"""
Sprint74 - Best-of-N Asset Selection Engine.

지금 파이프라인은 Imagen이 그린 첫 장을 그대로 쓴다. 그림이 나쁘면
렌더가 끝나고 Gemini 평가가 나온 뒤에야 알게 되고, 그때부터 재생성
사이클이 돈다 - 이미지 한 장 더, 전체 평가 한 번 더, 그리고 영상 전체를
다시 렌더한다.

Best-of-N은 그 판단을 렌더 앞으로 당긴다. 후보를 N장 뽑고, 그 자리에서
Gemini Vision에게 고르게 하고, 고른 것으로 scene을 확정한다. 재생성은
그래도 안 될 때만 돈다.

축적된 53건의 평가에서 ai_image scene의 점수는 평균 78.9, 표준편차
24.2였고 20%가 재생성 권고를 받았다. Best-of-N이 버는 것은 전적으로 그
분산이다 - 후보들이 서로 비슷하면 고르는 값이 없다. 그 분산이 정말
후보 사이의 것인지는 실제로 뽑아 봐야 안다.

여기 테스트는 Imagen도 Gemini도 부르지 않는다. 무엇을 몇 장 뽑고,
어떻게 고르고, 실패하면 어떻게 되는지만 고정한다.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.models.candidate_selection import CandidateScore, CandidateSelection
from app.services import best_of_n_service as best_of_n


def _score(candidate, fidelity=80, character=80, composition=80,
           unrequested_person=False):
    return CandidateScore(
        candidate=candidate,
        prompt_fidelity=fidelity,
        character_match=character,
        composition=composition,
        unrequested_person=unrequested_person,
        note=None,
    )


class TestCandidateBudget(unittest.TestCase):
    """예산은 scene들이 갈라지기 전에 정해진다.

    integrate_asset은 scene마다 스레드 3개로 병렬 실행된다. 거기서
    공유 카운터를 깎으면 경쟁 상태가 되고, 같은 입력이 실행마다 다른
    결과를 낸다. 배분은 팬아웃 이전에 순수 함수로 끝낸다.
    """

    def test_the_flag_and_the_numbers_are_declared(self):
        self.assertIsInstance(config.ENABLE_BEST_OF_N, bool)
        self.assertGreaterEqual(config.BEST_OF_N_CANDIDATES, 1)
        self.assertGreaterEqual(
            config.BEST_OF_N_MAX_CANDIDATES, config.BEST_OF_N_CANDIDATES,
        )

    def test_every_imagen_bound_scene_gets_the_default_count(self):
        scenes = [
            {"scene": 1, "visual_type": "ai"},
            {"scene": 2, "visual_type": "ai"},
        ]

        plan = best_of_n.plan_candidates(scenes, default_n=2, budget=10)

        self.assertEqual(plan, {1: 2, 2: 2})

    def test_stock_bound_scenes_get_a_single_candidate(self):
        # visual_type=real은 Pexels를 먼저 본다. 거기서 성공하면 Imagen을
        # 아예 부르지 않으므로 후보를 배정해 둘 이유가 없다.
        scenes = [
            {"scene": 1, "visual_type": "ai"},
            {"scene": 2, "visual_type": "real"},
        ]

        plan = best_of_n.plan_candidates(scenes, default_n=2, budget=10)

        self.assertEqual(plan, {1: 2, 2: 1})

    def test_the_budget_is_spent_in_scene_order_then_runs_out(self):
        """예산은 후보 이미지의 총량이다.

        scene 4개면 첫 장만으로 이미 4장을 쓴다. 5장 예산에서 두 번째
        장을 받을 수 있는 scene은 하나뿐이다.
        """

        scenes = [{"scene": n, "visual_type": "ai"} for n in range(1, 5)]

        plan = best_of_n.plan_candidates(scenes, default_n=2, budget=5)

        self.assertEqual(plan, {1: 2, 2: 1, 3: 1, 4: 1})
        self.assertEqual(sum(plan.values()), 5)

    def test_every_scene_always_gets_at_least_one(self):
        """예산이 0이어도 그림은 그린다.

        예산은 "후보를 더 뽑을지"를 정하는 것이지 "그릴지"를 정하는
        것이 아니다. 0장은 scene에 그림이 없다는 뜻이고, 그것은 예산
        문제가 아니라 파이프라인 고장이다.
        """

        scenes = [{"scene": n, "visual_type": "ai"} for n in range(1, 4)]

        plan = best_of_n.plan_candidates(scenes, default_n=2, budget=0)

        self.assertEqual(plan, {1: 1, 2: 1, 3: 1})

    def test_n_of_one_is_the_current_behaviour(self):
        scenes = [{"scene": 1, "visual_type": "ai"}]

        self.assertEqual(
            best_of_n.plan_candidates(scenes, default_n=1, budget=10), {1: 1},
        )


class TestSelection(unittest.TestCase):
    """무엇을 고르는가."""

    def test_the_highest_total_wins(self):
        selection = CandidateSelection(
            best_candidate=1,
            candidates=[_score(0, 60, 60, 60), _score(1, 90, 90, 90)],
            reason="",
        )

        self.assertEqual(best_of_n.winning_index(selection), 1)

    def test_an_unrequested_person_disqualifies_a_candidate(self):
        """Sprint73이 실측으로 만난 그 실패다.

        프롬프트는 "top-down view of a ceramic bowl"뿐이었는데 Imagen이
        젊은 여성의 얼굴을 그려 넣었고, 그 사람은 앵커 캐릭터와 달라
        character_consistency가 95 -> 20으로 무너졌다. 그때는 렌더가
        끝난 뒤에야 알았다. 여기서는 고르는 자리에서 걸러진다.

        점수가 더 높아도 탈락한다 - 사람이 하나 잘못 들어가면 영상
        전체가 무너지므로, 다른 항목으로 상쇄될 성질이 아니다.
        """

        selection = CandidateSelection(
            best_candidate=0,
            candidates=[
                _score(0, 95, 95, 95, unrequested_person=True),
                _score(1, 70, 70, 70),
            ],
            reason="",
        )

        self.assertEqual(best_of_n.winning_index(selection), 1)

    def test_all_candidates_disqualified_still_returns_the_best_of_them(self):
        # 전부 실격이어도 아무것도 고르지 않을 수는 없다. 그림은
        # 있어야 하고, 나머지는 재생성 엔진이 맡는다.
        selection = CandidateSelection(
            best_candidate=0,
            candidates=[
                _score(0, 40, 40, 40, unrequested_person=True),
                _score(1, 80, 80, 80, unrequested_person=True),
            ],
            reason="",
        )

        self.assertEqual(best_of_n.winning_index(selection), 1)

    def test_gemini_own_pick_is_not_trusted_over_the_scores(self):
        # best_candidate가 점수와 어긋나면 점수를 따른다. 구조화된
        # 숫자가 자유 서술보다 검증 가능하다.
        selection = CandidateSelection(
            best_candidate=0,
            candidates=[_score(0, 10, 10, 10), _score(1, 99, 99, 99)],
            reason="0번이 제일 낫습니다",
        )

        self.assertEqual(best_of_n.winning_index(selection), 1)

    def test_an_out_of_range_index_never_escapes(self):
        selection = CandidateSelection(
            best_candidate=7,
            candidates=[_score(7, 90, 90, 90)],
            reason="",
        )

        self.assertEqual(
            best_of_n.winning_index(selection, candidate_count=1), 0,
        )


class TestSelectBest(unittest.TestCase):
    """Gemini Vision을 부르는 자리. 여기서는 mock으로 계약만 본다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _candidates(self, count):
        paths = []
        for index in range(count):
            path = os.path.join(self._tmp.name, f"cand{index}.png")
            with open(path, "wb") as f:
                f.write(b"PNG")
            paths.append(path)
        return paths

    def test_a_single_candidate_never_calls_gemini(self):
        with patch.object(best_of_n, "_ask_gemini") as ask:
            index, selection = best_of_n.select_best(
                self._candidates(1), {"scene": 1, "image_prompt": "p"},
            )

        ask.assert_not_called()
        self.assertEqual(index, 0)
        self.assertIsNone(selection)

    def test_a_selection_failure_falls_back_to_the_first_candidate(self):
        """고르기가 실패했다고 영상을 버리지 않는다.

        Best-of-N은 개선 장치이지 필수 경로가 아니다. Gemini가 죽으면
        예전과 똑같이 첫 장을 쓰면 된다.
        """

        with patch.object(
            best_of_n, "_ask_gemini", side_effect=Exception("vision down"),
        ):
            index, selection = best_of_n.select_best(
                self._candidates(3), {"scene": 1, "image_prompt": "p"},
            )

        self.assertEqual(index, 0)
        self.assertIsNone(selection)

    def test_the_winner_is_returned_by_index(self):
        chosen = CandidateSelection(
            best_candidate=2,
            candidates=[_score(0, 50), _score(1, 60), _score(2, 95)],
            reason="가장 선명함",
        )

        with patch.object(best_of_n, "_ask_gemini", return_value=chosen):
            index, selection = best_of_n.select_best(
                self._candidates(3), {"scene": 1, "image_prompt": "p"},
            )

        self.assertEqual(index, 2)
        self.assertIs(selection, chosen)


class TestGenerateCandidates(unittest.TestCase):
    """후보를 뽑는 자리."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.staging = os.path.join(self._tmp.name, "scene1.raw")

    def test_one_candidate_uses_the_existing_single_image_path(self):
        """N=1이면 예전 코드 그대로다.

        플래그가 꺼진 상태에서 동작이 한 바이트도 달라지지 않아야
        하므로, 후보 1장은 generate_image를 그대로 부른다.
        """

        with patch.object(
            best_of_n.image_service, "generate_image", return_value=self.staging,
        ) as single, patch.object(
            best_of_n.image_service, "generate_image_candidates",
        ) as many:
            paths = best_of_n.generate_candidates(
                "prompt", self.staging, 1, channel="wellbeing",
                is_hook_scene=False, image_style="default",
            )

        single.assert_called_once()
        many.assert_not_called()
        self.assertEqual(paths, [self.staging])

    def test_many_candidates_are_requested_in_one_call(self):
        # Imagen은 한 요청에 여러 장을 돌려준다. N번 따로 부르면 왕복이
        # N배가 된다.
        expected = [f"{self.staging}.cand{i}" for i in range(3)]

        with patch.object(
            best_of_n.image_service, "generate_image_candidates",
            return_value=expected,
        ) as many:
            paths = best_of_n.generate_candidates(
                "prompt", self.staging, 3, channel="wellbeing",
                is_hook_scene=False, image_style="default",
            )

        many.assert_called_once()
        self.assertEqual(paths, expected)

    def test_fewer_candidates_than_asked_is_not_an_error(self):
        # Imagen이 안전 필터 등으로 요청보다 적게 돌려줄 수 있다.
        with patch.object(
            best_of_n.image_service, "generate_image_candidates",
            return_value=[f"{self.staging}.cand0"],
        ):
            paths = best_of_n.generate_candidates(
                "prompt", self.staging, 3, channel="wellbeing",
                is_hook_scene=False, image_style="default",
            )

        self.assertEqual(len(paths), 1)

    def test_zero_candidates_returned_is_an_error(self):
        with patch.object(
            best_of_n.image_service, "generate_image_candidates",
            return_value=[],
        ):
            with self.assertRaises(Exception):
                best_of_n.generate_candidates(
                    "prompt", self.staging, 3, channel="wellbeing",
                    is_hook_scene=False, image_style="default",
                )


class TestLosersAreCleanedUp(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_only_the_winner_survives(self):
        paths = []
        for index in range(3):
            path = os.path.join(self._tmp.name, f"c{index}.png")
            with open(path, "wb") as f:
                f.write(b"PNG")
            paths.append(path)

        best_of_n.discard_losers(paths, winner=1)

        self.assertFalse(os.path.exists(paths[0]))
        self.assertTrue(os.path.exists(paths[1]))
        self.assertFalse(os.path.exists(paths[2]))

    def test_a_missing_file_does_not_raise(self):
        path = os.path.join(self._tmp.name, "gone.png")
        best_of_n.discard_losers([path], winner=0)


if __name__ == "__main__":
    unittest.main()
