"""
Sprint100-2 - batch 라우터(app/routers/batch.py POST /generate-batch)도
factory.py와 동일하게 wellbeing 채널(BatchRequest에는 channel 필드가
없고 항상 wellbeing 채널로 생성됨)에 대해 upload profile을 기본으로
쓰게 한다. [[test_factory_router_profile]] 참고.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.routers.batch import generate_batch, BatchRequest


class TestBatchRouterDefaultsToUploadProfile(unittest.TestCase):

    @patch("app.routers.batch.generate_short_video")
    def test_each_topic_uses_upload_profile(self, mock_generate):
        mock_generate.return_value = {"success": True}

        generate_batch(BatchRequest(topics=["주제1", "주제2"]))

        mock_generate.assert_any_call(
            topic="주제1", channel="wellbeing", production_profile_name="upload",
        )
        mock_generate.assert_any_call(
            topic="주제2", channel="wellbeing", production_profile_name="upload",
        )
        self.assertEqual(mock_generate.call_count, 2)


if __name__ == "__main__":
    unittest.main()
