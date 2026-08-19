"""
Sprint233 - 영상 후보가 제 재료를 들고 들어온다 (Epic 70).

무엇이 있었나
-------------
저장된 후보 풀 39 scene 을 다시 재 보니 이랬다.

    영상 후보가 하나라도 있던 scene : 39 / 39   ← 전부 있었다
    그중 실제로 영상을 고른 scene   :  5
    영상 길이 : 최소 2s · 중앙 10s · 최대 33s   ← 길이도 충분했다

후보가 없어서도, 짧아서도 아니었다. 점수에서 진다.

    사진 최고점 - 영상 최고점 : 중앙 +0.040
    그 차이의 가장 큰 몫       : 관련도 중앙 +0.050 (가중치 1.0)

관련도가 갈리는 까닭이 코드에 적혀 있었다 - 영상 응답에는 alt 가 없다.
사진은 alt(중앙 13낱말) + 슬러그(7낱말)를 들고 오는데 영상은 슬러그
6낱말이 전부다. 판정의 가장 큰 항목에서 재료를 절반만 들고 들어간다.

응답을 통째로 열어 확인한 것(2026-08-19, 회귀 밖)
-------------------------------------------------
    tags        칸은 있는데 30개 중 30개가 비어 있었다
    user.name   찍은 사람의 이름이다. 내용과 상관없다
    image       **미리보기 그림 주소. 파일 이름에 다른 슬러그가 있다**

        url   .../video/a-woman-stretching-5510121/
        image .../videos/5510121/coaching-crossfit-training-fast-workout-
              at-home-fitness-5510121.jpeg

    표본 75 중 27개(36%)가 새 낱말을 얻는다(평균 1.7개). 나머지는
    pexels-photo 같은 껍데기라 아무것도 늘지 않는다.

영상에게 점수를 얹는 것이 아니다
--------------------------------
가중치도 기본 점수도 motion 보너스도 provider 선호도 건드리지 않았다.
사진이 이미 두 자리에서 말을 가져오는데 영상만 한 자리에서 가져오던
것을, 있는 자리를 마저 읽어 **같은 조건**으로 맞춘 것뿐이다.

말이 늘면 벌점도 늘 수 있다 - 그것이 옳다
-----------------------------------------
실측에서 한 후보의 총점이 0.250 에서 -0.350 으로 내려갔다.

    예전 말 : a little doing yoga pose
    지금 말 : a little doing yoga pose adult apartment baby beautiful

사람을 요구하지 않은 scene 인데 그 영상에는 사람이 있었다. 예전에는
"little" 이라 사람인 줄 몰랐을 뿐이다. 규칙이 나빠진 것이 아니라
사실이 드러난 것이다.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.providers import pexels_provider
from app.services import asset_relevance


def _old_text(candidate):
    """Sprint233 이전의 _candidate_text 를 그대로 옮긴 것."""

    alt = candidate.get("alt") or ""
    url = candidate.get("source_url") or ""

    slug = ""
    if url:
        parts = [part for part in url.rstrip("/").split("/") if part]
        if parts:
            slug = parts[-1].replace("-", " ").replace("_", " ")

    return f"{alt} {slug}".strip()


VIDEO = {
    "source": "pexels_video",
    "source_url": "https://www.pexels.com/video/a-woman-stretching-5510121/",
    "preview_url": ("https://images.pexels.com/videos/5510121/"
                    "coaching-crossfit-training-fast-workout-at-home-"
                    "fitness-5510121.jpeg?auto=compress"),
    "duration": 24,
    "width": 1080,
    "height": 1920,
    "alt": "",
}

PHOTO = {
    "source": "pexels_image",
    "source_url": "https://www.pexels.com/photo/knee-stretch-123456/",
    "alt": "A woman stretching her knee on a mat at home",
    "width": 1080,
    "height": 1920,
}


class TheVideoReadsItsPreviewNameTest(unittest.TestCase):
    """미리보기 그림을 쓰는 것이 아니라 그 이름을 읽는다."""

    def test_the_preview_words_join_the_judgement(self):
        said = asset_relevance._candidate_text(VIDEO)

        for word in ("coaching", "crossfit", "workout", "fitness"):
            with self.subTest(word=word):
                self.assertIn(word, said)

    def test_the_old_words_are_still_there(self):
        said = asset_relevance._candidate_text(VIDEO)

        for word in ("woman", "stretching"):
            with self.subTest(word=word):
                self.assertIn(word, said)

    def test_the_extension_is_dropped(self):
        said = asset_relevance._candidate_text(VIDEO)

        self.assertNotIn("jpeg", said)

    def test_what_comes_after_the_question_mark_is_dropped(self):
        said = asset_relevance._candidate_text(VIDEO)

        self.assertNotIn("compress", said)

    def test_it_actually_moves_the_relevance(self):
        scene = {"image_prompt": "workout at home fitness"}

        without = dict(VIDEO)
        without.pop("preview_url")

        self.assertGreater(
            asset_relevance.relevance_score(VIDEO, scene),
            asset_relevance.relevance_score(without, scene))


class NothingElseChangesTest(unittest.TestCase):
    """
    이 칸이 없는 후보는 예전과 한 글자도 다르지 않아야 한다.
    """

    def test_a_photo_is_untouched(self):
        self.assertEqual(asset_relevance._candidate_text(PHOTO),
                         _old_text(PHOTO))

    def test_a_candidate_without_the_field_is_untouched(self):
        without = dict(VIDEO)
        without.pop("preview_url")

        self.assertEqual(asset_relevance._candidate_text(without),
                         _old_text(without))

    def test_an_empty_field_is_untouched(self):
        for value in (None, ""):
            with self.subTest(value=value):
                one = dict(VIDEO, preview_url=value)

                self.assertEqual(asset_relevance._candidate_text(one),
                                 _old_text(one))

    def test_the_photo_relevance_is_the_same_number(self):
        scene = {"image_prompt": "knee stretching home"}

        wanted = asset_relevance._scene_words(scene)
        found = set(asset_relevance._words(_old_text(PHOTO)))
        before = len(wanted & found) / len(wanted)

        self.assertAlmostEqual(
            asset_relevance.relevance_score(PHOTO, scene), before)


class TheStoredPoolsAreUnchangedTest(unittest.TestCase):
    """
    이미 쌓인 후보 풀(39 scene · 234 후보)에는 이 칸이 없다. 그것으로
    내린 판정이 달라지면 지금까지의 기록과 앞으로가 서로 다른 것을
    뜻하게 된다.
    """

    def _rows(self):
        where = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".dataset", "asset_dataset.jsonl")

        if not os.path.isfile(where):
            self.skipTest("쌓인 표가 없다")

        with open(where, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_every_stored_candidate_reads_the_same(self):
        rows = self._rows()

        candidates = [c for r in rows for c in (r.get("candidates") or [])]

        self.assertTrue(candidates, "후보가 없다")

        changed = [c for c in candidates
                   if asset_relevance._candidate_text(c) != _old_text(c)]

        self.assertEqual(changed, [], f"{len(changed)}개가 달라졌다")

    def test_their_relevance_is_the_same(self):
        for row in self._rows():
            terms = row.get("scene_terms") or []

            if not terms:
                continue

            scene = {"image_prompt": " ".join(terms)}
            wanted = asset_relevance._scene_words(scene)

            for one in (row.get("candidates") or []):
                found = set(asset_relevance._words(_old_text(one)))
                before = (len(wanted & found) / len(wanted)
                          if wanted and found else 0.0)

                self.assertAlmostEqual(
                    asset_relevance.relevance_score(one, scene), before)


class TheRuleIsAppliedToTheNewWordsTooTest(unittest.TestCase):
    """
    말이 늘면 벌점도 늘 수 있다. 규칙을 영상만 비켜 가게 하지 않는다 -
    그러면 그것이 곧 "영상에게 점수를 얹는 것"이 된다.
    """

    def test_a_person_revealed_by_the_preview_is_counted(self):
        scene = {"image_prompt": "vegetables on a table"}

        hidden = {
            "source": "pexels_video",
            "source_url": "https://www.pexels.com/video/a-little-doing-yoga-1/",
            "alt": "",
        }
        revealed = dict(
            hidden,
            preview_url=("https://images.pexels.com/videos/1/"
                         "adult-apartment-baby-beautiful-1.jpeg"))

        self.assertEqual(asset_relevance.human_penalty(hidden, scene), 0.0)
        self.assertEqual(asset_relevance.human_penalty(revealed, scene),
                         asset_relevance.HUMAN_PENALTY)


class TheProviderCarriesTheFieldTest(unittest.TestCase):
    """응답에 있는 것을 그대로 싣는다. 없으면 없는 대로 둔다."""

    def _search(self, videos):
        class _Answer:
            status_code = 200

            def json(self):
                return {"videos": videos}

        with patch.dict(os.environ, {"PEXELS_API_KEY": "k"}), \
                patch.object(pexels_provider.requests, "get",
                             return_value=_Answer()):
            return pexels_provider.search_videos("무릎")

    def _video(self, **extra):
        one = {
            "url": "https://www.pexels.com/video/a-woman-stretching-1/",
            "duration": 12,
            "video_files": [{"link": "v.mp4", "width": 1080, "height": 1920}],
        }
        one.update(extra)

        return one

    def test_the_preview_comes_through(self):
        found = self._search([self._video(image="https://x/y-z-1.jpeg")])

        self.assertEqual(found[0]["preview_url"], "https://x/y-z-1.jpeg")

    def test_a_response_without_it_says_none(self):
        found = self._search([self._video()])

        self.assertIsNone(found[0]["preview_url"])

    def test_the_rest_of_the_candidate_is_unchanged(self):
        found = self._search([self._video(image="https://x/y.jpeg")])[0]

        self.assertEqual(found["source"], "pexels_video")
        self.assertEqual(found["duration"], 12)
        self.assertEqual(found["download_url"], "v.mp4")
        self.assertEqual(found["width"], 1080)
        self.assertEqual(found["height"], 1920)
        self.assertEqual(found["alt"], "")
        self.assertEqual(found["query"], "무릎")


if __name__ == "__main__":
    unittest.main()
