"""
Sprint74 - Best-of-N이 asset 생성 경로에 붙는 자리.

Imagen을 부르는 지점은 asset_integration_service._ai_result() 하나뿐이다.
visual_type="ai"는 거기로 바로 가고, "real"은 Pexels가 실패했을 때만
거기로 온다. 그래서 후보 선택은 그 한 곳에 붙는다.

가장 중요한 계약은 "플래그가 꺼져 있으면 아무것도 달라지지 않는다"이다.
"""

import os
from app.services import media_policy
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.candidate_selection import CandidateScore, CandidateSelection
from app.services import asset_integration_service


def _selection(best, scores):
    return CandidateSelection(
        best_candidate=best,
        candidates=[
            CandidateScore(
                candidate=index,
                prompt_fidelity=value,
                character_match=value,
                composition=value,
                unrequested_person=False,
                note=None,
            )
            for index, value in enumerate(scores)
        ],
        reason="",
    )


class TestBestOfNInAssetIntegration(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_path = self._tmp.name
        os.makedirs(os.path.join(self.project_path, "images"))

        # Sprint241 - 이 시험은 **유료 AI Provider 가 도는 것**을 잰다.
        #
        # 제품의 기본값은 AI 이미지 생성 금지다(결제 잠금). 그러니 AI
        # 경로를 재려면 그 전제를 적어야 한다 - 지금까지는 AI 를 쓰는
        # 세상이 유일해서 적을 필요가 없었을 뿐이다.
        #
        # 약하게 만드는 것이 아니라 숨어 있던 전제를 드러내는 것이다.
        media_policy.choose(self.project_path, media_policy.MODE_MINE_STOCK_AI)

        self.scene = {
            "scene": 2,
            "image_prompt": "a bowl of oatmeal",
            "visual_type": "ai",
        }

    def _write(self, path, payload):
        with open(path, "wb") as f:
            f.write(payload)
        return path

    def test_a_single_candidate_calls_generate_image_exactly_as_before(self):
        """플래그가 꺼진 기본 상태. 예전 경로 그대로여야 한다."""

        def fake_generate_image(prompt, output_file, **kwargs):
            return self._write(output_file, b"ONLY")

        with patch.object(
            asset_integration_service.image_service, "generate_image",
            side_effect=fake_generate_image,
        ) as single, patch.object(
            asset_integration_service.image_service,
            "generate_image_candidates",
        ) as many, patch.object(
            asset_integration_service.best_of_n_service, "_ask_gemini",
        ) as ask:
            enriched = asset_integration_service.integrate_asset(
                self.scene, self.project_path, candidate_count=1,
            )

        single.assert_called_once()
        many.assert_not_called()
        # 후보가 한 장이면 고를 것이 없다 - Gemini를 부르지 않는다.
        ask.assert_not_called()

        self.assertEqual(enriched["provider"], "ai_image")
        with open(enriched["asset_path"], "rb") as f:
            self.assertEqual(f.read(), b"ONLY")

    def test_the_selected_candidate_becomes_the_scene_image(self):
        def fake_candidates(prompt, output_files, **kwargs):
            payloads = [b"CAND0", b"CAND1", b"CAND2"]
            return [
                self._write(path, payloads[index])
                for index, path in enumerate(output_files)
            ]

        with patch.object(
            asset_integration_service.image_service,
            "generate_image_candidates", side_effect=fake_candidates,
        ), patch.object(
            asset_integration_service.best_of_n_service, "_ask_gemini",
            return_value=_selection(2, [50, 60, 95]),
        ):
            enriched = asset_integration_service.integrate_asset(
                self.scene, self.project_path, candidate_count=3,
            )

        with open(enriched["asset_path"], "rb") as f:
            self.assertEqual(f.read(), b"CAND2")

        self.assertEqual(
            enriched["asset_path"],
            os.path.join(self.project_path, "images", "scene2.png"),
        )

    def test_losing_candidates_do_not_stay_on_disk(self):
        def fake_candidates(prompt, output_files, **kwargs):
            return [
                self._write(path, f"C{index}".encode())
                for index, path in enumerate(output_files)
            ]

        with patch.object(
            asset_integration_service.image_service,
            "generate_image_candidates", side_effect=fake_candidates,
        ), patch.object(
            asset_integration_service.best_of_n_service, "_ask_gemini",
            return_value=_selection(0, [95, 50, 50]),
        ):
            asset_integration_service.integrate_asset(
                self.scene, self.project_path, candidate_count=3,
            )

        leftovers = [
            name for name in os.listdir(
                os.path.join(self.project_path, "images")
            )
            if name != "scene2.png"
        ]
        self.assertEqual(leftovers, [])

    def test_the_selection_is_recorded_on_the_scene(self):
        """모든 결정은 로그에 남긴다 - Sprint73에서 세운 원칙."""

        def fake_candidates(prompt, output_files, **kwargs):
            return [self._write(path, b"X") for path in output_files]

        with patch.object(
            asset_integration_service.image_service,
            "generate_image_candidates", side_effect=fake_candidates,
        ), patch.object(
            asset_integration_service.best_of_n_service, "_ask_gemini",
            return_value=_selection(1, [40, 90]),
        ):
            enriched = asset_integration_service.integrate_asset(
                self.scene, self.project_path, candidate_count=2,
            )

        self.assertEqual(enriched["candidate_count"], 2)
        self.assertEqual(enriched["selected_candidate"], 1)
        self.assertEqual(enriched["candidate_scores"], [40, 90])

    def test_a_stock_scene_that_succeeds_never_generates_candidates(self):
        """Selection은 Imagen 경로의 장치다. Pexels가 성공하면 후보를
        뽑을 일이 없다 - 배정된 후보 수와 무관하다."""

        scene = dict(self.scene, visual_type="real")

        def fake_download(candidate, staging_path):
            self._write(staging_path, b"STOCK")
            return {
                "source": "pexels_image",
                "local_path": staging_path,
                "metadata": {"query": "oatmeal"},
            }

        with patch.object(
            asset_integration_service, "get_candidates",
            return_value=[{"id": 1}],
        ), patch.object(
            asset_integration_service, "select_best_with_score",
            return_value=({"id": 1}, 90),
        ), patch.object(
            asset_integration_service, "download_candidate",
            side_effect=fake_download,
        ), patch.object(
            asset_integration_service.image_service,
            "generate_image_candidates",
        ) as many:
            enriched = asset_integration_service.integrate_asset(
                scene, self.project_path, candidate_count=3,
            )

        many.assert_not_called()
        self.assertEqual(enriched["provider"], "pexels_image")


class TestCollectAssetsPlansTheBudget(unittest.TestCase):
    """배분은 병렬 팬아웃 이전에 끝난다."""

    def test_each_scene_receives_its_planned_candidate_count(self):
        from app.steps import step02_assets

        scenes = [
            {"scene": 1, "visual_type": "ai", "image_prompt": "a"},
            {"scene": 2, "visual_type": "ai", "image_prompt": "b"},
        ]

        seen = {}

        def fake_integrate(scene, project_path, channel="wellbeing",
                          prefer_ai=False, candidate_count=1):
            seen[scene["scene"]] = candidate_count
            return dict(scene)

        with patch.object(
            step02_assets, "integrate_asset", side_effect=fake_integrate,
        ), patch.object(
            step02_assets.config, "ENABLE_BEST_OF_N", True,
        ), patch.object(
            step02_assets.config, "BEST_OF_N_CANDIDATES", 2,
        ), patch.object(
            step02_assets.config, "BEST_OF_N_MAX_CANDIDATES", 10,
        ):
            step02_assets.collect_assets(scenes, "/tmp/project")

        self.assertEqual(seen, {1: 2, 2: 2})

    def test_the_flag_off_means_one_candidate_everywhere(self):
        from app.steps import step02_assets

        scenes = [{"scene": 1, "visual_type": "ai", "image_prompt": "a"}]
        seen = {}

        def fake_integrate(scene, project_path, channel="wellbeing",
                           prefer_ai=False, candidate_count=1):
            seen[scene["scene"]] = candidate_count
            return dict(scene)

        with patch.object(
            step02_assets, "integrate_asset", side_effect=fake_integrate,
        ), patch.object(
            step02_assets.config, "ENABLE_BEST_OF_N", False,
        ), patch.object(
            step02_assets.config, "BEST_OF_N_CANDIDATES", 3,
        ):
            step02_assets.collect_assets(scenes, "/tmp/project")

        self.assertEqual(seen, {1: 1})


if __name__ == "__main__":
    unittest.main()
