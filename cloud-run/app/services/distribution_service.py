"""
Sprint104 - Video Distribution Intelligence.

publish() 하나로 "approved/failed -> publishing -> (published|failed)"
오케스트레이션을 담당한다: 상태 전이는 distribution_store에, 실제 발행
시도는 platform_adapter의 각 Adapter에 위임하고, 이 모듈은 그 사이의
순서/집계만 책임진다.

target_platforms 중 하나라도 실패하면 전체를 failed로 기록한다(부분
성공을 published로 취급하지 않는다 - 사람이 publish_result를 보고
실패한 플랫폼만 재시도할 수 있도록 결과는 플랫폼별로 전부 남긴다).
Adapter가 예외를 던져도(예: real API 플래그가 실수로 켜졌지만 실제
구현이 없는 경우) 그 플랫폼만 실패로 기록될 뿐 publish() 전체가
죽지 않는다.
"""

from app.services import distribution_queue as dq
from app.services import distribution_store
from app.services import platform_adapter


def publish(video_id: str) -> dict:

    entry = distribution_store.apply_action(video_id, dq.ACTION_PUBLISH)

    results = {}
    all_succeeded = True

    for platform in entry["target_platforms"]:

        adapter = platform_adapter.get_adapter(platform)

        try:
            result = adapter.publish(entry)
        except Exception as exc:
            result = platform_adapter.PublishResult(
                success=False, platform_post_id=None, error=str(exc),
            )

        results[platform] = {
            "success": result.success,
            "platform_post_id": result.platform_post_id,
            "error": result.error,
        }

        if not result.success:
            all_succeeded = False

    final_action = dq.ACTION_MARK_PUBLISHED if all_succeeded else dq.ACTION_MARK_FAILED

    return distribution_store.apply_action(
        video_id, final_action, publish_result=results,
    )
