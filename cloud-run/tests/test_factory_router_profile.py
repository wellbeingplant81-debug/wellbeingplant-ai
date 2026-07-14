"""
Sprint100-2 - "연습도 실전처럼": wellbeing 채널의 실제 업로드용 영상
생성(app/routers/factory.py POST /generate-short-video)이 지금까지
production_profile_name을 전혀 넘기지 않아, ProductionProfile(Sprint93+
- ElevenLabs/실제 BGM/실제 Asset Strategy/실제 Duration Target)이 실제
서비스에서 한 번도 켜진 적이 없었다(QA 스크립트에서만 --profile upload로
검증됨). wellbeing 채널 요청은 명시적으로 profile을 지정하지 않으면
"upload" profile로 기본 동작하게 한다.

전역 config.ENABLE_PRODUCTION_PROFILE 플래그는 건드리지 않는다 -
Sprint100-2(app/pipeline/pipeline.py)에서 production_profile_name이
명시되면 그 요청 1건에 한해 opt-in되도록 이미 바꿨으므로, 라우터는
그 인자만 채워 넘기면 된다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.request import VideoRequest
from app.routers.factory import create_video


class TestFactoryRouterDefaultsToUploadProfile(unittest.TestCase):

    @patch("app.routers.factory.generate_short_video")
    def test_wellbeing_channel_defaults_to_upload_profile(self, mock_generate):
        mock_generate.return_value = {"success": True}

        create_video(VideoRequest(topic="주제", channel="wellbeing"))

        mock_generate.assert_called_once_with(
            topic="주제", channel="wellbeing", production_profile_name="upload",
        )

    @patch("app.routers.factory.generate_short_video")
    def test_non_wellbeing_channel_is_untouched(self, mock_generate):
        mock_generate.return_value = {"success": True}

        create_video(VideoRequest(topic="주제", channel="other"))

        mock_generate.assert_called_once_with(
            topic="주제", channel="other", production_profile_name=None,
        )


if __name__ == "__main__":
    unittest.main()
