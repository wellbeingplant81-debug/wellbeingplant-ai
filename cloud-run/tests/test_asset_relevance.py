"""
Sprint76 - 후보를 실제로 순위 매긴다.

지금 score_asset은 asset_type 기본점수 + 세로비율 가산점 + provider
가중치 + hook 보너스 + 학습 bias로 점수를 낸다. 이 중 후보마다 달라지는
값은 세로비율뿐이다. 같은 provider에서 온 세로 사진 5장은 전부 같은
점수를 받고, max()가 그중 첫 번째를 고른다. select_asset은 아예
results[0]을 쓴다.

즉 순위라는 것이 없었다. 그리고 그것이 가장 큰 실패 원인과 맞물린다 -
축적된 스톡 scene 140건 중 80.7%가 재생성 권고를 받았고, 사유가 기록된
113건 중 89건이 "검색 결과가 장면과 다름"이었다.

의미 정보가 없어서 순위를 못 매긴 것이 아니다. Pexels 사진 응답에는
alt(사진 설명)가 있고 url에는 내용을 적은 슬러그가 있는데, provider가
그 두 필드를 버리고 있었다. 추가 API 호출 없이 얻을 수 있는 신호다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_relevance


def _candidate(**overrides):
    candidate = {
        "source": "pexels_image",
        "download_url": "https://x/a.jpg",
        "width": 1080,
        "height": 1920,
        "alt": "",
        "source_url": "",
    }
    candidate.update(overrides)
    return candidate


class TestSceneRelevance(unittest.TestCase):

    SCENE = {
        "subject": "a ceramic bowl of creamy oatmeal with blueberries",
        "action": "sitting on a wooden table",
        "environment": "a sunlit kitchen",
    }

    def test_a_matching_alt_scores_higher_than_an_unrelated_one(self):
        matching = _candidate(alt="a bowl of oatmeal with fresh blueberries")
        unrelated = _candidate(alt="a red sports car on a highway")

        self.assertGreater(
            asset_relevance.score(matching, self.SCENE),
            asset_relevance.score(unrelated, self.SCENE),
        )

    def test_the_url_slug_is_used_when_alt_is_missing(self):
        """Pexels 비디오 응답에는 alt가 없다. url 슬러그가 남는다."""

        slugged = _candidate(
            alt="",
            source_url="https://www.pexels.com/photo/bowl-of-oatmeal-123/",
        )
        bare = _candidate(alt="", source_url="https://www.pexels.com/photo/123/")

        self.assertGreater(
            asset_relevance.score(slugged, self.SCENE),
            asset_relevance.score(bare, self.SCENE),
        )

    def test_no_text_at_all_is_not_an_error(self):
        # 순위가 낮아질 뿐, 후보에서 사라지지는 않는다.
        score = asset_relevance.score(_candidate(), self.SCENE)

        self.assertIsInstance(score, float)


class TestHumanPresence(unittest.TestCase):
    """Sprint73/75에서 반복해 무너진 자리 - 사물 scene에 사람이 들어온다."""

    OBJECT_SCENE = {"subject": "a ceramic bowl of oatmeal"}
    PERSON_SCENE = {"subject": "a 50s Korean man drinking water",
                    "character_scene": True}

    def test_a_person_photo_is_penalised_for_an_object_scene(self):
        with_person = _candidate(alt="a woman holding a bowl of oatmeal")
        without = _candidate(alt="a bowl of oatmeal on a table")

        self.assertGreater(
            asset_relevance.score(without, self.OBJECT_SCENE),
            asset_relevance.score(with_person, self.OBJECT_SCENE),
        )

    def test_a_person_photo_is_not_penalised_for_a_person_scene(self):
        with_person = _candidate(alt="a man drinking a glass of water")

        penalty = asset_relevance.human_penalty(with_person, self.PERSON_SCENE)

        self.assertEqual(penalty, 0.0)


class TestComposition(unittest.TestCase):

    def test_portrait_beats_landscape(self):
        portrait = _candidate(width=1080, height=1920, alt="a bowl of oatmeal")
        landscape = _candidate(width=1920, height=1080, alt="a bowl of oatmeal")

        scene = {"subject": "a bowl of oatmeal"}

        self.assertGreater(
            asset_relevance.score(portrait, scene),
            asset_relevance.score(landscape, scene),
        )

    def test_missing_dimensions_are_not_fatal(self):
        unknown = _candidate(width=None, height=None, alt="a bowl of oatmeal")

        self.assertIsInstance(
            asset_relevance.score(unknown, {"subject": "a bowl"}), float,
        )


class TestMotionSuitability(unittest.TestCase):
    """Shorts의 한 scene은 몇 초짜리다. 20초 영상을 받아 첫 프레임만
    쓰는 것은 낭비이고, 1초짜리는 쓸 구간이 없다."""

    SCENE = {"subject": "water being poured into a glass"}

    def test_a_usable_duration_beats_an_extreme_one(self):
        usable = _candidate(source="pexels_video", duration=8,
                            alt="water poured into a glass")
        too_long = _candidate(source="pexels_video", duration=120,
                              alt="water poured into a glass")

        self.assertGreater(
            asset_relevance.score(usable, self.SCENE),
            asset_relevance.score(too_long, self.SCENE),
        )

    def test_duration_is_ignored_for_photos(self):
        photo = _candidate(alt="water poured into a glass")

        self.assertEqual(
            asset_relevance.motion_score(photo), 0.0,
        )


class TestDuplicatePenalty(unittest.TestCase):
    """같은 사진이 두 scene에 들어가면 영상이 반복돼 보인다."""

    SCENE = {"subject": "a bowl of oatmeal"}

    def test_an_already_used_asset_is_penalised(self):
        candidate = _candidate(
            alt="a bowl of oatmeal",
            source_url="https://www.pexels.com/photo/oatmeal-123/",
        )

        fresh = asset_relevance.score(candidate, self.SCENE, used=set())
        repeat = asset_relevance.score(
            candidate, self.SCENE,
            used={"https://www.pexels.com/photo/oatmeal-123/"},
        )

        self.assertGreater(fresh, repeat)

    def test_a_different_asset_is_not_penalised(self):
        candidate = _candidate(
            alt="a bowl of oatmeal",
            source_url="https://www.pexels.com/photo/oatmeal-999/",
        )

        self.assertEqual(
            asset_relevance.score(candidate, self.SCENE, used=set()),
            asset_relevance.score(
                candidate, self.SCENE, used={"https://other/1/"},
            ),
        )


class TestRanking(unittest.TestCase):

    def test_the_best_candidate_is_returned_first(self):
        scene = {"subject": "a ceramic bowl of oatmeal with blueberries"}

        candidates = [
            _candidate(alt="a red sports car"),
            _candidate(alt="a bowl of oatmeal topped with blueberries"),
            _candidate(alt="a plate of pasta"),
        ]

        ranked = asset_relevance.rank(candidates, scene)

        self.assertEqual(
            ranked[0]["alt"], "a bowl of oatmeal topped with blueberries",
        )

    def test_ranking_is_deterministic(self):
        scene = {"subject": "a bowl of oatmeal"}
        candidates = [_candidate(alt=f"photo {i}") for i in range(5)]

        self.assertEqual(
            [c["alt"] for c in asset_relevance.rank(candidates, scene)],
            [c["alt"] for c in asset_relevance.rank(candidates, scene)],
        )

    def test_an_empty_candidate_list_ranks_to_nothing(self):
        self.assertEqual(asset_relevance.rank([], {"subject": "x"}), [])


if __name__ == "__main__":
    unittest.main()
