"""
Sprint54-1 - BGM Selector.

기존 Music Review Tool(app/tools/music_review.py)이 이미 관리하는
assets/music/<category>/ 구조와 music_library.json을 그대로 재사용한다
(assets/bgm 같은 별도 구조를 새로 만들지 않는다).

지금은 대부분의 카테고리가 아직 비어 있다(리뷰가 진행 중이므로).
그래서 특정 카테고리를 영구적인 기본값으로 고정하지 않는다 - 대신:

- category에 실제로 분류된 mp3가 있으면 그 카테고리에서 고른다.
- category가 없거나(호출자가 지정하지 않음) 아직 비어 있으면
  assets/music/inbox(미분류 전체 풀)에서 임시로 고른다.
- category 이름 자체가 존재하지 않는 폴더면(오타 등 실제 오류) 명확한
  예외를 던진다.

Music Review Tool이 나중에 분류를 채워 넣으면, 코드 변경 없이도
다음 호출부터 자동으로 그 카테고리를 우선 사용하게 된다 - 두 시스템이
같은 디렉터리를 보기 때문이다.

random_fn을 주입 가능하게 해 둔 것도 같은 이유 - 나중에 AI 기반 선택
로직으로 교체할 때 이 함수의 나머지 부분(폴백/예외 처리)은 그대로
재사용할 수 있게 하기 위함이다.
"""

import os
import random

from app.tools.music_review import DEFAULT_MUSIC_ROOT

AUDIO_EXTENSION = ".mp3"
INBOX_DIR_NAME = "inbox"


def _list_mp3_files(directory: str):

    if not os.path.isdir(directory):
        return None

    return sorted(
        entry
        for entry in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, entry))
        and entry.lower().endswith(AUDIO_EXTENSION)
    )


def select_bgm(
    category: str = None,
    music_root: str = None,
    random_fn=random.choice,
) -> str:
    """
    assets/music/<category>/에 분류된 mp3가 있으면 거기서 고르고,
    없으면(또는 category가 None이면) assets/music/inbox/에서 고른다.

    category가 주어졌는데 그런 이름의 폴더 자체가 없으면 ValueError를
    던진다(오타 등 실제 잘못된 입력). 어느 쪽으로도 고를 mp3가 하나도
    없으면 FileNotFoundError를 던진다. 절대 조용히 None을 반환하지
    않는다.
    """

    music_root = music_root or DEFAULT_MUSIC_ROOT

    if category is not None:

        category_dir = os.path.join(music_root, category)
        tracks = _list_mp3_files(category_dir)

        if tracks is None:
            raise ValueError(
                f"BGM 카테고리 '{category}'가 존재하지 않습니다: {category_dir}"
            )

        if tracks:
            return os.path.join(category_dir, random_fn(tracks))

    inbox_dir = os.path.join(music_root, INBOX_DIR_NAME)
    inbox_tracks = _list_mp3_files(inbox_dir)

    if not inbox_tracks:
        raise FileNotFoundError(
            "사용 가능한 BGM 파일이 없습니다 "
            f"(카테고리 '{category}'도 비어 있고 inbox도 비어 있음): {music_root}"
        )

    return os.path.join(inbox_dir, random_fn(inbox_tracks))
