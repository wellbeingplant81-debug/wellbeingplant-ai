"""
Sprint103 - Semantic Query Intelligence. integrate_asset()의
motion_contract 경로(Sprint101)가 search_query_override를
generate_semantic_primary_query()로 산출하는지 확인한다(이전에는
extract_intent_aware_search_query()를 썼다 - 위치 기반 8단어 절단이
남아있는 카테고리 단어장 재정렬 방식이라 Sprint102 Root Cause 분석에서
근본 해결책이 아니라고 판정됐다).

_select_with_visual_relevance()는 mock해서, 이 파일은 "어떤 검색어
문자열을 넘기는지"만 순수하게 검증한다 - 실제 Pexels/AI 선택 로직은
건드리지 않는다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_integration_service as svc


class TestSemanticPrimaryQueryWiredIntoMotionContractPath(unittest.TestCase):

    @patch("app.services.asset_integration_service._finalize_downloaded_asset")
    @patch("app.services.asset_integration_service._select_with_visual_relevance")
    def test_search_query_override_uses_semantic_primary_query(
        self, mock_select, mock_finalize,
    ):
        mock_select.return_value = (
            {"source": "pexels_image", "local_path": "p.png", "metadata": {}},
            False,
            [],
            False,
        )

        image_prompt = (
            "high angle shot showing an artery gradually narrowing due to "
            "plaque buildup, dramatic lighting, somber mood"
        )
        scene = {
            "scene": 2,
            "image_prompt": image_prompt,
            "narration": "narration",
            "motion_contract": {
                "video_intent": {"intent": "preferred_image"},
                "visual_intent": "medical",
            },
        }

        svc.integrate_asset(scene, "output/proj")

        used_query = mock_select.call_args.args[9]
        # 카메라 메타 어휘는 없어야 하고, 위치 기반 절단이라면 잘려
        # 나갔을 뒷부분 핵심 명사(plaque/buildup)는 남아 있어야 한다.
        for camera_word in ["high", "angle", "shot", "showing", "dramatic", "lighting", "mood"]:
            self.assertNotIn(camera_word, used_query.split())
        self.assertIn("plaque", used_query)
        self.assertIn("buildup", used_query)


if __name__ == "__main__":
    unittest.main()
