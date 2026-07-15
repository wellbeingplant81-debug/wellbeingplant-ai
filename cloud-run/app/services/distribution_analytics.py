"""
Sprint106 - Distribution Analytics Intelligence.

compute_analytics()는 asset_feedback_service.summarize_usage()와 동일한
패턴의 순수 함수다 - queue_entries(distribution_store.list_entries()의
반환값)와 history_records(distribution_history.load_all()의 반환값)를
입력으로 받아 통계 dict를 반환할 뿐, 파일 I/O를 전혀 하지 않는다.

상태 전이 이력(승인/거절/취소 시점, 상태별 체류 시간)은 로깅되지 않으므로
이 모듈에서 계산하지 않는다(SPEC §1/§2 - 기존 queue.json/history.json
데이터만으로 계산 가능한 지표로 스코프를 한정했다).

출력 schema(고정):
- rate는 0~1 float(퍼센트 변환 안 함)
- 빈 그룹은 0이 아니라 null(None)
- platform_success_rate: history_records 기준 attempt 단위(재시도도
  전부 포함 - "최신 시도만"이 아니다)
- retry_stats/quality_correlation: queue_entries 중 publish_result가
  None이 아닌 것만 대상(발행 시도 자체가 없는 항목은 제외)
"""


def _platform_success_rate(history_records: list) -> dict:

    by_platform = {}

    for record in history_records:
        platform = record["platform"]
        stats = by_platform.setdefault(platform, {"attempts": 0, "successes": 0})
        stats["attempts"] += 1
        if record["success"]:
            stats["successes"] += 1

    return {
        platform: {**stats, "rate": stats["successes"] / stats["attempts"]}
        for platform, stats in by_platform.items()
    }


def _success_rate(entries: list) -> float:
    if not entries:
        return None
    return sum(1 for entry in entries if entry["status"] == "published") / len(entries)


def _retry_stats(queue_entries: list) -> dict:

    eligible = [entry for entry in queue_entries if entry.get("publish_result") is not None]
    eligible_count = len(eligible)

    if eligible_count == 0:
        return {
            "eligible_entries": 0,
            "average_retry_count": None,
            "success_rate_without_retry": None,
            "success_rate_after_retry": None,
        }

    average_retry_count = sum(entry["retry_count"] for entry in eligible) / eligible_count

    without_retry = [entry for entry in eligible if entry["retry_count"] == 0]
    after_retry = [entry for entry in eligible if entry["retry_count"] > 0]

    return {
        "eligible_entries": eligible_count,
        "average_retry_count": average_retry_count,
        "success_rate_without_retry": _success_rate(without_retry),
        "success_rate_after_retry": _success_rate(after_retry),
    }


def _summarize_quality_group(entries: list) -> dict:

    count = len(entries)

    if count == 0:
        return {"count": 0, "avg_quality_score": None, "avg_generation_time": None}

    avg_quality_score = sum(entry["quality_score"] for entry in entries) / count

    generation_times = [
        entry["generation_time"] for entry in entries
        if entry.get("generation_time") is not None
    ]
    avg_generation_time = (
        sum(generation_times) / len(generation_times) if generation_times else None
    )

    return {
        "count": count,
        "avg_quality_score": avg_quality_score,
        "avg_generation_time": avg_generation_time,
    }


def _quality_correlation(queue_entries: list) -> dict:

    eligible = [
        entry for entry in queue_entries
        if entry.get("quality_score") is not None and entry.get("publish_result") is not None
    ]

    published = [entry for entry in eligible if entry["status"] == "published"]
    failed = [entry for entry in eligible if entry["status"] == "failed"]

    return {
        "eligible_entries": len(eligible),
        "published": _summarize_quality_group(published),
        "failed": _summarize_quality_group(failed),
    }


def compute_analytics(queue_entries: list, history_records: list) -> dict:
    return {
        "platform_success_rate": _platform_success_rate(history_records),
        "retry_stats": _retry_stats(queue_entries),
        "quality_correlation": _quality_correlation(queue_entries),
    }
