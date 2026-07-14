"""
Sprint56 - 실제 파이프라인을 1회 실행하고(E2E), 끝나면 바로 QA 리포트를
출력한다. Sprint53~55에서 매번
"nohup .venv/Scripts/python.exe -c '...' > log 2>&1 & disown" 후
직접 PID를 폴링하던 패턴을 대체한다.

이 스크립트는 끝날 때까지 블로킹된다(수 분 소요) - Bash 도구의
run_in_background=true로 이 스크립트 자체를 호출하면, 셸 레벨
백그라운딩(nohup/&/disown) 없이도 하네스가 프로세스를 정확히 추적하고
완료 알림을 준다.

사용법:
  .venv/Scripts/python.exe scripts/run_e2e.py "주제 문자열" --channel wellbeing
  .venv/Scripts/python.exe scripts/run_e2e.py "주제 문자열" --profile upload

Sprint100-1 - --profile을 주면 ProductionProfile(ENABLE_PRODUCTION_
PROFILE)을 이 프로세스 안에서만 켜고 그 이름으로 생성한다(development/
upload). 생략하면 이전과 완전히 동일하게(ProductionProfile 비활성) 동작한다.
"""

import argparse
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config  # noqa: E402
from app.services.factory_service import generate_short_video  # noqa: E402
from app.services.qa_report_service import build_qa_report, format_report  # noqa: E402


def build_parser():

    return argparse.ArgumentParser(
        description="실제 파이프라인을 1회 실행하고 QA 리포트까지 출력합니다.",
    )


def main():

    sys.stdout.reconfigure(encoding="utf-8")

    parser = build_parser()
    parser.add_argument("topic", help="영상 주제")
    parser.add_argument("--channel", default="wellbeing")
    parser.add_argument(
        "--profile",
        default=None,
        choices=["development", "upload"],
        help="ProductionProfile 이름. 주면 ENABLE_PRODUCTION_PROFILE을 켠다.",
    )
    args = parser.parse_args()

    if args.profile is not None:
        config.ENABLE_PRODUCTION_PROFILE = True

    if args.profile == "upload":
        # Sprint100-2 - Motion Contract는 기본 False인 kill switch다.
        # --profile upload로 명시적으로 실행할 때만 이 프로세스 안에서
        # 켠다 - ENABLE_PRODUCTION_PROFILE과 동일한 in-process opt-in
        # 패턴(전역 상태를 서버 요청 간에 뒤집지 않음).
        config.ENABLE_MOTION_CONTRACT = True

    result = generate_short_video(
        args.topic, channel=args.channel, production_profile_name=args.profile,
    )

    print("RESULT:", result)

    report = build_qa_report(result["output"])

    print()
    print(format_report(report))

    sys.exit(0 if report["target_range_ok"] else 1)


if __name__ == "__main__":
    main()
