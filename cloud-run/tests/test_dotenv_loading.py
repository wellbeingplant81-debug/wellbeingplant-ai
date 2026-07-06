import os
import subprocess
import sys
import tempfile
import unittest

CLOUD_RUN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(CLOUD_RUN_ROOT, ".env")


class TestDotenvLoading(unittest.TestCase):
    """
    app/__init__.py의 load_dotenv() 배선이 실제로 동작하는지 확인한다.
    이미 import된 app 패키지를 재사용하면(모듈 캐시) 검증이 안 되므로,
    항상 새 인터프리터 프로세스로 "import app"부터 다시 실행한다.
    """

    def setUp(self):
        # 실제 개발자의 cloud-run/.env(진짜 API Key 등)가 이미 있을 수
        # 있으므로 절대 그냥 지우지 않는다 - 내용을 백업해두고 테스트가
        # 끝나면 원래대로 복원한다(없었다면 없는 채로 복원).
        self._backup = None

        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, "rb") as f:
                self._backup = f.read()

        self.addCleanup(self._restore_env_file)

    def _restore_env_file(self):
        if self._backup is not None:
            with open(ENV_PATH, "wb") as f:
                f.write(self._backup)
        elif os.path.exists(ENV_PATH):
            os.remove(ENV_PATH)

    def _probe(self, cwd):
        env = dict(os.environ)
        env.pop("SPRINT36_DOTENV_PROBE", None)
        env["PYTHONPATH"] = CLOUD_RUN_ROOT

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import app, os; "
                "print(os.getenv('SPRINT36_DOTENV_PROBE', 'MISSING'))",
            ],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
        )

        return result.stdout.strip()

    def test_env_file_is_loaded_regardless_of_caller_cwd(self):
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write("SPRINT36_DOTENV_PROBE=loaded_from_env_file\n")

        with tempfile.TemporaryDirectory() as other_cwd:
            output = self._probe(cwd=other_cwd)

        self.assertEqual(output, "loaded_from_env_file")

    def test_missing_env_file_does_not_break_import(self):
        output = self._probe(cwd=CLOUD_RUN_ROOT)

        self.assertEqual(output, "MISSING")

    def test_real_env_var_is_never_overridden_by_env_file(self):
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write("SPRINT36_DOTENV_PROBE=from_env_file\n")

        env = dict(os.environ)
        env["PYTHONPATH"] = CLOUD_RUN_ROOT
        env["SPRINT36_DOTENV_PROBE"] = "from_real_process_env"

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import app, os; "
                "print(os.getenv('SPRINT36_DOTENV_PROBE', 'MISSING'))",
            ],
            cwd=CLOUD_RUN_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout.strip(), "from_real_process_env")


if __name__ == "__main__":
    unittest.main()
