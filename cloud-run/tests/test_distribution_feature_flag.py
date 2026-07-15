"""
Sprint104 - Video Distribution Intelligence. config.ENABLE_DISTRIBUTION은
기본값 False다. 꺼져 있을 때 모든 상태 변경(mutation) 엔드포인트는
"비활성" 응답(HTTPException 403)을 반환해야 하고, 하위 store/service
함수는 아예 호출되면 안 된다 - 큐에 어떤 항목도 생기지 않는다는 것을
보장하기 위함이다.

조회(GET) 엔드포인트는 플래그와 무관하게 항상 동작한다(부작용이 없고,
꺼져 있으면 어차피 큐가 비어 있으므로 굳이 막을 이유가 없다).
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


SAMPLE_ENQUEUE_REQUEST = EnqueueRequest(
    video_id="20260715_120000",
    output_path="output/20260715_120000",
    title="제목",
    description="설명",
    hashtags=["health"],
    thumbnail_path="output/20260715_120000/thumbnail.png",
    target_platforms=["youtube"],
)


class TestDistributionDisabledByDefault(unittest.TestCase):

    def test_default_config_value_is_false(self):
        # 이 테스트는 다른 테스트가 플래그를 변경했다가 복구하지 않는
        # 회귀를 잡기 위한 것이다 - 항상 False로 시작해야 한다.
        self.assertFalse(config.ENABLE_DISTRIBUTION)

    def test_default_real_api_flags_are_false(self):
        self.assertFalse(config.ENABLE_YOUTUBE_REAL_API)
        self.assertFalse(config.ENABLE_INSTAGRAM_REAL_API)
        self.assertFalse(config.ENABLE_TIKTOK_REAL_API)


class TestMutationEndpointsDisabledWhenFlagOff(unittest.TestCase):

    def setUp(self):
        original = config.ENABLE_DISTRIBUTION
        config.ENABLE_DISTRIBUTION = False
        self.addCleanup(setattr, config, "ENABLE_DISTRIBUTION", original)

    @patch("app.routers.distribution.distribution_store.create_entry")
    def test_enqueue_disabled(self, mock_create):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            router.enqueue(SAMPLE_ENQUEUE_REQUEST)

        self.assertEqual(ctx.exception.status_code, 403)
        mock_create.assert_not_called()

    @patch("app.routers.distribution.distribution_store.apply_action")
    def test_approve_disabled(self, mock_apply):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            router.approve("v1", ApproveRequest())

        self.assertEqual(ctx.exception.status_code, 403)
        mock_apply.assert_not_called()

    @patch("app.routers.distribution.distribution_store.apply_action")
    def test_reject_disabled(self, mock_apply):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException):
            router.reject("v1")

        mock_apply.assert_not_called()

    @patch("app.routers.distribution.distribution_store.apply_action")
    def test_re_review_disabled(self, mock_apply):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException):
            router.re_review("v1")

        mock_apply.assert_not_called()

    @patch("app.routers.distribution.distribution_store.apply_action")
    def test_cancel_disabled(self, mock_apply):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException):
            router.cancel("v1")

        mock_apply.assert_not_called()

    @patch("app.routers.distribution.distribution_service.publish")
    def test_publish_disabled(self, mock_publish):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException):
            router.publish("v1")

        mock_publish.assert_not_called()


class TestReadEndpointsAlwaysWorkRegardlessOfFlag(unittest.TestCase):

    def setUp(self):
        original = config.ENABLE_DISTRIBUTION
        config.ENABLE_DISTRIBUTION = False
        self.addCleanup(setattr, config, "ENABLE_DISTRIBUTION", original)

    @patch("app.routers.distribution.distribution_store.list_entries", return_value=[])
    def test_list_queue_works_when_disabled(self, mock_list):
        result = router.list_queue(status=None)
        self.assertEqual(result, [])
        mock_list.assert_called_once()

    @patch("app.routers.distribution.distribution_store.get_entry", return_value=None)
    def test_get_queue_item_404_semantics_unaffected_by_flag(self, mock_get):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            router.get_queue_item("v1")

        # 플래그 때문이 아니라 "없어서" 404인지 구분 - 403이 아니어야 함.
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
