"""
Sprint56 - 전체/일부 unittest를 돌리고 깔끔한 요약만 출력한다.

사용법:
  .venv/Scripts/python.exe scripts/run_tests.py
      -> tests/ 전체 discover

  .venv/Scripts/python.exe scripts/run_tests.py tests.test_video_builder tests.test_bgm_service
      -> 지정된 모듈만
"""

import argparse
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.test_runner_service import run_tests  # noqa: E402


def build_parser():

    return argparse.ArgumentParser(
        description="tests/ 전체 또는 지정된 모듈만 돌리고 요약을 출력합니다.",
    )


def main():

    sys.stdout.reconfigure(encoding="utf-8")

    parser = build_parser()
    parser.add_argument(
        "modules",
        nargs="*",
        help="예: tests.test_video_builder tests.test_bgm_service (생략 시 전체)",
    )
    args = parser.parse_args()

    result = run_tests(args.modules)
    summary = result["summary"]

    if not summary["ok"]:
        print(result["raw_output"])

    status = "OK" if summary["ok"] else "FAILED"
    print(
        f"{status} - ran={summary['ran']} "
        f"failures={summary['failures']} errors={summary['errors']} "
        f"time={summary['seconds']:.2f}s"
    )

    sys.exit(result["returncode"])


if __name__ == "__main__":
    main()
