"""
Sprint70 - Evaluation Framework v2.

무엇을 고치려는 것인가
----------------------
Sprint69에서 실행 한 번짜리 A/B로는 아무것도 판정할 수 없다는 것이
실측으로 드러났다. 완전히 동일한 설정의 두 실행이 Gemini Vision 기준
overall_quality 40 vs 90, image_realism 50 vs 85, character_consistency
20 vs 80으로 갈렸다. Imagen이 매번 다른 그림을 그리고 평가자도 흔들리기
때문이다. 그 잡음 폭이 프롬프트 변경이 낼 수 있는 어떤 효과보다 컸다.

한 번씩 재서 비교하는 한, 우리가 보는 것은 변경의 효과가 아니라
샘플링 운이다. 그래서 arm마다 여러 번 생성해 분포를 만들고, 분포끼리
비교한다.

왜 순열검정인가
---------------
표본이 arm당 5개다. t검정은 정규성을 가정하는데, 5개로는 그 가정을
확인할 수도 없고 Gemini 점수가 정규분포일 이유도 없다.

정확 순열검정은 가정이 없다. 두 arm의 점수를 한 통에 넣고 가능한 모든
분할을 열거해, 관측된 차이만큼(혹은 그 이상) 벌어지는 분할이 전체의 몇
퍼센트인지 센다. 5 vs 5면 분할이 252가지뿐이라 전부 열거할 수 있다 -
근사도, 난수도, scipy도 필요 없다. 같은 입력에 항상 같은 답이 나온다.

한계도 분명하다. 5 vs 5에서 p의 하한은 1/252 ≈ 0.004이고, 후보가 기준선
전체보다 완전히 위에 있어야 그 값이 나온다. 즉 이 표본 크기로는 작은
개선을 잡아낼 수 없다 - 잡히는 것은 큰 개선뿐이다. 그것을 알고 쓰는
것과 모르고 쓰는 것은 다르다.
"""

import itertools
import math
import statistics


# arm당 기본 생성 횟수. 5 vs 5면 분할이 252가지라 정확 검정이 가능하고,
# 실행 시간도 감당할 만하다.
DEFAULT_RUNS = 5

# 절사평균에서 위아래로 몇 개씩 버릴지. Imagen이 가끔 완전히 빗나간
# 이미지를 내놓기 때문에, 평균만 보면 그 한 장에 결론이 끌려간다.
TRIM_COUNT = 1

SIGNIFICANCE_LEVEL = 0.05

# 판정의 기준이 되는 지표. 나머지는 "이것 때문에 저것을 깎지 않았는지"를
# 보는 가드레일이다.
PRIMARY_METRIC = "overall_quality"
GUARDRAIL_METRICS = ("image_realism", "composition", "hook_strength")

# 열거할 분할 수 상한. 넘으면 근사로 슬쩍 바꾸지 않고 거부한다 -
# "정확 검정"이라고 부르면서 실제로는 근사를 돌리면 읽는 사람이 속는다.
MAX_PERMUTATIONS = 200_000

VERDICT_ENABLE = "ENABLE"
VERDICT_KEEP_DISABLED = "KEEP_DISABLED"


def trimmed_mean(samples: list, trim: int = TRIM_COUNT) -> float:
    """
    정렬 후 위아래로 trim개씩 버린 평균. 버리고 나면 아무것도 안 남는
    작은 표본에서는 그냥 평균을 돌려준다 - 조용히 0을 반환하면 그게
    점수인지 결측인지 구분할 수 없다.
    """

    if not samples:
        raise ValueError("표본이 비어 있습니다.")

    ordered = sorted(samples)

    if len(ordered) <= 2 * trim:
        return statistics.fmean(ordered)

    kept = ordered[trim:len(ordered) - trim]

    return statistics.fmean(kept)


def summarize(samples: list) -> dict:
    """한 arm의 한 지표에 대한 기술통계."""

    if not samples:
        raise ValueError("표본이 비어 있습니다.")

    values = list(samples)

    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "trimmed_mean": trimmed_mean(values),
        "min": min(values),
        "max": max(values),
        "samples": values,
    }


def permutation_p_value(baseline: list, candidate: list) -> float:
    """
    "후보가 기준선보다 낫다"에 대한 단측 정확 순열검정.

    귀무가설은 "두 arm이 같은 분포에서 나왔다"이다. 그렇다면 어느 점수가
    어느 arm에 속했는지는 우연일 뿐이므로, 10개 점수를 5개씩 나누는 모든
    방법이 똑같이 그럴듯하다. 그중 관측된 것만큼 후보가 앞서는 분할이
    몇 개인지 세면 그것이 p값이다.

    통계량은 평균 차이다. 관측값 자신도 분할 하나로 세므로 p는 절대 0이
    되지 않는다 - 유한한 표본으로 "확률 0"을 주장할 수는 없다.
    """

    if not baseline or not candidate:
        raise ValueError("두 arm 모두 표본이 있어야 합니다.")

    total = len(baseline) + len(candidate)
    combination_count = math.comb(total, len(candidate))

    if combination_count > MAX_PERMUTATIONS:
        raise ValueError(
            f"분할이 {combination_count:,}가지라 정확 검정을 열거할 수 "
            f"없습니다(상한 {MAX_PERMUTATIONS:,}). 실행 횟수를 줄이세요 - "
            f"근사로 대체하지 않습니다."
        )

    pooled = list(baseline) + list(candidate)
    pooled_sum = sum(pooled)
    candidate_size = len(candidate)
    baseline_size = len(baseline)

    observed = (
        statistics.fmean(candidate) - statistics.fmean(baseline)
    )

    at_least_as_extreme = 0

    for indices in itertools.combinations(range(total), candidate_size):
        candidate_sum = sum(pooled[i] for i in indices)
        difference = (
            candidate_sum / candidate_size
            + (candidate_sum - pooled_sum) / baseline_size
        )

        # 부동소수 오차로 동률을 놓치지 않도록 아주 작은 여유를 둔다.
        if difference >= observed - 1e-9:
            at_least_as_extreme += 1

    return at_least_as_extreme / combination_count


def collect_scores(evaluations: list) -> dict:
    """
    회차별 Gemini 평가 결과에서 지표별 점수 계열을 모은다.

    실패한 회차(None)는 건너뛴다. 어떤 회차에만 있는 지표는 있는
    만큼만 모은다 - 없는 자리를 0으로 채우면 "0점"과 "측정 못 함"이
    같아져 통계가 거짓말을 한다.
    """

    collected = {}

    for entry in evaluations:

        if not entry:
            continue

        for metric, value in (entry.get("scores") or {}).items():
            collected.setdefault(metric, []).append(value)

    return collected


def compare_arms(baseline_scores: dict, candidate_scores: dict) -> dict:
    """
    두 arm의 지표별 분포를 비교한다.

    양쪽에 모두 있는 지표만 검정하고, 한쪽에만 있는 지표는
    unpaired_metrics에 이름을 남긴다 - 조용히 버리면 평가 대상이
    줄어든 것을 아무도 모른다.
    """

    shared = [
        metric
        for metric in baseline_scores
        if metric in candidate_scores
    ]

    unpaired = sorted(
        set(baseline_scores).symmetric_difference(candidate_scores)
    )

    metrics = {}

    for metric in shared:

        baseline_summary = summarize(baseline_scores[metric])
        candidate_summary = summarize(candidate_scores[metric])

        metrics[metric] = {
            "baseline": baseline_summary,
            "candidate": candidate_summary,
            "delta_mean": candidate_summary["mean"] - baseline_summary["mean"],
            "delta_trimmed_mean": (
                candidate_summary["trimmed_mean"]
                - baseline_summary["trimmed_mean"]
            ),
            "p_value": permutation_p_value(
                baseline_scores[metric], candidate_scores[metric],
            ),
            "p_value_worse": permutation_p_value(
                candidate_scores[metric], baseline_scores[metric],
            ),
        }

    return {"metrics": metrics, "unpaired_metrics": unpaired}


def decide(comparison: dict) -> dict:
    """
    비교 결과를 승인/보류 한 줄로 옮긴다.

    승인 조건 세 가지를 모두 만족해야 한다.

    1. 주지표가 유의하게 우수하다 (단측 p <= SIGNIFICANCE_LEVEL).
    2. 주지표의 절사평균도 우수하다. 평균만 보면 이상치 한 장이
       결론을 끌고 갈 수 있으므로, 가운데 값들도 같은 방향이어야 한다.
    3. 가드레일 지표 중 유의하게 나빠진 것이 없다. 한 지표를 올리려고
       다른 지표를 깎는 변경을 통과시키지 않기 위함이다.
    """

    metrics = comparison["metrics"]

    if PRIMARY_METRIC not in metrics:
        return {
            "approved": False,
            "verdict": VERDICT_KEEP_DISABLED,
            "blocking_metrics": [],
            "reason": (
                f"주지표 '{PRIMARY_METRIC}'가 양쪽 arm에 모두 있어야 "
                f"판정할 수 있습니다."
            ),
        }

    primary = metrics[PRIMARY_METRIC]

    blocking = [
        metric
        for metric in GUARDRAIL_METRICS
        if metric in metrics
        and metrics[metric]["p_value_worse"] <= SIGNIFICANCE_LEVEL
    ]

    significant = primary["p_value"] <= SIGNIFICANCE_LEVEL
    trimmed_agrees = primary["delta_trimmed_mean"] > 0

    if not significant:
        reason = (
            f"{PRIMARY_METRIC}의 차이가 잡음과 구분되지 않습니다 "
            f"(p={primary['p_value']:.4f} > {SIGNIFICANCE_LEVEL}). "
            f"평균 {primary['baseline']['mean']:.1f} -> "
            f"{primary['candidate']['mean']:.1f}."
        )
    elif not trimmed_agrees:
        reason = (
            f"{PRIMARY_METRIC}의 평균은 유의하게 올랐지만"
            f"(p={primary['p_value']:.4f}) 절사평균은 따라오지 않았습니다"
            f"({primary['delta_trimmed_mean']:+.1f}). 이상치가 평균을 "
            f"끌어올린 것으로 보입니다."
        )
    elif blocking:
        reason = (
            f"{PRIMARY_METRIC}는 좋아졌지만 "
            f"{', '.join(blocking)}가 유의하게 나빠졌습니다."
        )
    else:
        reason = (
            f"{PRIMARY_METRIC}가 유의하게 우수하고"
            f"(p={primary['p_value']:.4f}, 평균 "
            f"{primary['baseline']['mean']:.1f} -> "
            f"{primary['candidate']['mean']:.1f}), 절사평균도 같은 "
            f"방향이며({primary['delta_trimmed_mean']:+.1f}), 유의하게 "
            f"나빠진 가드레일 지표가 없습니다."
        )

    approved = significant and trimmed_agrees and not blocking

    return {
        "approved": approved,
        "verdict": VERDICT_ENABLE if approved else VERDICT_KEEP_DISABLED,
        "blocking_metrics": blocking,
        "reason": reason,
    }


def render_report(
    comparison: dict,
    decision: dict,
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
) -> str:
    """사람이 읽고 직접 판단할 수 있는 Markdown 비교 리포트."""

    lines = [
        "# Evaluation Report",
        "",
        f"- **{baseline_label}** vs **{candidate_label}**",
        f"- 판정: **{decision['verdict']}**",
        f"- 근거: {decision['reason']}",
        "",
        "## 지표별 비교",
        "",
        "| 지표 | arm | n | 평균 | 절사평균 | 표준편차 | 최소 | 최대 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    for metric, entry in comparison["metrics"].items():
        for label, key in ((baseline_label, "baseline"), (candidate_label, "candidate")):
            summary = entry[key]
            lines.append(
                f"| {metric} | {label} | {summary['count']} | "
                f"{summary['mean']:.1f} | {summary['trimmed_mean']:.1f} | "
                f"{summary['stdev']:.1f} | {summary['min']} | "
                f"{summary['max']} |"
            )

    lines += [
        "",
        "## 통계 검정 (단측 정확 순열검정)",
        "",
        "| 지표 | 평균 차이 | 절사평균 차이 | p(우수) | p(열세) | 판단 |",
        "|---|---:|---:|---:|---:|---|",
    ]

    for metric, entry in comparison["metrics"].items():
        if entry["p_value"] <= SIGNIFICANCE_LEVEL:
            call = "유의하게 우수"
        elif entry["p_value_worse"] <= SIGNIFICANCE_LEVEL:
            call = "유의하게 열세"
        else:
            call = "구분 불가"

        lines.append(
            f"| {metric} | {entry['delta_mean']:+.1f} | "
            f"{entry['delta_trimmed_mean']:+.1f} | "
            f"{entry['p_value']:.4f} | {entry['p_value_worse']:.4f} | "
            f"{call} |"
        )

    lines += ["", "## 회차별 원점수", "", "| 지표 | arm | 점수 |", "|---|---|---|"]

    for metric, entry in comparison["metrics"].items():
        for label, key in ((baseline_label, "baseline"), (candidate_label, "candidate")):
            scores = ", ".join(str(value) for value in entry[key]["samples"])
            lines.append(f"| {metric} | {label} | {scores} |")

    if comparison["unpaired_metrics"]:
        lines += [
            "",
            "## 한쪽 arm에만 있어 검정하지 못한 지표",
            "",
            ", ".join(comparison["unpaired_metrics"]),
        ]

    lines += [
        "",
        "## 읽을 때 유의할 점",
        "",
        f"- arm당 {DEFAULT_RUNS}회 기준으로 p의 하한은 "
        f"1/{math.comb(2 * DEFAULT_RUNS, DEFAULT_RUNS)} = "
        f"{1 / math.comb(2 * DEFAULT_RUNS, DEFAULT_RUNS):.4f}이며, "
        "후보가 기준선 전체보다 완전히 위에 있을 때만 그 값이 나온다.",
        "- 이 표본 크기로 잡아낼 수 있는 것은 큰 개선뿐이다. "
        "'구분 불가'는 '차이가 없다'가 아니라 '이만큼으로는 모른다'는 뜻이다.",
        "- Imagen은 같은 프롬프트에도 매번 다른 그림을 그린다. "
        "회차별 원점수의 흩어짐을 먼저 보고, 그 폭보다 작은 차이는 "
        "숫자가 어떻든 믿지 않는 편이 낫다.",
    ]

    return "\n".join(lines) + "\n"
