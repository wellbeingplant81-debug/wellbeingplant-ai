"""
Sprint104 - Video Distribution Intelligence. distribution_service.py는
publish() 하나로 "approved/failed -> publishing -> (published|failed)"
전이 + target_platforms 순회 + 각 PlatformAdapter 호출 + 결과 집계를
오케스트레이션한다.

Sprint105 - 각 플랫폼 발행 시도마다 distribution_history.record()를
호출해 이력을 append한다(재시도해도 이전 기록을 덮어쓰지 않는다 -
queue.json의 publish_result와 별개). retry_count 자체의 증가 로직은
distribution_store.apply_action()이 담당하므로(Sprint105
TestRetryCountTracking 참고), 이 모듈은 apply_action()이 돌려준
entry["retry_count"]를 그대로 history 기록에 실어 나르기만 한다.

이 모듈이 하지 않는 것:
- 상태 전이 판정(distribution_queue 소관) / 저장(distribution_store 소관)
- 실제 API 호출(platform_adapter의 각 Adapter가 이미 mock으로 처리)

전부 mock 기반이라 실제 파일 I/O/네트워크 호출이 없다 - Sprint105부터는
distribution_history.record()도 프로덕션 코드가 무조건 호출하므로,
모든 테스트가 이를 함께 mock한다(실제 output/distribution_history.json
파일이 테스트 중 생기지 않도록).
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import distribution_queue as dq
from app.services import distribution_service
from app.services.platform_adapter import PublishResult


class TestPublishAllSucceed(unittest.TestCase):

    @patch("app.services.distribution_service.distribution_history.record")
    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_all_platforms_succeed_marks_published(
        self, mock_apply, mock_get_adapter, mock_record,
    ):
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING, "retry_count": 0,
            "target_platforms": ["youtube", "instagram"],
        }
        entry_published = dict(entry_publishing, status=dq.STATUS_PUBLISHED)
        mock_apply.side_effect = [entry_publishing, entry_published]

        mock_adapter = MagicMock()
        mock_adapter.publish.return_value = PublishResult(
            success=True, platform_post_id="mock_id", error=None,
        )
        mock_get_adapter.return_value = mock_adapter

        result = distribution_service.publish("v1")

        self.assertEqual(mock_apply.call_count, 2)
        first_call, second_call = mock_apply.call_args_list
        self.assertEqual(first_call.args, ("v1", dq.ACTION_PUBLISH))
        self.assertEqual(second_call.args, ("v1", dq.ACTION_MARK_PUBLISHED))
        self.assertEqual(result["status"], dq.STATUS_PUBLISHED)

    @patch("app.services.distribution_service.distribution_history.record")
    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_calls_adapter_once_per_target_platform(
        self, mock_apply, mock_get_adapter, mock_record,
    ):
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING, "retry_count": 0,
            "target_platforms": ["youtube", "instagram", "tiktok"],
        }
        mock_apply.side_effect = [
            entry_publishing, dict(entry_publishing, status=dq.STATUS_PUBLISHED),
        ]

        mock_adapter = MagicMock()
        mock_adapter.publish.return_value = PublishResult(True, "id", None)
        mock_get_adapter.return_value = mock_adapter

        distribution_service.publish("v1")

        self.assertEqual(mock_get_adapter.call_count, 3)
        mock_get_adapter.assert_any_call("youtube")
        mock_get_adapter.assert_any_call("instagram")
        mock_get_adapter.assert_any_call("tiktok")


class TestPublishPartialFailure(unittest.TestCase):

    @patch("app.services.distribution_service.distribution_history.record")
    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_any_platform_failure_marks_failed(
        self, mock_apply, mock_get_adapter, mock_record,
    ):
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING, "retry_count": 0,
            "target_platforms": ["youtube", "instagram"],
        }
        entry_failed = dict(entry_publishing, status=dq.STATUS_FAILED)
        mock_apply.side_effect = [entry_publishing, entry_failed]

        def adapter_for(platform):
            adapter = MagicMock()
            if platform == "youtube":
                adapter.publish.return_value = PublishResult(True, "yt_id", None)
            else:
                adapter.publish.return_value = PublishResult(False, None, "quota exceeded")
            return adapter

        mock_get_adapter.side_effect = adapter_for

        result = distribution_service.publish("v1")

        second_call = mock_apply.call_args_list[1]
        self.assertEqual(second_call.args, ("v1", dq.ACTION_MARK_FAILED))
        self.assertEqual(result["status"], dq.STATUS_FAILED)

    @patch("app.services.distribution_service.distribution_history.record")
    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_publish_result_records_per_platform_outcome(
        self, mock_apply, mock_get_adapter, mock_record,
    ):
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING, "retry_count": 0,
            "target_platforms": ["youtube"],
        }
        mock_apply.side_effect = [
            entry_publishing, dict(entry_publishing, status=dq.STATUS_PUBLISHED),
        ]

        mock_adapter = MagicMock()
        mock_adapter.publish.return_value = PublishResult(True, "yt_123", None)
        mock_get_adapter.return_value = mock_adapter

        distribution_service.publish("v1")

        second_call = mock_apply.call_args_list[1]
        recorded = second_call.kwargs["publish_result"]
        self.assertEqual(recorded["youtube"]["success"], True)
        self.assertEqual(recorded["youtube"]["platform_post_id"], "yt_123")

    @patch("app.services.distribution_service.distribution_history.record")
    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_adapter_exception_is_treated_as_platform_failure_not_crash(
        self, mock_apply, mock_get_adapter, mock_record,
    ):
        # 어댑터가 raise해도(예: NotImplementedError - real API 플래그가
        # 실수로 켜진 경우) publish() 전체가 죽지 않고 해당 플랫폼만
        # 실패로 기록돼야 한다.
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING, "retry_count": 0,
            "target_platforms": ["youtube"],
        }
        mock_apply.side_effect = [
            entry_publishing, dict(entry_publishing, status=dq.STATUS_FAILED),
        ]

        mock_adapter = MagicMock()
        mock_adapter.publish.side_effect = NotImplementedError("real api not implemented")
        mock_get_adapter.return_value = mock_adapter

        result = distribution_service.publish("v1")

        self.assertEqual(result["status"], dq.STATUS_FAILED)
        recorded = mock_apply.call_args_list[1].kwargs["publish_result"]
        self.assertFalse(recorded["youtube"]["success"])
        self.assertIn("real api not implemented", recorded["youtube"]["error"])


class TestPublishPropagatesTransitionErrors(unittest.TestCase):

    @patch("app.services.distribution_service.distribution_history.record")
    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_invalid_initial_transition_propagates_without_calling_adapters(
        self, mock_apply, mock_get_adapter, mock_record,
    ):
        mock_apply.side_effect = dq.InvalidTransitionError("bad transition")

        with self.assertRaises(dq.InvalidTransitionError):
            distribution_service.publish("v1")

        mock_get_adapter.assert_not_called()
        mock_record.assert_not_called()


class TestPublishHistoryRecording(unittest.TestCase):
    """Sprint105 §6 - 발행 시도마다 distribution_history.record()가 호출된다."""

    @patch("app.services.distribution_service.distribution_history.record")
    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_records_one_history_entry_per_platform(
        self, mock_apply, mock_get_adapter, mock_record,
    ):
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING, "retry_count": 0,
            "target_platforms": ["youtube", "instagram"],
        }
        mock_apply.side_effect = [
            entry_publishing, dict(entry_publishing, status=dq.STATUS_PUBLISHED),
        ]

        mock_adapter = MagicMock()
        mock_adapter.publish.return_value = PublishResult(True, "id", None)
        mock_get_adapter.return_value = mock_adapter

        distribution_service.publish("v1")

        self.assertEqual(mock_record.call_count, 2)
        recorded_platforms = {
            call.kwargs["platform"] for call in mock_record.call_args_list
        }
        self.assertEqual(recorded_platforms, {"youtube", "instagram"})

    @patch("app.services.distribution_service.distribution_history.record")
    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_history_record_carries_retry_count_from_apply_action(
        self, mock_apply, mock_get_adapter, mock_record,
    ):
        # apply_action()이 이미 증가시킨 retry_count(재시도 케이스)를
        # 그대로 history에 실어 보내는지 확인한다 - 이 모듈이 직접
        # 증가시키지 않는다(그건 distribution_store 소관).
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING, "retry_count": 2,
            "target_platforms": ["youtube"],
        }
        mock_apply.side_effect = [
            entry_publishing, dict(entry_publishing, status=dq.STATUS_PUBLISHED),
        ]

        mock_adapter = MagicMock()
        mock_adapter.publish.return_value = PublishResult(True, "id", None)
        mock_get_adapter.return_value = mock_adapter

        distribution_service.publish("v1")

        self.assertEqual(mock_record.call_args.kwargs["retry_count"], 2)

    @patch("app.services.distribution_service.distribution_history.record")
    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_history_record_reflects_platform_outcome(
        self, mock_apply, mock_get_adapter, mock_record,
    ):
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING, "retry_count": 0,
            "target_platforms": ["youtube"],
        }
        mock_apply.side_effect = [
            entry_publishing, dict(entry_publishing, status=dq.STATUS_FAILED),
        ]

        mock_adapter = MagicMock()
        mock_adapter.publish.return_value = PublishResult(False, None, "quota exceeded")
        mock_get_adapter.return_value = mock_adapter

        distribution_service.publish("v1")

        call_kwargs = mock_record.call_args.kwargs
        self.assertEqual(call_kwargs["video_id"], "v1")
        self.assertEqual(call_kwargs["platform"], "youtube")
        self.assertFalse(call_kwargs["success"])
        self.assertEqual(call_kwargs["error"], "quota exceeded")


if __name__ == "__main__":
    unittest.main()
