import json
import os
from datetime import datetime, timezone

from app.config import QUALITY_MAX_RETRY
from app.models.quality_report import RetryAttempt, SceneRegenerationEntry
from app.services.image_service import generate_image
from app.services.video_builder import build_video
from app.services.final_video_service import merge_video_audio
from app.steps import step07_quality
from app.utils.atomic_write import atomic_write_json


# Sprint40 - Hybrid Asset Engine 연동. Pexels/Pixabay 실사진은 서로 다른
# 실존 인물이라 구조적으로 "장면 간 동일 인물" 일관성 평가를 통과할 수
# 없다 - 이 provider들로 선택된 scene은 Gemini가 regenerate=True를
# 매겨도 AI로 재생성하지 않는다(비용 절감 효과 보존). script.json에
# provider 필드가 없는(구버전) scene은 기존과 동일하게 AI로 취급한다.
STOCK_PROVIDERS = {"pexels_image", "pexels_video", "pixabay_image", "pixabay_video"}


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_project_metadata(project_path: str) -> dict:
    return _load_json(os.path.join(project_path, "project.json"))


def _load_script(project_path: str) -> dict:
    return _load_json(os.path.join(project_path, "script.json"))


def _write_report(project_path: str, report) -> None:
    report_path = os.path.join(project_path, "quality_report.json")
    atomic_write_json(report_path, report.model_dump())


def run(project_path: str):
    """
    Step08 - Auto Regeneration Engine.

    Args:
        project_path: path to the project directory containing
            project.json, script.json, and quality_report.json.

    Returns:
        QualityReport: always this type, on every code path - the
        current quality report (as loaded from disk, or as last written
        by Step07's evaluation).

    Raises:
        RuntimeError: if quality_report.json does not exist yet - Step07
            must run at least once before Step08 can be invoked.
    """

    channel = _load_project_metadata(project_path)["channel"]

    scenes_by_number = {
        scene["scene"]: scene
        for scene in _load_script(project_path)["scenes"]
    }

    report = step07_quality.load(project_path)

    if report is None:
        raise RuntimeError(
            "quality_report.json not found - Step07 must run before Step08"
        )

    while True:

        if report.ai_quality_evaluation is None:
            print(
                "[Step08] technical validation has not passed, cannot "
                "determine regeneration targets: "
                f"{report.technical_validation.blocking_failures}"
            )
            break

        regeneration_by_scene = {
            entry.scene: entry
            for entry in report.regeneration
        }

        eligible = [
            scene.scene
            for scene in report.ai_quality_evaluation.scenes
            if scene.regenerate
            and regeneration_by_scene.get(
                scene.scene,
                SceneRegenerationEntry(scene=scene.scene),
            ).regeneration.retry_count < QUALITY_MAX_RETRY
            and scenes_by_number.get(scene.scene, {}).get("provider")
            not in STOCK_PROVIDERS
        ]

        if not eligible:
            break

        reason_by_scene = {
            scene.scene: scene.reason
            for scene in report.ai_quality_evaluation.scenes
        }

        successful = []

        for scene_number in eligible:

            entry = regeneration_by_scene.get(
                scene_number,
                SceneRegenerationEntry(scene=scene_number),
            )

            output_file = os.path.join(
                project_path,
                "images",
                f"scene{scene_number}.png",
            )

            timestamp = datetime.now(timezone.utc).isoformat()

            try:
                generate_image(
                    scenes_by_number[scene_number]["image_prompt"],
                    output_file,
                    channel=channel,
                    is_hook_scene=(scene_number == 1),
                    visual_type=scenes_by_number[scene_number].get("visual_type"),
                )

                entry.regeneration.retry_count += 1
                entry.regeneration.retry_history.append(
                    RetryAttempt(
                        attempt=len(entry.regeneration.retry_history) + 1,
                        outcome="success",
                        reason=reason_by_scene.get(scene_number),
                        timestamp=timestamp,
                    )
                )

                successful.append(scene_number)

            except Exception as exc:
                entry.regeneration.retry_history.append(
                    RetryAttempt(
                        attempt=len(entry.regeneration.retry_history) + 1,
                        outcome="error",
                        reason=str(exc),
                        timestamp=timestamp,
                    )
                )

                print(f"[Step08] scene {scene_number} regeneration failed: {exc}")

            # Kept in memory only - no disk write until the end of a
            # successful cycle.
            regeneration_by_scene[scene_number] = entry

        if not successful:
            print(
                "[Step08] no scene regenerated successfully this cycle, "
                "skipping rebuild/evaluation and exiting"
            )
            break

        build_video(project_path)
        merge_video_audio(project_path)

        # The only place technical_validation / ai_quality_evaluation are
        # ever written. regeneration_service never sets these fields.
        report = step07_quality.evaluate(project_path)

        ai_eval_by_scene = (
            {
                scene.scene: scene
                for scene in report.ai_quality_evaluation.scenes
            }
            if report.ai_quality_evaluation is not None
            else {}
        )

        for scene_number in successful:

            entry = regeneration_by_scene[scene_number]

            scene_result = ai_eval_by_scene.get(scene_number)

            if scene_result is not None and not scene_result.regenerate:
                entry.regeneration.final_status = "passed"
            elif entry.regeneration.retry_count >= QUALITY_MAX_RETRY:
                entry.regeneration.final_status = "failed_max_retry"

            regeneration_by_scene[scene_number] = entry

        # report.regeneration currently holds whatever Step07 carried
        # forward from disk (pre-cycle state) - replace wholesale with
        # this cycle's authoritative in-memory state before the single
        # write for this cycle.
        report.regeneration = list(regeneration_by_scene.values())

        _write_report(project_path, report)

    return report
