import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.subtitle_placement_service import (
    DEFAULT_POSITION,
    POSITION_BOTTOM,
    POSITION_TOP,
    choose_subtitle_position,
)


def _make_image(path, height=800, width=600, top_noise=False, bottom_noise=False):
    """상/하 25% 스트립만 선택적으로 노이즈(복잡함)로 채우고, 나머지는
    균일한 회색(단순함)으로 둔 합성 이미지를 만든다."""

    array = np.full((height, width, 3), 128, dtype=np.uint8)

    strip_h = height // 4
    rng = np.random.default_rng(42)

    if top_noise:
        array[:strip_h, :, :] = rng.integers(0, 256, size=(strip_h, width, 3), dtype=np.uint8)

    if bottom_noise:
        array[height - strip_h:, :, :] = rng.integers(0, 256, size=(strip_h, width, 3), dtype=np.uint8)

    Image.fromarray(array).save(path)


class TestChooseSubtitlePosition(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_chooses_top_when_bottom_is_busier(self):
        # 사람 얼굴/피사체가 화면 하단에 있는 상황을 흉내낸다 -
        # 하단이 복잡하니 상대적으로 비어있는 상단을 골라야 한다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path, bottom_noise=True)

        self.assertEqual(choose_subtitle_position(path), POSITION_TOP)

    def test_chooses_bottom_when_top_is_busier(self):
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path, top_noise=True)

        self.assertEqual(choose_subtitle_position(path), POSITION_BOTTOM)

    def test_uniform_image_falls_back_to_default(self):
        # 상/하 모두 단순(동률)하면 기존 동작(하단)과 같은 안전한
        # 기본값을 유지한다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path)

        self.assertEqual(choose_subtitle_position(path), DEFAULT_POSITION)

    def test_missing_file_falls_back_to_default(self):
        result = choose_subtitle_position(os.path.join(self.tmp_dir, "nope.png"))
        self.assertEqual(result, DEFAULT_POSITION)

    def test_none_path_falls_back_to_default(self):
        self.assertEqual(choose_subtitle_position(None), DEFAULT_POSITION)

    def test_empty_string_path_falls_back_to_default(self):
        self.assertEqual(choose_subtitle_position(""), DEFAULT_POSITION)

    def test_corrupt_file_falls_back_to_default(self):
        path = os.path.join(self.tmp_dir, "corrupt.png")
        with open(path, "wb") as f:
            f.write(b"not a real image")

        self.assertEqual(choose_subtitle_position(path), DEFAULT_POSITION)

    def test_result_is_always_a_valid_position(self):
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path, top_noise=True)

        self.assertIn(choose_subtitle_position(path), (POSITION_TOP, POSITION_BOTTOM))

    def test_default_position_is_bottom(self):
        # 기존 자막 스타일(final_video_service.py의 Alignment=2)이
        # 항상 하단이었으므로, 판단이 애매할 땐 기존 동작을 그대로
        # 유지하는 쪽(하단)이 기본값이어야 한다.
        self.assertEqual(DEFAULT_POSITION, POSITION_BOTTOM)


if __name__ == "__main__":
    unittest.main()
