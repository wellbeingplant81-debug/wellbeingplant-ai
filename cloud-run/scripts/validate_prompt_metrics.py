"""
Sprint72 - prompt_metrics가 실제 영상 품질을 예측하는지 검증한다.

지금까지의 평가 실행이 남긴 산출물만 읽는다 - 새로 생성하지 않는다.
measurements.json(프롬프트 점수)과 evaluation.json(Gemini 품질)을
scene 번호로 짝지어 상관을 계산한다.

사용법
  .venv/Scripts/python.exe scripts/validate_prompt_metrics.py \
      --roots output/_evaluation <다른 평가 디렉터리> --out report.md
"""

import argparse
import json
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.tools import metrics_validation as mv  # noqa: E402


EVALUATION_FILENAMES = (
    "evaluation.json",
    "level1_evaluation.json",
    "quality_report.json",
)

# prompt_metrics["metrics"]의 항목들. 이것들이 100점을 나눠 갖는다.
CHECKS = (
    "prompt_preserved",
    "camera",
    "visual_type",
    "purpose",
    "length",
    "keywords",
    "duplicate_free",
)

TARGETS = ("realism_score", "composition_score")


def _load_evaluation(project_dir):
    for name in EVALUATION_FILENAMES:
        path = os.path.join(project_dir, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        if "ai_quality_evaluation" in payload:
            payload = payload["ai_quality_evaluation"]
        if payload and payload.get("scenes"):
            return payload
    return None


def harvest(roots):
    """scene 하나를 한 관측치로 모은다."""

    observations = []
    projects = 0

    for root in roots:
        for directory, _dirs, _files in os.walk(root):

            measurement_path = os.path.join(directory, "measurements.json")
            if not os.path.exists(measurement_path):
                continue

            evaluation = _load_evaluation(directory)
            if evaluation is None:
                continue

            with open(measurement_path, encoding="utf-8") as f:
                measurements = json.load(f)

            by_scene = {entry["scene"]: entry for entry in evaluation["scenes"]}
            projects += 1

            for entry in measurements.get("prompt_metrics", []):

                scene_id = entry["scene_id"]
                scene_eval = by_scene.get(scene_id)

                if scene_eval is None:
                    continue

                observations.append({
                    **{k: float(v) for k, v in entry["metrics"].items()},
                    "score": float(entry["score"]),
                    "realism_score": float(scene_eval["realism_score"]),
                    "composition_score": float(
                        scene_eval["composition_score"]
                    ),
                    "regenerate": bool(scene_eval["regenerate"]),
                })

    return observations, projects


def _fmt(value, width=8):
    if value is None:
        return "분산없음".rjust(width)
    return f"{value:>{width}.3f}"


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="prompt_metrics와 실제 품질의 상관을 검증합니다.",
    )
    parser.add_argument("--roots", nargs="+", required=True)
    parser.add_argument("--out", default="prompt_metrics_validation.md")
    args = parser.parse_args()

    observations, projects = harvest(args.roots)

    if not observations:
        print("짝지어진 관측치가 없습니다.")
        return 1

    lines = [
        "# Prompt Metrics Validation",
        "",
        f"- 프로젝트 {projects}개, scene 단위 관측치 {len(observations)}개",
        "- 새로 생성하지 않고 기존 평가 산출물만 읽었다.",
        "",
    ]

    print(f"프로젝트 {projects}개, 관측치 {len(observations)}개")

    analyses = {}

    for target in TARGETS:

        analysis = mv.correlate(observations, CHECKS + ("score",), target)
        analyses[target] = analysis

        lines += [
            f"## {target} 와의 상관",
            "",
            "| 항목 | 변동 | 고유값 | 평균 | Pearson | Spearman |",
            "|---|---|---:|---:|---:|---:|",
        ]

        print()
        print(f"=== {target} ===")
        print(f"{'항목':<20}{'변동':>6}{'고유값':>8}{'평균':>10}"
              f"{'Pearson':>10}{'Spearman':>10}")

        for name, entry in analysis.items():
            varies = "예" if entry["varies"] else "아니오"
            pearson_text = (
                "분산없음" if entry["pearson"] is None
                else f"{entry['pearson']:.3f}"
            )
            spearman_text = (
                "분산없음" if entry["spearman"] is None
                else f"{entry['spearman']:.3f}"
            )
            lines.append(
                f"| {name} | {varies} | {entry['distinct']} | "
                f"{entry['mean']:.2f} | {pearson_text} | {spearman_text} |"
            )
            print(f"{name:<20}{varies:>6}{entry['distinct']:>8}"
                  f"{entry['mean']:>10.2f}{_fmt(entry['pearson'], 10)}"
                  f"{_fmt(entry['spearman'], 10)}")

        lines.append("")

    # 불리언 check는 그룹 비교로도 본다.
    lines += ["## 불리언 check - 통과/실패 그룹 품질 비교", "",
              "| 항목 | 통과 | 실패 | 통과 평균 | 실패 평균 | 차이 | p |",
              "|---|---:|---:|---:|---:|---:|---:|"]

    print()
    print("=== 불리언 check 그룹 비교 (realism 기준) ===")

    for name in ("prompt_preserved", "camera", "visual_type", "purpose",
                 "duplicate_free"):
        flags = [bool(row[name]) for row in observations]
        quality = [row["realism_score"] for row in observations]
        comparison = mv.compare_groups(flags, quality)

        if not comparison["comparable"]:
            lines.append(
                f"| {name} | {comparison['passed_count']} | "
                f"{comparison['failed_count']} | - | - | 비교 불가 | - |"
            )
            print(f"  {name:<20} 통과 {comparison['passed_count']:>4} / "
                  f"실패 {comparison['failed_count']:>4}  -> 한쪽 그룹이 "
                  f"비어 비교 불가")
            continue

        p_text = (
            "-" if comparison["p_value"] is None
            else f"{comparison['p_value']:.4f}"
        )
        lines.append(
            f"| {name} | {comparison['passed_count']} | "
            f"{comparison['failed_count']} | "
            f"{comparison['passed_mean']:.1f} | "
            f"{comparison['failed_mean']:.1f} | "
            f"{comparison['gap']:+.1f} | {p_text} |"
        )
        print(f"  {name:<20} 통과 {comparison['passed_count']:>4} / "
              f"실패 {comparison['failed_count']:>4}  "
              f"차이 {comparison['gap']:+.1f}")

    verdict = mv.recommend_objective(analyses["realism_score"])

    lines += [
        "",
        "## 목적함수 판정",
        "",
        f"- 사용 가능: **{'예' if verdict['usable'] else '아니오'}**",
        f"- 예측력 있는 항목: "
        f"{', '.join(verdict['predictors']) or '없음'}",
        f"- 상수 항목: {', '.join(verdict['constant_checks']) or '없음'}",
        f"- 근거: {verdict['reason']}",
        "",
    ]

    print()
    print("=== 목적함수 판정 ===")
    print(f"  사용 가능: {'예' if verdict['usable'] else '아니오'}")
    print(f"  예측력 있는 항목: {', '.join(verdict['predictors']) or '없음'}")
    print(f"  상수 항목: {', '.join(verdict['constant_checks']) or '없음'}")
    print(f"  근거: {verdict['reason']}")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print()
    print(f"리포트: {args.out}")

    return 0 if verdict["usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
