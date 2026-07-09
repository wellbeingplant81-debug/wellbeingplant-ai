import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

import app.services.subtitle_placement_service as subtitle_placement_service
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


def _fake_face(x, y, w, h, score=0.9):
    # 실제 YuNet detect() 결과와 같은 15열 형태를 흉내낸다
    # (0-3: x,y,w,h, 4-13: 랜드마크, 14: score) - 코드는 0-3만 쓴다.
    return [x, y, w, h, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, score]


class TestFaceAvoidancePosition(unittest.TestCase):
    """Sprint58 - 얼굴이 한쪽 스트립에서만 검출되면 그 판단이
    Laplacian 복잡도 비교보다 우선해야 한다."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_face_only_in_bottom_strip_overrides_busier_top(self, mock_detect):
        # 순수 Laplacian이면(top_noise=True) "bottom"을 고른다
        # (test_chooses_bottom_when_top_is_busier 참고) - 그러나
        # 하단에 얼굴이 있으면 얼굴을 가리지 않도록 "top"을 골라야 한다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path, top_noise=True)
        mock_detect.return_value = [_fake_face(x=100, y=750, w=80, h=80)]

        self.assertEqual(choose_subtitle_position(path), POSITION_TOP)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_face_only_in_top_strip_overrides_busier_bottom(self, mock_detect):
        # 순수 Laplacian이면(bottom_noise=True) "top"을 고른다
        # (test_chooses_top_when_bottom_is_busier 참고) - 그러나
        # 상단에 얼굴이 있으면 "bottom"을 골라야 한다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path, bottom_noise=True)
        mock_detect.return_value = [_fake_face(x=100, y=50, w=80, h=80)]

        self.assertEqual(choose_subtitle_position(path), POSITION_BOTTOM)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_faces_in_both_strips_falls_back_to_laplacian(self, mock_detect):
        # 양쪽 다 얼굴이 있으면 타이브레이크로 Laplacian 결과를
        # 그대로 써야 한다("얼굴이 상단에 있으니 무조건 bottom"처럼
        # 한쪽만 보고 단순 판단하면 안 된다) - bottom_noise=True라
        # 순수 Laplacian 결과는 "top"이어야 한다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path, bottom_noise=True)
        mock_detect.return_value = [
            _fake_face(x=100, y=50, w=80, h=80),
            _fake_face(x=100, y=750, w=80, h=80),
        ]

        self.assertEqual(choose_subtitle_position(path), POSITION_TOP)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_no_faces_detected_falls_back_to_laplacian(self, mock_detect):
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path, bottom_noise=True)
        mock_detect.return_value = []

        self.assertEqual(choose_subtitle_position(path), POSITION_TOP)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_face_detection_unavailable_falls_back_to_laplacian(self, mock_detect):
        # _detect_faces가 None을 반환하는 건(검출기 로드 실패, detect()
        # 예외 등) "신뢰할 수 없음"을 뜻한다 - Sprint57과 동일하게
        # Laplacian 결과만으로 판단해야 한다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path, top_noise=True)
        mock_detect.return_value = None

        self.assertEqual(choose_subtitle_position(path), POSITION_BOTTOM)


class TestFaceDetectorInitialization(unittest.TestCase):
    """Sprint58 - 검출기는 성공 시에만 싱글톤으로 캐시하고, 실패는
    캐시하지 않아 다음 호출에서 재시도해야 한다(운영 중 모델 파일이
    뒤늦게 준비돼도 재시작 없이 자동 복구)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._original_detector = subtitle_placement_service._face_detector
        subtitle_placement_service._face_detector = None

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        subtitle_placement_service._face_detector = self._original_detector

    @patch("app.services.subtitle_placement_service.cv2.FaceDetectorYN_create")
    def test_successful_creation_is_cached_as_singleton(self, mock_create):
        sentinel_detector = MagicMock()
        mock_create.return_value = sentinel_detector

        first = subtitle_placement_service._get_face_detector()
        second = subtitle_placement_service._get_face_detector()

        self.assertIs(first, sentinel_detector)
        self.assertIs(second, sentinel_detector)
        self.assertEqual(mock_create.call_count, 1)

    @patch("app.services.subtitle_placement_service.cv2.FaceDetectorYN_create")
    def test_failed_creation_is_not_permanently_cached(self, mock_create):
        sentinel_detector = MagicMock()
        mock_create.side_effect = [RuntimeError("model not found yet"), sentinel_detector]

        first = subtitle_placement_service._get_face_detector()
        second = subtitle_placement_service._get_face_detector()

        self.assertIsNone(first)
        self.assertIs(second, sentinel_detector)
        self.assertEqual(mock_create.call_count, 2)

    @patch("app.services.subtitle_placement_service._get_face_detector")
    def test_detect_faces_returns_none_when_detector_unavailable(self, mock_get_detector):
        mock_get_detector.return_value = None

        result = subtitle_placement_service._detect_faces(
            np.zeros((10, 10, 3), dtype=np.uint8)
        )

        self.assertIsNone(result)

    @patch("app.services.subtitle_placement_service._get_face_detector")
    def test_detect_faces_returns_none_when_detect_raises(self, mock_get_detector):
        broken_detector = MagicMock()
        broken_detector.detect.side_effect = RuntimeError("inference failed")
        mock_get_detector.return_value = broken_detector

        result = subtitle_placement_service._detect_faces(
            np.zeros((10, 10, 3), dtype=np.uint8)
        )

        self.assertIsNone(result)

    @patch("app.services.subtitle_placement_service._get_face_detector")
    def test_detect_faces_returns_empty_list_when_no_faces_found(self, mock_get_detector):
        # 실제 YuNet API는 얼굴이 없으면 faces로 None을 반환한다.
        detector = MagicMock()
        detector.detect.return_value = (1, None)
        mock_get_detector.return_value = detector

        result = subtitle_placement_service._detect_faces(
            np.zeros((10, 10, 3), dtype=np.uint8)
        )

        self.assertEqual(list(result), [])

    @patch("app.services.subtitle_placement_service._get_face_detector")
    def test_detect_faces_passes_through_detected_faces(self, mock_get_detector):
        faces_array = np.array([_fake_face(10, 20, 30, 40)])
        detector = MagicMock()
        detector.detect.return_value = (1, faces_array)
        mock_get_detector.return_value = detector

        result = subtitle_placement_service._detect_faces(
            np.zeros((10, 10, 3), dtype=np.uint8)
        )

        np.testing.assert_array_equal(result, faces_array)

    @patch("app.services.subtitle_placement_service.cv2.FaceDetectorYN_create")
    def test_detector_created_only_once_across_multiple_calls(self, mock_create):
        detector = MagicMock()
        detector.detect.return_value = (1, None)
        mock_create.return_value = detector

        path_a = os.path.join(self.tmp_dir, "a.png")
        path_b = os.path.join(self.tmp_dir, "b.png")
        _make_image(path_a)
        _make_image(path_b)

        choose_subtitle_position(path_a)
        choose_subtitle_position(path_b)

        self.assertEqual(mock_create.call_count, 1)


if __name__ == "__main__":
    unittest.main()
