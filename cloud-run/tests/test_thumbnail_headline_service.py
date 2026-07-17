"""
Sprint124 (GREEN) - thumbnail_headline_service.generate_thumbnail_
headline()이 Gemini 응답(JSON)을 lines/keywords dict로 파싱한다.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import thumbnail_headline_service


FAKE_HEADLINE_DATA = {
    "lines": ["매일 걸으면", "수명이", "7년 늘어난다!"],
    "keywords": ["수명"],
}


def _mock_gemini_response(data=FAKE_HEADLINE_DATA, wrap_code_fence=False):
    response = MagicMock()
    text = json.dumps(data, ensure_ascii=False)
    if wrap_code_fence:
        text = f"```json\n{text}\n```"
    response.text = text
    return response


class TestGenerateThumbnailHeadline(unittest.TestCase):

    @patch("app.services.thumbnail_headline_service.client")
    def test_parses_lines_and_keywords_from_response(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response()

        result = thumbnail_headline_service.generate_thumbnail_headline(
            "걷기 운동", "매일 걷기만 해도 수명이 7년 늘어난다", "이게 진짜일까요?", "스크립트 본문",
        )

        self.assertEqual(result["lines"], FAKE_HEADLINE_DATA["lines"])
        self.assertEqual(result["keywords"], FAKE_HEADLINE_DATA["keywords"])

    @patch("app.services.thumbnail_headline_service.client")
    def test_strips_json_code_fence(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            wrap_code_fence=True,
        )

        result = thumbnail_headline_service.generate_thumbnail_headline(
            "topic", "title", "hook", "script",
        )

        self.assertEqual(result["lines"], FAKE_HEADLINE_DATA["lines"])

    @patch("app.services.thumbnail_headline_service.client")
    def test_missing_keywords_defaults_to_empty_list(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            data={"lines": ["한 줄"]},
        )

        result = thumbnail_headline_service.generate_thumbnail_headline(
            "topic", "title", "hook", "script",
        )

        self.assertEqual(result["keywords"], [])

    @patch("app.services.thumbnail_headline_service.client")
    def test_prompt_includes_title_hook_and_topic(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response()

        thumbnail_headline_service.generate_thumbnail_headline(
            "걷기 운동", "매일 걷기만 해도 수명이 7년 늘어난다", "후킹 문장", "스크립트 본문",
        )

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("걷기 운동", sent_prompt)
        self.assertIn("매일 걷기만 해도 수명이 7년 늘어난다", sent_prompt)
        self.assertIn("후킹 문장", sent_prompt)
        self.assertIn("스크립트 본문", sent_prompt)


if __name__ == "__main__":
    unittest.main()
