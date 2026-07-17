"""
Sprint124 (GREEN) - pipeline.py가 step01 직후 thumbnail_headline_
service로 썸네일 전용 헤드라인을 생성해 step06_thumbnail.run()에
전달한다. 생성이 실패해도(Gemini 오류 등) 파이프라인을 막지 않고
title 한 줄짜리로 안전하게 폴백한다 - render_profile opt-in 여부와
무관하게 항상 시도된다.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.pipeline import pipeline

from tests.test_pipeline_production_profile import patched_pipeline, _wire_defaults


class TestPipelineThumbnailHeadline(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def _run_pipeline(self, **kwargs):
        return pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
            **kwargs,
        )

    def test_headline_generated_from_title_hook_script(self):
        with patched_pipeline() as m:
            _wire_defaults(m)
            m["thumbnail_headline_service"].generate_thumbnail_headline.return_value = {
                "lines": ["매일 걸으면", "수명이", "7년 늘어난다!"], "keywords": ["수명"],
            }

            self._run_pipeline()

            m["thumbnail_headline_service"].generate_thumbnail_headline.assert_called_once_with(
                "주제", "t", "h", "s",
            )

    def test_headline_forwarded_to_step06(self):
        with patched_pipeline() as m:
            _wire_defaults(m)
            headline = {"lines": ["매일 걸으면", "수명이", "7년 늘어난다!"], "keywords": ["수명"]}
            m["thumbnail_headline_service"].generate_thumbnail_headline.return_value = headline

            self._run_pipeline()

            _, kwargs = m["step06"].run.call_args
            self.assertEqual(kwargs["thumbnail_headline"], headline)

    def test_headline_stored_on_result_data(self):
        with patched_pipeline() as m:
            _wire_defaults(m)
            headline = {"lines": ["매일 걸으면"], "keywords": []}
            m["thumbnail_headline_service"].generate_thumbnail_headline.return_value = headline

            result = self._run_pipeline()

            self.assertEqual(result["thumbnail_headline"], headline)

    def test_generation_failure_falls_back_to_title_only(self):
        with patched_pipeline() as m:
            _wire_defaults(m)
            m["thumbnail_headline_service"].generate_thumbnail_headline.side_effect = Exception("gemini down")

            result = self._run_pipeline()

            self.assertEqual(result["thumbnail_headline"], {"lines": ["t"], "keywords": []})
            _, kwargs = m["step06"].run.call_args
            self.assertEqual(kwargs["thumbnail_headline"], {"lines": ["t"], "keywords": []})


if __name__ == "__main__":
    unittest.main()
