"""
Sprint195 - 자식의 말을 어떤 글자로 읽을지 밝혀 둔다 (전수).

Sprint194에서 러너가 두 번 죽었다. subprocess에게 "글자로 달라"고만
하고 어떤 인코딩인지 말하지 않으면, 파이썬은 로케일로 읽는다. 그런데
이 환경에는 PYTHONIOENCODING=utf-8이 이미 걸려 있어 자식은 UTF-8로
말한다. 둘이 어긋나면 읽는 스레드가 죽고, 받는 쪽은 None을 쥔다.

무서운 것은 이것이 자식이 한글을 낼 때만 - 즉 대개는 무언가 잘못됐을
때만 - 드러난다는 점이다. 정작 무엇이 잘못됐는지 알아야 하는 순간에
아무것도 못 보게 된다.

소스를 문자열로 훑지 않는다
---------------------------
"text=True"를 grep하면 이 파일의 설명 주석에도 걸린다. 호출식은
AST로 본다.

app/ 는 여기서 고치지 않았다
----------------------------
남은 자리는 전부 Provider/Render 계열이고, Sprint195는 그쪽 동작을
바꾸지 않기로 했다. 대신 몇 곳이 남아 있는지를 적어 둔다 - 새로
늘어나면 이 테스트가 알려 준다. 줄 번호가 아니라 개수로 세는 것은,
줄은 위아래가 바뀌기만 해도 달라지기 때문이다.
"""

import ast
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

CLOUD_RUN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP = {".venv", "__pycache__", ".git", "output", "dist", "build"}

MAKERS = {"run", "Popen", "check_output", "call", "check_call"}

# Sprint195에서 손대지 않기로 한 자리. 전부 ffmpeg/ffprobe를 부르는
# Provider/Render 계열이다. 고치려면 그 동작을 건드려도 된다는 허락이
# 먼저 있어야 한다.
LEFT_IN_APP = {
    "app/production/providers/voice_import.py": 1,
    "app/providers/elevenlabs_provider.py": 1,
    "app/services/asset_integration_service.py": 1,
    "app/services/audio_service.py": 2,
    "app/services/duration_optimizer.py": 3,
    "app/services/final_video_service.py": 1,
    "app/services/technical_validation_service.py": 1,
}


def _is_true(node):
    return isinstance(node, ast.Constant) and node.value is True


def _maker(node):
    """subprocess.run(...) 같은 호출인지 본다."""

    func = node.func

    if (isinstance(func, ast.Attribute) and func.attr in MAKERS
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"):
        return func.attr

    return None


def reads_without_saying_how(node) -> bool:
    """
    받아 두고, 글자로 달라고 했고, 어떤 글자인지는 말하지 않았다.

    셋이 겹칠 때만 로케일로 읽는다. 바이트로 받으면 우리가 읽는
    것이므로 여기 해당하지 않는다.
    """

    maker = _maker(node)

    if maker is None:
        return False

    asked = {kw.arg: kw.value for kw in node.keywords if kw.arg}

    captured = (_is_true(asked.get("capture_output"))
                or "stdout" in asked or "stderr" in asked
                or maker == "check_output")

    as_text = (_is_true(asked.get("text"))
               or _is_true(asked.get("universal_newlines")))

    return captured and as_text and "encoding" not in asked


def found_in(folder: str) -> dict:
    """{상대경로: 몇 곳}."""

    tally = {}

    for here, dirs, files in os.walk(os.path.join(CLOUD_RUN_DIR, folder)):
        dirs[:] = [d for d in dirs if d not in SKIP]

        for name in sorted(files):
            if not name.endswith(".py"):
                continue

            path = os.path.join(here, name)

            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())

            count = sum(1 for node in ast.walk(tree)
                        if isinstance(node, ast.Call)
                        and reads_without_saying_how(node))

            if count:
                where = os.path.relpath(path, CLOUD_RUN_DIR)
                tally[where.replace("\\", "/")] = count

    return tally


class TestTheScannerItself(unittest.TestCase):
    """세는 자가 틀리면 나머지 판정도 전부 틀린다."""

    def read(self, said):
        return [node for node in ast.walk(ast.parse(said))
                if isinstance(node, ast.Call)
                and reads_without_saying_how(node)]

    def test_it_catches_text_without_an_encoding(self):
        self.assertEqual(
            len(self.read("subprocess.run(cmd, capture_output=True,"
                          " text=True)")), 1)

    def test_it_lets_a_named_encoding_pass(self):
        self.assertEqual(
            len(self.read("subprocess.run(cmd, capture_output=True,"
                          " text=True, encoding='utf-8')")), 0)

    def test_it_lets_bytes_pass(self):
        """바이트로 받으면 우리가 읽는다 - 로케일이 끼어들지 않는다."""

        self.assertEqual(
            len(self.read("subprocess.run(cmd, capture_output=True)")), 0)

    def test_it_lets_an_uncaptured_run_pass(self):
        """안 받으면 부모의 화면으로 그냥 흘러간다."""

        self.assertEqual(len(self.read("subprocess.run(cmd, text=True)")), 0)

    def test_it_catches_the_old_spelling(self):
        self.assertEqual(
            len(self.read("subprocess.run(cmd, stdout=subprocess.PIPE,"
                          " universal_newlines=True)")), 1)

    def test_it_catches_popen_too(self):
        self.assertEqual(
            len(self.read("subprocess.Popen(cmd, stdout=subprocess.PIPE,"
                          " text=True)")), 1)

    def test_it_does_not_trip_on_words_in_comments(self):
        """
        소스를 문자열로 훑던 검사가 제 설명 주석에 걸린 적이 있다.
        """

        self.assertEqual(
            len(self.read("# subprocess.run(cmd, capture_output=True,"
                          " text=True)\nx = 1")), 0)


class TestNoneLeftInTests(unittest.TestCase):
    """tests/ 에는 한 곳도 남기지 않는다."""

    def test_every_test_says_how_it_reads(self):
        left = found_in("tests")

        self.assertEqual(
            left, {},
            "자식의 말을 어떤 글자로 읽을지 밝히지 않은 자리가 남았습니다. "
            "encoding='utf-8', errors='replace' 를 함께 적어 주십시오.")


class TestWhatWeLeftInApp(unittest.TestCase):
    """
    app/ 에 남긴 것은 세어 둔다.

    고치지 않기로 한 것과 잊어버린 것은 다르다. 개수가 달라지면
    누군가 새로 만들었거나 고친 것이고, 어느 쪽이든 여기서 한 번은
    보고 지나가야 한다.
    """

    def test_the_ledger_still_matches(self):
        self.assertEqual(found_in("app"), LEFT_IN_APP)


if __name__ == "__main__":
    unittest.main()
