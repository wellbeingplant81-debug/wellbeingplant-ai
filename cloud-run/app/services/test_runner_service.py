"""
Sprint56 - Test Runner Service (개발환경 최적화, 기능 변경 없음).

Sprint53~55에서 테스트를 돌릴 때마다 매번
"OUT=$(pwd)/test_output.log && ... > $OUT 2>&1; grep ...; rm -f $OUT"
식으로 즉석 Bash를 짜던 걸 대체한다. 이 프로젝트의 고정 venv
파이썬(.venv/Scripts/python.exe)으로 unittest를 돌리고, 결과를 구조화된
요약(dict)으로 돌려준다 - 파이프라인/영상 생성 로직은 전혀 건드리지
않는다.
"""

import os
import re
import subprocess
import sys

_SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUD_RUN_DIR = os.path.dirname(os.path.dirname(_SERVICE_DIR))

_RAN_PATTERN = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s", re.MULTILINE)
_FAILED_PATTERN = re.compile(
    r"^FAILED \((?:failures=(\d+))?,?\s*(?:errors=(\d+))?\)", re.MULTILINE
)


def parse_unittest_summary(output: str) -> dict:
    """unittest의 표준 텍스트 출력(-v 여부 무관, stdout+stderr 합친 것도
    가능)에서 "Ran N tests in Xs" / "OK" 또는 "FAILED (failures=.., errors=..)"
    한 줄을 뽑아 구조화한다. 순수 함수 - 프로세스를 직접 실행하지 않는다."""

    ran_match = _RAN_PATTERN.search(output)
    ran = int(ran_match.group(1)) if ran_match else 0
    seconds = float(ran_match.group(2)) if ran_match else 0.0

    failed_match = _FAILED_PATTERN.search(output)

    if failed_match:
        failures = int(failed_match.group(1) or 0)
        errors = int(failed_match.group(2) or 0)
        ok = False
    else:
        failures = 0
        errors = 0
        ok = bool(ran_match) and "OK" in output

    return {
        "ran": ran,
        "seconds": seconds,
        "ok": ok,
        "failures": failures,
        "errors": errors,
    }


def _venv_python() -> str:

    candidate = os.path.join(CLOUD_RUN_DIR, ".venv", "Scripts", "python.exe")

    return candidate if os.path.exists(candidate) else sys.executable


def build_unittest_command(modules: list) -> list:
    """modules가 비어 있으면 tests/ 전체 discover, 아니면 지정된
    모듈들만 돌리는 명령 리스트를 만든다."""

    python = _venv_python()

    if not modules:
        return [python, "-m", "unittest", "discover", "-s", "tests"]

    return [python, "-m", "unittest", *modules]


def run_tests(modules: list = None) -> dict:
    """build_unittest_command()로 만든 명령을 CLOUD_RUN_DIR에서 실행하고,
    {"summary": parse_unittest_summary(...), "returncode": int,
    "raw_output": str}를 반환한다."""

    command = build_unittest_command(modules or [])

    result = subprocess.run(
        command,
        cwd=CLOUD_RUN_DIR,
        capture_output=True,
        text=True,
    )

    raw_output = result.stdout + result.stderr

    return {
        "summary": parse_unittest_summary(raw_output),
        "returncode": result.returncode,
        "raw_output": raw_output,
    }
