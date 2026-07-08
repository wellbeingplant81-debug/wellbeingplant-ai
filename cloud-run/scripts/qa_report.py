"""
Sprint56 - 실제 생성된 project 산출물(output/<id>/)의 QA 리포트를
출력한다. Sprint53~55에서 매번 즉석 ffprobe 반복문 + quality_report.json
파싱으로 하던 걸 대체한다 - 영상 생성 로직은 전혀 건드리지 않고 이미
만들어진 결과물만 읽는다.

사용법:
  .venv/Scripts/python.exe scripts/qa_report.py output/20260708_145700
"""

import argparse
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.qa_report_service import build_qa_report, format_report  # noqa: E402


def build_parser():

    return argparse.ArgumentParser(
        description="project_path의 실제 산출물을 ffprobe/quality_report.json 기준으로 리포트합니다.",
    )


def main():

    sys.stdout.reconfigure(encoding="utf-8")

    parser = build_parser()
    parser.add_argument("project_path", help="예: output/20260708_145700")
    args = parser.parse_args()

    report = build_qa_report(args.project_path)

    print(format_report(report))

    sys.exit(0 if report["target_range_ok"] else 1)


if __name__ == "__main__":
    main()
