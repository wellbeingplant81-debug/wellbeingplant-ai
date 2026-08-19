"""
Sprint228 - 필요한 길이를 검색에 실어 보낸다 (Epic 68, Phase 2).

Sprint227이 "이 영상이 이 scene을 채우는가"로 순위를 매기게 했다. 그런데
고르는 것만으로는 부족하다는 것이 곧 드러난다.

    받아 온 다섯 개가 전부 scene보다 짧으면
    순위를 아무리 잘 매겨도 결과는 hold(마지막 프레임 정지)다.
    고를 것이 없다.

그래서 짧은 것을 아예 받지 않는다.

Pexels는 실제로 걸러 준다 - 손검증(2026-08-19)
----------------------------------------------
    조건 없이         [5, 8, 10, 10, 10, 12, 18, 19, 22, 24]
    min_duration=10   [10, 10, 10, 10, 12, 18, 19, 22, 24, 26]

Pixabay에는 그런 질의 항목이 없다. 거르는 대신 더 받아 와서 고를 여지를
넓힌다 - 지어낸 질의 항목을 붙이지 않는다.

여기서는 바깥으로 나가지 않는다
-------------------------------
Pexels가 걸러 주는 그 동작을 대역이 그대로 흉내 낸다(짧은 것을 빼고
per_page만큼 자른다). 결과를 지어내는 것이 아니라, 실제로 확인한 동작을
재현하는 것이다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.providers import pexels_provider, pixabay_provider
from app.services import (
    asset_relevance, asset_selector, footage, provider_factory, search_cache,
)
from app.services.asset_ranking_service import select_best_with_score
from app.services.duration_estimator import estimate_duration


NARRATION = (
    "무릎이 아플 때는 앉아서 다리를 천천히 펴고 십 초를 세어 봅니다. "
    "그다음 반대쪽도 같은 방법으로 해 주십시오."
)

SCENE = {"scene": 1, "narration": NARRATION,
         "image_prompt": "knee stretching at home"}


class TheRequestCarriesTheLengthTest(unittest.TestCase):
    """검색 요청에 실려 나가는가."""

    def _params(self, **asked):
        seen = {}

        class _Answer:
            status_code = 200

            def json(self):
                return {"videos": []}

        def _get(url, headers=None, params=None, timeout=None):
            seen.update(params or {})

            return _Answer()

        with patch.dict(os.environ, {"PEXELS_API_KEY": "k"}), \
                patch.object(pexels_provider.requests, "get", _get):
            pexels_provider.search_videos("무릎", **asked)

        return seen

    def test_it_is_sent_when_we_know_the_scene(self):
        self.assertEqual(self._params(min_duration=12)["min_duration"], 12)

    def test_it_is_rounded_up_not_down(self):
        """
        내림하면 필요한 길이보다 짧은 것이 다시 섞인다 - 11.2초가
        필요한데 11초짜리를 받으면 그것은 덮지 못한다.
        """

        self.assertEqual(self._params(min_duration=11.2)["min_duration"], 12)

    def test_nothing_is_sent_when_we_do_not_know(self):
        self.assertNotIn("min_duration", self._params())

    def test_zero_is_not_a_condition(self):
        self.assertNotIn("min_duration", self._params(min_duration=0))

    def test_the_rest_of_the_request_is_unchanged(self):
        found = self._params(min_duration=12)

        self.assertEqual(found["query"], "무릎")
        self.assertEqual(found["orientation"], "portrait")
        self.assertEqual(found["per_page"], 5)


class TheChainOnlyAsksWhenItKnowsTest(unittest.TestCase):
    """모르면 예전 요청 그대로다."""

    def test_without_a_length_the_call_is_byte_for_byte_the_old_one(self):
        with patch.object(pexels_provider, "search_videos") as search:
            chain = dict(provider_factory.build_provider_chain())
            chain["pexels_video"]("무릎")

        search.assert_called_once_with("무릎")

    def test_with_a_length_one_condition_is_added(self):
        with patch.object(pexels_provider, "search_videos") as search:
            chain = dict(
                provider_factory.build_provider_chain(min_seconds=12))
            chain["pexels_video"]("무릎")

        search.assert_called_once_with("무릎", min_duration=12)

    def test_pixabay_is_widened_instead_of_filtered(self):
        """
        Pixabay에는 길이로 거르는 항목이 없다. 없는 것을 붙이지 않는다.
        """

        with patch.object(pixabay_provider, "search_videos") as search:
            chain = dict(
                provider_factory.build_provider_chain(min_seconds=12))
            chain["pixabay_video"]("무릎")

        search.assert_called_once_with(
            "무릎", per_page=provider_factory.WIDER_VIDEO_PER_PAGE)

    def test_pixabay_is_untouched_without_a_length(self):
        with patch.object(pixabay_provider, "search_videos") as search:
            chain = dict(provider_factory.build_provider_chain())
            chain["pixabay_video"]("무릎")

        search.assert_called_once_with("무릎")

    def test_the_picture_side_never_changes(self):
        """사진에는 길이가 없다."""

        for name, module in (("pexels_image", pexels_provider),
                             ("pixabay_image", pixabay_provider)):
            with self.subTest(name=name):
                caller = "search_photos" if "pexels" in name else "search_images"

                with patch.object(module, caller) as search:
                    chain = dict(
                        provider_factory.build_provider_chain(min_seconds=12))
                    chain[name]("무릎")

                search.assert_called_once_with("무릎")


class TheCacheDoesNotMixConditionsTest(unittest.TestCase):
    """
    같은 검색어라도 조건이 다르면 다른 결과다. 섞이면 짧은 조건으로
    받아 둔 것을 긴 scene이 물려받아 hold가 난다.
    """

    def setUp(self):
        search_cache.clear()
        self.addCleanup(search_cache.clear)

    def test_a_different_condition_is_a_different_entry(self):
        search_cache.search("pexels_video", "무릎",
                            lambda q: [{"duration": 2}], variant=None)

        self.assertFalse(search_cache.has("pexels_video", "무릎", variant=12))

    def test_each_condition_keeps_its_own_answer(self):
        short = search_cache.search("pexels_video", "무릎",
                                    lambda q: [{"duration": 2}], variant=None)
        long_one = search_cache.search("pexels_video", "무릎",
                                       lambda q: [{"duration": 20}],
                                       variant=12)

        self.assertEqual(short[0]["duration"], 2)
        self.assertEqual(long_one[0]["duration"], 20)

    def test_the_same_condition_still_hits(self):
        calls = []

        def _once(query):
            calls.append(query)

            return [{"duration": 20}]

        search_cache.search("pexels_video", "무릎", _once, variant=12)
        search_cache.search("pexels_video", "무릎", _once, variant=12)

        self.assertEqual(len(calls), 1)
        self.assertTrue(search_cache.has("pexels_video", "무릎", variant=12))

    def test_without_a_condition_it_behaves_as_before(self):
        calls = []

        def _once(query):
            calls.append(query)

            return [{"duration": 20}]

        search_cache.search("pexels_video", "무릎", _once)
        search_cache.search("pexels_video", "무릎", _once)

        self.assertEqual(len(calls), 1)
        self.assertTrue(search_cache.has("pexels_video", "무릎"))


# 손검증에서 본 Pexels의 실제 응답을 닮은 묶음.
#
# 앞쪽이 전부 짧다 - per_page만큼 잘라 받으면 짧은 것만 손에 들어온다.
POOL = [0.4, 0.5, 0.6, 0.7, 0.8, 12.0, 18.0, 24.0]


def _like_pexels(query, orientation="portrait", per_page=5, min_duration=None):
    """
    Pexels가 실제로 하는 일을 그대로 흉내 낸다 - 조건보다 짧은 것을
    빼고, 남은 것에서 per_page만큼 돌려준다.
    """

    kept = [one for one in POOL
            if min_duration is None or one >= min_duration]

    return [{"source": "pexels_video", "duration": seconds,
             "source_url": "u%s" % seconds, "download_url": "d%s" % seconds,
             "width": 1080, "height": 1920, "alt": "knee stretching",
             "query": query}
            for seconds in kept[:per_page]]


class FewerScenesFallBackToAStillTest(unittest.TestCase):
    """
    효과를 Sprint227이 만든 그 잣대로 잰다 - 고른 영상이 scene을 어떻게
    채우게 되는가(trim / loop / hold).
    """

    def setUp(self):
        search_cache.clear()
        self.addCleanup(search_cache.clear)

        self.needed = asset_relevance.needed_seconds(SCENE)

        self.assertIsNotNone(self.needed)
        self.assertAlmostEqual(self.needed, estimate_duration(NARRATION))

    def _mode(self, scene):
        """그 scene으로 검색해 고른 영상이 어떻게 채우게 되는가."""

        with patch.dict(os.environ, {"PEXELS_API_KEY": "k"}), \
                patch.object(pexels_provider, "search_videos", _like_pexels), \
                patch.object(pexels_provider, "search_photos",
                             lambda *a, **k: []), \
                patch.object(pixabay_provider, "search_videos",
                             lambda *a, **k: []), \
                patch.object(pixabay_provider, "search_images",
                             lambda *a, **k: []):

            candidates = asset_selector.get_candidates(
                SCENE["image_prompt"], allow_video=True, scene=scene)

        self.assertTrue(candidates, "후보가 하나도 없다")

        chosen, _ = select_best_with_score(candidates, scene=SCENE)

        return footage.plan(chosen["duration"], self.needed)["mode"]

    def test_without_the_condition_the_scene_freezes(self):
        """
        예전 길. 짧은 것만 받아 왔으므로 순위를 매길 것도 없다.
        """

        self.assertEqual(self._mode(None), footage.HOLD)

    def test_with_the_condition_it_actually_moves(self):
        self.assertEqual(self._mode(SCENE), footage.TRIM)

    def test_that_is_the_whole_point(self):
        """한 자리에서 나란히 본다."""

        before = self._mode(None)

        search_cache.clear()

        after = self._mode(SCENE)

        self.assertEqual(before, footage.HOLD)
        self.assertNotEqual(after, footage.HOLD)

    def test_the_condition_is_what_the_scene_needs(self):
        """
        보낸 조건이 이 scene이 필요로 하는 그 길이여야 한다.
        """

        seen = {}

        def _watch(query, orientation="portrait", per_page=5,
                   min_duration=None):
            seen["min_duration"] = min_duration

            return _like_pexels(query, orientation, per_page, min_duration)

        with patch.dict(os.environ, {"PEXELS_API_KEY": "k"}), \
                patch.object(pexels_provider, "search_videos", _watch), \
                patch.object(pexels_provider, "search_photos",
                             lambda *a, **k: []), \
                patch.object(pixabay_provider, "search_videos",
                             lambda *a, **k: []), \
                patch.object(pixabay_provider, "search_images",
                             lambda *a, **k: []):

            asset_selector.get_candidates(
                SCENE["image_prompt"], allow_video=True, scene=SCENE)

        self.assertAlmostEqual(seen["min_duration"], self.needed)


if __name__ == "__main__":
    unittest.main()
