"""
Sprint114 - Resolver들이 공유하는 어휘 (Epic 54, Phase 13).

Sprint106(대본)·111(이미지)·113(음성)이 각자 Resolver를 만들면서 같은
것을 세 번 적었다. 여기서 꺼내는 것은 그 세 번뿐이다.

무엇을 꺼내고 무엇을 두는가
---------------------------
꺼낸 것은 *데이터와 얕은 골격*이다.

    출처의 이름           auto / import / manual
    우선순위              적힌 것 > 디스크 > AUTO
    project.json 읽기     어느 칸을 볼지만 다르다
    번호 붙은 파일 세기   파일명 규칙만 다르다

두고 온 것은 *각 단계의 본질*이다. run()의 인자도, 반환값도, 무엇을
"준비됐다"로 볼지도, 모자랄 때 거절할지 물러설지도 단계마다 다르고,
그 다름이 곧 각 Resolver가 존재하는 이유다.

왜 클래스가 아닌가
------------------
StageResolver를 만들면 03의 폴백과 조립을 담기 위해 훅이 두세 개 더
생기고, 그 훅은 01과 02에서 비어 있게 된다. 상속으로 빈칸을 만드는
구조다. 여기서 얻으려는 것은 줄 수가 아니라 어휘와 우선순위가
갈라지지 않는다는 보장이고, 그것은 상태 없는 함수 넷이면 충분하다.

각 Resolver는 이 모듈을 쓰되 이 모듈을 상속하지 않고, 서로를 알지도
않는다.
"""

import json
import os

# 어디서 가져오는가. 세 단계가 같은 말을 쓴다 - 한쪽만 "upload"로
# 바뀌는 날이 오면 화면과 파이프라인이 조용히 어긋난다.
AUTO = "auto"
IMPORT = "import"
MANUAL = "manual"

SOURCES = (AUTO, IMPORT, MANUAL)

# 사용자가 미리 놓은 것을 쓰는 출처들. 둘 다 엔진을 부르지 않는다.
# 디스크에서는 구분되지 않는다 - 다른 것은 그것이 어디서 왔는가이고,
# 파이프라인이 알 필요가 없다.
PREPARED_SOURCES = (IMPORT, MANUAL)

# 사람이 고른 것을 적어 두는 파일. 어느 칸을 보는지는 단계마다
# 다르므로(production_source / image_source / voice_source) 칸 이름은
# 여기 두지 않는다.
PROJECT_FILENAME = "project.json"


def source_from_metadata(project_path, field):
    """
    project.json의 field에 적힌 출처. 없으면 None.

    적혀 있으면 그것이 가장 확실한 근거다 - 프로젝트를 만든 쪽이 직접
    남긴 것이므로 디스크 상태를 보고 추측할 필요가 없다.

    읽을 수 없는 project.json 때문에 제작이 멈추지는 않는다. 못 읽으면
    적혀 있지 않은 것과 같게 다룬다 - 최상위가 객체가 아닌 경우까지
    포함한다(그때 .get을 부르면 AttributeError로 터진다).
    """

    try:
        with open(
            os.path.join(project_path, PROJECT_FILENAME), "r", encoding="utf-8",
        ) as f:
            metadata = json.load(f)
    except Exception:
        return None

    value = metadata.get(field) if isinstance(metadata, dict) else None

    return value if value in SOURCES else None


def resolve_source(project_path, field, has_prepared):
    """
    적힌 것 > 디스크 > AUTO.

    디스크를 보는 이유는 create_project()가 산출물 디렉터리를 비운 채로
    만들기 때문이다. 비어 있으면 아직 아무도 놓지 않았다는 뜻이다.

    무엇을 "놓였다"로 볼지는 단계가 정한다 - has_prepared()가 그
    판단이고, 적혀 있으면 부르지 않는다.
    """

    recorded = source_from_metadata(project_path, field)

    if recorded is not None:
        return recorded

    return IMPORT if has_prepared() else AUTO


def numbered_files(directory, pattern):
    """
    directory에 실제로 있는 번호들. pattern은 {number} 자리를 가진
    파일명이다("scene{number}.png").

    파일이 있는 것만 센다 - 몇 개를 만들었어야 하는가가 아니라 지금
    무엇이 있는가를 묻는 자리다.
    """

    if not os.path.isdir(directory):
        return []

    stem, suffix = pattern.format(number="\0").split("\0")
    found = []

    for name in os.listdir(directory):
        if not (name.startswith(stem) and name.endswith(suffix)):
            continue

        digits = name[len(stem):len(name) - len(suffix)]

        if digits.isdigit():
            found.append(int(digits))

    return sorted(found)


def unknown_source_message(subject, resolved):
    """모르는 출처를 받았을 때 사람에게 할 말.

    예외 종류는 단계마다 다르다 - 어느 단계에서 멈췄는지가 잡는
    쪽에 필요하기 때문이다. 그래서 문장만 여기 있고 raise는 각자
    한다."""

    return (
        f"알 수 없는 {subject} 출처입니다: {resolved}. "
        f"{', '.join(SOURCES)} 중 하나여야 합니다."
    )
