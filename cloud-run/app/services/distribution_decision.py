"""
Sprint107 - Distribution Decision Intelligence.

compute_decision()은 distribution_analytics.compute_analytics()의
출력(dict)을 입력으로 받아 해석 결과를 반환하는 순수 함수다 - raw
queue_entries/history_records에는 전혀 접근하지 않는다(analytics
계층 위에 한 단계 더 쌓는 구조). 파일 I/O 없음.

무인 자동 판단이 아니다 - 어떤 발행/보류 액션도 자동으로 트리거하지
않는다. 사람이 dashboard/analytics를 해석해야 했던 부담을 줄여주는
보조 신호(platform_health/recommendations/overall_status)만 만든다.

SPEC 확정 규칙:
- score = platform_success_rate[platform]["rate"] 그대로
- attempts < MIN_SAMPLE_SIZE(5)인 플랫폼은 threshold 판정을 건너뛰고
  status="insufficient_data"(score는 여전히 rate를 담음 - 신뢰도가
  낮다는 뜻이지 값이 없다는 뜻이 아니다)
- threshold(attempts>=MIN_SAMPLE_SIZE일 때만): >=0.8 healthy,
  0.5~0.8 degraded, <0.5 critical
- recommendation: degraded/critical 플랫폼당 pattern="low_success_rate"
  1건. insufficient_data 플랫폼은 만들지 않는다(표본 부족은 실패
  패턴이 확인된 게 아니다)
- overall_status 우선순위: critical > degraded > healthy >
  insufficient_data(platform_health가 비어 있어도 insufficient_data)
"""

MIN_SAMPLE_SIZE = 5

STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_CRITICAL = "critical"
STATUS_INSUFFICIENT_DATA = "insufficient_data"

HEALTHY_THRESHOLD = 0.8
DEGRADED_THRESHOLD = 0.5

_STATUS_PRIORITY = [STATUS_CRITICAL, STATUS_DEGRADED, STATUS_HEALTHY, STATUS_INSUFFICIENT_DATA]


def _status_for(rate: float, attempts: int) -> str:

    if attempts < MIN_SAMPLE_SIZE:
        return STATUS_INSUFFICIENT_DATA

    if rate >= HEALTHY_THRESHOLD:
        return STATUS_HEALTHY

    if rate >= DEGRADED_THRESHOLD:
        return STATUS_DEGRADED

    return STATUS_CRITICAL


def _platform_health(platform_success_rate: dict) -> dict:

    return {
        platform: {
            "score": stats["rate"],
            "status": _status_for(stats["rate"], stats["attempts"]),
            "attempts": stats["attempts"],
        }
        for platform, stats in platform_success_rate.items()
    }


def _recommendations(platform_health: dict) -> list:

    recommendations = []

    for platform, health in platform_health.items():
        if health["status"] in (STATUS_DEGRADED, STATUS_CRITICAL):
            recommendations.append({
                "platform": platform,
                "pattern": "low_success_rate",
                "severity": health["status"],
                "message": (
                    f"{platform} success rate is {health['score']} "
                    f"over {health['attempts']} attempts"
                ),
            })

    return recommendations


def _overall_status(platform_health: dict) -> str:

    if not platform_health:
        return STATUS_INSUFFICIENT_DATA

    statuses = {health["status"] for health in platform_health.values()}

    for status in _STATUS_PRIORITY:
        if status in statuses:
            return status

    return STATUS_INSUFFICIENT_DATA


def compute_decision(analytics: dict) -> dict:

    platform_health = _platform_health(analytics["platform_success_rate"])

    return {
        "platform_health": platform_health,
        "recommendations": _recommendations(platform_health),
        "overall_status": _overall_status(platform_health),
    }
