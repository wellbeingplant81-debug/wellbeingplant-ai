"""
Sprint122 (RED) - step04_subtitle/step05_video/step06_thumbnail 얇은
wrapper가 render_profile(기본값 None)을 받아 그대로 실제 서비스 함수에
전달한다. pipeline.py -> step0N -> 서비스 함수 3단 배선 중 가운데
(step0N.run())를 각 서비스 함수를 mock해 가볍게 검증한다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.steps import step04_subtitle, step05_video, step06_thumbnail
from app.services.render_profile import RenderProfile


LONGFORM = RenderProfile.get("longform")


class TestStep04SubtitleRenderProfile(unittest.TestCase):

    @patch("app.steps.step04_subtitle.create_subtitle")
    def test_render_profile_forwarded(self, mock_create_subtitle):
        step04_subtitle.run("output/proj", render_profile=LONGFORM)

        _, kwargs = mock_create_subtitle.call_args
        self.assertEqual(kwargs["render_profile"], LONGFORM)

    @patch("app.steps.step04_subtitle.create_subtitle")
    def test_default_render_profile_is_none(self, mock_create_subtitle):
        step04_subtitle.run("output/proj")

        _, kwargs = mock_create_subtitle.call_args
        self.assertIsNone(kwargs["render_profile"])


class TestStep05VideoRenderProfile(unittest.TestCase):

    @patch("app.steps.step05_video.merge_video_audio")
    @patch("app.steps.step05_video.build_video")
    def test_render_profile_forwarded_to_both_calls(self, mock_build_video, mock_merge):
        step05_video.run("output/proj", render_profile=LONGFORM)

        self.assertEqual(mock_build_video.call_args[1]["render_profile"], LONGFORM)
        self.assertEqual(mock_merge.call_args[1]["render_profile"], LONGFORM)

    @patch("app.steps.step05_video.merge_video_audio")
    @patch("app.steps.step05_video.build_video")
    def test_default_render_profile_is_none(self, mock_build_video, mock_merge):
        step05_video.run("output/proj")

        self.assertIsNone(mock_build_video.call_args[1]["render_profile"])
        self.assertIsNone(mock_merge.call_args[1]["render_profile"])


class TestStep06ThumbnailRenderProfile(unittest.TestCase):

    @patch("app.steps.step06_thumbnail.create_thumbnail")
    def test_render_profile_forwarded(self, mock_create_thumbnail):
        step06_thumbnail.run(
            "title", "topic", "output/proj", "wellbeing", "n1", "p1",
            render_profile=LONGFORM,
        )

        _, kwargs = mock_create_thumbnail.call_args
        self.assertEqual(kwargs["render_profile"], LONGFORM)

    @patch("app.steps.step06_thumbnail.create_thumbnail")
    def test_default_render_profile_is_none(self, mock_create_thumbnail):
        step06_thumbnail.run("title", "topic", "output/proj", "wellbeing", "n1", "p1")

        _, kwargs = mock_create_thumbnail.call_args
        self.assertIsNone(kwargs["render_profile"])


if __name__ == "__main__":
    unittest.main()
