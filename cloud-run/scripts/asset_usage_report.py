import argparse
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_feedback_service  # noqa: E402


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

    print(f"전체 scene 수 : {total}")
    print(f"스톡(Pexels/Pixabay) 사용률 : {summary['stock_rate']:.1%}")
    print(f"AI Image 폴백률            : {summary['fallback_rate']:.1%}")
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


def main():

    sys.stdout.reconfigure(encoding="utf-8")

    build_parser().parse_args()

    records = asset_feedback_service.load_all()
    summary = asset_feedback_service.summarize_usage(records)

    print_report(summary)

    sys.exit(0)


if __name__ == "__main__":
    main()
