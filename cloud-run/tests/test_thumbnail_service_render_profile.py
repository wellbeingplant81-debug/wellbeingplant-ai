"""
Sprint124 (GREEN) - create_thumbnail()이 render_profile에 따라 어떤
무음 합성본(video/short.mp4 vs video/longform.mp4)에서 첫 프레임을
추출하는지, 어떤 파일명(thumbnail.png vs thumbnail_longform.png)으로
저장하는지 확인한다. render_profile을 안 넘기면(기본값 None) 기존
Shorts 파일명과 100% 동일하다.

(Sprint122 시절 이 파일은 generate_image()의 aspect_ratio kwarg를
검증했으나, Sprint124부터 썸네일은 Imagen 생성이 아니라 영상 첫 프레임
추출 방식으로 바뀌어 그 검증 대상 자체가 없어졌다 - test_thumbnail_
service_headline_overlay.py가 새 동작을 담당한다.)
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

from app.services.thumbnail_service import create_thumbnail
from app.services.render_profile import RenderProfile


LONGFORM = RenderProfile.get("longform")


class TestCreateThumbnailRenderProfile(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    @patch("app.services.thumbnail_service._extract_first_frame")
    def test_default_reads_short_mp4_and_writes_thumbnail_png(self, mock_extract):
        output = create_thumbnail("title", "topic", self.project_path)

        video_path, output_path = mock_extract.call_args[0]
        self.assertTrue(video_path.endswith(os.path.join("video", "short.mp4")))
        self.assertEqual(os.path.basename(output_path), "thumbnail.png")
        self.assertEqual(output, output_path)

    @patch("app.services.thumbnail_service._extract_first_frame")
    def test_longform_reads_longform_mp4_and_writes_distinct_filename(self, mock_extract):
        create_thumbnail(
            "title", "topic", self.project_path, render_profile=LONGFORM,
        )

        video_path, output_path = mock_extract.call_args[0]
        self.assertTrue(video_path.endswith(os.path.join("video", "longform.mp4")))
        self.assertEqual(os.path.basename(output_path), "thumbnail_longform.png")


if __name__ == "__main__":
    unittest.main()
