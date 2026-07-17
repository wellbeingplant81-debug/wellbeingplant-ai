"""
Sprint122 (RED) - collect_assets()이 render_profile(기본값 None)을
받으면 그대로 integrate_asset()에 전달한다. 안 넘기면(기본값) 기존
test_step02_assets.py의 모든 호출/mock과 100% 동일하게 kwarg 자체가
추가되지 않는다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.steps.step02_assets import collect_assets
from app.services.render_profile import RenderProfile


SAMPLE_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1"},
]

LONGFORM = RenderProfile.get("longform")


def _fake_integrate_asset(scene, project_path, channel="wellbeing", **kwargs):
    enriched = dict(scene)
    enriched["asset_path"] = f"{project_path}/images/scene{scene['scene']}.png"
    enriched["provider"] = "ai_image"
    enriched["asset_type"] = "image"
    enriched["search_query"] = "query"
    enriched["confidence"] = 1.0
    return enriched


class TestCollectAssetsRenderProfile(unittest.TestCase):

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_render_profile_is_forwarded_to_integrate_asset(self, mock_integrate):
        collect_assets(SAMPLE_SCENES, "output/proj", render_profile=LONGFORM)

        _, kwargs = mock_integrate.call_args
        self.assertEqual(kwargs["render_profile"], LONGFORM)

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_no_render_profile_omits_kwarg(self, mock_integrate):
        collect_assets(SAMPLE_SCENES, "output/proj")

        _, kwargs = mock_integrate.call_args
        self.assertNotIn("render_profile", kwargs)


if __name__ == "__main__":
    unittest.main()
