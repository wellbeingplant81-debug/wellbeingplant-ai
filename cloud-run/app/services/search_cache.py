"""
Sprint76 - 스톡 검색 응답 캐시.

asset_cache는 내려받은 파일을 캐시하지만 검색 응답은 캐시하지 않는다.
그래서 같은 검색어가 매번 API를 다시 쳤다 - 재생성이 돌 때, 그리고
검색어 확장이 여러 표현을 시도할 때 같은 질의가 반복된다.

프로세스 안에서만 산다. 디스크에 남기지 않는 이유는 스톡 검색 결과가
시간에 따라 바뀌고, 굳혀 두면 다음 실행이 낡은 결과를 쓰기 때문이다.
한 영상을 만드는 동안 같은 질의를 두 번 하지 않는 것으로 충분하다.
"""

import threading


_lock = threading.Lock()
_entries = {}


def clear() -> None:
    """캐시를 비운다. 테스트와 새 실행 사이에서 쓴다."""

    with _lock:
        _entries.clear()


def has(provider: str, query: str) -> bool:
    """Sprint77 - 이 질의가 이미 캐시에 있는가. 부작용 없는 조회다.

    Observatory가 적중/미스를 기록하려면 search()를 부르기 전에 알아야
    한다. search() 안에서 기록하게 만들면 캐시 모듈이 관측을 알게 되고,
    그러면 관측이 생산 경로에 얽힌다.
    """

    with _lock:
        return ((provider, (query or "").strip().lower())) in _entries


def search(provider: str, query: str, search_fn):
    """
    캐시에 있으면 그것을, 없으면 search_fn(query)를 부르고 저장한다.

    0건도 결과로 저장한다 - 같은 검색어로 다시 물어도 0건이고, 그것을
    확인하려고 API를 또 칠 이유가 없다.

    예외는 저장하지 않는다. 검색 실패는 일시적일 수 있는데 캐시에
    굳히면 그 실행 내내 provider가 죽은 것으로 남는다.

    돌려주는 것은 사본이다. 호출자가 정렬하거나 잘라내도 캐시가
    망가지지 않아야 한다.
    """

    key = (provider, (query or "").strip().lower())

    with _lock:
        if key in _entries:
            return [dict(item) for item in _entries[key]]

    results = search_fn(query)

    with _lock:
        _entries[key] = [dict(item) for item in (results or [])]
        return [dict(item) for item in _entries[key]]
