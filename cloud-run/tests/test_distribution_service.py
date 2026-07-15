"""
Sprint104 - Video Distribution Intelligence. distribution_service.py는
publish() 하나로 "approved/failed -> publishing -> (published|failed)"
전이 + target_platforms 순회 + 각 PlatformAdapter 호출 + 결과 집계를
오케스트레이션한다.

이 모듈이 하지 않는 것:
- 상태 전이 판정(distribution_queue 소관) / 저장(distribution_store 소관)
- 실제 API 호출(platform_adapter의 각 Adapter가 이미 mock으로 처리)

전부 mock 기반이라 실제 파일 I/O/네트워크 호출이 없다.
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

    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_all_platforms_succeed_marks_published(self, mock_apply, mock_get_adapter):
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING,
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

    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_calls_adapter_once_per_target_platform(self, mock_apply, mock_get_adapter):
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING,
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

    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_any_platform_failure_marks_failed(self, mock_apply, mock_get_adapter):
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING,
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

    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_publish_result_records_per_platform_outcome(self, mock_apply, mock_get_adapter):
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING,
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

    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_adapter_exception_is_treated_as_platform_failure_not_crash(
        self, mock_apply, mock_get_adapter,
    ):
        # 어댑터가 raise해도(예: NotImplementedError - real API 플래그가
        # 실수로 켜진 경우) publish() 전체가 죽지 않고 해당 플랫폼만
        # 실패로 기록돼야 한다.
        entry_publishing = {
            "video_id": "v1", "status": dq.STATUS_PUBLISHING,
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

    @patch("app.services.distribution_service.platform_adapter.get_adapter")
    @patch("app.services.distribution_service.distribution_store.apply_action")
    def test_invalid_initial_transition_propagates_without_calling_adapters(
        self, mock_apply, mock_get_adapter,
    ):
        mock_apply.side_effect = dq.InvalidTransitionError("bad transition")

        with self.assertRaises(dq.InvalidTransitionError):
            distribution_service.publish("v1")

        mock_get_adapter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
