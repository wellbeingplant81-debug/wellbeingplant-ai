"""
Sprint82 - Replay Viewer의 읽기 계층.

순수 뷰어다. 데이터셋도, Observatory도, 생산 산출물도 건드리지 않는다.
읽고, 규칙을 되돌려 보고, 화면이 쓸 모양으로 바꾼다.

Replay 자체는 Sprint78의 asset_replay가 한다. 여기서 다시 구현하지
않는다 - 화면과 스크립트가 서로 다른 답을 내면 둘 중 무엇이 맞는지
알 수 없게 된다.
"""

import copy
import os

from app.tools import asset_dataset, replay_rules


def _dataset_path() -> str:
    # 늦은 import - 파이프라인 모듈을 뷰어가 통째로 끌고 오지 않게.
    from app.pipeline.pipeline import DATASET_ROOT

    return os.path.join(DATASET_ROOT, asset_dataset.DATASET_FILENAME)


def _rank(values: list) -> dict:
    """점수 -> 순위(0부터). 동점이면 앞선 것이 이긴다 - 프로덕션의
    max()와 같은 규칙이어야 재생이 의미를 갖는다."""

    order = sorted(
        range(len(values)), key=lambda i: (-values[i], i),
    )

    return {index: rank for rank, index in enumerate(order)}


def _row_view(row: dict, scorer) -> dict:
    """행 하나를 화면 모양으로. 원본은 건드리지 않는다."""

    candidates = row.get("candidates") or []
    terms = list(row.get("scene_terms") or [])

    scene_context = {
        "scene": row.get("scene"),
        "scene_terms": terms,
        "subject": " ".join(terms),
        "query": row.get("query"),
    }

    original_scores = [
        (c.get("ranking_score") if c.get("ranking_score") is not None else 0.0)
        for c in candidates
    ]
    replay_scores = [
        scorer(copy.deepcopy(c), dict(scene_context)) for c in candidates
    ]

    original_rank = _rank(original_scores)
    replay_rank = _rank(replay_scores)

    original_index = next(
        (i for i, c in enumerate(candidates) if c.get("selected")), None,
    )
    new_index = min(
        range(len(candidates)), key=lambda i: replay_rank[i],
    ) if candidates else None

    changed = (
        original_index is not None
        and new_index is not None
        and original_index != new_index
    )

    view_candidates = []

    for index, candidate in enumerate(candidates):
        view_candidates.append({
            "index": index,
            "provider": candidate.get("provider"),
            "alt": candidate.get("alt"),
            "slug": candidate.get("slug"),
            "width": candidate.get("width"),
            "height": candidate.get("height"),
            "duration": candidate.get("duration"),
            # 점수 내역 - 무엇이 이 점수를 만들었는지
            "relevance": candidate.get("relevance"),
            "human_penalty": candidate.get("human_penalty"),
            "composition": candidate.get("composition"),
            "motion": candidate.get("motion"),
            "original_score": original_scores[index],
            "original_rank": original_rank[index],
            "replay_score": round(replay_scores[index], 4),
            "replay_rank": replay_rank[index],
            "delta": round(replay_scores[index] - original_scores[index], 4),
            "was_selected": index == original_index,
            "would_be_selected": index == new_index,
        })

    def _label(index):
        if index is None:
            return None
        candidate = candidates[index]
        return candidate.get("alt") or candidate.get("slug") or "(설명 없음)"

    return {
        "project": row.get("project"),
        "scene": row.get("scene"),
        "query": row.get("query"),
        "scene_terms": terms,
        "provider": row.get("provider"),
        "regenerate": bool(row.get("regenerate")),
        "gemini_reason": row.get("gemini_reason"),
        "realism": row.get("realism"),
        # Sprint83 - scene이 계획한 것. 구버전 행에는 없어서 전부
        # None이고, 화면은 그것을 "기록되지 않음"으로 보여 준다.
        "planned": {
            field: (row.get("planned") or {}).get(field)
            for field in ("camera", "composition", "visual_type", "purpose")
        },
        "has_plan": bool(row.get("has_plan")),
        "candidates": view_candidates,
        "original_winner": _label(original_index),
        "new_winner": _label(new_index),
        "status": "WOULD CHANGE" if changed else "UNCHANGED",
        "changed": changed,
        "delta": (
            round(replay_scores[new_index] - replay_scores[original_index], 4)
            if changed else 0.0
        ),
        "reason": (
            f"{_label(new_index)} 가 {_label(original_index)} 를 앞섭니다."
            if changed else "이 규칙에서는 선택이 바뀌지 않습니다."
        ),
    }


def replay_view(rule_key: str = replay_rules.BASELINE) -> dict:
    """
    축적된 데이터셋 전체를 규칙 하나로 되돌려 본다.

    데이터가 없으면 없다고 말한다. 지어내지 않는다 - 뷰어가 빈 화면
    대신 그럴듯한 숫자를 보여 주면 그것이 판단 근거가 되어 버린다.
    """

    scorer = replay_rules.scorer_for(rule_key)

    path = _dataset_path()
    rows = asset_dataset.load(path)

    views = [_row_view(row, scorer) for row in rows if row.get("candidates")]

    changed = [v for v in views if v["changed"]]

    return {
        "rule": rule_key,
        "rules": replay_rules.catalog(),
        "dataset_path": path,
        "has_data": bool(views),
        "missing_reason": (
            None if views else
            "후보 풀이 기록된 scene이 아직 없습니다. 스톡 scene이 있는 "
            "영상을 만들면 Observatory가 자동으로 쌓습니다."
        ),
        "scenes": len(views),
        "changed": len(changed),
        "changed_on_failed": sum(
            1 for v in changed if v["regenerate"]
        ),
        "changed_on_passed": sum(
            1 for v in changed if not v["regenerate"]
        ),
        "rows": views,
        "gate": asset_dataset.readiness(rows),
    }


def project_replay_view(project_path: str,
                        rule_key: str = replay_rules.BASELINE) -> dict:
    """
    프로젝트 하나의 Observatory를 되돌려 본다.

    asset_dataset.build()가 Observatory + 평가를 행으로 바꾸는 일을 이미
    한다. 여기서 다시 읽지 않는다.
    """

    scorer = replay_rules.scorer_for(rule_key)

    rows = [
        row for row in asset_dataset.build(project_path)
        if row.get("candidates")
    ]

    views = [_row_view(row, scorer) for row in rows]

    return {
        "rule": rule_key,
        "rules": replay_rules.catalog(),
        "has_data": bool(views),
        "missing_reason": (
            None if views else
            "이 프로젝트에는 후보 기록이 없습니다. scene이 전부 Imagen "
            "경로로 갔거나, Observatory가 도입되기 전에 만들어진 "
            "영상입니다."
        ),
        "scenes": len(views),
        "changed": sum(1 for v in views if v["changed"]),
        "rows": views,
    }
