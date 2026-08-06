import json
import os
import shutil
from datetime import datetime, timezone

from app.models.quality_report import RetryAttempt, SceneRegenerationEntry
from app.services import asset_integration_service
from app.services import quality_service
from app.services import regeneration_policy as policy
from app.services import scene_prompt_service
from app.services.image_service import generate_image
from app.services.video_builder import build_video
from app.services.final_video_service import merge_video_audio
from app.steps import step07_quality
from app.utils.atomic_write import atomic_write_json


# Sprint73 - 결정 로그 파일명. 어떤 scene을 왜 다시 그렸고, 왜 멈췄는지가
# 여기 남는다. 파이프라인의 어떤 단계도 이 파일을 읽지 않는다.
REGENERATION_LOG_FILENAME = "regeneration_log.json"

# Sprint40 - 하위 호환용 별칭. 판정 자체는 regeneration_policy가 한다.
STOCK_PROVIDERS = policy.STOCK_PROVIDERS

# Sprint73 - 되돌릴 원본을 두는 곳. 사이클이 끝나면 남기든 되돌리든
# 비운다. images/ 안에 두되 이름을 점으로 시작해, scene*.png만 훑는
# 파이프라인의 다른 단계가 이것을 scene으로 착각하지 않게 한다.
BACKUP_DIRNAME = ".regen_backup"


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


def _write_log(project_path: str, log: dict) -> None:
    """결정 로그를 남긴다. 실패해도 재생성 자체를 막지 않는다 - 이건
    관측 산출물이고, 기록이 안 됐다고 영상을 버릴 이유는 없다."""

    try:
        atomic_write_json(
            os.path.join(project_path, REGENERATION_LOG_FILENAME), log,
        )
    except Exception as exc:
        print(f"[Step08] 결정 로그 기록 실패(무시): {exc}")


def _backup_dir(project_path: str) -> str:
    return os.path.join(project_path, "images", BACKUP_DIRNAME)


def _back_up_scene(project_path: str, scene_number: int) -> None:
    """다시 그리기 전에 원본을 옆에 둔다.

    generate_image는 대상 파일을 그대로 덮어쓴다. 백업이 없으면 결과가
    더 나빠졌다는 것을 알아도 되돌릴 방법이 없다.
    """

    source = os.path.join(
        project_path, "images", f"scene{scene_number}.png",
    )

    if not os.path.exists(source):
        return

    directory = _backup_dir(project_path)
    os.makedirs(directory, exist_ok=True)
    shutil.copy2(source, os.path.join(directory, f"scene{scene_number}.png"))


def _restore_scenes(project_path: str, scene_numbers) -> list:
    """백업해 둔 원본으로 되돌린다. 되돌린 scene 번호를 반환한다."""

    directory = _backup_dir(project_path)
    restored = []

    for scene_number in scene_numbers:
        backup = os.path.join(directory, f"scene{scene_number}.png")

        if not os.path.exists(backup):
            continue

        shutil.copy2(
            backup,
            os.path.join(project_path, "images", f"scene{scene_number}.png"),
        )
        restored.append(scene_number)

    return restored


def _discard_backups(project_path: str) -> None:
    shutil.rmtree(_backup_dir(project_path), ignore_errors=True)


def _evaluate_images(project_path: str, script: dict):
    """
    이미지만 보고 품질을 다시 잰다.

    Sprint73 - 예전에는 사이클마다 build_video + merge_video_audio를
    돌린 뒤 step07을 다시 실행했다. 그런데 quality_service가 읽는 것은
    images/scene*.png와 thumbnail.png, 그리고 대본 텍스트뿐이다 -
    Ken Burns 렌더는 그 판단에 아무 영향을 주지 않으면서 사이클당 6분을
    썼다. 재생성 여부를 정하는 데 필요한 것만 계산하고, 영상은 루프가
    끝난 뒤 한 번만 다시 만든다.
    """

    try:
        result = quality_service.evaluate(project_path, script)
    except Exception as exc:
        print(f"[Step08] 이미지 품질 재평가 실패: {exc}")
        return None

    return (
        result.model_dump() if hasattr(result, "model_dump") else dict(result)
    )


def run(project_path: str):
    """
    Step08 - Intelligent Regeneration Engine.

    품질 평가에서 재생성 표시를 받은 scene만 다시 그린다. 통과한 scene은
    절대 건드리지 않는다 - 다시 그리면 좋아질 수도 있지만 나빠질 수도
    있고, 돈은 확실히 든다.

    멈추는 조건이 네 가지다(regeneration_policy 참고): 대상이 없거나,
    이미지 생성 예산을 다 썼거나, 직전 사이클보다 품질이 오르지
    않았거나, 이번 사이클에서 성공한 재생성이 하나도 없거나. 어느
    경우든 사유가 regeneration_log.json에 남는다.

    Returns:
        QualityReport: 항상 이 타입. 재생성이 한 번도 일어나지 않았어도
        디스크에서 읽은 현재 리포트를 그대로 돌려준다.

    Raises:
        RuntimeError: quality_report.json이 아직 없으면. Step07이 최소
            한 번은 먼저 돌아야 한다.
    """

    channel = _load_project_metadata(project_path)["channel"]

    script = _load_script(project_path)
    scenes_by_number = {scene["scene"]: scene for scene in script["scenes"]}

    report = step07_quality.load(project_path)

    if report is None:
        raise RuntimeError(
            "quality_report.json not found - Step07 must run before Step08"
        )

    log = policy.new_log()
    spent = 0
    cycle = 0
    regenerated_any = False
    previous_quality = None

    regeneration_by_scene = {
        entry.scene: entry for entry in report.regeneration
    }

    if report.ai_quality_evaluation is None:
        print(
            "[Step08] technical validation has not passed, cannot "
            "determine regeneration targets: "
            f"{report.technical_validation.blocking_failures}"
        )
        policy.close_log(
            log, policy.STOP_NOTHING_ELIGIBLE, spent, rendered=False,
        )
        _write_log(project_path, log)
        return report

    evaluation = report.ai_quality_evaluation.model_dump()

    while True:

        cycle += 1
        quality_before = policy.cycle_quality(evaluation)

        eligible = policy.regeneration_targets(
            evaluation,
            scenes_by_number,
            {
                number: entry.regeneration.retry_count
                for number, entry in regeneration_by_scene.items()
            },
        )

        decision = policy.decide_continue(
            eligible, spent, previous_quality, quality_before,
        )

        if not decision["continue"]:
            stop_reason = decision["stop_reason"]
            break

        allowed, dropped = policy.apply_cost_budget(
            eligible, spent, log["max_image_calls"],
        )

        if not allowed:
            stop_reason = policy.STOP_BUDGET_EXHAUSTED
            break

        reason_by_scene = {
            scene["scene"]: scene.get("reason")
            for scene in evaluation["scenes"]
        }

        succeeded = []
        failed = []

        for scene_number in allowed:

            entry = regeneration_by_scene.get(
                scene_number, SceneRegenerationEntry(scene=scene_number),
            )

            output_file = os.path.join(
                project_path, "images", f"scene{scene_number}.png",
            )

            timestamp = datetime.now(timezone.utc).isoformat()
            spent += 1

            _back_up_scene(project_path, scene_number)

            try:
                generate_image(
                    scenes_by_number[scene_number]["image_prompt"],
                    output_file,
                    channel=channel,
                    is_hook_scene=(scene_number == 1),
                    image_style=asset_integration_service.resolve_image_style(
                        scenes_by_number[scene_number],
                    ),
                    # Sprint75 - 재생성도 구조화된 프롬프트로 그린다.
                    # 실측에서 이 경로만 예전 방식으로 나갔다 - 같은
                    # scene을 처음 그릴 때와 다시 그릴 때 다른 프롬프트를
                    # 쓰면 무엇이 달라졌는지 알 수 없다.
                    elements=scene_prompt_service.scene_elements(
                        scenes_by_number[scene_number],
                    ),
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
                succeeded.append(scene_number)

            except Exception as exc:
                entry.regeneration.retry_history.append(
                    RetryAttempt(
                        attempt=len(entry.regeneration.retry_history) + 1,
                        outcome="error",
                        reason=str(exc),
                        timestamp=timestamp,
                    )
                )
                failed.append(scene_number)
                print(
                    f"[Step08] scene {scene_number} regeneration failed: {exc}"
                )

            regeneration_by_scene[scene_number] = entry

        if not succeeded:
            _discard_backups(project_path)
            policy.record_cycle(
                log, cycle, allowed, dropped, succeeded, failed,
                quality_before, None, spent,
            )
            stop_reason = policy.STOP_NO_SUCCESSFUL_REGENERATION
            break

        new_evaluation = _evaluate_images(project_path, script)

        quality_after = (
            None if new_evaluation is None
            else policy.cycle_quality(new_evaluation)
        )

        # 남길지 되돌릴지. 여기서 멈추는 것만으로는 부족하다 -
        # generate_image는 이미 원본을 덮어쓴 뒤이고, 되돌리지 않으면
        # 더 나빠진 그림이 그대로 영상에 들어간다.
        if policy.regressed(quality_before, quality_after):
            rolled_back = _restore_scenes(project_path, succeeded)
            _discard_backups(project_path)

            for scene_number in rolled_back:
                history = regeneration_by_scene[
                    scene_number
                ].regeneration.retry_history
                if history:
                    history[-1].outcome = "rolled_back"
                    history[-1].reason = (
                        "재생성 결과가 직전보다 나빠 원본으로 되돌렸습니다"
                    )

            policy.record_cycle(
                log, cycle, allowed, dropped, succeeded, failed,
                quality_before, quality_after, spent,
                rolled_back=rolled_back,
            )
            stop_reason = policy.STOP_REGRESSED
            break

        _discard_backups(project_path)
        regenerated_any = True

        policy.record_cycle(
            log, cycle, allowed, dropped, succeeded, failed,
            quality_before, quality_after, spent,
        )

        by_scene = {
            scene["scene"]: scene for scene in new_evaluation["scenes"]
        }

        for scene_number in succeeded:
            entry = regeneration_by_scene[scene_number]
            scene_result = by_scene.get(scene_number)

            if scene_result is not None and not scene_result.get("regenerate"):
                entry.regeneration.final_status = "passed"
            elif entry.regeneration.retry_count >= log["max_retry_per_scene"]:
                entry.regeneration.final_status = "failed_max_retry"

            regeneration_by_scene[scene_number] = entry

        previous_quality = quality_before
        evaluation = new_evaluation

    # 루프가 끝난 뒤 한 번만 영상을 다시 만들고, 그 결과로 최종 리포트를
    # 쓴다. 재생성이 한 번도 성공하지 않았으면 다시 만들 이유가 없다.
    rendered = False

    if regenerated_any:
        try:
            build_video(project_path)
            merge_video_audio(project_path)
            rendered = True
            report = step07_quality.evaluate(project_path)
        except Exception as exc:
            print(f"[Step08] 최종 렌더/평가 실패: {exc}")

    report.regeneration = list(regeneration_by_scene.values())
    _write_report(project_path, report)

    policy.close_log(log, stop_reason, spent, rendered)
    _write_log(project_path, log)

    print(
        f"[Step08] 사이클 {cycle - 1}회, 이미지 생성 {spent}회, "
        f"중단 사유: {policy.explain_stop(stop_reason)}"
    )

    return report
