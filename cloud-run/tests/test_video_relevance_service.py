"""
Sprint100-3.1 - video_relevance_service.score_relevance()가 Gemini
Vision을 올바른 인자(rubric + scene context + frame 이미지, 구조화
response_schema)로 호출하고 파싱된 결과를 그대로 반환하는지 확인한다.
실제 Gemini 호출은 client를 mock해 대체한다(script_service.py의
기존 테스트 패턴과 동일).
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from PIL import Image

from app.models.video_relevance import VideoRelevanceScore
from app.services import video_relevance_service


class TestScoreRelevance(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.frame_path = os.path.join(self._tmp_dir.name, "frame.png")
        Image.new("RGB", (8, 8), color="white").save(self.frame_path)

    def test_returns_parsed_score(self):
        with patch("app.services.video_relevance_service.client") as mock_client:
            mock_response = MagicMock()
            mock_response.parsed = VideoRelevanceScore(score=0.85, reasoning="관련성 높음")
            mock_client.models.generate_content.return_value = mock_response

            result = video_relevance_service.score_relevance(
                self.frame_path, narration="산책하는 모습", image_prompt="a person walking",
            )

            self.assertEqual(result.score, 0.85)
            self.assertEqual(result.reasoning, "관련성 높음")

    def test_raises_when_gemini_returns_no_parsed_result(self):
        with patch("app.services.video_relevance_service.client") as mock_client:
            mock_response = MagicMock()
            mock_response.parsed = None
            mock_client.models.generate_content.return_value = mock_response

            with self.assertRaises(ValueError):
                video_relevance_service.score_relevance(
                    self.frame_path, narration="n", image_prompt="p",
                )

    def test_calls_gemini_with_structured_schema(self):
        with patch("app.services.video_relevance_service.client") as mock_client:
            mock_response = MagicMock()
            mock_response.parsed = VideoRelevanceScore(score=0.5, reasoning="r")
            mock_client.models.generate_content.return_value = mock_response

            video_relevance_service.score_relevance(
                self.frame_path, narration="n", image_prompt="p",
            )

            _, kwargs = mock_client.models.generate_content.call_args
            self.assertEqual(kwargs["config"].response_schema, VideoRelevanceScore)


if __name__ == "__main__":
    unittest.main()
