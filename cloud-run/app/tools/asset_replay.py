"""
Sprint78 - Replay Harness.
Sprint79 - 축적된 행만으로도 돌아간다.

Observatory가 후보 풀을 통째로 남기므로, 새 순위 규칙을 실제 API 없이
되돌려 볼 수 있다 - "그 규칙이었다면 무엇을 골랐을까".

Ranking v3를 구현하기 전에 이것부터 만드는 이유는 Best-of-N 때문이다.
그때는 표본 없이 코퍼스 통계만 보고 착수했고, 실제로 돌려 보니 후보
사이 편차가 2.2점이라 엔진에 값이 없었다. 규칙은 착수 전에 기록으로
검증한다.

이 모듈은 네트워크를 건드리지 않는다. 디스크의 기록만 읽는다.
"""

import copy

from app.tools import asset_dataset


def replay_rows(rows: list, scorer) -> dict:
    """
    축적된 행에 새 규칙을 적용한다. 순수 계산입니다.

    scorer(candidate, scene) -> float. candidate는 Observatory가 남긴
    dict(alt, slug, relevance, ranking_score, 치수, 길이...)이고 scene은
    그 scene의 맥락(scene_terms, 검색어)이다. 원본 provider 응답을 다시
    만들지 않으므로 API가 필요 없다.

    후보 dict는 사본을 넘긴다 - 규칙이 실수로 건드려도 기록이 망가지지
    않아야 한다.

    반환값에서 중요한 것은 두 숫자다.

      changed_on_failed  이미 실패한 scene에서 선택이 바뀐 횟수.
                         고칠 기회가 있었다는 뜻이다(고쳐진다는 보장은
                         아니다 - 바뀐 후보가 좋은지는 평가해야 안다).
      changed_on_passed  통과한 scene에서 선택이 바뀐 횟수.
                         잘 되던 것을 망칠 위험이다.

    두 번째를 함께 세지 않으면 "실패를 고쳤다"만 보고 회귀를 놓친다.
    """

    scenes_seen = 0
    changes = []
    changed_on_failed = 0
    changed_on_passed = 0

    for row in (rows or []):
        candidates = row.get("candidates") or []

        if not candidates:
            continue

        scenes_seen += 1

        terms = list(row.get("scene_terms") or [])
        scene_context = {
            "scene": row.get("scene"),
            "scene_terms": terms,
            "subject": " ".join(terms),
            "query": row.get("query"),
        }

        original = next(
            (c for c in candidates if c.get("selected")), None,
        )

        scored = [
            (scorer(copy.deepcopy(candidate), dict(scene_context)), candidate)
            for candidate in candidates
        ]

        # 동점이면 앞선 후보가 이긴다 - max()가 첫 최대값을 준다.
        # 프로덕션 순위와 같은 규칙이어야 재생이 의미를 갖는다.
        _, winner = max(scored, key=lambda pair: pair[0])

        if winner is original:
            continue

        was_failure = bool(row.get("regenerate"))

        if was_failure:
            changed_on_failed += 1
        else:
            changed_on_passed += 1

        changes.append({
            "project": row.get("project"),
            "scene": row.get("scene"),
            "was": (original or {}).get("alt") or (original or {}).get("slug"),
            "now": winner.get("alt") or winner.get("slug"),
            "was_failure": was_failure,
            "gemini_reason": row.get("gemini_reason"),
        })

    return {
        "scenes": scenes_seen,
        "changed": len(changes),
        "changed_on_failed": changed_on_failed,
        "changed_on_passed": changed_on_passed,
        "changes": changes,
    }


def replay(root: str, scorer) -> dict:
    """프로젝트 디렉터리를 훑어 재생한다. 축적 파일이 생기기 전의
    산출물도 그대로 볼 수 있게 남겨 둔다."""

    return replay_rows(asset_dataset.build(root), scorer)
