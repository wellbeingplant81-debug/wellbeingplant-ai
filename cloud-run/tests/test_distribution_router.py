"""
Sprint104 - Video Distribution Intelligence. app/routers/distribution.py의
Review Gate API 계약을 확인한다.

이 리포의 기존 라우터 테스트 컨벤션(test_factory_router_profile.py)을
그대로 따른다 - FastAPI TestClient/HTTP 서버를 띄우지 않고, route
함수를 Pydantic 요청 모델과 함께 순수 Python 함수로 직접 호출하고,
하위 서비스 호출은 mock으로 검증한다.

ENABLE_DISTRIBUTION=False일 때의 "비활성" 응답은
test_distribution_feature_flag.py에서 별도로 다룬다 - 이 파일의 모든
테스트는 ENABLE_DISTRIBUTION=True를 전제로, 정상 경로의 요청/응답
계약만 검증한다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.models.distribution_request import ApproveRequest, EnqueueRequest
from app.routers import distribution as router
from app.services import distribution_queue as dq
from app.services import distribution_store


SAMPLE_ENQUEUE_REQUEST = EnqueueRequest(
    video_id="20260715_120000",
    output_path="output/20260715_120000",
    title="제목",
    description="설명",
    hashtags=["health", "shorts"],
    thumbnail_path="output/20260715_120000/thumbnail.png",
    target_platforms=["youtube"],
)


class DistributionEnabledTestCase(unittest.TestCase):

    def setUp(self):
        original = config.ENABLE_DISTRIBUTION
        config.ENABLE_DISTRIBUTION = True
        self.addCleanup(setattr, config, "ENABLE_DISTRIBUTION", original)


class TestEnqueueEndpoint(DistributionEnabledTestCase):

    @patch("app.routers.distribution.distribution_store.create_entry")
    def test_enqueue_delegates_to_store_create_entry(self, mock_create):
        mock_create.return_value = {"video_id": "20260715_120000", "status": "waiting_review"}

        result = router.enqueue(SAMPLE_ENQUEUE_REQUEST)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        self.assertEqual(call_kwargs["video_id"], "20260715_120000")
        self.assertEqual(call_kwargs["target_platforms"], ["youtube"])
        self.assertEqual(result["status"], "waiting_review")


class TestListAndGetEndpoints(DistributionEnabledTestCase):

    @patch("app.routers.distribution.distribution_store.list_entries")
    def test_list_queue_delegates_with_status_filter(self, mock_list):
        mock_list.return_value = []

        router.list_queue(status="waiting_review")

        mock_list.assert_called_once_with(status="waiting_review")

    @patch("app.routers.distribution.distribution_store.list_entries")
    def test_list_queue_without_filter(self, mock_list):
        mock_list.return_value = []

        router.list_queue(status=None)

        mock_list.assert_called_once_with(status=None)

    @patch("app.routers.distribution.distribution_store.get_entry")
    def test_get_queue_item_returns_entry(self, mock_get):
        mock_get.return_value = {"video_id": "v1", "status": "waiting_review"}

        result = router.get_queue_item("v1")

        self.assertEqual(result["video_id"], "v1")

    @patch("app.routers.distribution.distribution_store.get_entry", return_value=None)
    def test_get_queue_item_404_when_missing(self, mock_get):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            router.get_queue_item("missing")

        self.assertEqual(ctx.exception.status_code, 404)


class TestApproveEndpoint(DistributionEnabledTestCase):

    @patch("app.routers.distribution.distribution_store.apply_action")
    def test_approve_delegates_with_field_overrides(self, mock_apply):
        mock_apply.return_value = {"video_id": "v1", "status": "approved"}

        result = router.approve(
            "v1", ApproveRequest(title="수정된 제목"),
        )

        mock_apply.assert_called_once()
        call_args = mock_apply.call_args
        self.assertEqual(call_args.args[0], "v1")
        self.assertEqual(call_args.args[1], dq.ACTION_APPROVE)
        self.assertEqual(call_args.kwargs["field_overrides"]["title"], "수정된 제목")
        self.assertEqual(result["status"], "approved")

    @patch("app.routers.distribution.distribution_store.apply_action")
    def test_approve_without_overrides_sends_no_field_changes(self, mock_apply):
        mock_apply.return_value = {"video_id": "v1", "status": "approved"}

        router.approve("v1", ApproveRequest())

        call_args = mock_apply.call_args
        self.assertFalse(call_args.kwargs.get("field_overrides"))

    @patch(
        "app.routers.distribution.distribution_store.apply_action",
        side_effect=distribution_store.EntryNotFoundError("v1"),
    )
    def test_approve_404_when_entry_missing(self, mock_apply):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            router.approve("v1", ApproveRequest())

        self.assertEqual(ctx.exception.status_code, 404)

    @patch(
        "app.routers.distribution.distribution_store.apply_action",
        side_effect=dq.InvalidTransitionError("bad transition"),
    )
    def test_approve_409_on_invalid_transition(self, mock_apply):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            router.approve("v1", ApproveRequest())

        self.assertEqual(ctx.exception.status_code, 409)


class TestRejectReReviewCancelEndpoints(DistributionEnabledTestCase):

    @patch("app.routers.distribution.distribution_store.apply_action")
    def test_reject_uses_reject_action(self, mock_apply):
        mock_apply.return_value = {"video_id": "v1", "status": "rejected"}

        router.reject("v1")

        self.assertEqual(mock_apply.call_args.args[1], dq.ACTION_REJECT)

    @patch("app.routers.distribution.distribution_store.apply_action")
    def test_re_review_uses_re_review_action(self, mock_apply):
        mock_apply.return_value = {"video_id": "v1", "status": "waiting_review"}

        router.re_review("v1")

        self.assertEqual(mock_apply.call_args.args[1], dq.ACTION_RE_REVIEW)

    @patch("app.routers.distribution.distribution_store.apply_action")
    def test_cancel_uses_cancel_action(self, mock_apply):
        mock_apply.return_value = {"video_id": "v1", "status": "waiting_review"}

        router.cancel("v1")

        self.assertEqual(mock_apply.call_args.args[1], dq.ACTION_CANCEL)


class TestPublishEndpoint(DistributionEnabledTestCase):

    @patch("app.routers.distribution.distribution_service.publish")
    def test_publish_delegates_to_distribution_service(self, mock_publish):
        mock_publish.return_value = {"video_id": "v1", "status": "published"}

        result = router.publish("v1")

        mock_publish.assert_called_once_with("v1")
        self.assertEqual(result["status"], "published")

    @patch(
        "app.routers.distribution.distribution_service.publish",
        side_effect=dq.InvalidTransitionError("bad transition"),
    )
    def test_publish_409_on_invalid_transition(self, mock_publish):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            router.publish("v1")

        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
