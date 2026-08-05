"""
Sprint70 - Evaluation Framework v2 러너.

두 설정(baseline / candidate)으로 각각 여러 번 이미지를 생성하고,
회차마다 Gemini Vision 평가를 받아 통계로 비교한다.

사용법
  .venv/Scripts/python.exe scripts/run_evaluation.py \
      --source output/20260709_165931 --runs 5 --out eval_report.md

왜 영상을 렌더하지 않는가
------------------------
quality_service.evaluate()가 읽는 것은 images/scene*.png와
thumbnail.png, 그리고 대본 텍스트다. Ken Burns 렌더와 자막 번인은 그
평가에 아무 영향을 주지 않는다. 렌더까지 돌리면 실행당 6분이 더 붙어
10회 생성이 비현실적이 된다 - 재려는 대상에 맞춰 뺀 것이지 질러간
것이 아니다. MP4 검증은 승자 설정으로 한 번만 하면 된다.

왜 대본과 나레이션을 고정하는가
------------------------------
Gemini는 같은 대본으로도 매번 다른 문장을 쓰고, TTS는 같은 문장으로도
매번 다른 길이를 낸다. 그것까지 같이 흔들리면 무엇이 이미지를 바꿨는지
알 수 없다. 저장된 실제 대본을 그대로 재사용해 변수를 하나로 줄인다.
"""

import argparse
import copy
import json
import os
import shutil
import sys
import time

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from unittest.mock import patch  # noqa: E402

import app  # noqa: F401,E402

from app import config  # noqa: E402
from app.pipeline import pipeline  # noqa: E402
from app.services import prompt_learning_service, quality_service  # noqa: E402
from app.tools import evaluation  # noqa: E402


ARMS = {
    "baseline": {
        "ENABLE_SCENE_PLANNER": False,
        "ENABLE_PROMPT_ENRICHMENT": False,
    },
    "candidate": {
        "ENABLE_SCENE_PLANNER": True,
        "ENABLE_PROMPT_ENRICHMENT": True,
    },
}


def load_clean_script(source_project):
    """이전 실행이 남긴 파생 필드를 걷어내고 순수 대본만 남긴다."""

    with open(
        os.path.join(source_project, "script.json"), encoding="utf-8",
    ) as f:
        source = json.load(f)

    return {
        "title": source["title"],
        "hook": source["hook"],
        "script": source.get("script", ""),
        "scenes": [
            {
                "scene": scene["scene"],
                "narration": scene["narration"],
                "image_prompt": scene["image_prompt"],
            }
            for scene in source["scenes"]
        ],
    }


def run_once(work_dir, run_index, arm, flags, script, source_project):
    """이미지 생성 + 썸네일 + Gemini 평가를 한 번 수행한다."""

    project = os.path.join(work_dir, f"{arm}_run{run_index}")
    if os.path.exists(project):
        shutil.rmtree(project)
    os.makedirs(project)

    # 오디오는 평가에 쓰이지 않지만, 파이프라인의 이후 단계가 파일을
    # 찾으므로 원본을 그대로 복사해 둔다.
    shutil.copytree(
        os.path.join(source_project, "audio"),
        os.path.join(project, "audio"),
    )

    def fake_step01(topic, path):
        data = copy.deepcopy(script)
        with open(
            os.path.join(path, "script.json"), "w", encoding="utf-8",
        ) as out:
            json.dump(data, out, ensure_ascii=False, indent=4)
        return data

    prompt_learning_service.reset_learning()

    with patch.multiple(
        "app.pipeline.pipeline.config",
        ENABLE_PROMPT_EFFECTIVENESS=True,
        ENABLE_PROMPT_LEARNING=True,
        ENABLE_AI_DIRECTOR=True,
        ENABLE_PROMPT_OPTIMIZATION=False,
        ENABLE_VIRAL_WRITER=False,
        **flags,
    ), \
         patch.object(pipeline.step01_script, "run", fake_step01), \
         patch.object(pipeline.step03_tts, "run", lambda s, p: None), \
         patch.object(pipeline.step04_subtitle, "run", lambda p: None), \
         patch.object(pipeline.step05_video, "run", lambda p: None), \
         patch.object(pipeline.step07_quality, "run", lambda *a, **k: None), \
         patch.object(pipeline.regeneration_service, "run", lambda p: None):

        data = pipeline.run_pipeline(
            topic=script["title"],
            project_path=project,
            channel="wellbeing",
        )

    try:
        result = quality_service.evaluate(project, data)
    except Exception as exc:
        print(f"    [{arm} run{run_index}] 평가 실패: "
              f"{type(exc).__name__}: {str(exc)[:160]}")
        return None, project

    payload = (
        result.model_dump() if hasattr(result, "model_dump") else dict(result)
    )

    with open(
        os.path.join(project, "evaluation.json"), "w", encoding="utf-8",
    ) as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload, project


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="두 설정을 여러 번 생성해 통계적으로 비교합니다.",
    )
    parser.add_argument(
        "--source", required=True,
        help="대본과 오디오를 가져올 기존 프로젝트 경로",
    )
    parser.add_argument(
        "--runs", type=int, default=evaluation.DEFAULT_RUNS,
        help=f"arm당 생성 횟수 (기본 {evaluation.DEFAULT_RUNS})",
    )
    parser.add_argument(
        "--work", default="output/_evaluation",
        help="생성 결과를 둘 작업 디렉터리",
    )
    parser.add_argument(
        "--out", default="evaluation_report.md",
        help="Markdown 리포트 출력 경로",
    )
    args = parser.parse_args()

    script = load_clean_script(args.source)

    os.makedirs(args.work, exist_ok=True)

    collected = {}
    projects = {}

    for arm, flags in ARMS.items():

        print("=" * 70)
        print(f"{arm}  ({args.runs}회)")
        print("=" * 70)

        evaluations = []
        projects[arm] = []

        for index in range(1, args.runs + 1):
            started = time.perf_counter()
            payload, project = run_once(
                args.work, index, arm, flags, script, args.source,
            )
            evaluations.append(payload)
            projects[arm].append(project)

            scores = (payload or {}).get("scores", {})
            print(
                f"  run{index}  {time.perf_counter() - started:5.1f}s  "
                f"overall={scores.get('overall_quality', '-')}"
                f"  realism={scores.get('image_realism', '-')}"
                f"  comp={scores.get('composition', '-')}"
                f"  hook={scores.get('hook_strength', '-')}"
            )

        collected[arm] = evaluation.collect_scores(evaluations)

    comparison = evaluation.compare_arms(
        collected["baseline"], collected["candidate"],
    )
    decision = evaluation.decide(comparison)

    report = evaluation.render_report(
        comparison, decision,
        baseline_label="baseline",
        candidate_label="candidate (Scene Planner v2 + Enrichment)",
    )

    report += "\n## 생성 산출물 (사람이 직접 볼 것)\n\n"
    for arm in ARMS:
        report += f"### {arm}\n\n"
        for path in projects[arm]:
            report += f"- `{path}`\n"
        report += "\n"

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)

    print()
    print(report)
    print(f"리포트: {args.out}")

    return 0 if decision["approved"] else 1


if __name__ == "__main__":
    sys.exit(main())
