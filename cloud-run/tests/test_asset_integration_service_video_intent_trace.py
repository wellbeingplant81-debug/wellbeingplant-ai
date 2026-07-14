"""
Sprint101 - Asset Integration은 Motion Contract가 이미 결정한
video_intent를 Selection Trace에 그대로 전달(pass-through)만 한다는
계약을 확인한다. 새 선택 정책을 만들지 않는다 - select_with_relevance
자체는 mock해서 순수하게 "video_intent가 trace에 태깅되는지"만
검증한다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_integration_service as svc


class TestSelectWithVisualRelevanceVideoIntentTagging(unittest.TestCase):

    @patch("app.services.asset_integration_service.get_candidates", return_value=[])
    @patch("app.services.asset_integration_service.select_with_relevance")
    def test_video_intent_is_tagged_onto_every_trace_entry(
        self, mock_select, mock_get_candidates,
    ):
        mock_select.return_value = (
            {"source": "pexels_image", "local_path": "p.png", "metadata": {}},
            [{"candidate": "a", "type": "image", "score": 0.9, "passed": True, "selected": True}],
            False,
        )

        video_intent = {
            "intent": "preferred_video",
            "confidence": 0.9,
            "reason": "운동 동작이 핵심이라 video가 더 자연스러움",
            "source": "ai_classifier",
        }

        _, _, trace, _ = svc._select_with_visual_relevance(
            image_prompt="prompt", staging_path="staging", channel="wellbeing",
            is_hook_scene=False, visual_type=None, visual_profile=None,
            narration="narration", prefer_ai=False, allow_video=True,
            search_query_override="query", video_intent=video_intent,
        )

        self.assertEqual(trace[0]["video_intent"]["intent"], "preferred_video")
        self.assertEqual(trace[0]["video_intent"]["reason"], "운동 동작이 핵심이라 video가 더 자연스러움")
        self.assertEqual(trace[0]["video_intent"]["source"], "ai_classifier")
        # 기존 trace 필드(candidate/type/score/passed/selected)는 그대로 유지된다.
        self.assertEqual(trace[0]["candidate"], "a")
        self.assertEqual(trace[0]["score"], 0.9)
        self.assertTrue(trace[0]["selected"])

    @patch("app.services.asset_integration_service.get_candidates", return_value=[])
    @patch("app.services.asset_integration_service.select_with_relevance")
    def test_video_intent_defaults_to_none_when_not_provided(
        self, mock_select, mock_get_candidates,
    ):
        mock_select.return_value = (
            {"source": "pexels_image", "local_path": "p.png", "metadata": {}},
            [{"candidate": "a", "type": "image", "score": 0.9, "passed": True, "selected": True}],
            False,
        )

        _, _, trace, _ = svc._select_with_visual_relevance(
            image_prompt="prompt", staging_path="staging", channel="wellbeing",
            is_hook_scene=False, visual_type=None, visual_profile=None,
            narration="narration", prefer_ai=False, allow_video=True,
            search_query_override="query",
        )

        self.assertIsNone(trace[0]["video_intent"])


if __name__ == "__main__":
    unittest.main()
