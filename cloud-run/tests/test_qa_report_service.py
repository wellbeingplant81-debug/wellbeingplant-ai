import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import qa_report_service
from app.services.qa_report_service import (
    get_real_durations,
    load_quality_summary,
    build_qa_report,
    format_report,
)


class RealProjectFixture(unittest.TestCase):
    """실제 ffmpeg로 짧은 mp3/mp4 fixture를 만들어 진짜 project_path
    구조에 대해 검증하는 통합 테스트 베이스."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_path = os.path.join(self.tmp_dir, "project")
        os.makedirs(os.path.join(self.project_path, "audio", "scenes"))
        os.makedirs(os.path.join(self.project_path, "video"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_audio(self, path, seconds):
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", f"{seconds:.2f}",
             "-i", "anullsrc=r=44100:cl=mono", "-c:a", "libmp3lame", path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def _make_video(self, path, seconds):
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", f"{seconds:.2f}",
             "-i", "color=c=black:s=320x240", "-c:v", "libx264", path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class TestGetRealDurations(RealProjectFixture):

    def test_reports_scene_and_total_durations(self):
        self._make_audio(os.path.join(self.project_path, "audio", "scenes", "scene1.mp3"), 3.0)
        self._make_audio(os.path.join(self.project_path, "audio", "scenes", "scene2.mp3"), 4.0)
        self._make_audio(os.path.join(self.project_path, "audio", "voice.mp3"), 7.0)
        self._make_audio(os.path.join(self.project_path, "audio", "final_audio.mp3"), 7.0)
        self._make_video(os.path.join(self.project_path, "video", "final_short.mp4"), 7.0)

        result = get_real_durations(self.project_path)

        self.assertEqual(len(result["scenes"]), 2)
        self.assertAlmostEqual(result["scenes"][0]["duration"], 3.0, delta=0.1)
        self.assertAlmostEqual(result["scenes"][1]["duration"], 4.0, delta=0.1)
        self.assertAlmostEqual(result["voice"], 7.0, delta=0.1)
        self.assertAlmostEqual(result["final_audio"], 7.0, delta=0.1)
        self.assertAlmostEqual(result["final_video"], 7.0, delta=0.1)

    def test_missing_files_are_none_not_error(self):
        result = get_real_durations(self.project_path)

        self.assertEqual(result["scenes"], [])
        self.assertIsNone(result["voice"])
        self.assertIsNone(result["final_audio"])
        self.assertIsNone(result["final_video"])

    def test_scenes_are_sorted_numerically(self):
        for i in [2, 10, 1]:
            self._make_audio(
                os.path.join(self.project_path, "audio", "scenes", f"scene{i}.mp3"), 1.0
            )

        result = get_real_durations(self.project_path)

        self.assertEqual([s["scene"] for s in result["scenes"]], [1, 2, 10])


class TestLoadQualitySummary(unittest.TestCase):

    def test_missing_quality_report_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertIsNone(load_quality_summary(tmp_dir))

    def test_extracts_passed_and_checks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report = {
                "technical_validation": {
                    "passed": True,
                    "checks": {
                        "video_duration": {"passed": True, "duration_seconds": 45.0},
                        "audio_video_sync": {"passed": True, "delta_ms": 5.0},
                    },
                    "blocking_failures": [],
                }
            }
            with open(os.path.join(tmp_dir, "quality_report.json"), "w", encoding="utf-8") as f:
                json.dump(report, f)

            summary = load_quality_summary(tmp_dir)

            self.assertTrue(summary["passed"])
            self.assertEqual(summary["blocking_failures"], [])
            self.assertTrue(summary["checks"]["video_duration"]["passed"])


class TestBuildQaReport(RealProjectFixture):

    def test_combines_durations_and_quality_summary(self):
        self._make_audio(os.path.join(self.project_path, "audio", "scenes", "scene1.mp3"), 5.0)
        self._make_audio(os.path.join(self.project_path, "audio", "voice.mp3"), 5.0)
        self._make_audio(os.path.join(self.project_path, "audio", "final_audio.mp3"), 5.0)
        self._make_video(os.path.join(self.project_path, "video", "final_short.mp4"), 5.0)

        report = build_qa_report(self.project_path)

        self.assertIn("durations", report)
        self.assertIn("quality", report)
        self.assertIn("target_range_ok", report)

    def test_target_range_ok_true_when_within_43_47(self):
        self._make_audio(os.path.join(self.project_path, "audio", "voice.mp3"), 45.0)
        self._make_video(os.path.join(self.project_path, "video", "final_short.mp4"), 45.0)

        report = build_qa_report(self.project_path)

        self.assertTrue(report["target_range_ok"])

    def test_target_range_ok_false_when_outside_43_47(self):
        self._make_audio(os.path.join(self.project_path, "audio", "voice.mp3"), 30.0)
        self._make_video(os.path.join(self.project_path, "video", "final_short.mp4"), 30.0)

        report = build_qa_report(self.project_path)

        self.assertFalse(report["target_range_ok"])

    def test_format_report_does_not_raise(self):
        self._make_audio(os.path.join(self.project_path, "audio", "voice.mp3"), 45.0)

        report = build_qa_report(self.project_path)
        text = format_report(report)

        self.assertIsInstance(text, str)
        self.assertIn(self.project_path, text)


def _write_script(project_path, scenes):
    with open(os.path.join(project_path, "script.json"), "w", encoding="utf-8") as f:
        json.dump({"scenes": scenes}, f)


def _write_png(path, seed):
    """
    seed로 결정되는 8x8 랜덤 노이즈 이미지를 저장한다. 단색 이미지는
    average_hash()의 평균 임계값과 모든 픽셀이 항상 같은 쪽에 걸려
    색상과 무관하게 전부 동일한 해시(전부 1비트)가 되는 퇴화 케이스라
    피한다 - 서로 다른 seed는 서로 다른 해시를, 같은 seed는 완전히
    동일한(바이트 단위) 파일을 만든다(exact-duplicate 테스트용).
    """
    import numpy as np

    os.makedirs(os.path.dirname(path), exist_ok=True)
    rng = np.random.default_rng(seed)
    array = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)
    Image.fromarray(array, mode="RGB").save(path)


def _write_scene_audio_placeholder(project_path, scene_number):
    """
    get_real_durations()는 glob으로 audio/scenes/sceneN.mp3의 존재
    여부부터 확인한 뒤에야 get_audio_duration()을 호출한다 - 이
    플레이스홀더 파일이 없으면 mock한 duration 값이 아예 조회되지
    않는다. 내용은 의미 없다(get_audio_duration을 mock하므로 실제로
    읽지 않음).
    """
    path = os.path.join(
        project_path, "audio", "scenes", f"scene{scene_number}.mp3",
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x00")


def _mock_duration_by_scene(durations_by_scene):
    """
    get_audio_duration(path)를 실제 ffprobe 없이 scene 번호 기반으로
    고정값을 반환하도록 mock한다. path에 "sceneN.mp3"가 없으면(scene
    오디오가 아닌 다른 파일) 0.0을 반환한다.
    """

    def _side_effect(path):
        match = re.search(r"scene(\d+)\.mp3$", path)
        if not match:
            return 0.0
        return durations_by_scene.get(int(match.group(1)), 0.0)

    return _side_effect


class TestBuildAssetIntelligenceSummary(unittest.TestCase):
    """
    Sprint64-5 - script.json의 scene별 assets/role을 읽어, 실제 이미지
    파일 중복 여부(asset_duplicate_detector)와 role 기반 기대 duration
    (asset_usage_planner)을 읽기 전용으로 리포트한다. 새로운 판정
    로직은 만들지 않고 Sprint64-1/64-3의 기존 함수를 그대로 재사용한다.
    """

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def _image_path(self, name):
        return os.path.join(self.project_path, "images", name)

    @patch("app.services.qa_report_service.get_audio_duration")
    def test_multi_asset_scene_with_valid_roles(self, mock_get_audio_duration):
        mock_get_audio_duration.side_effect = _mock_duration_by_scene({1: 10.0})
        _write_scene_audio_placeholder(self.project_path, 1)

        _write_png(self._image_path("scene1.png"), seed=1)
        _write_png(self._image_path("scene1_2.png"), seed=2)
        _write_png(self._image_path("scene1_3.png"), seed=3)
        _write_png(self._image_path("scene1_4.png"), seed=4)

        scene = {
            "scene": 1,
            "assets": [
                {"path": self._image_path("scene1.png"), "type": "image", "role": "environment"},
                {"path": self._image_path("scene1_2.png"), "type": "image", "role": "subject"},
                {"path": self._image_path("scene1_3.png"), "type": "image", "role": "detail"},
                {"path": self._image_path("scene1_4.png"), "type": "image", "role": "transition"},
            ],
        }
        _write_script(self.project_path, [scene])

        summary = qa_report_service.build_asset_intelligence_summary(self.project_path)

        self.assertEqual(len(summary), 1)
        entry = summary[0]
        self.assertEqual(entry["scene"], 1)
        self.assertEqual(entry["asset_count"], 4)
        self.assertEqual(
            entry["roles"], ["environment", "subject", "detail", "transition"],
        )
        self.assertEqual(entry["duplicates"], [])
        self.assertEqual(len(entry["expected_durations"]), 4)
        self.assertAlmostEqual(sum(entry["expected_durations"]), 10.0, places=1)
        # environment(가중치 1.2)가 transition(가중치 0.6)보다 길어야 한다.
        self.assertGreater(entry["expected_durations"][0], entry["expected_durations"][3])
        self.assertTrue(entry["role_validation"])

    @patch("app.services.qa_report_service.get_audio_duration")
    def test_duplicate_assets_are_reported(self, mock_get_audio_duration):
        mock_get_audio_duration.side_effect = _mock_duration_by_scene({1: 8.0})
        _write_scene_audio_placeholder(self.project_path, 1)

        # scene1.png와 scene1_2.png는 같은 seed로 만든 완전히 동일한
        # 이미지(정확 중복).
        _write_png(self._image_path("scene1.png"), seed=10)
        _write_png(self._image_path("scene1_2.png"), seed=10)
        _write_png(self._image_path("scene1_3.png"), seed=20)
        _write_png(self._image_path("scene1_4.png"), seed=30)

        scene = {
            "scene": 1,
            "assets": [
                {"path": self._image_path("scene1.png"), "role": "environment"},
                {"path": self._image_path("scene1_2.png"), "role": "subject"},
                {"path": self._image_path("scene1_3.png"), "role": "detail"},
                {"path": self._image_path("scene1_4.png"), "role": "transition"},
            ],
        }
        _write_script(self.project_path, [scene])

        summary = qa_report_service.build_asset_intelligence_summary(self.project_path)

        entry = summary[0]
        self.assertEqual(len(entry["duplicates"]), 1)
        self.assertEqual(entry["duplicates"][0]["index"], 1)
        self.assertEqual(entry["duplicates"][0]["duplicate_of_index"], 0)
        self.assertEqual(entry["duplicates"][0]["reason"], "exact")

    def test_legacy_scene_without_assets_field_is_handled(self):
        scene = {
            "scene": 1,
            "narration": "n",
            "image_prompt": "p",
            "asset_path": "images/scene1.png",
        }
        _write_script(self.project_path, [scene])

        summary = qa_report_service.build_asset_intelligence_summary(self.project_path)

        self.assertEqual(len(summary), 1)
        entry = summary[0]
        self.assertEqual(entry["asset_count"], 0)
        self.assertEqual(entry["roles"], [])
        self.assertEqual(entry["duplicates"], [])
        self.assertEqual(entry["expected_durations"], [])
        self.assertTrue(entry["role_validation"])

    @patch("app.services.qa_report_service.get_audio_duration")
    def test_single_asset_without_role_is_handled(self, mock_get_audio_duration):
        mock_get_audio_duration.side_effect = _mock_duration_by_scene({1: 6.0})
        _write_scene_audio_placeholder(self.project_path, 1)

        _write_png(self._image_path("scene1.png"), seed=42)

        scene = {
            "scene": 1,
            "assets": [
                {"path": self._image_path("scene1.png"), "type": "image"},
            ],
        }
        _write_script(self.project_path, [scene])

        summary = qa_report_service.build_asset_intelligence_summary(self.project_path)

        entry = summary[0]
        self.assertEqual(entry["asset_count"], 1)
        self.assertEqual(entry["roles"], [None])
        self.assertEqual(entry["duplicates"], [])
        self.assertEqual(entry["expected_durations"], [6.0])
        # role이 전혀 없으면(하위 호환) 위반이 아니라 정상으로 취급한다.
        self.assertTrue(entry["role_validation"])

    @patch("app.services.qa_report_service.get_audio_duration")
    def test_role_validation_false_when_roles_out_of_order(self, mock_get_audio_duration):
        mock_get_audio_duration.side_effect = _mock_duration_by_scene({1: 8.0})
        _write_scene_audio_placeholder(self.project_path, 1)

        for name, seed in [
            ("scene1.png", 101), ("scene1_2.png", 102),
            ("scene1_3.png", 103), ("scene1_4.png", 104),
        ]:
            _write_png(self._image_path(name), seed=seed)

        # 순서가 뒤바뀐(잘못된) role 배치.
        scene = {
            "scene": 1,
            "assets": [
                {"path": self._image_path("scene1.png"), "role": "transition"},
                {"path": self._image_path("scene1_2.png"), "role": "detail"},
                {"path": self._image_path("scene1_3.png"), "role": "subject"},
                {"path": self._image_path("scene1_4.png"), "role": "environment"},
            ],
        }
        _write_script(self.project_path, [scene])

        summary = qa_report_service.build_asset_intelligence_summary(self.project_path)

        self.assertFalse(summary[0]["role_validation"])

    def test_missing_script_json_returns_empty_list(self):
        result = qa_report_service.build_asset_intelligence_summary(self.project_path)

        self.assertEqual(result, [])

    @patch("app.services.qa_report_service.get_audio_duration")
    def test_missing_audio_duration_skips_expected_durations_gracefully(
        self, mock_get_audio_duration,
    ):
        # scene 오디오 파일 자체가 없는 상황(파이프라인 중간 단계) -
        # get_real_durations()가 scene 목록에서 아예 빠뜨리므로,
        # expected_durations는 크래시 없이 빈 리스트여야 한다. role은
        # 이 테스트의 관심사가 아니므로 넣지 않는다(단일 asset에 role
        # 하나만 있으면 그 자체로 role_validation이 False가 되는 것이
        # 맞는 동작 - 별도 테스트에서 다룸).
        mock_get_audio_duration.side_effect = _mock_duration_by_scene({})

        _write_png(self._image_path("scene1.png"), seed=7)

        scene = {
            "scene": 1,
            "assets": [
                {"path": self._image_path("scene1.png")},
            ],
        }
        _write_script(self.project_path, [scene])

        summary = qa_report_service.build_asset_intelligence_summary(self.project_path)

        self.assertEqual(summary[0]["expected_durations"], [])
        self.assertTrue(summary[0]["role_validation"])


class TestBuildQaReportIncludesAssetIntelligence(unittest.TestCase):
    """
    build_qa_report()의 기존 반환 키(durations/quality/target_range_ok)
    는 전혀 바뀌지 않고, asset_intelligence 키만 추가되어야 한다
    (기존 QA 출력을 깨뜨리지 않는다).
    """

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def test_existing_keys_preserved_and_new_key_added(self):
        _write_script(self.project_path, [{"scene": 1, "asset_path": "a.png"}])

        report = qa_report_service.build_qa_report(self.project_path)

        self.assertIn("project_path", report)
        self.assertIn("durations", report)
        self.assertIn("quality", report)
        self.assertIn("target_range_ok", report)
        self.assertIn("asset_intelligence", report)
        self.assertEqual(report["asset_intelligence"][0]["role_validation"], True)

    def test_format_report_still_includes_existing_sections(self):
        _write_script(self.project_path, [{"scene": 1, "asset_path": "a.png"}])

        report = qa_report_service.build_qa_report(self.project_path)
        text = qa_report_service.format_report(report)

        self.assertIn("QA Report:", text)
        self.assertIn("Scene durations:", text)
        self.assertIn("target range", text)


if __name__ == "__main__":
    unittest.main()
