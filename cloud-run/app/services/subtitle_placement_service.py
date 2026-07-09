"""
Sprint57 - Smart Subtitle Placement v1.

기존 자막은 항상 화면 하단(final_video_service.py의 Alignment=2)에
고정되어 있어, 실제 E2E에서 사람 얼굴/피사체가 하단에 있는 이미지에
자막이 그대로 겹치는 문제가 있었다. 이 모듈은 scene 이미지 하나를
받아 화면 상단 25% / 하단 25% 영역의 "복잡도"(Laplacian 분산 - 값이
클수록 가장자리/디테일이 많다는 뜻)를 비교해서, 더 단순한(비어있는)
쪽에 자막을 배치하도록 "top"/"bottom" 중 하나를 고른다.

이미지가 없거나 읽을 수 없으면 기존 동작과 동일한 DEFAULT_POSITION
(하단)으로 안전하게 폴백한다 - 어떤 경우에도 예외를 던지지 않는다
(subtitle 생성이 이 판단 하나 때문에 실패하면 안 된다).

Sprint58 - 얼굴 회피 (FaceDetectorYN).

opencv-python-headless 5.0.0에는 cv2.CascadeClassifier가 없어(Haar
Cascade 사용 불가), DNN 기반 YuNet(cv2.FaceDetectorYN)으로 얼굴을
찾는다. 얼굴이 상/하단 스트립 중 한쪽에서만 검출되면 그 판단이
Laplacian 복잡도 비교보다 우선한다(자막이 얼굴을 가리는 걸 막는 게
목적이므로, "복잡도는 낮지만 얼굴이 있는 쪽"을 고르면 안 된다).
양쪽 다 얼굴이 있거나 둘 다 없으면(또는 얼굴 검출 자체가 불가능하면)
기존 Sprint57 Laplacian 비교로 폴백한다 - 얼굴 검출은 있으면 우선
적용되는 추가 신호일 뿐, 실패 시 전체 기능이 죽는 하드 디펜던시가
아니다.

검출기 초기화가 실패해도(모델 파일이 아직 없는 등) 그 실패를
영구적으로 캐시하지 않는다 - 성공했을 때만 싱글톤으로 재사용하고,
실패하면 다음 호출에서 다시 시도한다(운영 중 모델 파일이 나중에
채워지는 경우에도 재시작 없이 자동 복구되도록).
"""

import os

import cv2

TOP_STRIP_RATIO = 0.25
BOTTOM_STRIP_RATIO = 0.25

POSITION_TOP = "top"
POSITION_BOTTOM = "bottom"

DEFAULT_POSITION = POSITION_BOTTOM

_SERVICES_DIR = os.path.dirname(os.path.abspath(__file__))
_CLOUD_RUN_DIR = os.path.dirname(os.path.dirname(_SERVICES_DIR))
FACE_MODEL_PATH = os.path.join(
    _CLOUD_RUN_DIR, "assets", "models", "face_detection_yunet_2023mar.onnx"
)

FACE_CREATE_INPUT_SIZE = (320, 320)
FACE_SCORE_THRESHOLD = 0.7
FACE_NMS_THRESHOLD = 0.3
FACE_TOP_K = 5000

# 성공했을 때만 채워지는 싱글톤 - 실패는 절대 여기 캐시하지 않는다.
_face_detector = None


def _create_face_detector():
    return cv2.FaceDetectorYN_create(
        FACE_MODEL_PATH,
        "",
        FACE_CREATE_INPUT_SIZE,
        FACE_SCORE_THRESHOLD,
        FACE_NMS_THRESHOLD,
        FACE_TOP_K,
    )


def _get_face_detector():
    """얼굴 검출기를 지연 생성해서 재사용한다.

    생성에 성공하면 프로세스 생애주기 동안 캐시해서 씬마다 모델을
    다시 로드하지 않는다. 생성에 실패하면(모델 파일 없음 등) None을
    반환하되 그 실패 자체는 캐시하지 않는다 - 다음 호출에서 다시
    시도하므로, 운영 중 모델 파일이 뒤늦게 준비돼도 재시작 없이
    자동으로 복구된다.
    """

    global _face_detector

    if _face_detector is not None:
        return _face_detector

    try:
        _face_detector = _create_face_detector()
    except Exception:
        return None

    return _face_detector


def _detect_faces(image_bgr):
    """image_bgr에서 얼굴 bbox 목록을 검출한다.

    검출기를 준비할 수 없거나 detect() 자체가 실패하면 None을
    반환한다(= "이번엔 얼굴 검출을 신뢰할 수 없음", 얼굴이 0개인
    것과는 구분된다). 정상적으로 얼굴이 0개면 빈 리스트를 반환한다.
    """

    detector = _get_face_detector()

    if detector is None:
        return None

    try:
        height, width = image_bgr.shape[:2]
        detector.setInputSize((width, height))
        _, faces = detector.detect(image_bgr)
    except Exception:
        return None

    if faces is None:
        return []

    return faces


def _region_complexity(gray_region) -> float:
    return float(cv2.Laplacian(gray_region, cv2.CV_64F).var())


def _face_strip_presence(faces, height, top_h, bottom_h):
    """얼굴 bbox 중심 y좌표를 기준으로 상단/하단 스트립에 얼굴이
    있는지 판정한다. (face_in_top, face_in_bottom) 튜플을 반환한다."""

    face_in_top = False
    face_in_bottom = False

    bottom_boundary = height - bottom_h

    for face in faces:
        face_y, face_h = float(face[1]), float(face[3])
        center_y = face_y + face_h / 2

        if center_y < top_h:
            face_in_top = True
        elif center_y >= bottom_boundary:
            face_in_bottom = True

    return face_in_top, face_in_bottom


def choose_subtitle_position(image_path: str) -> str:
    """
    얼굴이 상/하단 25% 스트립 중 한쪽에서만 검출되면 반대쪽에 자막을
    배치한다(얼굴 회피 최우선). 양쪽 다 얼굴이 있거나 둘 다 없으면
    (또는 얼굴 검출이 불가능하면) 상단/하단 중 더 단순한(복잡도가
    낮은) 쪽에 배치하기로 결정한다. 경로가 없거나, 파일이 없거나,
    이미지를 디코딩할 수 없으면 DEFAULT_POSITION을 반환한다.
    """

    if not image_path or not os.path.exists(image_path):
        return DEFAULT_POSITION

    image_bgr = cv2.imread(image_path, cv2.IMREAD_COLOR)

    if image_bgr is None or image_bgr.size == 0:
        return DEFAULT_POSITION

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    height = gray.shape[0]
    top_h = max(1, int(height * TOP_STRIP_RATIO))
    bottom_h = max(1, int(height * BOTTOM_STRIP_RATIO))

    top_region = gray[:top_h, :]
    bottom_region = gray[height - bottom_h:, :]

    top_complexity = _region_complexity(top_region)
    bottom_complexity = _region_complexity(bottom_region)

    laplacian_position = (
        POSITION_TOP if bottom_complexity > top_complexity else POSITION_BOTTOM
    )

    faces = _detect_faces(image_bgr)

    if faces is None:
        return laplacian_position

    face_in_top, face_in_bottom = _face_strip_presence(faces, height, top_h, bottom_h)

    if face_in_top and not face_in_bottom:
        return POSITION_BOTTOM

    if face_in_bottom and not face_in_top:
        return POSITION_TOP

    return laplacian_position
