"""
Sprint176 - 만든 쪽이 직접 적는다 (Epic 58, Phase 8).

Sprint175는 화면이 job을 물어볼 때 결과를 적었다. 아무도 물어보지
않으면 아무것도 안 적혔다 - 창을 닫아 두고 기다린 사람의 렌더는
기록에 없다. 우리가 알고 싶은 것이 정확히 그 사람이다.

그래서 만드는 실이 끝나는 자리에서 적는다.

왜 따로 모듈인가
----------------
studio_jobs는 작업을 굴리는 자리다. 거기에 "무엇을 적을까"와 "결과가
있다고 볼 수 있는가"까지 들어가면, 그 판단을 아무도 따로 시험할 수
없게 된다. 이 파일은 둘 사이의 얇은 층이고, 여기 있는 판단은 전부
테스트가 직접 부른다.

엔진은 한 글자도 건드리지 않는다 - 이 층은 결과를 '보기만' 한다.

"됐다"와 "됐다고 볼 수 있다"는 다르다
-------------------------------------
엔진이 예외 없이 끝나도 파일이 없으면 그 사람은 영상을 받지 못했다.
그것을 completed로 적으면 우리는 나중에 "잘 되셨네요"라고 답하게
된다. 그래서 결과 파일을 눈으로 본 다음에만 completed다.

파일이 없으면 failed로 적고, 종류는 NO_OUTPUT이다. 사양이 정하지
않은 자리라 우리가 정했다 - 아무것도 안 적는 쪽은 그 사람이 기록에서
사라지는 것이라 더 나쁘다.

무엇을 적지 않는가는 그대로다
-----------------------------
mp4 경로도, 프로젝트 id도, traceback도 적지 않는다. 있는지는 보기만
한다 - 보는 것과 적는 것은 다르다.
"""

import os

# 엔진이 끝났다는데 결과가 없을 때의 종류.
NO_OUTPUT = "no_output"

# 파일이 있다고 볼 최소 크기. 만들다 만 0바이트짜리가 남을 수 있다.
MIN_BYTES = 1


def video_path(project_path: str) -> str:
    """
    최종 영상이 놓이는 자리.

    여기서 새로 정하지 않는다 - output_check가 이미 정한 그 자리를
    쓴다. 두 자리가 따로 정해지면 만들어 놓고도 못 찾는다(이 저장소는
    ffmpeg와 배경 음악에서 이미 두 번 겪었다).
    """

    from app.services import output_check

    return os.path.join(project_path, *output_check.VIDEO_RELATIVE)


def _made_something(project_path: str) -> bool:
    """결과 파일이 실제로 있는가. 보기만 한다."""

    if not project_path:
        return False

    try:
        return os.path.getsize(video_path(project_path)) >= MIN_BYTES
    except OSError:
        return False


def started():
    """
    만들기 시작했다.

    같은 것을 두 번 적지 않는 규칙은 여기 없다 - 만드는 실은 한 번
    돌고 끝나므로, 두 번 적혔다면 정말 두 번 돈 것이다.
    """

    from app.services import beta_telemetry

    return beta_telemetry.note(beta_telemetry.RENDER_STARTED)


def finished(project_path: str):
    """
    엔진이 예외 없이 끝났다. 결과를 보고 무엇으로 적을지 정한다.
    """

    from app.services import beta_telemetry

    if _made_something(project_path):
        return beta_telemetry.note(beta_telemetry.RENDER_COMPLETED)

    beta_telemetry.note_failure(NO_OUTPUT)

    return beta_telemetry.note(beta_telemetry.RENDER_FAILED)


def crashed(failure):
    """
    예외로 끝났다. 종류만 적는다 - 메시지에는 경로가 들어 있다.
    """

    from app.services import beta_telemetry

    beta_telemetry.note_failure(failure)

    return beta_telemetry.note(beta_telemetry.RENDER_FAILED)
