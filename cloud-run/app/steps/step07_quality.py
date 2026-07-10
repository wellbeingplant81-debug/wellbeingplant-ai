import json
import os
import time
from datetime import datetime, timezone

from app.models.quality_report import (
    PerformanceMetrics,
    QualityReport,
    QualityReportMetadata,
    TechnicalValidation,
    VisualDiversitySummary,
)
from app.services import quality_service
from app.services import technical_validation_service
from app.services.visual_diversity_engine import summarize_visual_diversity


SCHEMA_VERSION = "sprint23"


def _build_visual_diversity_summary(scenes: list):
    """
    Sprint72-3 - Visual Diversity QA. scenes(step07_quality.run()에
    넘어오는 data["scenes"], Sprint72-2 이후 scene["visual_profile"]을
    가질 수 있음)에서 visual_profile이 있는 scene만 모아 quality_
    report.json에 실을 요약을 만든다. 판정 로직은 새로 만들지 않고
    visual_diversity_engine.summarize_visual_diversity()를 그대로
    재사용한다. visual_profile이 하나도 없으면(요구사항: profile=None
    이면 완전 no-op) None을 반환해 QualityReport.visual_diversity가
    그대로 None으로 남는다 - 기존 스키마와 완전히 하위 호환된다.
    """

    profiles_by_scene = {
        scene["scene"]: scene["visual_profile"]
        for scene in (scenes or [])
        if scene.get("visual_profile")
    }

    if not profiles_by_scene:
        return None

    summary = summarize_visual_diversity(list(profiles_by_scene.values()))
    summary["profiles_by_scene"] = profiles_by_scene

    return VisualDiversitySummary(**summary)


def _report_path(project_path):
    return os.path.join(project_path, "quality_report.json")


def load(project_path):
    """
    Read the current quality_report.json, if any. Used by Step08 to read
    evaluation results without duplicating this module's parsing logic.
    """

    path = _report_path(project_path)

    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        return QualityReport.model_validate(json.load(f))


def _load_prior_regeneration(project_path):
    """
    Carry forward the "regeneration" block Step08 owns. Step07 never
    reads or interprets its contents - only preserves them across
    re-evaluations so a regeneration cycle isn't lost when Step07 rewrites
    quality_report.json.
    """

    prior = load(project_path)

    return prior.regeneration if prior is not None else []


def _load_script(project_path):
    script_path = os.path.join(project_path, "script.json")

    with open(script_path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate(project_path):
    """
    Stable public entry point for re-running quality evaluation outside
    the step01-06 pipeline sequence (e.g. Step08's regeneration cycle).
    Loads script.json itself and supplies fresh timing bookkeeping, so
    callers outside a full pipeline run never need to know about run()'s
    pipeline-internal `timings`/`pipeline_start` parameters.
    """

    return run(
        project_path,
        _load_script(project_path),
        timings={},
        pipeline_start=time.perf_counter(),
    )


def run(
    project_path,
    data,
    timings,
    pipeline_start,
):

    project_id = os.path.basename(project_path.rstrip("/\\"))

    validation_result = technical_validation_service.validate(
        project_path,
        data,
    )

    ai_quality_evaluation = None
    ai_evaluation_skipped_reason = None

    quality_eval_start = time.perf_counter()

    if validation_result["passed"]:

        try:
            ai_quality_evaluation = quality_service.evaluate(
                project_path,
                data,
            )
        except Exception as exc:
            ai_evaluation_skipped_reason = f"AI evaluation failed: {exc}"

    else:
        ai_evaluation_skipped_reason = (
            "Technical validation failed: "
            + ", ".join(validation_result["blocking_failures"])
        )

    timings["quality_evaluation"] = time.perf_counter() - quality_eval_start
    timings["total_generation_time"] = time.perf_counter() - pipeline_start

    final_video_path = os.path.join(project_path, "video", "final_short.mp4")
    thumbnail_path = os.path.join(project_path, "thumbnail.png")

    performance_metrics = PerformanceMetrics(
        project_creation_seconds=timings.get("project_creation", 0.0),
        script_generation_seconds=timings.get("script_generation", 0.0),
        image_generation_seconds=timings.get("image_generation", 0.0),
        tts_generation_seconds=timings.get("tts_generation", 0.0),
        subtitle_generation_seconds=timings.get("subtitle_generation", 0.0),
        video_rendering_seconds=timings.get("video_rendering", 0.0),
        thumbnail_generation_seconds=timings.get("thumbnail_generation", 0.0),
        quality_evaluation_seconds=timings.get("quality_evaluation", 0.0),
        total_generation_time_seconds=timings.get("total_generation_time", 0.0),
        final_file_size_bytes=(
            os.path.getsize(final_video_path)
            if os.path.exists(final_video_path)
            else 0
        ),
        thumbnail_file_size_bytes=(
            os.path.getsize(thumbnail_path)
            if os.path.exists(thumbnail_path)
            else 0
        ),
    )

    technical_validation = TechnicalValidation(
        passed=validation_result["passed"],
        checks=validation_result["checks"],
        performance_metrics=performance_metrics,
        blocking_failures=validation_result["blocking_failures"],
    )

    report = QualityReport(
        project_id=project_id,
        technical_validation=technical_validation,
        ai_quality_evaluation=ai_quality_evaluation,
        regeneration=_load_prior_regeneration(project_path),
        metadata=QualityReportMetadata(
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            schema_version=SCHEMA_VERSION,
            ai_evaluation_skipped_reason=ai_evaluation_skipped_reason,
        ),
        visual_diversity=_build_visual_diversity_summary(data.get("scenes")),
    )

    output_path = os.path.join(project_path, "quality_report.json")

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            report.model_dump(),
            f,
            ensure_ascii=False,
            indent=2,
        )

    return report
