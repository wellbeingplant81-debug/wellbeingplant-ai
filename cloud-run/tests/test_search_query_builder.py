"""
Sprint76 - 검색어를 문장 자르기가 아니라 요소에서 만든다.

축적된 37개 프로젝트에서 스톡 scene 140건을 뽑아 보니, 검색어는 예외
없이 정확히 8단어였다 - 100%가 상한에 걸렸다는 뜻이고, 프롬프트 단어를
덮는 비율은 평균 15.2%였다. 나머지는 검색에 아예 반영되지 않았다.

그 8단어 중 36.9%가 카메라 어휘였다(150개 검색어 1200단어 중 443단어).
"wide shot", "top down view", "close up shot" 같은 말이 예산의 3분의 1을
먹었는데, Pexels는 사진을 카메라 앵글로 색인하지 않는다.

그 부분은 Sprint75가 이미 상당히 고쳤다 - 파생 image_prompt가 subject를
앞에 두면서 앞 8단어가 피사체로 채워졌다. 여기서 고치는 것은 남은
문제다. 검색어가 여전히 "문장에서 앞 N단어"이고, 중복 단어가 그대로
들어가며("clear glass water lukewarm water poured glass gentle"), 검색이
실패해도 다른 표현을 시도하지 않는다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import search_query_builder as builder


class TestBuildFromElements(unittest.TestCase):

    def _scene(self, **overrides):
        scene = {
            "scene": 4,
            "subject": "a ceramic bowl of creamy oatmeal topped with "
                       "fresh blueberries and almonds",
            "action": "sitting on a rustic wooden table",
            "environment": "a warm sunlit breakfast table",
            "camera": "top-down view, camera directly above looking straight down",
            "composition": "rule of thirds",
            "lighting": "warm appetizing morning light",
        }
        scene.update(overrides)
        return scene

    def test_the_camera_never_reaches_the_query(self):
        """실측 - 검색어 단어의 36.9%가 카메라 어휘였다. Pexels는
        사진을 앵글로 색인하지 않는다."""

        query = builder.build_query(self._scene())

        for word in ("top", "down", "view", "camera", "straight"):
            with self.subTest(word=word):
                self.assertNotIn(word, query.split())

    def test_composition_and_lighting_do_not_reach_the_query(self):
        query = builder.build_query(self._scene())

        for word in ("rule", "thirds", "appetizing"):
            with self.subTest(word=word):
                self.assertNotIn(word, query.split())

    def test_the_subject_leads(self):
        query = builder.build_query(self._scene())

        self.assertTrue(query.startswith("ceramic bowl"))

    def test_repeated_words_appear_once(self):
        """실측된 검색어 - "clear glass water lukewarm water poured
        glass gentle". water와 glass가 예산을 두 번씩 먹었다."""

        query = builder.build_query({
            "subject": "a clear glass of water",
            "action": "lukewarm water being poured into the glass",
        })

        words = query.split()
        self.assertEqual(len(words), len(set(words)))

    def test_a_legacy_scene_still_produces_a_query(self):
        """구버전 대본은 image_prompt 하나뿐이다."""

        query = builder.build_query({
            "image_prompt": "a beautiful bowl of oatmeal with blueberries",
        })

        self.assertIn("oatmeal", query)

    def test_an_empty_scene_gives_an_empty_query(self):
        self.assertEqual(builder.build_query({}), "")

    def test_the_query_stays_short(self):
        query = builder.build_query(self._scene())

        self.assertLessEqual(len(query.split()), builder.MAX_QUERY_WORDS)


class TestExpansion(unittest.TestCase):
    """검색이 실패하면 다른 표현을 시도한다.

    지금은 한 번 검색해서 결과가 없으면 그대로 AI 폴백이다. 스톡
    검색은 어휘가 조금만 어긋나도 0건이 나오므로, 좁은 표현에서
    넓은 표현으로 물러나며 몇 번 더 시도할 값이 있다.
    """

    def test_the_first_candidate_is_the_full_query(self):
        candidates = builder.expand({
            "subject": "a ceramic bowl of creamy oatmeal with blueberries",
            "action": "sitting on a wooden table",
        })

        self.assertEqual(candidates[0], builder.build_query({
            "subject": "a ceramic bowl of creamy oatmeal with blueberries",
            "action": "sitting on a wooden table",
        }))

    def test_candidates_get_broader(self):
        """뒤로 갈수록 단어가 줄어든다 - 좁은 검색이 0건이면 넓힌다."""

        candidates = builder.expand({
            "subject": "a ceramic bowl of creamy oatmeal with blueberries",
            "action": "sitting on a wooden table",
            "environment": "a sunlit kitchen",
        })

        lengths = [len(c.split()) for c in candidates]
        self.assertEqual(lengths, sorted(lengths, reverse=True))

    def test_there_are_no_duplicate_candidates(self):
        candidates = builder.expand({"subject": "running shoes"})

        self.assertEqual(len(candidates), len(set(candidates)))

    def test_an_empty_scene_expands_to_nothing(self):
        self.assertEqual(builder.expand({}), [])

    def test_the_last_candidate_is_the_bare_subject_head(self):
        candidates = builder.expand({
            "subject": "a ceramic bowl of creamy oatmeal with blueberries",
            "action": "sitting on a wooden table",
        })

        self.assertLessEqual(len(candidates[-1].split()), 3)


if __name__ == "__main__":
    unittest.main()
