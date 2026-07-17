"""
Sprint122 (RED) - render_profile_name passthrough at the factory_service
entry point (factory_service -> pipeline). Mirrors the existing
production_profile_name passthrough (generate_short_video ->
run_pipeline) added in Sprint100-2.

이번 스프린트는 "인터페이스 관통"이 목표이므로 generate_short_video()
자체의 이름은 바꾸지 않는다 - render_profile_name="longform"으로 같은
함수를 호출하는 것으로 충분하다(요구사항 문서의 generate_long_video()
예시는 설명용이지 새 함수를 요구한 것이 아니다).
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import factory_service


class TestGenerateShortVideoRenderProfilePassthrough(unittest.TestCase):

    @patch("app.services.factory_service.create_project")
    @patch("app.services.factory_service.run_pipeline")
    def test_render_profile_name_passed_through_to_run_pipeline(
        self, mock_run_pipeline, mock_create_project,
    ):
        mock_create_project.return_value = {"id": "1", "path": "output/proj"}
        mock_run_pipeline.return_value = {"title": "t"}

        factory_service.generate_short_video(
            "topic", channel="wellbeing", render_profile_name="longform",
        )

        _, kwargs = mock_run_pipeline.call_args
        self.assertEqual(kwargs["render_profile_name"], "longform")

    @patch("app.services.factory_service.create_project")
    @patch("app.services.factory_service.run_pipeline")
    def test_default_render_profile_name_is_none(
        self, mock_run_pipeline, mock_create_project,
    ):
        mock_create_project.return_value = {"id": "1", "path": "output/proj"}
        mock_run_pipeline.return_value = {"title": "t"}

        factory_service.generate_short_video("topic")

        _, kwargs = mock_run_pipeline.call_args
        self.assertIsNone(kwargs["render_profile_name"])

    @patch("app.services.factory_service.create_project")
    @patch("app.services.factory_service.run_pipeline")
    def test_both_profile_names_can_be_combined(
        self, mock_run_pipeline, mock_create_project,
    ):
        mock_create_project.return_value = {"id": "1", "path": "output/proj"}
        mock_run_pipeline.return_value = {"title": "t"}

        factory_service.generate_short_video(
            "topic",
            production_profile_name="upload",
            render_profile_name="longform",
        )

        _, kwargs = mock_run_pipeline.call_args
        self.assertEqual(kwargs["production_profile_name"], "upload")
        self.assertEqual(kwargs["render_profile_name"], "longform")


if __name__ == "__main__":
    unittest.main()
