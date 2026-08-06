"""
Sprint77 - Asset Observatory.

Sprint77 분석에서 Semantic Retrieval을 기각한 이유는 근거가 없어서가
아니라 **판단할 데이터가 없어서**였다. 실패한 스톡 scene에서 "더 나은
후보가 후보 풀에 있었는가"를 물었는데, 후보 풀을 한 번도 저장한 적이
없었다.

이 모듈은 그것을 남긴다. 기능을 더하지 않는다 - 이미 받아 놓은 Pexels
응답을 적을 뿐이라 Gemini도 Imagen도 늘지 않는다.

가장 중요한 계약은 "관측이 생산을 바꾸지 않는다"이다. Sprint66에서
같은 실수를 한 적이 있다 - 측정 결과를 project_data에 담아 두었더니
_save_script()가 그것까지 script.json에 써서, 플래그를 켜는 것만으로
생성 산출물의 바이트가 달라졌다(실측 +1,277자).
"""

import json
import os
import sys
import threading
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_observatory as observatory


def _candidate(alt="a bowl of oatmeal", source="pexels_image", **overrides):
    candidate = {
        "source": source,
        "alt": alt,
        "source_url": "https://www.pexels.com/photo/oatmeal-1/",
        "download_url": "https://images.pexels.com/a.jpg",
        "width": 1080,
        "height": 1920,
    }
    candidate.update(overrides)
    return candidate


class TestSessionLifecycle(unittest.TestCase):
    """세션 밖의 기록은 조용히 버린다.

    integrate_asset은 파이프라인 밖에서도 불린다(테스트, 라우터).
    거기서 전역 상태에 쌓이면 다음 세션이 남의 데이터를 물려받는다.
    """

    def tearDown(self):
        observatory.abandon()

    def test_recording_outside_a_session_is_dropped(self):
        observatory.abandon()

        observatory.record_search(1, "oatmeal", "pexels_image",
                                  cache_hit=False, result_count=3)

        self.assertEqual(observatory.snapshot(), {})

    def test_a_session_starts_empty(self):
        observatory.start()

        self.assertEqual(observatory.snapshot(), {})

    def test_starting_again_discards_the_previous_session(self):
        observatory.start()
        observatory.record_search(1, "q", "pexels_image",
                                  cache_hit=False, result_count=1)

        observatory.start()

        self.assertEqual(observatory.snapshot(), {})


class TestRecording(unittest.TestCase):

    def setUp(self):
        observatory.start()
        self.addCleanup(observatory.abandon)

    def test_a_search_records_query_provider_and_cache(self):
        observatory.record_search(
            4, "ceramic bowl oatmeal", "pexels_image",
            cache_hit=True, result_count=5,
        )

        entry = observatory.snapshot()[4]["searches"][0]

        self.assertEqual(entry["query"], "ceramic bowl oatmeal")
        self.assertEqual(entry["provider"], "pexels_image")
        self.assertTrue(entry["cache_hit"])
        self.assertEqual(entry["result_count"], 5)

    def test_query_expansion_is_recorded_in_order(self):
        """0건이면 표현을 넓혀 다시 시도한다. 무엇을 몇 번 시도했고
        어디서 결과가 나왔는지가 남아야 한다."""

        observatory.record_search(4, "narrow specific query", "pexels_image",
                                  cache_hit=False, result_count=0)
        observatory.record_search(4, "broader query", "pexels_image",
                                  cache_hit=False, result_count=4)

        searches = observatory.snapshot()[4]["searches"]

        self.assertEqual([s["query"] for s in searches],
                         ["narrow specific query", "broader query"])
        self.assertEqual([s["result_count"] for s in searches], [0, 4])

    def test_ranking_records_every_candidate_with_its_score(self):
        candidates = [
            _candidate(alt="a red sports car"),
            _candidate(alt="a bowl of oatmeal with blueberries"),
        ]
        scene = {"scene": 4, "subject": "a bowl of oatmeal with blueberries"}

        observatory.record_ranking(
            4, scene, candidates, chosen=candidates[1],
            scores=[0.10, 1.44],
        )

        recorded = observatory.snapshot()[4]["candidates"]

        self.assertEqual(len(recorded), 2)
        self.assertEqual(recorded[1]["alt"],
                         "a bowl of oatmeal with blueberries")
        self.assertTrue(recorded[1]["selected"])
        self.assertFalse(recorded[0]["selected"])

    def test_every_field_needed_to_recompute_the_ranking_is_kept(self):
        """"선택 과정 100% 재현 가능"의 실질.

        나중에 다른 순위 방식을 시험하려면 후보의 원본 신호가 그대로
        있어야 한다. 점수만 남기면 재현이 아니라 기록일 뿐이다.
        """

        candidate = _candidate(
            alt="a bowl", source="pexels_video", duration=8,
            width=1080, height=1920,
        )
        scene = {"scene": 4, "subject": "a bowl"}

        observatory.record_ranking(4, scene, [candidate],
                                   chosen=candidate, scores=[1.0])

        recorded = observatory.snapshot()[4]["candidates"][0]

        for field in ("provider", "alt", "slug", "duration",
                      "width", "height", "source_url"):
            with self.subTest(field=field):
                self.assertIn(field, recorded)

    def test_the_slug_is_extracted_from_the_url(self):
        candidate = _candidate(
            source_url="https://www.pexels.com/photo/bowl-of-oatmeal-123/",
        )
        observatory.record_ranking(4, {"scene": 4}, [candidate],
                                   chosen=candidate, scores=[1.0])

        self.assertEqual(
            observatory.snapshot()[4]["candidates"][0]["slug"],
            "bowl of oatmeal 123",
        )

    def test_the_scene_terms_used_for_matching_are_kept(self):
        scene = {"scene": 4, "subject": "a ceramic bowl of oatmeal",
                 "action": "on a table"}

        observatory.record_ranking(4, scene, [_candidate()],
                                   chosen=None, scores=[0.0])

        terms = observatory.snapshot()[4]["scene_terms"]

        self.assertIn("oatmeal", terms)
        self.assertIn("ceramic", terms)

    def test_the_selection_reason_is_human_readable(self):
        candidates = [_candidate(alt="a bowl of oatmeal")]

        observatory.record_ranking(4, {"scene": 4, "subject": "oatmeal bowl"},
                                   candidates, chosen=candidates[0],
                                   scores=[1.2])

        reason = observatory.snapshot()[4]["selection_reason"]

        self.assertTrue(reason)
        self.assertIsInstance(reason, str)

    def test_no_candidates_is_recorded_as_a_fallback(self):
        observatory.record_ranking(4, {"scene": 4}, [], chosen=None, scores=[])

        entry = observatory.snapshot()[4]

        self.assertEqual(entry["candidates"], [])
        self.assertIn("후보", entry["selection_reason"])

    def test_the_final_asset_is_recorded(self):
        observatory.record_outcome(
            4, provider="pexels_image",
            asset_path="/p/images/scene4.png",
        )

        entry = observatory.snapshot()[4]

        self.assertEqual(entry["final_provider"], "pexels_image")
        self.assertEqual(entry["final_asset"], "/p/images/scene4.png")


class TestThreadSafety(unittest.TestCase):
    """collect_assets는 scene마다 스레드 3개로 병렬 실행된다."""

    def setUp(self):
        observatory.start()
        self.addCleanup(observatory.abandon)

    def test_parallel_scenes_do_not_lose_records(self):
        def record(scene_number):
            for _ in range(20):
                observatory.record_search(
                    scene_number, f"q{scene_number}", "pexels_image",
                    cache_hit=False, result_count=1,
                )

        threads = [
            threading.Thread(target=record, args=(n,)) for n in range(1, 7)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        snapshot = observatory.snapshot()

        self.assertEqual(sorted(snapshot), [1, 2, 3, 4, 5, 6])
        for number in range(1, 7):
            self.assertEqual(len(snapshot[number]["searches"]), 20)


class TestWriting(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name
        observatory.start()
        self.addCleanup(observatory.abandon)

    def test_the_file_is_written_with_scenes_in_order(self):
        for number in (6, 1, 4):
            observatory.record_search(number, "q", "pexels_image",
                                      cache_hit=False, result_count=1)

        observatory.write(self.project)

        path = os.path.join(self.project, observatory.OBSERVATORY_FILENAME)
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)

        self.assertEqual([s["scene"] for s in payload["scenes"]], [1, 4, 6])

    def test_a_write_failure_never_breaks_the_pipeline(self):
        """Sprint73에서 세운 원칙 - 관측 산출물의 기록 실패가 영상을
        버릴 이유는 없다."""

        observatory.record_search(1, "q", "pexels_image",
                                  cache_hit=False, result_count=1)

        # 존재하지 않는 경로
        observatory.write(os.path.join(self.project, "no", "such", "dir"))

    def test_an_empty_session_still_writes_a_file(self):
        """스톡을 한 번도 쓰지 않은 영상도 그 사실이 기록이다."""

        observatory.write(self.project)

        self.assertTrue(os.path.exists(
            os.path.join(self.project, observatory.OBSERVATORY_FILENAME)
        ))

    def test_the_cache_summary_is_written(self):
        observatory.record_search(1, "q", "pexels_image",
                                  cache_hit=False, result_count=1)
        observatory.record_search(1, "q", "pexels_image",
                                  cache_hit=True, result_count=1)

        observatory.write(self.project)

        with open(
            os.path.join(self.project, observatory.OBSERVATORY_FILENAME),
            encoding="utf-8",
        ) as f:
            payload = json.load(f)

        self.assertEqual(payload["cache"]["hits"], 1)
        self.assertEqual(payload["cache"]["misses"], 1)


class TestObservationDoesNotChangeProduction(unittest.TestCase):
    """이 Epic의 가장 중요한 계약.

    Sprint66에서 같은 실수를 했다 - 측정 결과를 project_data에 담아
    두었더니 _save_script()가 script.json에 써서, 플래그를 켜는 것만으로
    생성 산출물이 +1,277자 달라졌다. 관측은 별도 파일로만 나간다.
    """

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name
        os.makedirs(os.path.join(self.project, "images"), exist_ok=True)
        self.addCleanup(observatory.abandon)

    def _integrate(self, recording):
        from unittest.mock import patch
        from app.services import asset_integration_service

        observatory.start() if recording else observatory.abandon()

        scene = {
            "scene": 2,
            "subject": "a ceramic bowl of oatmeal",
            "image_prompt": "a ceramic bowl of oatmeal",
            "visual_type": "real",
        }

        def fake_download(candidate, staging_path):
            with open(staging_path, "wb") as f:
                f.write(b"STOCK")
            return {
                "source": "pexels_image",
                "local_path": staging_path,
                "metadata": {"query": "oatmeal"},
            }

        with patch.object(
            asset_integration_service, "get_candidates",
            return_value=[_candidate()],
        ), patch.object(
            asset_integration_service, "download_candidate",
            side_effect=fake_download,
        ):
            return asset_integration_service.integrate_asset(
                scene, self.project,
            )

    def test_the_enriched_scene_has_the_same_keys_either_way(self):
        without = self._integrate(recording=False)
        with_recording = self._integrate(recording=True)

        self.assertEqual(sorted(without), sorted(with_recording))

    def test_no_observatory_field_leaks_into_the_scene(self):
        enriched = self._integrate(recording=True)

        for key in enriched:
            with self.subTest(key=key):
                self.assertNotIn("observator", key.lower())
                self.assertNotIn("candidates", key.lower())

    def test_the_selected_provider_is_the_same_either_way(self):
        self.assertEqual(
            self._integrate(recording=False)["provider"],
            self._integrate(recording=True)["provider"],
        )


class TestImagenOnlyScenesAreLegible(unittest.TestCase):
    """검색이 일어나지 않은 scene도 그 사실이 기록이어야 한다.

    실측에서 6개 scene 중 4개가 Imagen 우선 경로라 검색이 0회였고,
    selection_reason이 None으로 남았다. "검색이 없었다"와 "검색이
    실패했다"가 구분되지 않으면 사후 분석에서 잘못 읽힌다.
    """

    def setUp(self):
        observatory.start()
        self.addCleanup(observatory.abandon)

    def test_a_scene_that_never_searched_says_so(self):
        observatory.record_outcome(1, provider="ai_image",
                                   asset_path="/p/images/scene1.png")

        reason = observatory.snapshot()[1]["selection_reason"]

        self.assertIn("Imagen", reason)

    def test_a_recorded_ranking_reason_is_not_overwritten(self):
        candidates = [_candidate()]
        observatory.record_search(2, "q", "pexels_image",
                                  cache_hit=False, result_count=1)
        observatory.record_ranking(2, {"scene": 2, "subject": "oatmeal"},
                                   candidates, chosen=candidates[0],
                                   scores=[1.2])
        observatory.record_outcome(2, provider="pexels_image",
                                   asset_path="/p/images/scene2.png")

        self.assertNotIn("Imagen", observatory.snapshot()[2]["selection_reason"])


if __name__ == "__main__":
    unittest.main()
