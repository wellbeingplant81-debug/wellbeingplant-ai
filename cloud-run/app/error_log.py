"""
Sprint170 - 죽을 때 남길 것을 남긴다 (Epic 58, Phase 2).

묶인 프로그램이 켜자마자 죽으면, 창에 traceback이 쏟아지고 창이
닫히면서 그것마저 사라진다. 사람이 할 수 있는 말은 "안 켜져요"뿐이다.

그래서 둘로 나눈다
------------------
    창에는   사람이 읽을 수 있는 한 줄과 로그가 어디 있는지
    파일에는 traceback 전부

traceback을 창에 쏟지 않는 이유는 숨기려는 것이 아니다. 그 밑에
"무엇을 하십시오"라고 적어도 안 보이기 때문이다.

어디에 쌓이는가
---------------
    <사용자 자리>/logs/error-YYYYMMDD-HHMMSS.log

사용자 자리다 - 프로그램 자리는 읽기 전용일 수 있고, 임시 폴더는
다음에 켤 때 사라진다.

무엇을 함께 적는가
------------------
판번호와 빌드 날짜. 받아 본 사람이 "어느 판입니까"를 되묻지 않아도
되게 한다.
"""

import datetime
import os
import traceback

DIRNAME = "logs"

# 한 번에 남기는 파일 하나의 이름.
_STAMP = "%Y%m%d-%H%M%S"


def directory() -> str:
    """로그가 쌓이는 자리."""

    from app import runtime_paths

    return os.path.join(runtime_paths.home(), DIRNAME)


def write(failed: BaseException) -> str:
    """
    무엇이 어떻게 죽었는지 적고, 적은 자리를 돌려준다.

    여기서 다시 죽지 않는다 - 오류를 적다가 나는 오류는 원래 오류를
    덮어 버리고, 그러면 아무것도 남지 않는다.
    """

    from app import app_info, runtime_paths

    try:
        folder = runtime_paths.ensure(directory())

        when = datetime.datetime.now()
        path = os.path.join(folder, f"error-{when.strftime(_STAMP)}.log")

        body = [
            app_info.title(),
            f"언제  {when.isoformat(timespec='seconds')}",
            f"판    {app_info.VERSION}",
            f"자리  {runtime_paths.home()}",
            "",
            "".join(traceback.format_exception(
                type(failed), failed, failed.__traceback__)),
        ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(body))

        return path
    except Exception:
        return ""
