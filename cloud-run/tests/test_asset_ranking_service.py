import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_ranking_service import select_best


class TestSelectBest(unittest.TestCase):

    def setUp(self):
        # Sprint31 Learning Layer 격리: 실제 공유 feedback.json 상태와
        # 무관하게 이 테스트들이 항상 결정적으로 동작하도록, feedback
        # 이력이 없는 것처럼 고정한다 (Sprint30 시절 동작과 동일).
        patcher = patch(
            "app.services.asset_ranking_service.load_all",
            return_value=[],
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_empty_candidates_returns_none(self):
        self.assertIsNone(select_best([]))

    def test_single_candidate_is_returned(self):
        candidate = {"source": "ai_image"}
        self.assertEqual(select_best([candidate]), candidate)

    def test_higher_scoring_candidate_wins(self):
        low = {"source": "pixabay_image", "width": 1920, "height": 1080}
        high = {"source": "pexels_image", "width": 1080, "height": 1920}

        self.assertEqual(select_best([low, high]), high)
        self.assertEqual(select_best([high, low]), high)

    def test_video_loses_to_image_when_otherwise_equal(self):
        video = {"source": "pexels_video", "width": 1080, "height": 1920}
        image = {"source": "pixabay_image", "width": 1080, "height": 1920}

        self.assertEqual(select_best([video, image]), image)

    def test_hook_scene_flag_passed_through_to_scoring(self):
        # 두 후보 모두 동일하게 hook 보너스를 받으므로 상대 순위는
        # 바뀌지 않지만, 예외 없이 정상 동작하는지 확인한다.
        low = {"source": "pixabay_image", "width": 1920, "height": 1080}
        high = {"source": "pexels_image", "width": 1080, "height": 1920}

        result = select_best([low, high], is_hook_scene=True)
        self.assertEqual(result, high)


class TestSelectBestWithLearning(unittest.TestCase):
    """Sprint31 - select_best()가 feedback 이력을 실제로 반영하는지 검증.
    load_all()만 mock하고, compute_bias/score_asset은 실제 로직을
    그대로 실행시켜 전체 연결을 검증한다."""

    def test_learned_bias_can_flip_ranking_between_close_candidates(self):
        # 기본 스코어는 pexels_image(0.92) > pixabay_image(0.90)이지만,
        # 이력이 전부 pixabay_image의 success뿐이면 (a) pixabay_image는
        # +0.05(success bonus cap) 가산되고 (b) 이력에 전혀 등장하지
        # 않는 pexels_image는 표본이 충분한데 success가 0회이므로
        # -0.03(failure penalty) 감산되어, 두 효과가 합쳐져 역전된다.
        pixabay = {"source": "pixabay_image", "width": 1080, "height": 1920}
        pexels = {"source": "pexels_image", "width": 1080, "height": 1920}

        records = [
            {"provider": "pixabay_image", "outcome": "success"}
            for _ in range(10)  # MAX_SUCCESS_BONUS(0.05)까지 포화
        ]

        with patch(
            "app.services.asset_ranking_service.load_all",
            return_value=records,
        ):
            result = select_best([pexels, pixabay])

        self.assertEqual(result, pixabay)

    def test_no_feedback_history_behaves_like_sprint30(self):
        pixabay = {"source": "pixabay_image", "width": 1080, "height": 1920}
        pexels = {"source": "pexels_image", "width": 1080, "height": 1920}

        with patch(
            "app.services.asset_ranking_service.load_all",
            return_value=[],
        ):
            result = select_best([pexels, pixabay])

        self.assertEqual(result, pexels)


if __name__ == "__main__":
    unittest.main()
