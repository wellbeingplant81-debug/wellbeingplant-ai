"""
Sprint56 - Test Runner Service (개발환경 최적화, 기능 변경 없음).

Sprint53~55에서 테스트를 돌릴 때마다 매번
"OUT=$(pwd)/test_output.log && ... > $OUT 2>&1; grep ...; rm -f $OUT"
식으로 즉석 Bash를 짜던 걸 대체한다. 이 프로젝트의 고정 venv
파이썬(.venv/Scripts/python.exe)으로 unittest를 돌리고, 결과를 구조화된
요약(dict)으로 돌려준다 - 파이프라인/영상 생성 로직은 전혀 건드리지
않는다.
"""

import locale
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


def decode_line(line: bytes) -> str:
    """
    한 줄을 읽어 낸다. UTF-8 먼저, 그 다음 로케일.

    순서가 중요하다. UTF-8 한글은 cp949로도 '읽히기는' 한다 - 엉뚱한
    한자로. 그러면 깨진 줄 모르고 지나간다. 반대로 cp949 한글은 UTF-8로
    거의 언제나 읽히지 않으므로, UTF-8을 먼저 대 보면 각 줄이 제
    주인에게 간다.

    둘 다 아니면 그때는 글자를 잃더라도 읽는다. 여기서 예외를 내면
    윗줄과 아랫줄까지 통째로 못 보게 된다.
    """

    for codec in ("utf-8", locale.getpreferredencoding(False)):
        try:
            return line.decode(codec)
        except (UnicodeDecodeError, LookupError):
            continue

    return line.decode("utf-8", errors="replace")


def decode_output(raw: bytes) -> str:
    """
    Sprint194 - 자식이 낸 바이트를 글로 바꾼다.

    한 스트림에 인코딩이 둘 섞일 수 있다. 자식 unittest는 로케일로
    쓰는데, 파이프를 물려받은 손자(ffmpeg 같은 것)는 제 인코딩으로
    쓰기 때문이다. 그건 우리가 정할 수 있는 것이 아니다.

    그래서 한 줄씩 본다. 줄 하나는 대개 한 사람이 쓴 것이라, 줄 단위로
    고르면 둘 다 살릴 수 있다.

    자식에게 "UTF-8로 말하라"고 시키지 않는다. 그 지시는 손자에게까지
    내려가고, 손자의 말을 로케일로 읽고 있던 다른 테스트가 대신
    깨진다 - Sprint194에서 실제로 그렇게 만들었다가 되돌렸다.
    """

    if not raw:
        return ""

    return "".join(decode_line(line) for line in raw.splitlines(keepends=True))


def run_tests(modules: list = None) -> dict:
    """build_unittest_command()로 만든 명령을 CLOUD_RUN_DIR에서 실행하고,
    {"summary": parse_unittest_summary(...), "returncode": int,
    "raw_output": str}를 반환한다.

    Sprint194 - 바이트로 받아 우리가 읽는다.

    subprocess에게 글자로 달라고 하면(text=True) 로케일로 읽다가,
    한글 traceback이 나오는 순간 - 즉 테스트가 깨졌을 때만 - 읽는
    스레드가 죽는다. stdout/stderr가 None이 되어, 정작 무엇이
    실패했는지를 못 본다. Sprint192/193에서 두 번 그랬다.

    글자 몇 개가 깨져도 요약과 traceback은 남는다 - 아무것도 못 보는
    것보다 낫다.
    """

    command = build_unittest_command(modules or [])

    result = subprocess.run(
        command,
        cwd=CLOUD_RUN_DIR,
        capture_output=True,
    )

    raw_output = decode_output(result.stdout) + decode_output(result.stderr)

    return {
        "summary": parse_unittest_summary(raw_output),
        "returncode": result.returncode,
        "raw_output": raw_output,
    }
