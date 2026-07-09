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


class TestHookSceneLargeFacePolicy(unittest.TestCase):
    """Sprint60 Hotfix - Hook Scene(scene 1)에서 얼굴이 화면 대부분을
    채우는 클로즈업이면, 얼굴 bbox 중심이 상/하 25% 스트립 어느 쪽에도
    속하지 않아(중앙) 기존 회피 로직이 전혀 작동하지 않고 자막이 얼굴
    중앙(코/입)을 그대로 가리는 문제가 실측됐다(2026-07-09 QA -
    scene1.png, 얼굴이 13.8%~50.6% 구간을 채움, center_y가 25%/75%
    경계 밖이라 avoidance 미작동). is_hook_scene=True이고 큰 얼굴이면
    "하단 Safe Area가 안 겹치는지 -> 상단 Safe Area가 안 겹치는지 ->
    그 외(기존 로직)" 우선순위로 직접 겹침을 판정한다."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_hook_scene_large_middle_face_prefers_bottom_when_clear(
        self, mock_detect,
    ):
        # height=800(_make_image 기본값) -> top_h=200, bottom_boundary=600.
        # 얼굴이 y=250~550(center=400, 중앙) - 어느 스트립 중심 판정에도
        # 안 걸리지만, bbox 자체는 top_h~bottom_boundary 사이(하단 Safe
        # Area 안 겹침)에 완전히 들어간다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path)
        mock_detect.return_value = [_fake_face(x=100, y=250, w=200, h=300)]

        result = choose_subtitle_position(path, is_hook_scene=True)

        self.assertEqual(result, POSITION_BOTTOM)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_hook_scene_large_face_prefers_top_when_bottom_overlaps(
        self, mock_detect,
    ):
        # 얼굴이 y=450~750(bottom_boundary=600을 침범) - 하단 Safe Area는
        # 얼굴과 겹치지만, 상단(top_h=200 이후부터 시작하므로 안 겹침)은
        # 비어 있다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path)
        mock_detect.return_value = [_fake_face(x=100, y=450, w=200, h=300)]

        result = choose_subtitle_position(path, is_hook_scene=True)

        self.assertEqual(result, POSITION_TOP)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_hook_scene_face_overlapping_both_areas_falls_back_to_existing_logic(
        self, mock_detect,
    ):
        # 얼굴이 y=50~750로 화면 대부분(상/하 Safe Area 둘 다)을 덮으면
        # 새 정책이 답을 못 찾고, 기존 로직(중심점 스트립 판정 ->
        # Laplacian)에 그대로 맡긴다 - 여기선 uniform 이미지라
        # DEFAULT_POSITION(bottom)이 되어야 한다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path)
        mock_detect.return_value = [_fake_face(x=100, y=50, w=200, h=700)]

        result = choose_subtitle_position(path, is_hook_scene=True)

        self.assertEqual(result, DEFAULT_POSITION)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_hook_scene_small_face_uses_existing_logic_unchanged(
        self, mock_detect,
    ):
        # 얼굴이 작으면(HOOK_LARGE_FACE_HEIGHT_RATIO 미만) 새 정책이
        # 아예 관여하지 않는다 - 기존 회피 로직(스트립 중심점)만
        # 적용된다. 이 작은 얼굴은 중앙에 있어(어느 스트립 중심
        # 판정에도 안 걸림) 기존 로직대로 Laplacian(uniform ->
        # DEFAULT_POSITION)으로 간다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path)
        mock_detect.return_value = [_fake_face(x=100, y=380, w=80, h=40)]

        result = choose_subtitle_position(path, is_hook_scene=True)

        self.assertEqual(result, DEFAULT_POSITION)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_hook_scene_29_percent_face_still_triggers_policy(self, mock_detect):
        # 회귀 재현 - 2026-07-09 2차 QA 실측: height_ratio=0.299인 실제
        # Hook Scene 얼굴이 처음 임계값(0.30)을 근소하게 못 넘어 정책이
        # 발동하지 않았고, 여전히 자막이 입 위에 겹쳤다(영상 프레임으로
        # 직접 확인). 이 정도 크기도 "큰 얼굴"로 잡아야 한다.
        #
        # bottom_noise=True를 써서, 정책이 발동하지 않았을 때(순수
        # Laplacian)의 답("top")과 정책이 발동했을 때의 답("bottom")이
        # 실제로 달라지게 만든다 - 얼굴이 200~600(중앙) 사이에 완전히
        # 들어가 있어(어느 스트립도 안 겹침) 정책이 발동하면 우선순위
        # 1번(하단 안 겹침)으로 즉시 "bottom"을 고른다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path, bottom_noise=True)
        # height=800 기준 29% -> h=232, 중앙(center_y=400)에 위치.
        mock_detect.return_value = [_fake_face(x=100, y=284, w=200, h=232)]

        result = choose_subtitle_position(path, is_hook_scene=True)

        self.assertEqual(result, POSITION_BOTTOM)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_hook_scene_no_faces_uses_existing_default(self, mock_detect):
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path)
        mock_detect.return_value = []

        result = choose_subtitle_position(path, is_hook_scene=True)

        self.assertEqual(result, DEFAULT_POSITION)

    @patch("app.services.subtitle_placement_service._detect_faces")
    def test_non_hook_scene_unaffected_by_large_face_policy(self, mock_detect):
        # is_hook_scene 기본값(False)에서는 완전히 기존 동작 그대로여야
        # 한다 - 같은 "큰 중앙 얼굴"이어도 새 정책이 관여하지 않는다.
        path = os.path.join(self.tmp_dir, "img.png")
        _make_image(path)
        mock_detect.return_value = [_fake_face(x=100, y=250, w=200, h=300)]

        result = choose_subtitle_position(path)

        self.assertEqual(result, DEFAULT_POSITION)


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


class TestFaceDetectionDownscaling(unittest.TestCase):
    """Sprint60 Hotfix - 문제3: YuNet은 파이프라인이 실제로 만드는
    초고해상도(수천 px) 이미지에서 신뢰도가 급락한다(2026-07-09 E2E
    실측 - 2333x3500/4480x6720 원본 해상도에서 뚜렷한 얼굴을 0건
    검출하거나, 3981x5972에서 얼굴 대신 22x26px짜리 엉뚱한 blob을
    검출함. 동일 이미지를 640px로 축소하면 4장 모두 0.9+ confidence로
    정확히 검출됨). detect() 전에 적당한 최대 변으로 축소하고, bbox는
    원본 좌표계로 복원해야 한다."""

    def setUp(self):
        self._original_detector = subtitle_placement_service._face_detector
        subtitle_placement_service._face_detector = None

    def tearDown(self):
        subtitle_placement_service._face_detector = self._original_detector

    @patch("app.services.subtitle_placement_service._get_face_detector")
    def test_large_image_is_downscaled_before_detect(self, mock_get_detector):
        detector = MagicMock()
        detector.detect.return_value = (1, None)
        mock_get_detector.return_value = detector

        large_image = np.zeros((3500, 2333, 3), dtype=np.uint8)  # h=3500, w=2333
        subtitle_placement_service._detect_faces(large_image)

        detector.setInputSize.assert_called_once()
        (called_size,), _ = detector.setInputSize.call_args
        called_w, called_h = called_size

        self.assertLessEqual(
            max(called_w, called_h),
            subtitle_placement_service.FACE_DETECTION_MAX_DIMENSION,
        )
        # 원본 비율(2333:3500)이 유지돼야 한다.
        self.assertAlmostEqual(called_w / called_h, 2333 / 3500, places=2)

    @patch("app.services.subtitle_placement_service._get_face_detector")
    def test_small_image_is_not_resized(self, mock_get_detector):
        detector = MagicMock()
        detector.detect.return_value = (1, None)
        mock_get_detector.return_value = detector

        small_image = np.zeros((400, 300, 3), dtype=np.uint8)  # h=400, w=300
        subtitle_placement_service._detect_faces(small_image)

        detector.setInputSize.assert_called_once_with((300, 400))

    @patch("app.services.subtitle_placement_service._get_face_detector")
    def test_detected_face_bbox_is_rescaled_back_to_original_coordinates(
        self, mock_get_detector,
    ):
        detector = MagicMock()
        # 축소된 좌표계에서 검출된 얼굴(x=100,y=150,w=50,h=60).
        detected_face = _fake_face(100, 150, 50, 60)
        detector.detect.return_value = (
            1, np.array([detected_face], dtype=np.float32),
        )
        mock_get_detector.return_value = detector

        large_image = np.zeros((3500, 2333, 3), dtype=np.uint8)
        result = subtitle_placement_service._detect_faces(large_image)

        # 관찰된 호출 인자가 아니라, 기대하는 상수로부터 독립적으로
        # scale을 계산한다 - 그래야 축소 자체가 빠진 구현(scale=1.0)을
        # 이 테스트가 실제로 잡아낼 수 있다.
        expected_scale = (
            subtitle_placement_service.FACE_DETECTION_MAX_DIMENSION / 3500
        )

        self.assertEqual(len(result), 1)
        rescaled = result[0]
        self.assertAlmostEqual(float(rescaled[0]), 100 / expected_scale, delta=1.0)
        self.assertAlmostEqual(float(rescaled[1]), 150 / expected_scale, delta=1.0)
        self.assertAlmostEqual(float(rescaled[2]), 50 / expected_scale, delta=1.0)
        self.assertAlmostEqual(float(rescaled[3]), 60 / expected_scale, delta=1.0)

    @patch("app.services.subtitle_placement_service._get_face_detector")
    def test_no_faces_found_on_large_image_returns_empty_list(
        self, mock_get_detector,
    ):
        detector = MagicMock()
        detector.detect.return_value = (1, None)
        mock_get_detector.return_value = detector

        large_image = np.zeros((3500, 2333, 3), dtype=np.uint8)
        result = subtitle_placement_service._detect_faces(large_image)

        self.assertEqual(list(result), [])


if __name__ == "__main__":
    unittest.main()
