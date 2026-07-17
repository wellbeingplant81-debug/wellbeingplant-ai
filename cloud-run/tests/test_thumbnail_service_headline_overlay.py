"""
Sprint124 (GREEN) - Thumbnail=First Frame Policy + Headline Overlay.

create_thumbnail()은 더 이상 Imagen을 호출하지 않는다 - 이미 렌더링된
무음 합성본(video_builder.py 출력, subtitle mux 전)의 첫 프레임을 그대로
추출하고, thumbnail_headline이 있으면 그 위에 텍스트만 그린다.
thumbnail_headline이 없으면(생성 실패 등) 오버레이 없이 첫 프레임
그대로를 반환한다 - 예외를 던지지 않는다.

keywords에 해당하는 단어는 빨간색, 나머지는 노란색으로 색상이 갈린다
(_line_words_with_colors 순수 함수로 검증).
"""

import os
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import thumbnail_service
from app.services.thumbnail_service import (
    KEYWORD_COLOR,
    TEXT_COLOR,
    _line_words_with_colors,
    create_thumbnail,
)


def _make_test_video(path: str, size: str = "1080x1920", color: str = "blue"):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:s={size}:d=1.0",
            "-pix_fmt", "yuv420p",
            path,
        ],
        capture_output=True,
        check=True,
    )


class TestLineWordsWithColors(unittest.TestCase):

    def test_keyword_word_is_colored_red(self):
        result = _line_words_with_colors("수명이 늘어난다", ["수명"])
        self.assertEqual(result[0], ("수명이", KEYWORD_COLOR))
        self.assertEqual(result[1], ("늘어난다", TEXT_COLOR))

    def test_no_keywords_all_words_are_yellow(self):
        result = _line_words_with_colors("매일 걸으면", [])
        self.assertTrue(all(color == TEXT_COLOR for _, color in result))


class TestCreateThumbnailFirstFrame(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name
        os.makedirs(os.path.join(self.project_path, "video"))

        self.video_path = os.path.join(self.project_path, "video", "short.mp4")
        _make_test_video(self.video_path)

    def test_no_headline_returns_raw_first_frame(self):
        output = create_thumbnail("title", "topic", self.project_path)

        self.assertTrue(os.path.exists(output))
        with Image.open(output) as image:
            self.assertEqual(image.size, (1080, 1920))

    def test_headline_is_drawn_onto_first_frame(self):
        raw_output = create_thumbnail("title", "topic", self.project_path)
        with Image.open(raw_output) as raw_image:
            raw_pixels = list(raw_image.getdata())

        with_headline_output = create_thumbnail(
            "title", "topic", self.project_path,
            thumbnail_headline={"lines": ["매일 걸으면", "수명이", "7년 늘어난다!"], "keywords": ["수명"]},
        )
        with Image.open(with_headline_output) as headline_image:
            headline_pixels = list(headline_image.getdata())

        self.assertNotEqual(raw_pixels, headline_pixels)

    def test_empty_headline_lines_leaves_frame_unmodified(self):
        raw_output = create_thumbnail("title", "topic", self.project_path)
        with Image.open(raw_output) as raw_image:
            raw_pixels = list(raw_image.getdata())

        same_output = create_thumbnail(
            "title", "topic", self.project_path,
            thumbnail_headline={"lines": [], "keywords": []},
        )
        with Image.open(same_output) as same_image:
            same_pixels = list(same_image.getdata())

        self.assertEqual(raw_pixels, same_pixels)


if __name__ == "__main__":
    unittest.main()
