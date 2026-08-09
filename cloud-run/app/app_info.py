"""
Sprint170 - 이 프로그램이 제 이름과 판을 안다 (Epic 58, Phase 2).

받은 사람이 물을 수 있는 것은 셋뿐이다.

    이게 뭐냐        이름
    어느 판이냐      판번호
    언제 만든 거냐   빌드 날짜

지금까지 셋 다 아무 데도 없었다. 무엇이 잘못됐을 때 "어느 판을 쓰고
계십니까"라고 물으면 답할 방법이 없다.

판번호는 여기 하나뿐이다
------------------------
창에 찍는 것, exe의 파일 속성, README, 오류 로그가 모두 이것을 읽는다.
자리마다 적어 두면 어느 날 서로 다른 말을 한다.

빌드 날짜는 재는 것이지 정하는 것이 아니다
------------------------------------------
묶을 때 build_info.json이 프로그램 안에 들어간다. 개발 중에는 묶은
적이 없으므로 없다 - 그때 오늘 날짜를 적으면 "언제 묶은 것인가"라는
물음에 거짓으로 답하게 된다.
"""

import json
import os

# 사람이 부르는 이름. 사용자 자리의 폴더 이름과 같다 - 탐색기에서
# 찾을 때 같은 글자여야 한다.
NAME = "AI영상제작소"

# 처음으로 남에게 줄 수 있게 묶은 판이다.
#
# 1.0.0으로 적지 않는다. 실기기랄 것은 없으나 아직 이 저장소 밖의
# PC에서 돈 적이 없고, 그 사실을 판번호로 감출 이유가 없다.
VERSION = "0.1.0"

# 묶을 때 프로그램 안에 들어가는 것.
BUILD_FILENAME = "build_info.json"

# Sprint174 - 막혔을 때 물어볼 곳.
#
# 여기 하나에서만 온다. README도 창도 화면도 이것을 읽는다 - 손으로
# 옮겨 적으면, 바뀐 줄 모르고 없는 주소로 보내는 사람이 생긴다.
# 답을 못 받은 사람은 다시 묻지 않는다.
CONTACT = "wellbeingplant81@gmail.com"


def build_date():
    """
    언제 묶었는가. 묶은 적이 없으면 None.

    묶는 쪽이 적어 둔 것을 읽기만 한다.
    """

    from app import runtime_paths

    path = os.path.join(runtime_paths.bundle_root(), BUILD_FILENAME)

    try:
        with open(path, encoding="utf-8") as f:
            found = json.load(f)
    except Exception:
        return None

    if not isinstance(found, dict):
        return None

    return found.get("built_at") or None


def label() -> str:
    """이름과 판. 화면의 좁은 자리에 들어간다."""

    return f"{NAME} {VERSION}"


def title() -> str:
    """창과 로그의 첫 줄. 아는 것만 적는다."""

    made = build_date()

    return label() + (f" ({made} 빌드)" if made else "")


# Sprint173 - 화면이 판번호를 말하는 자리.
#
# 화면에 판번호를 손으로 적지 않는다. 적으면 그 자리가 다음 판에
# 뒤처지고, 실제로 그랬다 - 화면에는 "Studio v1"이라고 적혀 있었고
# 프로그램은 0.1.0이었다.
#
# 화면은 이 표를 들고 있고, 내보낼 때 여기서 채운다.
PAGE_TOKEN = "{{APP_VERSION}}"

# Sprint174 - 문의처도 같은 방식이다. 화면에 적어 두지 않는다.
CONTACT_TOKEN = "{{APP_CONTACT}}"
