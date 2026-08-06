"""
Sprint77 - Asset Observatory.

Semantic Retrieval을 기각한 이유는 근거가 없어서가 아니라 판단할
데이터가 없어서였다. 실패한 스톡 scene에서 "더 나은 후보가 후보 풀에
있었는가"를 물었는데, 후보 풀을 한 번도 저장한 적이 없었다.

여기서 남기는 것이 그것이다. 기능을 더하지 않는다 - 이미 받아 놓은
Pexels 응답을 적을 뿐이라 Gemini도 Imagen도 늘지 않는다.

가장 중요한 계약은 "관측이 생산을 바꾸지 않는다"이다. Sprint66에서
같은 실수를 했다 - 측정 결과를 project_data에 담아 두었더니
_save_script()가 script.json에 써서, 플래그를 켜는 것만으로 생성
산출물이 +1,277자 달라졌다. 관측은 별도 파일로만 나간다.

세션 개념이 있는 이유는 integrate_asset이 파이프라인 밖에서도 불리기
때문이다(라우터, 테스트). 세션이 시작되지 않았으면 기록은 조용히
버려진다 - 전역 상태에 쌓이면 다음 세션이 남의 데이터를 물려받는다.
"""

import threading

from app.services import asset_relevance
from app.utils.atomic_write import atomic_write_json


OBSERVATORY_FILENAME = "asset_observatory.json"

SCHEMA_VERSION = "sprint77"


_lock = threading.Lock()
_active = False
_scenes = {}


def start() -> None:
    """새 세션을 연다. 이전 세션의 기록은 버린다."""

    global _active

    with _lock:
        _active = True
        _scenes.clear()


def abandon() -> None:
    """세션을 닫고 기록을 버린다."""

    global _active

    with _lock:
        _active = False
        _scenes.clear()


def snapshot() -> dict:
    """현재까지의 기록. 사본이므로 호출자가 만져도 안전하다."""

    with _lock:
        return {
            number: {
                key: (list(value) if isinstance(value, list) else value)
                for key, value in entry.items()
            }
            for number, entry in _scenes.items()
        }


def _entry(scene_number: int) -> dict:
    """호출자가 이미 _lock을 잡고 있어야 한다."""

    return _scenes.setdefault(scene_number, {
        "scene": scene_number,
        "searches": [],
        "candidates": [],
        "scene_terms": [],
        "selection_reason": None,
        "final_provider": None,
        "final_asset": None,
    })


def record_search(scene_number: int, query: str, provider: str,
                  cache_hit: bool, result_count: int) -> None:
    """
    검색 한 번. 확장이 몇 번 돌았는지는 이 기록의 개수로 드러난다 -
    좁은 검색어가 0건이면 넓혀 다시 시도하므로, 같은 scene에 여러 건이
    남는다.
    """

    with _lock:
        if not _active:
            return

        _entry(scene_number)["searches"].append({
            "query": query,
            "provider": provider,
            "cache_hit": bool(cache_hit),
            "result_count": int(result_count),
        })


def _slug(candidate: dict) -> str:
    url = candidate.get("source_url") or ""

    if not url:
        return ""

    parts = [part for part in url.rstrip("/").split("/") if part]

    if not parts:
        return ""

    return parts[-1].replace("-", " ").replace("_", " ")


def _explain(chosen, candidates, scores, scene) -> str:
    """왜 그것을 골랐는지 사람이 읽는 문장으로."""

    if not candidates:
        return "스톡 후보가 없어 Imagen으로 갔습니다."

    if chosen is None:
        return f"후보 {len(candidates)}개 중 선택된 것이 없습니다."

    index = candidates.index(chosen)
    relevance = asset_relevance.relevance_score(chosen, scene or {})
    penalty = asset_relevance.human_penalty(chosen, scene or {})

    parts = [
        f"후보 {len(candidates)}개 중 {index}번",
        f"관련도 {relevance:.3f}",
    ]

    if scores and index < len(scores):
        parts.append(f"총점 {scores[index]:.3f}")

    if penalty:
        parts.append(f"인물 감점 {penalty:.2f}")

    if index:
        parts.append("1번 결과를 뒤집었습니다")

    return ", ".join(parts)


def record_ranking(scene_number: int, scene: dict, candidates: list,
                   chosen, scores: list) -> None:
    """
    후보 전체와 각각의 점수. 이 Epic의 본체다.

    점수만 남기면 기록일 뿐 재현이 아니다. 나중에 다른 순위 방식을
    시험하려면 후보의 원본 신호(alt, 슬러그, 치수, 길이)가 그대로
    있어야 하므로 전부 남긴다.
    """

    scene = scene or {}

    recorded = []

    for index, candidate in enumerate(candidates or []):
        recorded.append({
            "provider": candidate.get("source"),
            "alt": candidate.get("alt") or "",
            "slug": _slug(candidate),
            "source_url": candidate.get("source_url"),
            "download_url": candidate.get("download_url"),
            "width": candidate.get("width"),
            "height": candidate.get("height"),
            "duration": candidate.get("duration"),
            "relevance": round(
                asset_relevance.relevance_score(candidate, scene), 4,
            ),
            "human_penalty": round(
                asset_relevance.human_penalty(candidate, scene), 4,
            ),
            "composition": round(
                asset_relevance.composition_score(candidate), 4,
            ),
            "motion": round(asset_relevance.motion_score(candidate), 4),
            "ranking_score": (
                round(scores[index], 4)
                if scores and index < len(scores) else None
            ),
            "selected": candidate is chosen,
        })

    reason = _explain(chosen, list(candidates or []), scores, scene)
    terms = sorted(asset_relevance._scene_words(scene))

    with _lock:
        if not _active:
            return

        entry = _entry(scene_number)
        entry["candidates"] = recorded
        entry["scene_terms"] = terms
        entry["selection_reason"] = reason


def record_outcome(scene_number: int, provider: str, asset_path: str) -> None:
    """이 scene이 최종적으로 무엇을 썼는지."""

    with _lock:
        if not _active:
            return

        entry = _entry(scene_number)
        entry["final_provider"] = provider
        entry["final_asset"] = asset_path

        # 스톡 검색이 아예 일어나지 않은 scene(Imagen 우선 경로)은
        # 이유가 비어 있으면 "검색이 실패한 것"과 구분되지 않는다.
        if entry["selection_reason"] is None and not entry["searches"]:
            entry["selection_reason"] = (
                "스톡 검색 없이 Imagen으로 갔습니다 (visual_type=ai)."
            )


def write(project_path: str) -> None:
    """
    관측 파일을 남긴다. 실패해도 파이프라인을 막지 않는다 - 이건
    관측 산출물이고, 기록이 안 됐다고 영상을 버릴 이유는 없다
    (Sprint73에서 세운 원칙).

    스톡을 한 번도 쓰지 않은 영상도 파일을 남긴다. "관측이 안 된 것"과
    "쓸 일이 없었던 것"은 다르고, 그 구분이 사후 분석에 필요하다.
    """

    scenes = snapshot()

    hits = sum(
        1 for entry in scenes.values()
        for search in entry["searches"] if search["cache_hit"]
    )
    misses = sum(
        1 for entry in scenes.values()
        for search in entry["searches"] if not search["cache_hit"]
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "cache": {"hits": hits, "misses": misses},
        "scenes": [scenes[number] for number in sorted(scenes)],
    }

    import os

    try:
        atomic_write_json(
            os.path.join(project_path, OBSERVATORY_FILENAME), payload,
        )
    except Exception as exc:
        print(f"[Observatory] 기록 실패(무시): {exc}")
