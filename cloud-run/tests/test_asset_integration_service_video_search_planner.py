"""
Sprint102 - Video Coverage Intelligence. asset_integration_service.
_gather_stock_result()가

1. config.ENABLE_VIDEO_SEARCH_PLANNER가 꺼져 있으면(기본값) 기존과
   100% 동일하게 검색어 하나(search_query_override)만 시도하는지
2. 켜져 있고 allow_video=True면, 첫 검색어가 실패(all_failed)했을 때
   video_search_planner가 만든 다음 검색어로 재시도하는지
3. "충분한 품질"의 기준이 select_with_relevance()의 all_failed 그대로
   인지(새 채점 로직을 만들지 않는지) - 즉 어떤 시도에서 통과하는
   순간 더 이상 검색어를 시도하지 않는지
4. MAX_QUERY_ATTEMPTS를 넘는 검색어는 시도하지 않는지
5. allow_video=False면 플래그가 켜져 있어도 검색어를 하나만 시도하는지
   (Video Search Planner는 video를 더 잘 찾기 위한 것 - image-only
   scene에는 적용할 이유가 없다)

를 확인한다. 전부 mock 기반이며 실제 Gemini/Pexels 호출은 없다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.services import asset_integration_service as svc


class TestGatherStockResultFeatureFlagOff(unittest.TestCase):

    def setUp(self):
        original_flag = config.ENABLE_VIDEO_SEARCH_PLANNER
        config.ENABLE_VIDEO_SEARCH_PLANNER = False
        self.addCleanup(setattr, config, "ENABLE_VIDEO_SEARCH_PLANNER", original_flag)

    @patch("app.services.asset_integration_service.video_search_planner.plan_video_search_queries")
    @patch("app.services.asset_integration_service.get_candidates", return_value=[])
    @patch("app.services.asset_integration_service.select_with_relevance")
    def test_tries_exactly_one_query_when_disabled(
        self, mock_select, mock_get_candidates, mock_plan,
    ):
        mock_select.return_value = (None, [], True)

        svc._gather_stock_result(
            "image prompt", True, "primary query", "narration", "staging",
        )

        mock_get_candidates.assert_called_once_with(
            "image prompt", allow_video=True, search_query_override="primary query",
        )
        mock_plan.assert_not_called()


class TestGatherStockResultFeatureFlagOn(unittest.TestCase):

    def setUp(self):
        original_flag = config.ENABLE_VIDEO_SEARCH_PLANNER
        config.ENABLE_VIDEO_SEARCH_PLANNER = True
        self.addCleanup(setattr, config, "ENABLE_VIDEO_SEARCH_PLANNER", original_flag)

    @patch("app.services.asset_integration_service.video_search_planner.plan_video_search_queries")
    @patch("app.services.asset_integration_service.get_candidates", return_value=["candidate"])
    @patch("app.services.asset_integration_service.select_with_relevance")
    def test_retries_next_query_when_first_fails(
        self, mock_select, mock_get_candidates, mock_plan,
    ):
        mock_plan.return_value = ["primary query", "action query", "fallback query"]
        mock_select.side_effect = [
            (None, [{"candidate": "a", "score": 0.2}], True),   # primary 실패
            ({"source": "pexels_video", "local_path": "p.png"}, [{"candidate": "b", "score": 0.8}], False),  # action 통과
        ]

        result, trace, all_failed = svc._gather_stock_result(
            "image prompt", True, "primary query", "narration", "staging",
        )

        self.assertFalse(all_failed)
        self.assertEqual(result["local_path"], "p.png")
        # 통과한 순간 멈춰야 하므로 get_candidates/select_with_relevance는
        # 딱 2번만 호출된다(fallback query까지 가지 않음).
        self.assertEqual(mock_get_candidates.call_count, 2)
        self.assertEqual(mock_select.call_count, 2)

    @patch("app.services.asset_integration_service.video_search_planner.plan_video_search_queries")
    @patch("app.services.asset_integration_service.get_candidates", return_value=["candidate"])
    @patch("app.services.asset_integration_service.select_with_relevance")
    def test_stops_after_max_query_attempts(
        self, mock_select, mock_get_candidates, mock_plan,
    ):
        mock_plan.return_value = [
            "primary", "action", "fallback1", "fallback2", "fallback3",
        ]
        mock_select.return_value = (None, [], True)  # 전부 실패

        svc._gather_stock_result(
            "image prompt", True, "primary", "narration", "staging",
        )

        self.assertLessEqual(mock_get_candidates.call_count, svc.MAX_QUERY_ATTEMPTS)

    @patch("app.services.asset_integration_service.video_search_planner.plan_video_search_queries")
    @patch("app.services.asset_integration_service.get_candidates", return_value=["candidate"])
    @patch("app.services.asset_integration_service.select_with_relevance")
    def test_all_queries_fail_returns_last_attempt_with_all_failed_true(
        self, mock_select, mock_get_candidates, mock_plan,
    ):
        mock_plan.return_value = ["primary", "action"]
        mock_select.side_effect = [
            (None, [{"candidate": "a"}], True),
            ({"source": "pexels_image", "local_path": "last.png"}, [{"candidate": "b"}], True),
        ]

        result, trace, all_failed = svc._gather_stock_result(
            "image prompt", True, "primary", "narration", "staging",
        )

        self.assertTrue(all_failed)
        self.assertEqual(result["local_path"], "last.png")  # 마지막 시도 결과를 그대로 반환
        self.assertEqual(len(trace), 2)  # 두 시도의 trace가 모두 합쳐짐

    @patch("app.services.asset_integration_service.video_search_planner.plan_video_search_queries")
    @patch("app.services.asset_integration_service.get_candidates", return_value=[])
    @patch("app.services.asset_integration_service.select_with_relevance")
    def test_allow_video_false_skips_planner_even_when_flag_on(
        self, mock_select, mock_get_candidates, mock_plan,
    ):
        mock_select.return_value = (None, [], True)

        svc._gather_stock_result(
            "image prompt", False, "primary query", "narration", "staging",
        )

        mock_plan.assert_not_called()
        mock_get_candidates.assert_called_once_with(
            "image prompt", allow_video=False, search_query_override="primary query",
        )

    @patch("app.services.asset_integration_service.video_search_planner.plan_video_search_queries")
    @patch("app.services.asset_integration_service.get_candidates", return_value=["candidate"])
    @patch("app.services.asset_integration_service.select_with_relevance")
    def test_search_query_tagged_onto_trace_entries(
        self, mock_select, mock_get_candidates, mock_plan,
    ):
        mock_plan.return_value = ["primary", "action"]
        mock_select.side_effect = [
            (None, [{"candidate": "a"}], True),
            ({"source": "pexels_video", "local_path": "p.png"}, [{"candidate": "b"}], False),
        ]

        _, trace, _ = svc._gather_stock_result(
            "image prompt", True, "primary", "narration", "staging",
        )

        self.assertEqual(trace[0]["search_query"], "primary")
        self.assertEqual(trace[1]["search_query"], "action")

    @patch("app.services.asset_integration_service.video_search_planner.plan_video_search_queries")
    @patch("app.services.asset_integration_service.get_candidates", return_value=["candidate"])
    @patch("app.services.asset_integration_service.select_with_relevance")
    def test_each_query_attempt_uses_a_distinct_staging_path(
        self, mock_select, mock_get_candidates, mock_plan,
    ):
        """
        Sprint102 하드닝 - 여러 쿼리 시도가 select_with_relevance()에
        넘기는 staging_path_prefix가 서로 달라야 한다. 그래야 내부
        candidate{index}.png 파일명이 시도마다 겹치지 않아, 앞선 시도의
        아직 discard되지 않은 결과 파일을 다음 시도가 덮어쓰는 경로
        충돌이 구조적으로 불가능하다.
        """
        mock_plan.return_value = ["primary", "action", "fallback"]
        mock_select.return_value = (None, [], True)  # 전부 실패 -> 끝까지 순회

        svc._gather_stock_result(
            "image prompt", True, "primary", "narration", "base_staging",
        )

        used_staging_paths = [
            call.args[3] for call in mock_select.call_args_list
        ]
        self.assertEqual(len(used_staging_paths), len(set(used_staging_paths)))
        self.assertTrue(all(p.startswith("base_staging") for p in used_staging_paths))


if __name__ == "__main__":
    unittest.main()
