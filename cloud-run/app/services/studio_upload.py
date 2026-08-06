"""
Sprint92 - Pipeline Upload Integration (Phase 5).

Sprint89(Upload Core) / Sprint90(OAuth) / Sprint91(Upload Runtime)을
실제 제작 흐름에 붙인다. 이 모듈은 업로드를 직접 하지 않는다 - 언제
해도 되는지만 판정하고, 되면 Sprint91의 run_youtube_upload_step()에
넘긴다.

호출 위치를 정해야 했다. Epic이 준 순서는

    생성 완료 -> Inspection 통과 -> Approved -> Upload -> Queue -> Published

이고, 원칙은 "Workflow를 중심으로 연결"이다. 그래서 방아쇠는 승인이다 -
파이프라인이 영상을 다 만들었다는 사실만으로는 올리지 않는다. 갓 만든
프로젝트는 아직 사람이 보지 않았고, 검수 전에 올라가면 되돌릴 수 없다.

파이프라인 끝에서도 같은 함수를 부른다(Acceptance 1). 다만 갓 만든
프로젝트는 승인 상태가 아니므로 거기서는 항상 건너뛴다. 두 입구가
같은 문을 쓰는 것이 요점이다 - 업로드해도 되는지 판정하는 곳이 두
군데가 되면 언젠가 서로 어긋난다.

건너뛸 때는 파일을 쓰지 않는다. 기본값(ENABLE_YOUTUBE_UPLOAD=False)
으로 도는 파이프라인이 프로젝트 폴더에 새 파일을 남기면, 기존 산출물
계약이 조용히 바뀐다. 실제로 시도한 경우에만 기록이 남는다.

업로드 실패는 파이프라인 실패가 아니다. 영상은 이미 다 만들어졌고,
올리는 데 실패한 것뿐이다 - 예외를 밖으로 내보내지 않는다.
"""

import json
import os

from app import config
from app.services import studio_workflow

# 업로드 결과의 어휘. 여기에 두는 이유가 있다.
#
# 이 모듈은 파이프라인이 import한다. 그런데 youtube_upload_step_service
# 에서 이 이름들을 가져오면 그 한 줄 때문에 Upload Core 전체와
# googleapiclient가 파이프라인에 딸려 들어온다 - 플래그가 꺼져 있어
# 업로드할 생각이 없는 실행에서도 그렇다. 아래 run_upload()가 무거운
# 것을 함수 안에서 들이는 것과 같은 이유다.
#
# 그래서 어휘는 의존성이 없는 이 층이 갖고, step service가 여기서
# 가져다 쓴다.
RESULT_FILENAME = "youtube_upload_result.json"

# 읽는 쪽이 "시도하지 않음"과 "시도했다 거절당함"을 구분할 수 있어야
# 한다. success=False만 보면 플래그가 꺼져 있어서 아무 일도 안 한
# 프로젝트가 업로드 실패로 보인다.
UPLOADED = "uploaded"
SKIPPED = "skipped"
FAILED = "failed"

DISABLED_REASON = "ENABLE_YOUTUBE_UPLOAD가 꺼져 있습니다."
NOT_APPROVED_REASON = (
    "승인되지 않은 프로젝트입니다. Production Queue에서 승인한 뒤에 "
    "업로드할 수 있습니다."
)


def default_store_path() -> str:
    """승인 기록이 있는 곳. 프로젝트 디렉터리 밖이다(Sprint84).

    DATASET_ROOT가 pipeline에 있고 pipeline이 이 모듈을 부르므로 함수
    안에서 들인다 - 모듈 최상단에 두면 순환한다."""

    from app.pipeline.pipeline import DATASET_ROOT

    return os.path.join(
        os.path.dirname(DATASET_ROOT), ".workflow",
        studio_workflow.STORE_FILENAME,
    )


def _load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def read_result(project_path: str):
    """업로드 결과. 없으면 None - 아직 시도한 적이 없다는 뜻이다."""

    return _load(os.path.join(project_path, RESULT_FILENAME))


def _skipped(reason: str) -> dict:
    """건너뜀. 파일을 쓰지 않는다 - 아무 일도 일어나지 않았다."""

    return {
        "success": False,
        "outcome": SKIPPED,
        "upload_id": None,
        "url": None,
        "error": reason,
        "thumbnail_error": None,
        "playlist_error": None,
    }


def is_approved(project_id: str, store_path: str) -> bool:
    stored = studio_workflow.load_store(store_path)

    return (stored.get(project_id) or {}).get("status") == studio_workflow.APPROVED


def run_upload(project_path: str, store_path: str) -> dict:
    """
    승인된 프로젝트를 YouTube에 올린다.

    판정 순서가 곧 안전장치다. 플래그가 먼저고, 승인이 그다음이고,
    자격증명은 Sprint91이 본다. 앞 관문에서 막히면 뒤쪽 코드는 아예
    실행되지 않는다.
    """

    if not config.ENABLE_YOUTUBE_UPLOAD:
        return _skipped(DISABLED_REASON)

    project_id = os.path.basename(os.path.normpath(project_path))

    if not is_approved(project_id, store_path):
        return _skipped(NOT_APPROVED_REASON)

    # 여기서만 무거운 것을 들인다. 플래그가 꺼져 있으면 Upload Core도
    # OAuth도 import되지 않는다.
    from app.services import youtube_upload_step_service

    meta = _load(os.path.join(project_path, "project.json")) or {}
    data = _load(os.path.join(project_path, "script.json")) or {}

    return youtube_upload_step_service.run_youtube_upload_step(
        meta.get("topic") or data.get("title") or "",
        project_path,
        data,
    )


def run_upload_quietly(project_path: str, store_path: str) -> dict:
    """
    파이프라인 끝에서 부르는 입구.

    업로드가 어떻게 되든 영상 생성은 이미 끝났다 - 예외를 밖으로
    내보내지 않는다. 관측이 생산을 막지 않는다는 Sprint79의 원칙과
    같다.
    """

    try:
        return run_upload(project_path, store_path)
    except Exception as exc:
        print(f"Upload step failed: {exc}")
        return _skipped(f"업로드 단계에서 예외가 발생했습니다: {exc}")
