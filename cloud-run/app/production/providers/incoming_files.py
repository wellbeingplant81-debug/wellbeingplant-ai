"""
Sprint112 - 사용자가 준 것을 파일 목록으로 편다 (Epic 54, Phase 11).

Sprint110이 이미지에서 쓰던 것을 그대로 꺼냈다. Sprint112가 음성에서
같은 것을 필요로 하는데, 받는 모양이 넷(폴더/여러 파일/ZIP/섞인 목록)
이라는 사실은 이미지든 음성이든 다르지 않다. 양쪽에 따로 적어 두면
한쪽만 고쳐지는 날이 온다.

다른 것은 받아 주는 확장자와 거절할 때 던지는 예외뿐이라, 그 둘만
받는다. 여기에는 어떤 단계의 어휘도 없다 - 이미지도 음성도 모른다.
"""

import os
import shutil
import zipfile


def is_supported(name: str, suffixes) -> bool:
    return os.path.splitext(name)[1].lower() in suffixes


def sort_key(path: str):
    """번호 순서로 세운다.

    파일 이름이 순서다 - 사람이 0001, 0002로 적었으면 그 순서고,
    2와 10이 섞여 있으면 2가 먼저다(문자열로 세면 10이 앞선다)."""

    stem = os.path.splitext(os.path.basename(path))[0]
    digits = "".join(ch for ch in stem if ch.isdigit())

    return (0, int(digits)) if digits else (1, stem.lower())


def from_directory(path: str, suffixes) -> list:
    found = [
        os.path.join(path, name)
        for name in os.listdir(path)
        if is_supported(name, suffixes)
    ]

    return sorted(found, key=sort_key)


def from_zip(path: str, workspace: str, suffixes) -> list:
    extracted = []

    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or not is_supported(info.filename, suffixes):
                continue
            # 압축 안의 경로는 버리고 이름만 쓴다 - 압축 파일이
            # 바깥 경로를 가리키는 것을 막는다.
            name = os.path.basename(info.filename)
            target = os.path.join(workspace, name)
            with archive.open(info) as source, open(target, "wb") as out:
                shutil.copyfileobj(source, out)
            extracted.append(target)

    return sorted(extracted, key=sort_key)


def collect(payload, workspace: str, suffixes, error, subject: str) -> list:
    """준 것을 파일 목록으로 편다. 목록의 순서는 지킨다.

    error는 거절할 때 던질 예외 클래스, subject는 사람에게 보일
    이름("이미지"/"음성")이다."""

    if payload is None:
        raise error(f"{subject}을(를) 받지 못했습니다.")

    entries = payload if isinstance(payload, (list, tuple)) else [payload]
    collected = []

    for entry in entries:
        path = str(entry)

        if not os.path.exists(path):
            raise error(f"찾을 수 없는 경로입니다: {path}")

        if os.path.isdir(path):
            collected.extend(from_directory(path, suffixes))
        elif zipfile.is_zipfile(path):
            collected.extend(from_zip(path, workspace, suffixes))
        elif is_supported(path, suffixes):
            collected.append(path)
        else:
            suffix = os.path.splitext(path)[1] or "(확장자 없음)"
            raise error(
                f"지원하지 않는 형식입니다: {suffix}. "
                f"{', '.join(suffixes)}만 받습니다."
            )

    if not collected:
        raise error(
            f"{subject}을(를) 하나도 찾지 못했습니다. "
            f"{', '.join(suffixes)} 파일이 있어야 합니다."
        )

    return collected
