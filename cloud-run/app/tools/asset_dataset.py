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

# Sprint229 - footage.plan이 정하는 세 갈래.
#
# 왜 여기에 글자를 다시 적는가
# ----------------------------
# footage 모듈에서 가져오는 것이 옳아 보이지만, 그것은 moviepy를 들고
# 있다. 이 파일은 쌓인 JSON을 읽는 자리이고 영상을 열지 않는데,
# 라우터가 이 모듈을 최상단에서 들이므로(studio.py) 가져오는 순간
# 화면을 켜는 것만으로 moviepy가 딸려 온다.
#
# 그래서 값은 여기 적고, **두 곳이 갈라지지 않는 것은 시험으로
# 잠근다**(test_footage_counted_across_projects). 갈라지는 날 이
# 집계는 조용히 0을 세게 되므로, 조용히 지나가지 않게 하는 것이
# 요점이다.
FOOTAGE_TRIM = "trim"
FOOTAGE_LOOP = "loop"
FOOTAGE_HOLD = "hold"

# Sprint230 - 그 영상이 어디서 왔는가.
#
# 스톡은 이름이 <업체>_video 다(provider_factory 가 그렇게 짓는다).
# 내 자료는 provider_selection.LOCAL_STOCK 이고, 그 글자도 여기 다시
# 적는다 - 위와 같은 이유이며 갈라지지 않는 것은 시험으로 잠근다.
FOOTAGE_LOCAL_PROVIDER = "local_stock"
FOOTAGE_STOCK_SUFFIX = "_video"
REPORT_FILENAME = "quality_report.json"

# Sprint79 - 축적 파일. 영상을 만들 때마다 여기 쌓인다.
DATASET_FILENAME = "asset_dataset.jsonl"

# Sprint83 - Observatory v2가 남기는 scene 계획. 구버전 기록에는 없다.
PLANNED_FIELDS = ("camera", "composition", "visual_type", "purpose")

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


def has_candidates(row: dict) -> bool:
    """
    이 행이 순위를 말할 수 있는가. 순수 함수입니다.

    Sprint230 이전에 쌓인 표에는 이 칸이 없다 - 그때는 후보가 있는
    scene 만 행이 됐으므로 후보 수로 판단한다. 옛 파일을 고치라고
    하지 않는다.
    """

    if "has_candidates" in row:
        return bool(row["has_candidates"])

    return bool(row.get("candidate_count"))


def is_stock_footage(row: dict) -> bool:
    """스톡에서 받아 온 영상인가. 순수 함수입니다."""

    return str(row.get("provider") or "").endswith(FOOTAGE_STOCK_SUFFIX)


def is_local_footage(row: dict) -> bool:
    """사람이 제 폴더에 넣어 둔 영상인가. 순수 함수입니다."""

    return row.get("provider") == FOOTAGE_LOCAL_PROVIDER


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

            # Sprint229 - 고른 영상이 이 scene 을 어떻게 채웠는가.
            footage = entry.get("footage") or {}

            # Sprint230 - 후보가 없어도 영상을 썼으면 행을 만든다.
            #
            # 예전에는 후보가 없으면 그냥 넘겼다("고를 후보가 없었으므로
            # 순위 분석의 대상이 아니다", Sprint79). 그 판단은 순위에
            # 대해서는 여전히 옳다.
            #
            # 그런데 내 자료 영상은 스톡 검색을 거치지 않는다 - 후보가
            # 없다. 그래서 무료 경로로 만든 scene 이 hold 집계에서 통째로
            # 빠졌고, 보고서에 적힌 비율이 스톡만의 값이면서 전체인 척
            # 했다. 재는 숫자가 무엇을 재는지 틀리면 그 숫자로 내리는
            # 판단이 전부 틀린다.
            #
            # 행은 만들되 순위 지표에는 넣지 않는다 - 아래 has_candidates
            # 가 그 경계다.
            if not candidates and not footage:
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
                # Sprint230 - "후보가 없었다"와 "후보는 있었는데 그것을
                # 골랐다"를 가른다. 순위 지표는 이것이 참인 행만 센다.
                "has_candidates": bool(candidates),
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
                # Sprint83 - scene이 계획한 것. Sprint82까지 쌓인 기록에는
                # 없으므로 전부 None으로 채워 준다 - 없다고 행을 버리면
                # 지금까지 모은 것이 통째로 죽는다.
                "planned": {
                    field: (entry.get("planned") or {}).get(field)
                    for field in PLANNED_FIELDS
                },
                "has_plan": any(
                    (entry.get("planned") or {}).get(field)
                    for field in PLANNED_FIELDS
                ),
                # Sprint229 - trim / loop / hold. 영상이 아니었던
                # scene은 셋 다 None이다.
                "footage_mode": footage.get("mode"),
                "source_seconds": footage.get("source_seconds"),
                "scene_seconds": footage.get("scene_seconds"),
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

    # Sprint230 - 순위를 말하는 숫자는 후보가 있던 행만 센다.
    #
    # 내 자료 영상 scene 은 후보가 없다(스톡 검색을 거치지 않는다).
    # 그 행이 분모에 들어가면 "provider 가 준 1번을 뒤집었는가" 같은
    # 지표가 조용히 묽어진다 - 뒤집을 1번이 애초에 없던 행이다.
    #
    # 옛 표에는 이 칸이 없다. 그때는 후보가 있는 scene 만 행이 됐으므로
    # 후보 수로 판단한다 - migration 을 강요하지 않는다.
    ranking = [r for r in rows if has_candidates(r)]

    failures = [r for r in ranking if r.get("regenerate")]

    # Sprint229 - 고른 영상이 scene을 어떻게 채웠는가.
    #
    # 분모는 **영상을 쓴 scene**이다. 그림 scene을 섞으면 비율이 뜻을
    # 잃는다 - 영상 10개 중 hold 2개면 20%여야 하는데, 그림 90개가
    # 함께 세어지면 2%로 보인다. 그러면 이 숫자를 보고 아무도 아무
    # 판단도 하지 않는다.
    #
    # 이쪽은 순위와 무관하다. 후보가 있었든 없었든, 영상을 썼으면 센다.
    footage_rows = [r for r in rows if r.get("footage_mode")]
    footage_modes = Counter(r["footage_mode"] for r in footage_rows)

    causes = Counter(classify(r.get("gemini_reason")) for r in failures)

    used = Counter(
        r.get("selected_asset") for r in ranking if r.get("selected_asset")
    )
    duplicates = sum(1 for count in used.values() if count > 1)

    return {
        # 표에 있는 행 전부. Sprint230 부터 후보 없는 영상 scene 도
        # 여기 들어간다.
        "rows": len(rows),
        # 그중 순위를 말할 수 있는 행. 아래 지표들의 분모다.
        "ranking_rows": len(ranking),
        "projects": len({r.get("project") for r in rows}),
        "failures": len(failures),
        "failure_rate": (
            100.0 * len(failures) / len(ranking) if ranking else 0.0
        ),
        "causes": causes.most_common(10),
        "duplicates": duplicates,
        "picked_first": sum(
            1 for r in ranking if r.get("selected_rank") == 0),
        "picked_lower": sum(
            1 for r in ranking
            if r.get("selected_rank") not in (None, 0)
        ),
        "with_evaluation": sum(
            1 for r in ranking if r.get("has_evaluation")),
        "mean_candidates": (
            sum(r.get("candidate_count") or 0 for r in ranking) / len(ranking)
            if ranking else 0.0
        ),
        # Sprint229 - 영상을 쓴 scene이 실제로 어떻게 채워졌는가.
        "footage_scenes": len(footage_rows),
        "footage_trim": footage_modes.get(FOOTAGE_TRIM, 0),
        "footage_loop": footage_modes.get(FOOTAGE_LOOP, 0),
        "footage_hold": footage_modes.get(FOOTAGE_HOLD, 0),
        # 영상이 하나도 없으면 비율이라는 것이 없다. 0.0으로 적으면
        # "영상을 썼는데 hold가 하나도 없었다"와 구별되지 않는다.
        "footage_hold_rate": (
            100.0 * footage_modes.get(FOOTAGE_HOLD, 0) / len(footage_rows)
            if footage_rows else None
        ),
        # Sprint230 - 그 영상이 어디서 왔는가. 둘을 합쳐 세면 무료
        # 경로가 늘었는지 줄었는지 영영 모른다.
        "footage_stock": sum(1 for r in footage_rows if is_stock_footage(r)),
        "footage_local": sum(1 for r in footage_rows if is_local_footage(r)),
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

    # Sprint230 - 여기 세는 것은 "실패 스톡 scene"과 "누적 scene"이다.
    # 후보가 없던 행(내 자료 영상)은 스톡 scene 이 아니므로 넣지 않는다 -
    # 넣으면 Ranking v3 를 착수할 시점이 실제보다 빨리 온 것처럼 보인다.
    rows = [r for r in (rows or []) if has_candidates(r)]
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
