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
from app.services import image_service
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


def _scene_quality(scene, regenerate, reason=None, score=90):
    return SceneQuality(
        scene=scene,
        realism_score=score,
        composition_score=score,
        regenerate=regenerate,
        reason=reason,
    )


def _ai_evaluation(scene_flags, score=90):
    """Sprint73 - score를 받는다. 사이클 간 품질 개선 여부가 이제
    루프를 계속 돌지 말지를 정하므로, 점수가 고정이면 한 사이클 뒤
    멈추는 것이 정상이다."""

    scenes = [
        _scene_quality(scene, regenerate, reason, score)
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


@patch("app.services.regeneration_service.quality_service")
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
        mock_quality_service,
    ):
        mock_step07.load.return_value = None

        with self.assertRaises(RuntimeError):
            regeneration_service.run(self.project_path)

        mock_generate_image.assert_not_called()

    def test_breaks_immediately_when_ai_evaluation_missing(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
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
        mock_quality_service,
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
        mock_quality_service,
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
        mock_quality_service,
    ):
        initial_report = _report(
            ai_evaluation=_ai_evaluation([(3, True, "손가락이 이상함")]),
        )
        post_cycle_report = _report(
            ai_evaluation=_ai_evaluation([(3, False, None)]),
        )
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report
        # Sprint73 - 사이클 중 품질 재평가는 이미지만 보는
        # quality_service가 맡는다. 렌더는 루프가 끝난 뒤 한 번뿐이다.
        mock_quality_service.evaluate.return_value = (
            post_cycle_report.ai_quality_evaluation
        )

        result = regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once_with(
            "prompt3",
            os.path.join(self.project_path, "images", "scene3.png"),
            channel="wellbeing",
            is_hook_scene=False,
            image_style=image_service.IMAGE_STYLE_DEFAULT,
            # Sprint75 - 이 테스트의 scene은 image_prompt만 있는
            # 구버전 형태라 요소가 비어 있다.
            elements={},
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

    def _write_scene_image(self, number, payload):
        directory = os.path.join(self.project_path, "images")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"scene{number}.png")
        with open(path, "wb") as f:
            f.write(payload)
        return path

    def test_a_regressed_cycle_is_rolled_back_and_the_original_kept(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        """Sprint73 - 멈추는 것과 되돌리는 것은 다른 일이다.

        실측에서 엔진은 정확히 규칙대로 한 사이클 뒤 멈췄다. 그런데
        그 시점에는 generate_image가 이미 원본을 덮어쓴 뒤였고, 더
        나빠진 그림이 그대로 영상에 들어갔다 - overall_quality 70 -> 60.
        "개선된 경우에만 유지한다"를 지키려면 유지하지 않을 수도 있어야
        한다.
        """

        original = b"ORIGINAL-IMAGE-BYTES"
        path = self._write_scene_image(3, original)

        def overwrite(*args, **kwargs):
            with open(path, "wb") as f:
                f.write(b"WORSE-IMAGE-BYTES")

        mock_generate_image.side_effect = overwrite

        mock_step07.load.return_value = _report(
            ai_evaluation=_ai_evaluation([(3, True, "손가락")], score=80),
        )
        # 재생성 결과가 더 나쁘다.
        mock_quality_service.evaluate.return_value = _ai_evaluation(
            [(3, True, "여전히 나쁨")], score=40,
        )

        regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once()

        with open(path, "rb") as f:
            self.assertEqual(f.read(), original)

        mock_build_video.assert_not_called()
        mock_merge.assert_not_called()

        with open(
            os.path.join(
                self.project_path,
                regeneration_service.REGENERATION_LOG_FILENAME,
            ),
            encoding="utf-8",
        ) as f:
            log = json.load(f)

        self.assertEqual(log["stop_reason"], "regressed")
        self.assertEqual(log["cycles"][0]["rolled_back"], [3])
        self.assertFalse(log["rendered"])

    def test_an_improved_cycle_keeps_the_new_image(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        path = self._write_scene_image(3, b"ORIGINAL-IMAGE-BYTES")

        def overwrite(*args, **kwargs):
            with open(path, "wb") as f:
                f.write(b"BETTER-IMAGE-BYTES")

        mock_generate_image.side_effect = overwrite

        mock_step07.load.return_value = _report(
            ai_evaluation=_ai_evaluation([(3, True, "손가락")], score=40),
        )
        better = _ai_evaluation([(3, False, None)], score=90)
        mock_quality_service.evaluate.return_value = better
        mock_step07.evaluate.return_value = _report(ai_evaluation=better)

        regeneration_service.run(self.project_path)

        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"BETTER-IMAGE-BYTES")

        mock_build_video.assert_called_once_with(self.project_path)

        self.assertFalse(
            os.path.exists(
                os.path.join(
                    self.project_path, "images",
                    regeneration_service.BACKUP_DIRNAME,
                )
            ),
            "유지하기로 했으면 백업은 남기지 않는다",
        )

    def test_hook_scene_passes_is_hook_scene_true(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        initial_report = _report(ai_evaluation=_ai_evaluation([(1, True, "reason")]))
        post_cycle_report = _report(ai_evaluation=_ai_evaluation([(1, False, None)]))
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report
        # Sprint73 - 사이클 중 품질 재평가는 이미지만 보는
        # quality_service가 맡는다. 렌더는 루프가 끝난 뒤 한 번뿐이다.
        mock_quality_service.evaluate.return_value = (
            post_cycle_report.ai_quality_evaluation
        )

        regeneration_service.run(self.project_path)

        _, kwargs = mock_generate_image.call_args
        self.assertTrue(kwargs["is_hook_scene"])

    def test_all_failures_skip_rebuild_and_do_not_persist(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        initial_report = _report(ai_evaluation=_ai_evaluation([(3, True, "bad")]))
        mock_step07.load.return_value = initial_report
        mock_generate_image.side_effect = Exception("imagen failed")

        result = regeneration_service.run(self.project_path)

        mock_build_video.assert_not_called()
        mock_merge.assert_not_called()
        mock_step07.evaluate.assert_not_called()

        # Sprint73 - 실패한 시도도 기록에 남는다. 예전에는 통째로
        # 버렸는데, 그러면 다음 실행이 "이 scene을 이미 한 번 시도해
        # 봤다"는 것을 알 수 없다. "모든 결정은 로그에 남긴다"는
        # 원칙이 성공한 결정에만 적용될 이유가 없다.
        entry = {e.scene: e for e in result.regeneration}[3]
        self.assertEqual(entry.regeneration.retry_count, 0)
        self.assertEqual(entry.regeneration.retry_history[0].outcome, "error")

    def test_mixed_success_and_failure_rebuilds_once(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        initial_report = _report(
            ai_evaluation=_ai_evaluation([(1, True, "a"), (3, True, "b")]),
        )
        post_cycle_report = _report(
            ai_evaluation=_ai_evaluation([(1, False, None), (3, False, None)]),
        )
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report
        # Sprint73 - 사이클 중 품질 재평가는 이미지만 보는
        # quality_service가 맡는다. 렌더는 루프가 끝난 뒤 한 번뿐이다.
        mock_quality_service.evaluate.return_value = (
            post_cycle_report.ai_quality_evaluation
        )

        def _side_effect(prompt, output_file, channel, is_hook_scene,
                         image_style=None, elements=None):
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
        mock_quality_service,
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
        # Sprint73 - 사이클 중 품질 재평가는 이미지만 보는
        # quality_service가 맡는다. 렌더는 루프가 끝난 뒤 한 번뿐이다.
        mock_quality_service.evaluate.return_value = (
            post_cycle_report.ai_quality_evaluation
        )

        result = regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once()
        entry = {e.scene: e for e in result.regeneration}[3]
        self.assertEqual(entry.regeneration.retry_count, 3)
        self.assertEqual(entry.regeneration.final_status, "failed_max_retry")

    def test_loops_across_multiple_cycles_until_clean(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        # Sprint73 - 사이클을 이어가려면 품질이 실제로 올라야 한다.
        # 점수가 오르는 동안에는 계속 돌고, 마지막에 통과하면 끝난다.
        initial_report = _report(
            ai_evaluation=_ai_evaluation([(3, True, "bad")], score=40),
        )
        still_bad = _ai_evaluation([(3, True, "still bad")], score=60)
        clean = _ai_evaluation([(3, False, None)], score=90)

        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = _report(ai_evaluation=clean)
        mock_quality_service.evaluate.side_effect = [still_bad, clean]

        result = regeneration_service.run(self.project_path)

        self.assertEqual(mock_generate_image.call_count, 2)

        # 렌더는 사이클마다가 아니라 루프가 끝난 뒤 한 번뿐이다.
        # 품질 판정은 이미지만 보므로 사이클 중 렌더는 순수한 낭비였다.
        self.assertEqual(mock_build_video.call_count, 1)
        self.assertEqual(mock_merge.call_count, 1)

        entry = {e.scene: e for e in result.regeneration}[3]
        self.assertEqual(entry.regeneration.retry_count, 2)
        self.assertEqual(entry.regeneration.final_status, "passed")

    def test_stops_immediately_when_quality_does_not_improve(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        """개선이 없으면 재시도 한도가 남아 있어도 멈춘다.

        Imagen은 같은 프롬프트에도 매번 다른 그림을 그리므로, 계속
        돌린다고 좋아진다는 보장이 없다. 나빠지는 쪽으로 굴러가며
        예산만 태우는 것을 막는다.
        """

        initial_report = _report(
            ai_evaluation=_ai_evaluation([(3, True, "bad")], score=50),
        )
        no_better = _ai_evaluation([(3, True, "still bad")], score=50)

        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = _report(ai_evaluation=no_better)
        mock_quality_service.evaluate.return_value = no_better

        regeneration_service.run(self.project_path)

        # 한 번만 시도하고 멈춘다 - QUALITY_MAX_RETRY가 3이어도.
        self.assertEqual(mock_generate_image.call_count, 1)

    def test_the_decision_log_records_why_it_stopped(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        initial_report = _report(
            ai_evaluation=_ai_evaluation([(3, True, "bad")], score=50),
        )
        no_better = _ai_evaluation([(3, True, "still bad")], score=50)

        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = _report(ai_evaluation=no_better)
        mock_quality_service.evaluate.return_value = no_better

        regeneration_service.run(self.project_path)

        log_path = os.path.join(
            self.project_path,
            regeneration_service.REGENERATION_LOG_FILENAME,
        )
        self.assertTrue(os.path.exists(log_path))

        with open(log_path, encoding="utf-8") as f:
            log = json.load(f)

        self.assertEqual(log["stop_reason"], "no_improvement")
        self.assertTrue(log["stop_explanation"])
        self.assertEqual(log["total_image_calls"], 1)
        self.assertEqual(len(log["cycles"]), 1)
        self.assertEqual(log["cycles"][0]["succeeded"], [3])

    def test_the_cost_budget_caps_total_image_calls(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        # scene을 예산보다 많이 실패시켜 두고, 예산만큼만 그리는지 본다.
        with open(
            os.path.join(self.project_path, "script.json"), "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                {
                    "scenes": [
                        {"scene": n, "image_prompt": f"prompt{n}"}
                        for n in range(1, 11)
                    ]
                },
                f,
            )

        flags = [(n, True, "bad") for n in range(1, 11)]
        initial_report = _report(ai_evaluation=_ai_evaluation(flags, score=50))

        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = initial_report
        mock_quality_service.evaluate.return_value = _ai_evaluation(
            flags, score=50,
        )

        regeneration_service.run(self.project_path)

        self.assertEqual(
            mock_generate_image.call_count,
            regeneration_service.policy.REGENERATION_MAX_IMAGE_CALLS,
        )

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
        mock_quality_service,
    ):
        """Sprint40의 규칙을 Sprint73에 한 번 걷어냈다가 실측으로 되돌렸다.

        사물 scene을 Imagen에 맡기면 프롬프트에 없는 사람을 그려 넣고,
        그 사람은 앵커 캐릭터와 다르므로 character_consistency가 무너진다.
        자세한 실측 근거는 test_intelligent_regeneration.py에 있다.
        """

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
        mock_quality_service,
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
        # Sprint73 - 사이클 중 품질 재평가는 이미지만 보는
        # quality_service가 맡는다. 렌더는 루프가 끝난 뒤 한 번뿐이다.
        mock_quality_service.evaluate.return_value = (
            post_cycle_report.ai_quality_evaluation
        )

        result = regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once_with(
            "prompt1",
            os.path.join(self.project_path, "images", "scene1.png"),
            channel="wellbeing",
            is_hook_scene=True,
            image_style=image_service.IMAGE_STYLE_DEFAULT,
            # Sprint75 - 이 테스트의 scene은 image_prompt만 있는
            # 구버전 형태라 요소가 비어 있다.
            elements={},
        )

        entries = {e.scene: e for e in result.regeneration}
        self.assertEqual(entries[1].regeneration.final_status, "passed")
        self.assertNotIn(3, entries)

    def test_missing_provider_field_defaults_to_ai_behavior(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        # 구버전 script.json(provider 필드 없음)은 기존과 동일하게
        # AI scene으로 취급해 정상적으로 재생성돼야 한다.
        initial_report = _report(ai_evaluation=_ai_evaluation([(3, True, "bad")]))
        post_cycle_report = _report(ai_evaluation=_ai_evaluation([(3, False, None)]))
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report
        # Sprint73 - 사이클 중 품질 재평가는 이미지만 보는
        # quality_service가 맡는다. 렌더는 루프가 끝난 뒤 한 번뿐이다.
        mock_quality_service.evaluate.return_value = (
            post_cycle_report.ai_quality_evaluation
        )

        regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once()

    # --- Sprint60 Hotfix 문제1: 재생성 시에도 visual_type이 그대로
    # 전달돼야 의료 일러스트 스타일이 유지된다(안 그러면 재생성해도
    # 계속 같은 "사람 얼굴 + 의료 이미지" 문제가 반복된다) ---

    def test_visual_type_is_passed_through_on_regeneration(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
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
        # Sprint73 - 사이클 중 품질 재평가는 이미지만 보는
        # quality_service가 맡는다. 렌더는 루프가 끝난 뒤 한 번뿐이다.
        mock_quality_service.evaluate.return_value = (
            post_cycle_report.ai_quality_evaluation
        )

        regeneration_service.run(self.project_path)

        mock_generate_image.assert_called_once_with(
            "prompt3",
            os.path.join(self.project_path, "images", "scene3.png"),
            channel="wellbeing",
            is_hook_scene=False,
            image_style=image_service.IMAGE_STYLE_MEDICAL,
            elements={},
        )

    def test_visual_type_missing_uses_the_default_style(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
    ):
        # visual_type 필드 자체가 없는(구버전) script.json도 KeyError
        # 없이 동작해야 한다.
        initial_report = _report(ai_evaluation=_ai_evaluation([(3, True, "bad")]))
        post_cycle_report = _report(ai_evaluation=_ai_evaluation([(3, False, None)]))
        mock_step07.load.return_value = initial_report
        mock_step07.evaluate.return_value = post_cycle_report
        # Sprint73 - 사이클 중 품질 재평가는 이미지만 보는
        # quality_service가 맡는다. 렌더는 루프가 끝난 뒤 한 번뿐이다.
        mock_quality_service.evaluate.return_value = (
            post_cycle_report.ai_quality_evaluation
        )

        regeneration_service.run(self.project_path)

        _, kwargs = mock_generate_image.call_args
        self.assertEqual(
            kwargs["image_style"], image_service.IMAGE_STYLE_DEFAULT,
        )

    def test_total_failure_cycle_stops_without_a_second_attempt(
        self, mock_step07, mock_generate_image, mock_build_video, mock_merge,
        mock_quality_service,
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
