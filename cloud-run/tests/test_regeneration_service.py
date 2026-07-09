import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.quality_report import (
    AIQualityEvaluation,
    PerformanceMetrics,
    QualityReport,
    QualityReportMetadata,
    QualityScores,
    QualitySummary,
    RegenerationState,
    RetryAttempt,
    SceneQuality,
    SceneRegenerationEntry,
    TechnicalChecks,
    TechnicalValidation,
    ThumbnailQuality,
)
from app.services import regeneration_service


def _performance_metrics():
    return PerformanceMetrics(
        project_creation_seconds=0.0,
        script_generation_seconds=0.0,
        image_generation_seconds=0.0,
        tts_generation_seconds=0.0,
        subtitle_generation_seconds=0.0,
        video_rendering_seconds=0.0,
        thumbnail_generation_seconds=0.0,
        quality_evaluation_seconds=0.0,
        total_generation_time_seconds=0.0,
        final_file_size_bytes=0,
        thumbnail_file_size_bytes=0,
    )


def _technical_validation(passed=True, blocking_failures=None):
    return TechnicalValidation(
        passed=passed,
        checks=TechnicalChecks.model_validate(
            {
                "required_files_exist": {"passed": True, "missing": []},
                "scene_count_consistency": {
                    "passed": True, "script_scenes": 1,
                    "image_files": 1, "audio_files": 1,
                },
                "image_resolution": {"passed": True, "warnings": [], "details": []},
                "video_duration": {"passed": True, "duration_seconds": 1.0},
                "subtitle_existence": {"passed": True, "cue_count": 1},
                "audio_video_sync": {
                    "passed": True, "video_duration_seconds": 1.0,
                    "audio_duration_seconds": 1.0, "delta_ms": 0.0,
                    "tolerance_ms": 250.0,
                },
                "thumbnail_existence": {"passed": True},
            }
        ),
        performance_metrics=_performance_metrics(),
        blocking_failures=blocking_failures or [],
    )


def _scene_quality(scene, regenerate, reason=None):
    return SceneQuality(
        scene=scene,
        realism_score=90,
        composition_score=90,
        regenerate=regenerate,
        reason=reason,
    )


def _ai_evaluation(scene_flags):
    scenes = [
        _scene_quality(scene, regenerate, reason)
        for scene, regenerate, reason in scene_flags
    ]
    return AIQualityEvaluation(
        scores=QualityScores(
            hook_strength=90, scene1_quality=90, thumbnail_quality=90,
            image_realism=90, character_consistency=90, composition=90,
            overall_quality=90,
        ),
        scenes=scenes,
        thumbnail=ThumbnailQuality(
            consistency_with_scene1=90, ctr_score=90, regenerate=False,
        ),
        summary=QualitySummary(
            regenerate_recommended=any(r for _, r, _ in scene_flags),
            scenes_to_regenerate=[s for s, r, _ in scene_flags if r],
            notes="",
        ),
    )


def _report(
    ai_evaluation=None,
    regeneration=None,
    technical_validation=None,
):
    return QualityReport(
        project_id="proj",
        technical_validation=technical_validation or _technical_validation(),
        ai_quality_evaluation=ai_evaluation,
        regeneration=regeneration or [],
        metadata=QualityReportMetadata(
            evaluated_at="2026-01-01T00:00:00+00:00",
            schema_version="sprint23",
            ai_evaluation_skipped_reason=None,
        ),
    )


@patch("app.services.regeneration_service.merge_video_audio")
@patch("app.services.regeneration_service.build_video")
@patch("app.services.regeneration_service.generate_image")
@patch("app.services.regeneration_service.step07_quality")
class TestRegenerationService(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

        with open(
            os.path.join(self.project_path, "project.json"), "w", encoding="utf-8"
        ) as f:
            json.dump({"channel": "wellbeing"}, f)

        with open(
            os.path.join(self.project_path, "script.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "scenes": [
                        {"scene": 1, "image_prompt": "prompt1"},
                        {"scene": 2, "image_prompt": "prompt2"},
                        {"scene": 3, "image_prompt": "prompt3"},
                    ]
                },
                f,
            )

    def test_raises_when_no_quality_report(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        mock_step07.load.return_value = None

        with self.assertRaises(RuntimeError):
            regeneration_service.run(self.project_path)

        mock_generate_image.assert_not_called()

    def test_breaks_immediately_when_ai_evaluation_missing(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        report = _report(
            ai_evaluation=None,
            technical_validation=_technical_validation(
                passed=False, blocking_failures=["missing file"],
            ),
        )
        mock_step07.load.return_value = report

        result = regeneration_service.run(self.project_path)

        self.assertIs(result, report)
        mock_generate_image.assert_not_called()
        mock_build_video.assert_not_called()

    def test_no_eligible_scenes_does_nothing(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        report = _report(ai_evaluation=_ai_evaluation([(1, False, None)]))
        mock_step07.load.return_value = report

        result = regeneration_service.run(self.project_path)

        self.assertIs(result, report)
        mock_generate_image.assert_not_called()
        mock_build_video.assert_not_called()
        mock_merge.assert_not_called()

    def test_already_at_max_retry_is_excluded(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        report = _report(
            ai_evaluation=_ai_evaluation([(3, True, "still bad")]),
            regeneration=[
                SceneRegenerationEntry(
                    scene=3,
                    regeneration=RegenerationState(retry_count=3),
                )
            ],
        )
        mock_step07.load.return_value = report

        result = regeneration_service.run(self.project_path)

        self.assertIs(result, report)
        mock_generate_image.assert_not_called()

    def test_successful_regeneration_calls_generate_image_and_rebuilds(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        initial_report = _report(
            ai_evaluation=_ai_evaluation([(3, True, "손가락이 이상함")]),
        )
        post_cycle_report = _report(
            ai_evaluation=_ai_evaluation([(3, False, None)]),
        )
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report

        result = regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once_with(
            "prompt3",
            os.path.join(self.project_path, "images", "scene3.png"),
            channel="wellbeing",
            is_hook_scene=False,
            visual_type=None,
        )
        mock_build_video.assert_called_once_with(self.project_path)
        mock_merge.assert_called_once_with(self.project_path)

        entry = {e.scene: e for e in result.regeneration}[3]
        self.assertEqual(entry.regeneration.retry_count, 1)
        self.assertEqual(entry.regeneration.final_status, "passed")
        self.assertEqual(len(entry.regeneration.retry_history), 1)
        self.assertEqual(entry.regeneration.retry_history[0].outcome, "success")

        with open(
            os.path.join(self.project_path, "quality_report.json"),
            encoding="utf-8",
        ) as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["regeneration"][0]["scene"], 3)

    def test_hook_scene_passes_is_hook_scene_true(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        initial_report = _report(ai_evaluation=_ai_evaluation([(1, True, "reason")]))
        post_cycle_report = _report(ai_evaluation=_ai_evaluation([(1, False, None)]))
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report

        regeneration_service.run(self.project_path)

        _, kwargs = mock_generate_image.call_args
        self.assertTrue(kwargs["is_hook_scene"])

    def test_all_failures_skip_rebuild_and_do_not_persist(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        initial_report = _report(ai_evaluation=_ai_evaluation([(3, True, "bad")]))
        mock_step07.load.return_value = initial_report
        mock_generate_image.side_effect = Exception("imagen failed")

        result = regeneration_service.run(self.project_path)

        mock_build_video.assert_not_called()
        mock_merge.assert_not_called()
        mock_step07.evaluate.assert_not_called()
        self.assertEqual(result.regeneration, [])
        self.assertFalse(
            os.path.exists(os.path.join(self.project_path, "quality_report.json"))
        )

    def test_mixed_success_and_failure_rebuilds_once(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        initial_report = _report(
            ai_evaluation=_ai_evaluation([(1, True, "a"), (3, True, "b")]),
        )
        post_cycle_report = _report(
            ai_evaluation=_ai_evaluation([(1, False, None), (3, False, None)]),
        )
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report

        def _side_effect(prompt, output_file, channel, is_hook_scene, visual_type=None):
            if "scene1" in output_file:
                raise Exception("scene1 failed")

        mock_generate_image.side_effect = _side_effect

        result = regeneration_service.run(self.project_path)

        mock_build_video.assert_called_once_with(self.project_path)
        entries = {e.scene: e for e in result.regeneration}
        self.assertEqual(entries[3].regeneration.final_status, "passed")
        self.assertEqual(entries[1].regeneration.retry_count, 0)
        self.assertIsNone(entries[1].regeneration.final_status)
        self.assertEqual(entries[1].regeneration.retry_history[0].outcome, "error")

    def test_reaches_max_retry_sets_failed_status_and_stops(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        initial_report = _report(
            ai_evaluation=_ai_evaluation([(3, True, "still bad")]),
            regeneration=[
                SceneRegenerationEntry(
                    scene=3,
                    regeneration=RegenerationState(retry_count=2),
                )
            ],
        )
        post_cycle_report = _report(
            ai_evaluation=_ai_evaluation([(3, True, "still bad after retry")]),
        )
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report

        result = regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once()
        entry = {e.scene: e for e in result.regeneration}[3]
        self.assertEqual(entry.regeneration.retry_count, 3)
        self.assertEqual(entry.regeneration.final_status, "failed_max_retry")

    def test_loops_across_multiple_cycles_until_clean(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        initial_report = _report(ai_evaluation=_ai_evaluation([(3, True, "bad")]))
        still_bad_report = _report(ai_evaluation=_ai_evaluation([(3, True, "still bad")]))
        clean_report = _report(ai_evaluation=_ai_evaluation([(3, False, None)]))

        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.side_effect = [still_bad_report, clean_report]

        result = regeneration_service.run(self.project_path)

        self.assertEqual(mock_generate_image.call_count, 2)
        self.assertEqual(mock_build_video.call_count, 2)
        entry = {e.scene: e for e in result.regeneration}[3]
        self.assertEqual(entry.regeneration.retry_count, 2)
        self.assertEqual(entry.regeneration.final_status, "passed")

    # --- Sprint40: Hybrid Asset Engine 연동 (stock scene은 재생성 skip) ---

    def _write_script_with_providers(self, providers_by_scene):
        with open(
            os.path.join(self.project_path, "script.json"), "w", encoding="utf-8",
        ) as f:
            json.dump(
                {
                    "scenes": [
                        {
                            "scene": scene,
                            "image_prompt": f"prompt{scene}",
                            "provider": provider,
                        }
                        for scene, provider in providers_by_scene.items()
                    ]
                },
                f,
            )

    def test_pexels_sourced_scene_is_never_regenerated_even_when_flagged(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        self._write_script_with_providers({3: "pexels_image"})

        report = _report(
            ai_evaluation=_ai_evaluation([(3, True, "인물 불일치")]),
        )
        mock_step07.load.return_value = report

        result = regeneration_service.run(self.project_path)

        self.assertIs(result, report)
        mock_generate_image.assert_not_called()
        mock_build_video.assert_not_called()

    def test_ai_sourced_scene_still_regenerates_when_mixed_with_stock_scene(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        self._write_script_with_providers({1: "ai_image", 3: "pexels_video"})

        initial_report = _report(
            ai_evaluation=_ai_evaluation([(1, True, "손 기형"), (3, True, "인물 불일치")]),
        )
        post_cycle_report = _report(
            ai_evaluation=_ai_evaluation([(1, False, None), (3, True, "인물 불일치")]),
        )
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report

        result = regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once_with(
            "prompt1",
            os.path.join(self.project_path, "images", "scene1.png"),
            channel="wellbeing",
            is_hook_scene=True,
            visual_type=None,
        )

        entries = {e.scene: e for e in result.regeneration}
        self.assertEqual(entries[1].regeneration.final_status, "passed")
        self.assertNotIn(3, entries)

    def test_missing_provider_field_defaults_to_ai_behavior(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        # 구버전 script.json(provider 필드 없음)은 기존과 동일하게
        # AI scene으로 취급해 정상적으로 재생성돼야 한다.
        initial_report = _report(ai_evaluation=_ai_evaluation([(3, True, "bad")]))
        post_cycle_report = _report(ai_evaluation=_ai_evaluation([(3, False, None)]))
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report

        regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once()

    # --- Sprint60 Hotfix 문제1: 재생성 시에도 visual_type이 그대로
    # 전달돼야 의료 일러스트 스타일이 유지된다(안 그러면 재생성해도
    # 계속 같은 "사람 얼굴 + 의료 이미지" 문제가 반복된다) ---

    def test_visual_type_is_passed_through_on_regeneration(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        with open(
            os.path.join(self.project_path, "script.json"), "w", encoding="utf-8",
        ) as f:
            json.dump(
                {
                    "scenes": [
                        {"scene": 1, "image_prompt": "prompt1", "visual_type": "real"},
                        {"scene": 3, "image_prompt": "prompt3", "visual_type": "ai"},
                    ]
                },
                f,
            )

        initial_report = _report(ai_evaluation=_ai_evaluation([(3, True, "얼굴 합성됨")]))
        post_cycle_report = _report(ai_evaluation=_ai_evaluation([(3, False, None)]))
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report

        regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once_with(
            "prompt3",
            os.path.join(self.project_path, "images", "scene3.png"),
            channel="wellbeing",
            is_hook_scene=False,
            visual_type="ai",
        )

    def test_visual_type_missing_defaults_to_none(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        # visual_type 필드 자체가 없는(구버전) script.json도 KeyError
        # 없이 동작해야 한다.
        initial_report = _report(ai_evaluation=_ai_evaluation([(3, True, "bad")]))
        post_cycle_report = _report(ai_evaluation=_ai_evaluation([(3, False, None)]))
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report

        regeneration_service.run(self.project_path)

        _, kwargs = mock_generate_image.call_args
        self.assertIsNone(kwargs["visual_type"])

    def test_total_failure_cycle_stops_without_a_second_attempt(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
    ):
        # 한 cycle에서 대상 scene이 전부 실패하면 rebuild/재평가 없이
        # 즉시 종료합니다 - 같은 run() 호출 안에서 자동 재시도는
        # 없습니다(재시도는 다음 파이프라인 실행에서 다시 감지됨).
        initial_report = _report(ai_evaluation=_ai_evaluation([(3, True, "bad")]))
        mock_step07.load.return_value = initial_report
        mock_generate_image.side_effect = Exception("transient failure")

        regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once()
        mock_step07.evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
