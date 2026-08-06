"""
Sprint73 - Intelligent Regeneration Engine.

기존 regeneration_service는 이미 "PASS한 scene은 건드리지 않고 FAIL한
scene만, 최대 3회까지" 재생성한다. 빠진 것은 멈추는 법이다.

1. 비용 상한이 없다. scene 6개면 최대 18번의 이미지 생성이 가능하고,
   그것을 막는 것은 재시도 횟수뿐이다.

2. 개선을 보지 않는다. 재생성이 품질을 떨어뜨려도 재시도 한도까지
   계속 돈다. Imagen은 같은 프롬프트에도 매번 다른 그림을 그리므로,
   나빠지는 방향으로 굴러가는 것이 얼마든지 가능하다.

3. 사이클마다 영상을 다시 렌더한다. 그런데 품질 판정은 이미지와
   대본만 읽는다 - Ken Burns 렌더는 그 판단에 아무 영향이 없으면서
   사이클당 6분을 쓴다.

여기 테스트들은 그 세 가지를 고정한다. 실제 Imagen/Gemini를 부르지
않고 결정 논리만 검증한다 - 멈추는 조건을 확인하는 데 실제 생성이
필요할 이유가 없다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.services import regeneration_policy as policy


class TestCostCap(unittest.TestCase):

    def test_a_cap_is_declared(self):
        self.assertIsInstance(config.REGENERATION_MAX_IMAGE_CALLS, int)
        self.assertGreater(config.REGENERATION_MAX_IMAGE_CALLS, 0)

    def test_scenes_are_dropped_once_the_budget_runs_out(self):
        eligible = [1, 2, 3, 4]

        allowed, dropped = policy.apply_cost_budget(
            eligible, spent=0, budget=2,
        )

        self.assertEqual(allowed, [1, 2])
        self.assertEqual(dropped, [3, 4])

    def test_nothing_is_allowed_when_the_budget_is_already_spent(self):
        allowed, dropped = policy.apply_cost_budget(
            [1, 2], spent=5, budget=5,
        )

        self.assertEqual(allowed, [])
        self.assertEqual(dropped, [1, 2])

    def test_a_budget_larger_than_the_work_allows_everything(self):
        allowed, dropped = policy.apply_cost_budget(
            [1, 2], spent=0, budget=99,
        )

        self.assertEqual(allowed, [1, 2])
        self.assertEqual(dropped, [])


class TestQualityScore(unittest.TestCase):
    """사이클끼리 비교할 하나의 숫자."""

    def _evaluation(self, scenes):
        return {
            "scenes": [
                {
                    "scene": number,
                    "realism_score": realism,
                    "composition_score": composition,
                    "regenerate": regenerate,
                }
                for number, realism, composition, regenerate in scenes
            ]
        }

    def test_better_scenes_give_a_higher_score(self):
        worse = policy.cycle_quality(
            self._evaluation([(1, 40, 40, True), (2, 50, 50, True)])
        )
        better = policy.cycle_quality(
            self._evaluation([(1, 90, 90, False), (2, 80, 80, False)])
        )

        self.assertGreater(better, worse)

    def test_an_empty_evaluation_scores_zero_rather_than_raising(self):
        self.assertEqual(policy.cycle_quality({"scenes": []}), 0.0)
        self.assertEqual(policy.cycle_quality(None), 0.0)

    def test_character_consistency_counts(self):
        """Sprint73 - 목적 함수가 재생성이 부수는 것을 보지 못했다.

        scene별 realism/composition만 재면, 한 scene이 또렷해지는 대신
        영상 전체의 인물 일관성이 무너져도 점수가 올라간다. 그러면
        엔진은 "좋아졌다"고 판단하고 그 결과를 그대로 내보낸다.
        """

        scenes = self._evaluation([(1, 80, 80, False)])

        intact = policy.cycle_quality({**scenes, "scores": {
            "character_consistency": 95}})
        broken = policy.cycle_quality({**scenes, "scores": {
            "character_consistency": 20}})

        self.assertLess(broken, intact)

    def test_a_consistency_collapse_outweighs_a_small_scene_gain(self):
        """실측 그대로의 숫자다.

        scene 평균은 81.2 -> 83.8로 올랐지만 character_consistency는
        95 -> 20으로 무너졌고 overall_quality는 70 -> 60이었다. 예전
        목적 함수는 이것을 +2.6점 개선으로 읽었다.
        """

        before = policy.cycle_quality({
            "scores": {"character_consistency": 95},
            "scenes": [
                {"scene": 1, "realism_score": 95, "composition_score": 95},
                {"scene": 2, "realism_score": 90, "composition_score": 85},
                {"scene": 3, "realism_score": 90, "composition_score": 85},
                {"scene": 4, "realism_score": 20, "composition_score": 70},
                {"scene": 5, "realism_score": 85, "composition_score": 85},
                {"scene": 6, "realism_score": 90, "composition_score": 85},
            ],
        })
        after = policy.cycle_quality({
            "scores": {"character_consistency": 20},
            "scenes": [
                {"scene": 1, "realism_score": 95, "composition_score": 95},
                {"scene": 2, "realism_score": 95, "composition_score": 90},
                {"scene": 3, "realism_score": 90, "composition_score": 90},
                {"scene": 4, "realism_score": 70, "composition_score": 50},
                {"scene": 5, "realism_score": 90, "composition_score": 85},
                {"scene": 6, "realism_score": 95, "composition_score": 90},
            ],
        })

        self.assertLess(after, before)
        self.assertTrue(policy.regressed(before, after))


class TestRollback(unittest.TestCase):
    """개선되지 않은 재생성 결과는 남기지 않는다.

    "개선이 없으면 멈춘다"만으로는 부족하다. 멈추는 시점에는 이미
    generate_image가 원본 파일을 덮어쓴 뒤이고, 더 나빠진 그림이 그대로
    영상에 들어간다. 멈추는 것과 되돌리는 것은 다른 일이다.
    """

    def test_a_drop_is_a_regression(self):
        self.assertTrue(policy.regressed(80.0, 60.0))

    def test_holding_steady_is_not_a_regression(self):
        self.assertFalse(policy.regressed(80.0, 80.0))

    def test_a_gain_is_not_a_regression(self):
        self.assertFalse(policy.regressed(60.0, 80.0))

    def test_an_unmeasurable_cycle_is_treated_as_a_regression(self):
        # 재평가가 실패했으면 좋아졌다는 근거가 없다. 근거 없이
        # 남기지 않는다.
        self.assertTrue(policy.regressed(80.0, None))

    def test_the_stop_reason_exists_and_reads(self):
        self.assertIn(policy.STOP_REGRESSED, policy.STOP_REASONS)
        self.assertTrue(policy.explain_stop(policy.STOP_REGRESSED))


class TestStopDecision(unittest.TestCase):

    def test_stops_when_nothing_is_eligible(self):
        decision = policy.decide_continue(
            eligible=[], spent=0, previous_quality=None, current_quality=50.0,
        )

        self.assertFalse(decision["continue"])
        self.assertEqual(decision["stop_reason"], policy.STOP_NOTHING_ELIGIBLE)

    def test_stops_when_the_budget_is_exhausted(self):
        decision = policy.decide_continue(
            eligible=[1, 2],
            spent=config.REGENERATION_MAX_IMAGE_CALLS,
            previous_quality=40.0,
            current_quality=50.0,
        )

        self.assertFalse(decision["continue"])
        self.assertEqual(decision["stop_reason"], policy.STOP_BUDGET_EXHAUSTED)

    def test_stops_when_quality_did_not_improve(self):
        decision = policy.decide_continue(
            eligible=[1], spent=2, previous_quality=60.0, current_quality=60.0,
        )

        self.assertFalse(decision["continue"])
        self.assertEqual(decision["stop_reason"], policy.STOP_NO_IMPROVEMENT)

    def test_stops_when_quality_got_worse(self):
        decision = policy.decide_continue(
            eligible=[1], spent=2, previous_quality=70.0, current_quality=55.0,
        )

        self.assertFalse(decision["continue"])
        self.assertEqual(decision["stop_reason"], policy.STOP_NO_IMPROVEMENT)

    def test_continues_when_quality_improved_and_work_remains(self):
        decision = policy.decide_continue(
            eligible=[1], spent=2, previous_quality=40.0, current_quality=65.0,
        )

        self.assertTrue(decision["continue"])
        self.assertIsNone(decision["stop_reason"])

    def test_the_first_cycle_runs_without_a_previous_quality(self):
        decision = policy.decide_continue(
            eligible=[1, 2], spent=0, previous_quality=None,
            current_quality=None,
        )

        self.assertTrue(decision["continue"])

    def test_a_tiny_gain_does_not_count_as_improvement(self):
        # 잡음만큼의 변화로 예산을 계속 태우지 않는다.
        decision = policy.decide_continue(
            eligible=[1], spent=2,
            previous_quality=60.0,
            current_quality=60.0 + policy.MIN_IMPROVEMENT / 2,
        )

        self.assertFalse(decision["continue"])
        self.assertEqual(decision["stop_reason"], policy.STOP_NO_IMPROVEMENT)


class TestDecisionLog(unittest.TestCase):

    def test_a_cycle_records_what_it_did_and_why(self):
        log = policy.new_log()

        policy.record_cycle(
            log,
            cycle=1,
            targeted=[1, 3],
            dropped_for_budget=[5],
            succeeded=[1],
            failed=[3],
            quality_before=40.0,
            quality_after=55.0,
            spent=2,
        )

        entry = log["cycles"][0]

        self.assertEqual(entry["cycle"], 1)
        self.assertEqual(entry["targeted"], [1, 3])
        self.assertEqual(entry["dropped_for_budget"], [5])
        self.assertEqual(entry["succeeded"], [1])
        self.assertEqual(entry["failed"], [3])
        self.assertAlmostEqual(entry["quality_before"], 40.0)
        self.assertAlmostEqual(entry["quality_after"], 55.0)
        self.assertEqual(entry["spent"], 2)

    def test_the_stop_reason_is_recorded_once_at_the_end(self):
        log = policy.new_log()

        policy.close_log(
            log, stop_reason=policy.STOP_NO_IMPROVEMENT, spent=4,
            rendered=True,
        )

        self.assertEqual(log["stop_reason"], policy.STOP_NO_IMPROVEMENT)
        self.assertEqual(log["total_image_calls"], 4)
        self.assertTrue(log["rendered"])

    def test_every_stop_reason_has_a_human_readable_explanation(self):
        for reason in policy.STOP_REASONS:
            with self.subTest(reason=reason):
                self.assertTrue(policy.explain_stop(reason))

    def test_an_unknown_stop_reason_is_not_silently_blank(self):
        self.assertIn("알 수 없", policy.explain_stop("something_else"))


class TestPassedScenesAreNeverTouched(unittest.TestCase):
    """이 엔진의 첫 번째 원칙."""

    def test_only_scenes_flagged_for_regeneration_are_eligible(self):
        evaluation = {
            "scenes": [
                {"scene": 1, "realism_score": 95, "composition_score": 90,
                 "regenerate": False},
                {"scene": 2, "realism_score": 30, "composition_score": 20,
                 "regenerate": True},
                {"scene": 3, "realism_score": 90, "composition_score": 85,
                 "regenerate": False},
            ]
        }

        targets = policy.regeneration_targets(
            evaluation,
            scenes_by_number={
                1: {"provider": "ai_image"},
                2: {"provider": "ai_image"},
                3: {"provider": "ai_image"},
            },
            retry_counts={},
        )

        self.assertEqual(targets, [2])

    def test_stock_scenes_stay_excluded(self):
        """Sprint73 - 이 규칙을 한 번 걷어냈다가 실측으로 되돌렸다.

        Sprint40이 적어 둔 근거("스톡 사진은 서로 다른 실존 인물이라
        일관성 평가를 통과할 수 없다")는 Character Consistency가 켜진
        뒤로 성립하지 않는다 - 인물 scene은 애초에 스톡으로 가지 않는다.
        그래서 규칙을 지웠고, 실제로 돌렸다.

        결과는 정반대 방향의 같은 결론이었다. realism 20점을 받은
        오트밀 사진(사물 scene, 인물 없음)을 Imagen으로 다시 그리자,
        프롬프트가 요구하지도 않은 젊은 여성의 얼굴이 그릇 위로
        들어왔다. 프롬프트는 "top-down view of a ceramic bowl"뿐이었다.
        그 여성은 1/2/3/6번 scene의 50대 남성과 당연히 다른 사람이므로
        character_consistency가 95 -> 20으로 무너졌고, overall_quality는
        70 -> 60으로 떨어졌다. 육안으로 확인했다.

        즉 위험은 "스톡이 서로 다른 사람"이 아니라 "사물 scene을
        Imagen에 맡기면 사람을 그려 넣는다"였다. 규칙은 유지하고
        근거만 실측한 것으로 바꾼다.
        """

        evaluation = {
            "scenes": [
                {"scene": 1, "realism_score": 30, "composition_score": 20,
                 "regenerate": True},
            ]
        }

        targets = policy.regeneration_targets(
            evaluation,
            scenes_by_number={1: {"provider": "pexels_image"}},
            retry_counts={},
        )

        self.assertEqual(targets, [])

    def test_scenes_at_the_retry_cap_are_excluded(self):
        evaluation = {
            "scenes": [
                {"scene": 1, "realism_score": 30, "composition_score": 20,
                 "regenerate": True},
            ]
        }

        targets = policy.regeneration_targets(
            evaluation,
            scenes_by_number={1: {"provider": "ai_image"}},
            retry_counts={1: config.QUALITY_MAX_RETRY},
        )

        self.assertEqual(targets, [])


if __name__ == "__main__":
    unittest.main()
