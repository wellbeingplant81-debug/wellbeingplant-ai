"""
Sprint72 - Prompt Metrics Validation.

Stage 4(Prompt Optimization)는 prompt_metrics 점수를 올리는 방향으로
프롬프트를 고친다. 그러니 그 점수가 실제 영상 품질과 상관이 있어야
한다. 없으면 Optimization은 아무 의미 없는 숫자를 향해 달린다.

Stage 3에서 이미 한 번 어긋났다. Enrichment를 켜자 점수는 90 -> 100으로
올랐는데 실제 이미지는 나빠졌다. 루브릭이 "계획한 문구가 프롬프트에
들어갔는가"를 재기 때문에, 문구를 넣으면 정의상 점수가 오른다. 점수와
품질이 반대로 움직인 것이다.

이 모듈은 그 상관을 데이터로 잰다. 새 생성은 필요 없다 - 지금까지의
평가 실행이 measurements.json(프롬프트 점수)과 evaluation.json(Gemini
품질)을 이미 남겨 뒀고, scene 번호로 짝지으면 된다.

설계에서 한 가지를 특히 조심한다. 분산이 없는 지표에 상관계수 0을
돌려주지 않는다. "상관이 0이다"와 "계산할 수 없다"는 전혀 다른
이야기인데, 둘을 같은 0으로 적으면 읽는 사람은 전자로 읽는다. 항상
True인 check는 무엇과도 상관을 가질 수 없다 - 그건 결과가 아니라
그 check가 아무것도 재고 있지 않다는 뜻이다.
"""

import math
import statistics

from app.tools.evaluation import permutation_p_value


# 상관이 "예측력이 있다"고 부를 만한 최소 크기. 사회과학 관행에서
# 중간 정도로 보는 지점이고, 목적함수로 쓰려면 최소한 이 정도는
# 되어야 한다.
MIN_PREDICTIVE_CORRELATION = 0.3

SIGNIFICANCE_LEVEL = 0.05


def _as_floats(values):
    return [float(value) for value in values]


def describe_series(values: list) -> dict:
    """한 계열이 변동하는지, 어떤 모양인지."""

    numeric = _as_floats(values)
    distinct = len(set(numeric))

    return {
        "count": len(numeric),
        "distinct": distinct,
        "varies": distinct > 1,
        "mean": statistics.fmean(numeric) if numeric else None,
        "stdev": statistics.stdev(numeric) if len(numeric) > 1 else 0.0,
        "min": min(numeric) if numeric else None,
        "max": max(numeric) if numeric else None,
    }


def pearson(xs: list, ys: list):
    """
    선형 상관계수. 어느 한쪽이라도 분산이 없으면 None을 돌려준다 -
    0이 아니다.
    """

    if len(xs) != len(ys):
        raise ValueError("두 계열의 길이가 다릅니다.")

    if len(xs) < 2:
        return None

    x = _as_floats(xs)
    y = _as_floats(ys)

    mean_x = statistics.fmean(x)
    mean_y = statistics.fmean(y)

    dx = [value - mean_x for value in x]
    dy = [value - mean_y for value in y]

    denominator = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))

    if denominator == 0:
        return None

    return sum(a * b for a, b in zip(dx, dy)) / denominator


def _ranks(values: list) -> list:
    """동점은 평균 순위로 준다."""

    ordered = sorted(range(len(values)), key=lambda i: values[i])

    ranks = [0.0] * len(values)
    position = 0

    while position < len(ordered):
        end = position
        while (
            end + 1 < len(ordered)
            and values[ordered[end + 1]] == values[ordered[position]]
        ):
            end += 1

        average = (position + end) / 2 + 1
        for index in range(position, end + 1):
            ranks[ordered[index]] = average

        position = end + 1

    return ranks


def spearman(xs: list, ys: list):
    """
    순위 상관계수. Gemini 점수는 5점/10점 단위로 뚝뚝 끊기고 눈금 간격이
    고르다는 보장도 없으므로, 값 자체보다 순위를 보는 편이 정직하다.
    """

    if len(xs) != len(ys):
        raise ValueError("두 계열의 길이가 다릅니다.")

    if len(xs) < 2:
        return None

    x = _as_floats(xs)
    y = _as_floats(ys)

    if len(set(x)) < 2 or len(set(y)) < 2:
        return None

    return pearson(_ranks(x), _ranks(y))


def compare_groups(flags: list, quality: list) -> dict:
    """
    불리언 check는 상관계수보다 "통과한 scene과 실패한 scene의 품질
    차이"로 보는 편이 읽기 쉽다. 한쪽 그룹이 비어 있으면 비교 자체가
    불가능하므로 gap을 None으로 두고 comparable=False로 표시한다.
    """

    if len(flags) != len(quality):
        raise ValueError("두 계열의 길이가 다릅니다.")

    passed = [q for flag, q in zip(flags, quality) if flag]
    failed = [q for flag, q in zip(flags, quality) if not flag]

    if not passed or not failed:
        return {
            "comparable": False,
            "passed_count": len(passed),
            "failed_count": len(failed),
            "passed_mean": statistics.fmean(passed) if passed else None,
            "failed_mean": statistics.fmean(failed) if failed else None,
            "gap": None,
            "p_value": None,
        }

    passed_mean = statistics.fmean(passed)
    failed_mean = statistics.fmean(failed)

    try:
        p_value = permutation_p_value(failed, passed)
    except ValueError:
        # 표본이 너무 커서 전수 열거가 불가능한 경우. 근사로 바꾸지
        # 않고 없는 것으로 둔다.
        p_value = None

    return {
        "comparable": True,
        "passed_count": len(passed),
        "failed_count": len(failed),
        "passed_mean": passed_mean,
        "failed_mean": failed_mean,
        "gap": passed_mean - failed_mean,
        "p_value": p_value,
    }


def correlate(observations: list, features: tuple, target: str) -> dict:
    """
    각 feature가 target(실제 품질)을 얼마나 설명하는지 계산한다.

    observations는 scene 하나가 한 항목이며, feature와 target을 같은
    dict에 담고 있어야 한다.
    """

    if not observations:
        raise ValueError("관측치가 비어 있습니다.")

    target_values = [float(row[target]) for row in observations]
    target_summary = describe_series(target_values)

    result = {}

    for feature in features:

        values = [float(row[feature]) for row in observations]
        summary = describe_series(values)

        result[feature] = {
            **summary,
            "pearson": pearson(values, target_values),
            "spearman": spearman(values, target_values),
            "target": target_summary,
        }

    return result


def recommend_objective(analysis: dict) -> dict:
    """
    상관 분석 결과를 "이 루브릭을 최적화 목적함수로 쓸 수 있는가"로
    옮긴다.

    쓸 수 있으려면 최소한 하나의 항목이 (1) 실제로 변동하고
    (2) 품질과 의미 있는 상관을 가져야 한다. 변동하지 않는 항목은
    올릴 수도 없고 올려도 아무 일이 일어나지 않는다.
    """

    varying = [
        name for name, entry in analysis.items() if entry.get("varies")
    ]

    predictors = [
        name
        for name in varying
        if abs(analysis[name].get("pearson") or 0.0)
        >= MIN_PREDICTIVE_CORRELATION
        or abs(analysis[name].get("spearman") or 0.0)
        >= MIN_PREDICTIVE_CORRELATION
    ]

    if not varying:
        return {
            "usable": False,
            "predictors": [],
            "constant_checks": sorted(analysis),
            "reason": (
                "모든 항목이 상수라 변동이 없습니다. 변동하지 않는 점수는 "
                "올릴 수도 없고, 올려도 산출물이 달라지지 않습니다."
            ),
        }

    constant = sorted(set(analysis) - set(varying))

    if not predictors:
        return {
            "usable": False,
            "predictors": [],
            "constant_checks": constant,
            "reason": (
                f"변동하는 항목({', '.join(sorted(varying))})은 있지만 "
                f"실제 품질과의 상관이 |r| < {MIN_PREDICTIVE_CORRELATION}로 "
                f"약합니다. 이 점수를 올려도 품질이 따라 오른다는 근거가 "
                f"없습니다."
            ),
        }

    return {
        "usable": True,
        "predictors": sorted(predictors),
        "constant_checks": constant,
        "reason": (
            f"{', '.join(sorted(predictors))}이(가) 품질과 의미 있는 상관을 "
            f"가집니다. 목적함수는 이 항목들만으로 다시 정의해야 합니다 - "
            f"상수 항목({', '.join(constant) or '없음'})은 점수를 채우기만 "
            f"할 뿐 최적화의 방향을 주지 못합니다."
        ),
    }
