import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_duplicate_detector


def _save_8x8_grayscale(path: str, pixel_values):
    """
    pixel_values: 길이 64인 0~255 값 리스트. 8x8 소스 이미지를 그대로
    저장하므로 average_hash()의 resize((8,8))이 항등 변환이 되어,
    Hamming distance를 픽셀 값만으로 정확히 예측할 수 있다.
    """
    array = np.array(pixel_values, dtype=np.uint8).reshape(8, 8)
    Image.fromarray(array, mode="L").save(path)


# 32개는 밝게(220), 32개는 어둡게(30) - 평균은 정확히 125가 되어
# threshold(>=평균) 판정이 픽셀 값만으로 결정된다.
BASE_PIXELS = [220] * 32 + [30] * 32


def _near_duplicate_pixels(flips: int):
    """
    BASE_PIXELS에서 어두운 픽셀 flips개를 밝게 바꾼 변형을 만든다.
    평균이 재계산되어도(130.9 등) 원래 밝은/어두운 그룹은 각각
    새 평균보다 여전히 높거나/낮으므로, 정확히 flips개의 해시 비트만
    달라진다(Hamming distance == flips).
    """
    pixels = list(BASE_PIXELS)
    for i in range(flips):
        # 어두운 픽셀(인덱스 32~63) 중 앞에서부터 flips개를 밝게 변경
        pixels[32 + i] = 220
    return pixels


class TestFindDuplicateAssets(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)

    def _path(self, name):
        return os.path.join(self._tmp_dir.name, name)

    # --- 정확 중복 ---

    def test_detects_exact_duplicate_by_file_content(self):
        path_a = self._path("a.png")
        path_b = self._path("b.png")
        _save_8x8_grayscale(path_a, BASE_PIXELS)
        _save_8x8_grayscale(path_b, BASE_PIXELS)

        result = asset_duplicate_detector.find_duplicate_assets([path_a, path_b])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["index"], 1)
        self.assertEqual(result[0]["duplicate_of_index"], 0)
        self.assertEqual(result[0]["reason"], "exact")
        self.assertEqual(result[0]["hamming_distance"], 0)
        self.assertEqual(result[0]["similarity"], 1.0)

    # --- 근사 중복 ---

    def test_detects_near_duplicate_within_default_threshold(self):
        path_a = self._path("a.png")
        path_b = self._path("b.png")
        _save_8x8_grayscale(path_a, BASE_PIXELS)
        _save_8x8_grayscale(path_b, _near_duplicate_pixels(flips=2))

        result = asset_duplicate_detector.find_duplicate_assets([path_a, path_b])

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["index"], 1)
        self.assertEqual(entry["duplicate_of_index"], 0)
        self.assertEqual(entry["reason"], "near_duplicate")
        self.assertEqual(entry["hamming_distance"], 2)
        self.assertAlmostEqual(entry["similarity"], 1 - 2 / 64, places=3)

    def test_similarity_field_matches_formula(self):
        path_a = self._path("a.png")
        path_b = self._path("b.png")
        _save_8x8_grayscale(path_a, BASE_PIXELS)
        _save_8x8_grayscale(path_b, _near_duplicate_pixels(flips=4))

        result = asset_duplicate_detector.find_duplicate_assets([path_a, path_b])

        entry = result[0]
        self.assertEqual(entry["hamming_distance"], 4)
        self.assertEqual(entry["similarity"], round(1 - 4 / 64, 3))

    # --- 임계값 경계 ---

    def test_distance_at_threshold_boundary_is_flagged(self):
        path_a = self._path("a.png")
        path_b = self._path("b.png")
        _save_8x8_grayscale(path_a, BASE_PIXELS)
        _save_8x8_grayscale(
            path_b,
            _near_duplicate_pixels(flips=asset_duplicate_detector.DEFAULT_HAMMING_THRESHOLD),
        )

        result = asset_duplicate_detector.find_duplicate_assets([path_a, path_b])

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]["hamming_distance"],
            asset_duplicate_detector.DEFAULT_HAMMING_THRESHOLD,
        )

    def test_distance_beyond_threshold_is_not_flagged(self):
        path_a = self._path("a.png")
        path_b = self._path("b.png")
        _save_8x8_grayscale(path_a, BASE_PIXELS)
        _save_8x8_grayscale(
            path_b,
            _near_duplicate_pixels(
                flips=asset_duplicate_detector.DEFAULT_HAMMING_THRESHOLD + 1,
            ),
        )

        result = asset_duplicate_detector.find_duplicate_assets([path_a, path_b])

        self.assertEqual(result, [])

    def test_custom_threshold_overrides_default(self):
        path_a = self._path("a.png")
        path_b = self._path("b.png")
        _save_8x8_grayscale(path_a, BASE_PIXELS)
        _save_8x8_grayscale(path_b, _near_duplicate_pixels(flips=3))

        # 기본 threshold(5)라면 잡히지만, threshold=2로 좁히면 안 잡혀야 한다.
        result = asset_duplicate_detector.find_duplicate_assets(
            [path_a, path_b], hamming_threshold=2,
        )

        self.assertEqual(result, [])

    # --- 완전히 다른 이미지 ---

    def test_clearly_different_images_report_no_duplicates(self):
        path_a = self._path("a.png")
        path_b = self._path("b.png")
        _save_8x8_grayscale(path_a, BASE_PIXELS)
        # BASE_PIXELS를 완전히 반전 - Hamming distance는 64(최대)여야 한다.
        inverted = [30 if v == 220 else 220 for v in BASE_PIXELS]
        _save_8x8_grayscale(path_b, inverted)

        result = asset_duplicate_detector.find_duplicate_assets([path_a, path_b])

        self.assertEqual(result, [])

    # --- 여러 개 중 일부만 중복 ---

    def test_only_the_duplicate_pair_is_reported_among_four_assets(self):
        path_0 = self._path("0.png")
        path_1 = self._path("1.png")
        path_2 = self._path("2.png")
        path_3 = self._path("3.png")

        _save_8x8_grayscale(path_0, BASE_PIXELS)
        inverted = [30 if v == 220 else 220 for v in BASE_PIXELS]
        _save_8x8_grayscale(path_1, inverted)
        _save_8x8_grayscale(path_2, BASE_PIXELS)  # index 0과 정확히 동일
        _save_8x8_grayscale(path_3, _near_duplicate_pixels(flips=6))  # threshold(5) 초과, 안 잡힘

        result = asset_duplicate_detector.find_duplicate_assets(
            [path_0, path_1, path_2, path_3],
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["index"], 2)
        self.assertEqual(result[0]["duplicate_of_index"], 0)
        self.assertEqual(result[0]["reason"], "exact")

    # --- 존재하지 않는 파일 경로 ---

    def test_missing_file_path_is_skipped_not_raised(self):
        path_a = self._path("a.png")
        missing_path = self._path("does_not_exist.png")
        path_c = self._path("c.png")

        _save_8x8_grayscale(path_a, BASE_PIXELS)
        _save_8x8_grayscale(path_c, BASE_PIXELS)  # a와 정확히 동일

        # missing_path(index 1)는 비교 대상에서 제외되고, a(0)와 c(2)의
        # 정확 중복만 정상적으로 잡혀야 한다 - 예외가 발생하면 안 된다.
        result = asset_duplicate_detector.find_duplicate_assets(
            [path_a, missing_path, path_c],
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["index"], 2)
        self.assertEqual(result[0]["duplicate_of_index"], 0)

    def test_all_missing_paths_returns_empty_list(self):
        result = asset_duplicate_detector.find_duplicate_assets(
            [self._path("missing1.png"), self._path("missing2.png")],
        )

        self.assertEqual(result, [])

    def test_empty_list_returns_empty_list(self):
        self.assertEqual(asset_duplicate_detector.find_duplicate_assets([]), [])

    def test_single_asset_returns_empty_list(self):
        path_a = self._path("a.png")
        _save_8x8_grayscale(path_a, BASE_PIXELS)

        result = asset_duplicate_detector.find_duplicate_assets([path_a])

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
