import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_selector


PROMPT = "Ultra realistic photo of a tired woman in a messy office."


class TestAssetSelector(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.output_file = os.path.join(self._tmp_dir.name, "scene1.png")

    def _write_fake_cached_asset(self, content=b"fake bytes"):
        cached_path = os.path.join(self._tmp_dir.name, "cached_asset.jpg")
        with open(cached_path, "wb") as f:
            f.write(content)
        return cached_path, {"source": "pexels_video", "query": "tired woman"}

    @patch("app.services.asset_selector.generate_image")
    @patch("app.services.asset_selector.asset_cache.save_to_cache")
    @patch("app.services.asset_selector.asset_cache.get_cached", return_value=None)
    @patch("app.services.asset_selector._download", return_value=b"video bytes")
    @patch("app.providers.pixabay_provider.search_images")
    @patch("app.providers.pixabay_provider.search_videos")
    @patch("app.providers.pexels_provider.search_photos")
    @patch("app.providers.pexels_provider.search_videos")
    def test_first_provider_success_stops_chain(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_download,
        mock_get_cached,
        mock_save_to_cache,
        mock_generate_image,
    ):
        mock_pexels_video.return_value = [
            {"source": "pexels_video", "download_url": "video.mp4", "source_url": "u", "width": 1080, "height": 1920, "query": "tired woman"}
        ]

        cached_path = os.path.join(self._tmp_dir.name, "asset.mp4")
        with open(cached_path, "wb") as f:
            f.write(b"video bytes")
        mock_save_to_cache.return_value = cached_path

        result = asset_selector.select_asset(PROMPT, self.output_file)

        self.assertEqual(result["source"], "pexels_video")
        mock_pexels_photo.assert_not_called()
        mock_pixabay_video.assert_not_called()
        mock_pixabay_image.assert_not_called()
        mock_generate_image.assert_not_called()
        self.assertTrue(os.path.exists(self.output_file))
        with open(self.output_file, "rb") as f:
            self.assertEqual(f.read(), b"video bytes")

    @patch("app.services.asset_selector.generate_image")
    @patch("app.services.asset_selector.asset_cache.save_to_cache")
    @patch("app.services.asset_selector.asset_cache.get_cached", return_value=None)
    @patch("app.services.asset_selector._download", return_value=b"photo bytes")
    @patch("app.providers.pixabay_provider.search_images")
    @patch("app.providers.pixabay_provider.search_videos")
    @patch("app.providers.pexels_provider.search_photos")
    @patch("app.providers.pexels_provider.search_videos")
    def test_falls_through_when_first_provider_empty(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_download,
        mock_get_cached,
        mock_save_to_cache,
        mock_generate_image,
    ):
        mock_pexels_video.return_value = []
        mock_pexels_photo.return_value = [
            {"source": "pexels_image", "download_url": "photo.jpg", "source_url": "u", "width": 1080, "height": 1920, "query": "tired woman"}
        ]

        cached_path = os.path.join(self._tmp_dir.name, "asset.jpg")
        with open(cached_path, "wb") as f:
            f.write(b"photo bytes")
        mock_save_to_cache.return_value = cached_path

        result = asset_selector.select_asset(PROMPT, self.output_file)

        self.assertEqual(result["source"], "pexels_image")
        mock_pixabay_video.assert_not_called()
        mock_pixabay_image.assert_not_called()
        mock_generate_image.assert_not_called()

    @patch("app.services.asset_selector.generate_image")
    @patch("app.providers.pixabay_provider.search_images", return_value=[])
    @patch("app.providers.pixabay_provider.search_videos", return_value=[])
    @patch("app.providers.pexels_provider.search_photos", return_value=[])
    @patch("app.providers.pexels_provider.search_videos", return_value=[])
    def test_falls_back_to_ai_image_when_all_empty(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_generate_image,
    ):
        mock_generate_image.return_value = self.output_file

        result = asset_selector.select_asset(PROMPT, self.output_file)

        self.assertEqual(result["source"], "ai_image")
        self.assertEqual(result["local_path"], self.output_file)
        mock_generate_image.assert_called_once()

    @patch("app.services.asset_selector.generate_image")
    @patch("app.providers.pixabay_provider.search_images", return_value=[])
    @patch("app.providers.pixabay_provider.search_videos", return_value=[])
    @patch("app.providers.pexels_provider.search_photos", return_value=[])
    @patch("app.providers.pexels_provider.search_videos", side_effect=Exception("network error"))
    def test_provider_exception_falls_through_to_next(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_generate_image,
    ):
        mock_generate_image.return_value = self.output_file

        result = asset_selector.select_asset(PROMPT, self.output_file)

        # pexels_video raised, but the chain should continue rather than crash
        self.assertEqual(result["source"], "ai_image")
        mock_pexels_photo.assert_called_once()

    @patch("app.services.asset_selector.generate_image")
    @patch("app.services.asset_selector._download")
    @patch("app.providers.pexels_provider.search_videos")
    def test_cached_asset_reused_without_download(
        self,
        mock_pexels_video,
        mock_download,
        mock_generate_image,
    ):
        mock_pexels_video.return_value = [
            {"source": "pexels_video", "download_url": "video.mp4", "source_url": "u", "width": 1080, "height": 1920, "query": "tired woman"}
        ]

        cached_path, meta = self._write_fake_cached_asset(b"cached bytes")

        with patch(
            "app.services.asset_selector.asset_cache.get_cached",
            return_value=(cached_path, meta),
        ):
            result = asset_selector.select_asset(PROMPT, self.output_file)

        mock_download.assert_not_called()
        self.assertEqual(result["source"], "pexels_video")
        with open(self.output_file, "rb") as f:
            self.assertEqual(f.read(), b"cached bytes")

    @patch("app.services.asset_selector.generate_image")
    @patch("app.providers.pixabay_provider.search_images")
    @patch("app.providers.pixabay_provider.search_videos")
    @patch("app.providers.pexels_provider.search_photos")
    @patch("app.providers.pexels_provider.search_videos")
    def test_empty_query_skips_search_and_uses_ai_fallback(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_generate_image,
    ):
        mock_generate_image.return_value = self.output_file

        # 전부 상투어라서 extract_search_query가 빈 문자열을 반환하는 프롬프트
        filler_only_prompt = "Ultra realistic, cinematic photography, no text, no watermark."

        result = asset_selector.select_asset(filler_only_prompt, self.output_file)

        mock_pexels_video.assert_not_called()
        mock_pexels_photo.assert_not_called()
        mock_pixabay_video.assert_not_called()
        mock_pixabay_image.assert_not_called()
        self.assertEqual(result["source"], "ai_image")


class TestGetCandidates(unittest.TestCase):
    """Sprint30 - get_candidates()는 select_asset()과 별개의 새 함수이며,
    기존 select_asset() 테스트는 위에서 전혀 변경하지 않았습니다."""

    @patch("app.providers.pixabay_provider.search_images")
    @patch("app.providers.pixabay_provider.search_videos")
    @patch("app.providers.pexels_provider.search_photos")
    @patch("app.providers.pexels_provider.search_videos")
    def test_collects_results_from_every_provider(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
    ):
        mock_pexels_video.return_value = [
            {"source": "pexels_video", "download_url": "v.mp4", "query": "q"}
        ]
        mock_pexels_photo.return_value = [
            {"source": "pexels_image", "download_url": "p.jpg", "query": "q"}
        ]
        mock_pixabay_video.return_value = [
            {"source": "pixabay_video", "download_url": "pv.mp4", "query": "q"}
        ]
        mock_pixabay_image.return_value = [
            {"source": "pixabay_image", "download_url": "pi.jpg", "query": "q"}
        ]

        candidates = asset_selector.get_candidates(PROMPT)

        # 첫 provider에서 멈추지 않고 4개 provider 결과 모두 수집
        sources = [c["source"] for c in candidates]
        self.assertEqual(
            sources,
            ["pexels_video", "pexels_image", "pixabay_video", "pixabay_image"],
        )

    @patch("app.providers.pixabay_provider.search_images", return_value=[])
    @patch("app.providers.pixabay_provider.search_videos", return_value=[])
    @patch("app.providers.pexels_provider.search_photos", return_value=[])
    @patch("app.providers.pexels_provider.search_videos", side_effect=Exception("boom"))
    def test_failed_provider_is_skipped_others_still_collected(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
    ):
        mock_pexels_photo.return_value = [
            {"source": "pexels_image", "download_url": "p.jpg", "query": "q"}
        ]

        candidates = asset_selector.get_candidates(PROMPT)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source"], "pexels_image")

    @patch("app.providers.pixabay_provider.search_images", return_value=[])
    @patch("app.providers.pixabay_provider.search_videos", return_value=[])
    @patch("app.providers.pexels_provider.search_photos", return_value=[])
    @patch("app.providers.pexels_provider.search_videos", return_value=[])
    def test_search_query_override_is_used_when_provided(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
    ):
        """
        Sprint100-4 버그 수정 - search_query_override가 실제 provider
        search_fn 호출의 query 인자로 전달되는지 확인한다(이전에는
        파라미터만 있고 함수 본문에서 읽지 않아 항상 extract_search_
        query(image_prompt)로 덮어써졌다).
        """

        asset_selector.get_candidates(
            PROMPT, search_query_override="healthy vegetables potassium diet",
        )

        mock_pexels_video.assert_called_once_with("healthy vegetables potassium diet")
        mock_pexels_photo.assert_called_once_with("healthy vegetables potassium diet")
        mock_pixabay_video.assert_called_once_with("healthy vegetables potassium diet")
        mock_pixabay_image.assert_called_once_with("healthy vegetables potassium diet")

    @patch("app.providers.pixabay_provider.search_images", return_value=[])
    @patch("app.providers.pixabay_provider.search_videos", return_value=[])
    @patch("app.providers.pexels_provider.search_photos", return_value=[])
    @patch("app.providers.pexels_provider.search_videos", return_value=[])
    def test_no_override_falls_back_to_generate_semantic_primary_query(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
    ):
        """
        Sprint103 후속 Hotfix - override를 넘기지 않으면(기본값 None)
        generate_semantic_primary_query(image_prompt) 결과를 쓴다.
        이전에는 extract_search_query()(위치 기반 8단어 절단)로
        폴백했다 - motion_contract가 없는 scene(라이브 서버의
        ENABLE_MOTION_CONTRACT=False 상태에서는 전부 여기 해당)은
        전부 이 fallback을 타므로, 실제 프로덕션 검색 경로가 여전히
        구 알고리즘을 쓰고 있었다(Sprint103 배선 검토 분석 결과).
        """

        from app.services.search_query_extractor import (
            generate_semantic_primary_query,
        )

        asset_selector.get_candidates(PROMPT)

        expected_query = generate_semantic_primary_query(PROMPT)
        mock_pexels_video.assert_called_once_with(expected_query)

    @patch("app.providers.pixabay_provider.search_images", return_value=[])
    @patch("app.providers.pixabay_provider.search_videos", return_value=[])
    @patch("app.providers.pexels_provider.search_photos", return_value=[])
    @patch("app.providers.pexels_provider.search_videos", return_value=[])
    def test_no_override_camera_meta_words_do_not_survive(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
    ):
        """
        Sprint103 후속 Hotfix 회귀 방지 - 카메라 앵글이 문장 앞에 오는
        image_prompt에서, fallback 검색어가 더 이상 위치 기반 절단으로
        카메라 메타 어휘에 예산을 뺏기지 않는지 확인한다.
        """

        camera_first_prompt = (
            "high angle shot showing an artery gradually narrowing due "
            "to plaque buildup"
        )

        asset_selector.get_candidates(camera_first_prompt)

        used_query = mock_pexels_video.call_args.args[0]
        for camera_word in ["high", "angle", "shot", "showing"]:
            self.assertNotIn(camera_word, used_query.split())
        self.assertIn("plaque", used_query)
        self.assertIn("buildup", used_query)

    @patch("app.providers.pixabay_provider.search_images", return_value=[])
    @patch("app.providers.pixabay_provider.search_videos", return_value=[])
    @patch("app.providers.pexels_provider.search_photos", return_value=[])
    @patch("app.providers.pexels_provider.search_videos", return_value=[])
    def test_all_empty_returns_empty_list(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
    ):
        self.assertEqual(asset_selector.get_candidates(PROMPT), [])

    @patch("app.providers.pexels_provider.search_videos")
    def test_candidates_without_download_url_are_excluded(self, mock_pexels_video):
        mock_pexels_video.return_value = [
            {"source": "pexels_video", "download_url": None, "query": "q"},
            {"source": "pexels_video", "download_url": "ok.mp4", "query": "q"},
        ]

        with patch("app.providers.pexels_provider.search_photos", return_value=[]), \
             patch("app.providers.pixabay_provider.search_videos", return_value=[]), \
             patch("app.providers.pixabay_provider.search_images", return_value=[]):

            candidates = asset_selector.get_candidates(PROMPT)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["download_url"], "ok.mp4")

    @patch("app.providers.pexels_provider.search_videos")
    def test_respects_max_per_provider_limit(self, mock_pexels_video):
        mock_pexels_video.return_value = [
            {"source": "pexels_video", "download_url": f"v{i}.mp4", "query": "q"}
            for i in range(5)
        ]

        with patch("app.providers.pexels_provider.search_photos", return_value=[]), \
             patch("app.providers.pixabay_provider.search_videos", return_value=[]), \
             patch("app.providers.pixabay_provider.search_images", return_value=[]):

            candidates = asset_selector.get_candidates(PROMPT, max_per_provider=2)

        self.assertEqual(len(candidates), 2)

    def test_empty_query_returns_empty_list_without_calling_providers(self):
        # Sprint103 후속 Hotfix - 원래 이 테스트에 쓰던 프롬프트("Ultra
        # realistic, cinematic photography, no text, no watermark.")는
        # generate_semantic_primary_query()에서는 더 이상 빈 문자열이
        # 아니다("photography"가 남는다) - style_boilerplate_stripper가
        # "cinematic"만 먼저 제거해버려서, search_query_extractor의
        # FILLER_PHRASES에 있는 "cinematic photography"(2단어 결합)가
        # 더 이상 매칭되지 않기 때문(실측 확인됨, Sprint103 자체
        # 로직은 이번 Hotfix 범위 밖이라 수정하지 않는다). 이 테스트가
        # 검증하려는 것(빈 쿼리면 provider를 아예 안 부른다)은 여전히
        # 유효한 동작이므로, 새 함수에서도 빈 문자열이 나오는 프롬프트로
        # 바꿔 같은 분기를 계속 커버한다.
        filler_only_prompt = "Ultra realistic, no text, no watermark, no logo."

        with patch("app.providers.pexels_provider.search_videos") as mock_video:
            candidates = asset_selector.get_candidates(filler_only_prompt)
            mock_video.assert_not_called()

        self.assertEqual(candidates, [])

    def test_search_fn_still_called_even_when_no_api_key(self):
        # Sprint32: 로그 분류만 추가되었을 뿐, 실제 호출 흐름은 이전과
        # 동일하게 항상 search_fn을 호출해야 한다 (기존 mock 기반
        # 테스트들이 계속 통과하려면 이 동작이 반드시 유지되어야 함).
        with patch(
            "app.providers.pexels_provider.has_api_key", return_value=False,
        ), patch(
            "app.providers.pexels_provider.search_videos",
        ) as mock_video, patch(
            "app.providers.pexels_provider.search_photos", return_value=[],
        ), patch(
            "app.providers.pixabay_provider.search_videos", return_value=[],
        ), patch(
            "app.providers.pixabay_provider.search_images", return_value=[],
        ):
            mock_video.return_value = [
                {"source": "pexels_video", "download_url": "v.mp4", "query": "q"}
            ]

            candidates = asset_selector.get_candidates(PROMPT)

        mock_video.assert_called_once()
        self.assertEqual(len(candidates), 1)

    @patch("app.providers.pixabay_provider.has_api_key", return_value=False)
    @patch("app.providers.pexels_provider.has_api_key", return_value=False)
    @patch("app.providers.pixabay_provider.search_images")
    @patch("app.providers.pixabay_provider.search_videos")
    @patch("app.providers.pexels_provider.search_photos")
    @patch("app.providers.pexels_provider.search_videos")
    def test_final_log_distinguishes_all_missing_keys(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_pexels_has_key,
        mock_pixabay_has_key,
    ):
        for mock_fn in (
            mock_pexels_video, mock_pexels_photo,
            mock_pixabay_video, mock_pixabay_image,
        ):
            mock_fn.side_effect = Exception("API Key 없음 시뮬레이션")

        with patch("builtins.print") as mock_print:
            candidates = asset_selector.get_candidates(PROMPT)
            messages = " ".join(str(c.args[0]) for c in mock_print.call_args_list)

        self.assertEqual(candidates, [])
        self.assertIn("모든 stock provider에 API Key가 없어", messages)

    @patch("app.providers.pixabay_provider.has_api_key", return_value=True)
    @patch("app.providers.pexels_provider.has_api_key", return_value=True)
    @patch("app.providers.pixabay_provider.search_images", return_value=[])
    @patch("app.providers.pixabay_provider.search_videos", return_value=[])
    @patch("app.providers.pexels_provider.search_photos", return_value=[])
    @patch("app.providers.pexels_provider.search_videos", return_value=[])
    def test_final_log_distinguishes_keys_present_but_no_results(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_pexels_has_key,
        mock_pixabay_has_key,
    ):
        with patch("builtins.print") as mock_print:
            candidates = asset_selector.get_candidates(PROMPT)
            messages = " ".join(str(c.args[0]) for c in mock_print.call_args_list)

        self.assertEqual(candidates, [])
        self.assertIn("API Key는 있었지만 유효한 후보를 찾지 못해", messages)

    @patch("app.providers.pexels_provider.has_api_key", return_value=True)
    @patch("app.providers.pexels_provider.search_videos")
    def test_final_log_reports_success_when_candidates_found(
        self, mock_pexels_video, mock_has_key,
    ):
        mock_pexels_video.return_value = [
            {"source": "pexels_video", "download_url": "v.mp4", "query": "q"}
        ]

        with patch("app.providers.pexels_provider.search_photos", return_value=[]), \
             patch("app.providers.pixabay_provider.search_videos", return_value=[]), \
             patch("app.providers.pixabay_provider.search_images", return_value=[]), \
             patch("builtins.print") as mock_print:

            candidates = asset_selector.get_candidates(PROMPT)
            messages = " ".join(str(c.args[0]) for c in mock_print.call_args_list)

        self.assertEqual(len(candidates), 1)
        self.assertIn("후보 1건 수집 완료", messages)


class TestDownloadCandidate(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.output_file = os.path.join(self._tmp_dir.name, "scene1.png")

    @patch("app.services.asset_selector.asset_cache.save_to_cache")
    @patch("app.services.asset_selector.asset_cache.get_cached", return_value=None)
    @patch("app.services.asset_selector._download", return_value=b"fresh bytes")
    def test_downloads_and_saves_new_candidate(
        self, mock_download, mock_get_cached, mock_save_to_cache,
    ):
        cached_path = os.path.join(self._tmp_dir.name, "asset.jpg")
        with open(cached_path, "wb") as f:
            f.write(b"fresh bytes")
        mock_save_to_cache.return_value = cached_path

        candidate = {
            "source": "pexels_image", "download_url": "img.jpg",
            "source_url": "u", "width": 1080, "height": 1920, "query": "q",
        }

        result = asset_selector.download_candidate(candidate, self.output_file)

        self.assertEqual(result["source"], "pexels_image")
        mock_download.assert_called_once_with("img.jpg")
        with open(self.output_file, "rb") as f:
            self.assertEqual(f.read(), b"fresh bytes")

    @patch("app.services.asset_selector._download")
    def test_reuses_cached_asset_without_downloading(self, mock_download):
        cached_path = os.path.join(self._tmp_dir.name, "cached.jpg")
        with open(cached_path, "wb") as f:
            f.write(b"cached bytes")

        candidate = {
            "source": "pexels_image", "download_url": "img.jpg", "query": "q",
        }

        with patch(
            "app.services.asset_selector.asset_cache.get_cached",
            return_value=(cached_path, {"source": "pexels_image"}),
        ):
            result = asset_selector.download_candidate(candidate, self.output_file)

        mock_download.assert_not_called()
        self.assertEqual(result["local_path"], self.output_file)
        with open(self.output_file, "rb") as f:
            self.assertEqual(f.read(), b"cached bytes")


if __name__ == "__main__":
    unittest.main()
