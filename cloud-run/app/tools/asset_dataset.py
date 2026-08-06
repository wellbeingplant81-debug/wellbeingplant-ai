"""
Sprint78 - 누적된 Observatory를 한 표로.

Sprint77의 Observatory는 프로젝트마다 asset_observatory.json을 남긴다.
그것 하나로는 "이번 영상에서 무슨 일이 있었나"만 보인다. 여러 편을
가로질러 "어떤 실패가 반복되는가"를 보려면 합쳐야 한다.

Gemini도 Imagen도 부르지 않는다. 디스크에 이미 있는 것만 읽는다.
"""

import json
import os
from collections import Counter


OBSERVATORY_FILENAME = "asset_observatory.json"
REPORT_FILENAME = "quality_report.json"

# Sprint79 - 축적 파일. 영상을 만들 때마다 여기 쌓인다.
DATASET_FILENAME = "asset_dataset.jsonl"

# Sprint79 - Ranking v3 착수 조건. 사용자가 정한 값이다.
#
# 사람이 눈대중으로 "이 정도면 됐다"고 판단하면 Best-of-N을 다시 한다.
# 그때는 표본 없이 코퍼스 통계만 보고 착수했고, 실제 후보 편차가
# 2.2점이라 엔진에 값이 없었다.
READY_FAILED_STOCK_SCENES = 30
READY_TOTAL_SCENES = 100


# 실패 사유를 무엇으로 고칠 수 있는지 기준으로 가른다. Sprint77
# Observatory가 실제로 잡아낸 두 가지(붉은 빨대, top view 누락)가
# 각각 "색/불필요한 요소"와 "구도/앵글"에 해당한다.
# Gemini는 한국어로도 영어로도 답한다(실측 - 같은 파이프라인에서 둘 다
# 나왔다). 한쪽만 넣으면 분류가 조용히 "기타"로 새고, 통계가 그만큼
# 쓸모없어진다.
_CAUSE_RULES = (
    ("구도/앵글", ("구도", "앵글", "정면", "시점", "잘림", "크롭",
                  "flat lay", "top-down", "top down", "composition",
                  "angle", "cropped", "framing", "held by a hand")),
    ("색/불필요한 요소", ("붉은", "빨대", "불필요", "이상한 물체",
                        "strange", "red object", "straw", "unwanted",
                        "distracting")),
    ("인물 문제", ("인물", "사람", "얼굴", "주인공", "일관성",
                  "person", "face", "character", "consistency", "woman",
                  "man ")),
    ("생성 결함", ("아티팩트", "기형", "손가락", "오타", "글자", "철자",
                  "artifact", "deformed", "finger", "typo", "misspell")),
    ("톤/조명", ("조명", "톤", "이질", "분위기", "그림자",
                "lighting", "moody", "aesthetic", "shadow", "tone")),
    ("피사체 불일치", ("일치하지", "전혀 다른", "무관", "아니라", "아닌",
                     "대신", "빠져", "다릅니다",
                     "does not match", "not match", "instead of",
                     "unrelated", "missing", "different from")),
)


def classify(reason) -> str:
    """실패 사유 한 줄을 분류한다. 순수 함수입니다."""

    if not reason:
        return "사유 없음"

    text = str(reason).lower()

    for label, markers in _CAUSE_RULES:
        if any(marker.lower() in text for marker in markers):
            return label

    return "기타"


def _projects(root: str):
    """관측 파일을 가진 디렉터리들. root 자신과 한 단계 아래를 본다."""

    found = []

    for base, dirs, files in os.walk(root):
        if OBSERVATORY_FILENAME in files:
            found.append(base)
        # 깊이 2까지만 - 산출물 디렉터리는 그보다 깊지 않다.
        if base.count(os.sep) - root.count(os.sep) >= 2:
            dirs[:] = []

    return sorted(found)


def _load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def build(root: str) -> list:
    """
    누적된 Observatory를 scene 한 줄씩의 표로. 순수 읽기입니다.

    평가(quality_report.json)가 없는 프로젝트도 버리지 않는다. 후보
    풀 자체가 분석 가치를 갖고, "아직 평가 전"과 "관측이 없음"은 다르다.

    스톡 검색이 일어나지 않은 scene(Imagen 우선 경로)은 행을 만들지
    않는다 - 고를 후보가 없었으므로 순위 분석의 대상이 아니다.
    """

    rows = []

    for project in _projects(root):
        observatory = _load(os.path.join(project, OBSERVATORY_FILENAME))

        if not observatory:
            continue

        report = _load(os.path.join(project, REPORT_FILENAME)) or {}
        evaluation = report.get("ai_quality_evaluation") or {}
        scores = evaluation.get("scores") or {}
        by_scene = {s.get("scene"): s for s in evaluation.get("scenes", [])}

        for entry in observatory.get("scenes", []):
            candidates = entry.get("candidates") or []

            if not candidates:
                continue

            selected = next(
                (c for c in candidates if c.get("selected")), None,
            )

            # 차점자를 뽑는 데만 쓴다.
            ranked = sorted(
                candidates,
                key=lambda c: (
                    c.get("ranking_score")
                    if c.get("ranking_score") is not None else -1e9
                ),
                reverse=True,
            )

            result = by_scene.get(entry.get("scene")) or {}
            searches = entry.get("searches") or []

            rows.append({
                "project": os.path.basename(project),
                "scene": entry.get("scene"),
                "provider": entry.get("final_provider"),
                "query": searches[0]["query"] if searches else None,
                "search_count": len(searches),
                "cache_hits": sum(
                    1 for s in searches if s.get("cache_hit")
                ),
                "candidate_count": len(candidates),
                # provider가 준 순서에서 몇 번째를 골랐나. 점수 순위로
                # 재면 항상 0이 나온다 - 선택이 곧 최고점이기 때문이다.
                # 알고 싶은 것은 "Pexels의 1번을 뒤집었는가"이고, 그건
                # provider 순서로만 보인다(Sprint76이 세운 지표).
                "selected_rank": (
                    candidates.index(selected)
                    if selected in candidates else None
                ),
                "selected_alt": (selected or {}).get("alt"),
                "selected_slug": (selected or {}).get("slug"),
                "selected_score": (selected or {}).get("ranking_score"),
                "selected_relevance": (selected or {}).get("relevance"),
                "selected_asset": (selected or {}).get("source_url"),
                "best_alternative_alt": (
                    ranked[1].get("alt") if len(ranked) > 1 else None
                ),
                "gemini_reason": result.get("reason"),
                "regenerate": bool(result.get("regenerate")) if result else False,
                "realism": result.get("realism_score"),
                "overall_quality": scores.get("overall_quality"),
                "image_realism": scores.get("image_realism"),
                "composition": scores.get("composition"),
                "character_consistency": scores.get("character_consistency"),
                "has_evaluation": bool(result),
                # Sprint79 - 후보 풀과 매칭 어휘를 행에 담는다. 담지
                # 않으면 원본 프로젝트 디렉터리가 사라진 뒤 재생할 수
                # 없다 - scratchpad는 임시 디렉터리다.
                "candidates": candidates,
                "scene_terms": list(entry.get("scene_terms") or []),
            })

    return rows


def summarize(rows: list) -> dict:
    """
    표를 집계한다. 순수 함수입니다.

    picked_first는 "provider가 준 1번을 그대로 골랐다"의 횟수다.
    Sprint76 이전에는 사실상 항상 1번이었으므로, picked_lower가 늘어나는
    것이 순위가 실제로 일하고 있다는 신호다.
    """

    rows = list(rows or [])

    failures = [r for r in rows if r.get("regenerate")]

    causes = Counter(classify(r.get("gemini_reason")) for r in failures)

    used = Counter(
        r.get("selected_asset") for r in rows if r.get("selected_asset")
    )
    duplicates = sum(1 for count in used.values() if count > 1)

    return {
        "rows": len(rows),
        "projects": len({r.get("project") for r in rows}),
        "failures": len(failures),
        "failure_rate": (100.0 * len(failures) / len(rows)) if rows else 0.0,
        "causes": causes.most_common(10),
        "duplicates": duplicates,
        "picked_first": sum(1 for r in rows if r.get("selected_rank") == 0),
        "picked_lower": sum(
            1 for r in rows
            if r.get("selected_rank") not in (None, 0)
        ),
        "with_evaluation": sum(1 for r in rows if r.get("has_evaluation")),
        "mean_candidates": (
            sum(r.get("candidate_count") or 0 for r in rows) / len(rows)
            if rows else 0.0
        ),
    }


def append_project(project_path: str, dataset_path: str) -> int:
    """
    프로젝트 하나의 행을 축적 파일에 덧붙인다. 추가된 행 수를 반환한다.

    같은 프로젝트를 두 번 쌓지 않는다. 파이프라인이 재실행되거나 수동
    으로 다시 불릴 수 있고, 중복이 쌓이면 실패율 통계가 조용히 왜곡된다.

    무슨 일이 있어도 예외를 밖으로 내보내지 않는다 - 관측이 생산을
    막지 않는다(Sprint73에서 세운 원칙).
    """

    try:
        rows = build(project_path)

        if not rows:
            return 0

        existing = load(dataset_path)
        seen = {(r.get("project"), r.get("scene")) for r in existing}

        fresh = [
            row for row in rows
            if (row.get("project"), row.get("scene")) not in seen
        ]

        if not fresh:
            return 0

        directory = os.path.dirname(dataset_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(dataset_path, "a", encoding="utf-8") as f:
            for row in fresh:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        return len(fresh)

    except Exception as exc:
        print(f"[Dataset] 축적 실패(무시): {exc}")
        return 0


def load(dataset_path: str) -> list:
    """
    축적된 행을 읽는다. 깨진 줄은 건너뛴다 - 한 줄이 잘렸다고 지금까지
    모은 것을 전부 버릴 이유가 없다.
    """

    if not os.path.exists(dataset_path):
        return []

    rows = []

    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception as exc:
        print(f"[Dataset] 읽기 실패(무시): {exc}")

    return rows


def readiness(rows: list) -> dict:
    """
    Ranking v3를 착수해도 되는가. 순수 함수입니다.

    조건을 코드가 판정하게 두는 이유는, 눈대중으로 "이 정도면 됐다"고
    넘어가는 것이 정확히 Best-of-N에서 한 실수이기 때문이다.
    """

    rows = list(rows or [])
    failures = sum(1 for row in rows if row.get("regenerate"))

    by_failures = failures >= READY_FAILED_STOCK_SCENES
    by_scenes = len(rows) >= READY_TOTAL_SCENES

    if by_failures:
        reason = f"실패 스톡 scene {failures}개 (기준 {READY_FAILED_STOCK_SCENES})"
    elif by_scenes:
        reason = f"누적 scene {len(rows)}개 (기준 {READY_TOTAL_SCENES})"
    else:
        reason = (
            f"아직 부족하다 - 실패 {failures}/{READY_FAILED_STOCK_SCENES}, "
            f"scene {len(rows)}/{READY_TOTAL_SCENES}"
        )

    return {
        "ready": by_failures or by_scenes,
        "reason": reason,
        "failures": failures,
        "scenes": len(rows),
        "failures_needed": max(0, READY_FAILED_STOCK_SCENES - failures),
        "scenes_needed": max(0, READY_TOTAL_SCENES - len(rows)),
    }
