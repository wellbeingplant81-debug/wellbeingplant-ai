import argparse
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import runtime_paths  # noqa: E402
from app.services import asset_feedback_service  # noqa: E402
from app.tools import asset_dataset  # noqa: E402


def build_parser():

    return argparse.ArgumentParser(
        description=(
            "asset_feedback_service.json에 누적된 이력으로 "
            "Pexels/Pixabay/AI Image의 실제 사용률을 집계합니다."
        ),
    )


def print_report(summary: dict):

    total = summary["total"]

    if total == 0:
        print(
            "누적된 feedback 이력이 없습니다 "
            f"({asset_feedback_service.DEFAULT_FEEDBACK_PATH}). "
            "파이프라인을 몇 건 실행한 뒤 다시 확인하세요."
        )
        return

    outcome_counts = summary.get("outcome_counts", {})
    ai_image_count = summary["by_provider"].get("ai_image", {}).get("count", 0)
    pexels_image_count = summary["by_provider"].get("pexels_image", {}).get("count", 0)
    pexels_video_count = summary["by_provider"].get("pexels_video", {}).get("count", 0)

    print(f"전체 scene 수 : {total}")
    print(f"스톡(Pexels/Pixabay) 사용률 : {summary['stock_rate']:.1%}")
    print(f"AI Image 사용률            : {summary['fallback_rate']:.1%}")
    print()
    print(f"AI Image 개수    : {ai_image_count}")
    print(f"Pexels Image 개수 : {pexels_image_count}")
    print(f"Pexels Video 개수 : {pexels_video_count}")
    print(f"Fallback 개수    : {outcome_counts.get('fallback', 0)} "
          f"(AI 우선 품질 게이트 통과: {outcome_counts.get('ai_priority', 0)})")
    print(
        "예상 AI 생성 비용 절감률 : "
        f"{summary['estimated_ai_cost_savings_rate']:.1%} "
        "(전량 AI 생성 대비)"
    )
    print()

    headers = ["Provider", "Count", "Rate"]
    rows = [
        [provider, str(stats["count"]), f"{stats['rate']:.1%}"]
        for provider, stats in sorted(
            summary["by_provider"].items(),
            key=lambda item: item[1]["count"],
            reverse=True,
        )
    ]

    widths = [
        max(len(str(row[i])) for row in ([headers] + rows))
        for i in range(len(headers))
    ]

    def format_row(row):
        return " | ".join(
            str(cell).ljust(widths[i]) for i, cell in enumerate(row)
        )

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))

    for row in rows:
        print(format_row(row))


def dataset_path() -> str:
    """쌓인 관측이 사는 자리. 파이프라인이 쓰는 그 자리다."""

    return os.path.join(
        runtime_paths.dataset_root(), asset_dataset.DATASET_FILENAME,
    )


def print_footage_report(summary: dict, where: str):
    """
    Sprint229 - 고른 영상이 그 장면을 어떻게 채웠는가.

    Sprint227이 프로젝트마다 남기기 시작한 것을 여러 편에 걸쳐 센다.
    알고 싶은 것은 hold다 - 받아 온 영상이 scene보다 많이 짧아 마지막
    프레임을 붙잡은 scene이고, 그 scene은 영상을 골랐는데도 사실상
    정지 사진으로 되돌아간다.

    분모는 영상을 쓴 scene뿐이다. 그림 scene을 섞으면 비율이 뜻을
    잃는다.
    """

    print()
    print("고른 영상이 그 장면을 어떻게 채웠는가")

    total = summary.get("footage_scenes") or 0

    if not total:
        print(f"  아직 영상을 쓴 scene이 없습니다 ({where}).")
        print("  스톡 영상이나 내 자료 영상으로 몇 편 만든 뒤 다시 "
              "확인하세요.")
        return

    stock = summary.get("footage_stock", 0)
    local = summary.get("footage_local", 0)

    print(f"  영상 scene 수 : {total}")
    print(f"    스톡 영상   : {stock}")
    print(f"    내 자료 영상 : {local}")

    other = total - stock - local

    if other:
        # 둘 중 어느 쪽도 아닌 것이 있으면 조용히 삼키지 않는다 -
        # 합이 안 맞는 표를 보고 사람이 먼저 눈치채는 것이 가장 나쁘다.
        print(f"    그 밖       : {other}")

    print()
    print(f"  trim (한 번에 덮음)      : {summary.get('footage_trim', 0)}")
    print(f"  loop (되풀이해서 덮음)   : {summary.get('footage_loop', 0)}")
    print(f"  hold (마지막 프레임 정지) : {summary.get('footage_hold', 0)}")

    rate = summary.get("footage_hold_rate")

    if rate is not None:
        print(f"  hold 비율 : {rate:.1f}%  <- 사실상 정지 사진으로 "
              "되돌아간 scene")


def main():

    sys.stdout.reconfigure(encoding="utf-8")

    build_parser().parse_args()

    records = asset_feedback_service.load_all()
    summary = asset_feedback_service.summarize_usage(records)

    print_report(summary)

    # Sprint229 - 같은 자리에서 이어 적는다. 새 화면을 만들지 않는다.
    where = dataset_path()
    print_footage_report(
        asset_dataset.summarize(asset_dataset.load(where)), where,
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
