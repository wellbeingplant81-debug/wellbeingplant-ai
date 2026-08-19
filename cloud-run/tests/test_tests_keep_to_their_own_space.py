"""
Sprint231 - 시험은 제 자리에서만 논다 (Epic 67, Phase 2).

무엇을 찾으러 갔고 무엇을 찾았나
--------------------------------
Sprint230 회귀에서 처음으로 반복 결과가 갈렸다(3회 중 1회,
test_deployment.test_render_complete_from_release_bundle). 묶인 exe 를
실제로 띄우는 시험이라 "공유 자리를 쓰는 것 아닌가"를 의심했다.

실측한 결과는 그 의심과 달랐다.

    묶인 exe 시험      이미 제 임시 집을 쓴다(AI_STUDIO_HOME 을 자식에게
                       넘기고 PATH 도 비운다). 같은 시험 두 개를 동시에
                       돌려도 둘 다 통과했다.
    %APPDATA%          오늘 하루 아무것도 생기지 않았다.
    저장소 output/     여기가 진짜였다 - 오늘 20개가 생겼다.

그 20개는 전부 Sprint226 이전 시각이다. POST /api/jobs 가 띄운 작업
스레드가 실제 파이프라인을 돌리며 프로젝트를 만들고 있었고, Sprint226
이 그 문을 닫으면서 함께 멈췄다. 지금 회귀는 0개를 만든다(전수 확인).

그래서 이 회차가 하는 일
------------------------
고칠 것이 아니라 **되돌아오지 못하게 잠그는 것**이다. 이번 세션에서
회귀가 두 번 흔들렸고 두 번 다 같은 모양이었다.

    Sprint226   남의 임시 집에 .dataset 을 만든 스레드
    Sprint231   저장소 output/ 에 프로젝트를 만든 작업

둘 다 "시험이 제 자리 밖에 쓴다"이고, 둘 다 그때는 아무도 몰랐다.
여기서 그것을 본다.

여기서 보는 것의 한계
---------------------
이 시험은 **제 앞에서 돈 것들**만 볼 수 있다(같은 프로세스에서 먼저
끝난 시험들). 뒤에 오는 것까지 보려면 회기 전체를 감시하는 자리가
필요하고, 그것은 시험이 아니라 러너의 일이다. 반쪽이라도 두는 이유는,
이번에 걸린 두 건이 전부 앞쪽에서 났기 때문이다.
"""

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import runtime_paths

HERE = os.path.dirname(os.path.abspath(__file__))
CLOUD_RUN = os.path.dirname(HERE)

# 저장소 안의 산출물 자리. 개발 중에는 runtime_paths.output_root() 가
# 이 상대 경로를 돌려준다 - AI_STUDIO_HOME 을 주지 않은 채 프로젝트를
# 만들면 여기 쌓인다.
REPO_OUTPUT = os.path.join(CLOUD_RUN, "output")


def _listing(where):
    try:
        return set(os.listdir(where))
    except Exception:
        return set()


# ── 회기가 시작될 때 찍어 둔다 ──────────────────────────────────
#
# 들일 때 잰다. pytest 는 시험을 돌리기 전에 모든 모듈을 먼저 들이므로,
# 이 값은 "아무 시험도 돌기 전"의 모습이다. 그리고 그때는 아직 아무도
# AI_STUDIO_HOME 을 바꿔 놓지 않았으므로 사람의 진짜 집을 가리킨다.
BEFORE_REPO_OUTPUT = _listing(REPO_OUTPUT)

REAL_HOME = runtime_paths.home()
BEFORE_REAL_HOME_OUTPUT = _listing(os.path.join(REAL_HOME, "output"))


class NothingIsWrittenOutsideItsOwnSpaceTest(unittest.TestCase):
    """
    시험이 제 임시 자리 밖에 쓰면 여기서 걸린다.
    """

    def test_no_project_appeared_in_the_repository(self):
        """
        Sprint226 이전에는 여기에 쌓이고 있었다 - 회귀를 한 번 돌 때마다
        실제 프로젝트 폴더가 늘었고, 같은 초에 두 번 만들면 이름까지
        부딪혔다.
        """

        fresh = _listing(REPO_OUTPUT) - BEFORE_REPO_OUTPUT

        self.assertEqual(
            fresh, set(),
            "저장소 output/ 에 새로 생겼습니다. 어떤 시험이 "
            "AI_STUDIO_HOME 없이 프로젝트를 만들었습니다: "
            + ", ".join(sorted(fresh)))

    def test_nothing_appeared_in_the_persons_own_place(self):
        """
        사람이 실제로 쓰는 자리다. 시험이 여기 쓰면 그 사람의 목록에
        검사용 프로젝트가 섞인다.
        """

        fresh = _listing(
            os.path.join(REAL_HOME, "output")) - BEFORE_REAL_HOME_OUTPUT

        self.assertEqual(
            fresh, set(),
            "사람의 자리에 새로 생겼습니다: " + ", ".join(sorted(fresh)))

    def test_the_place_we_watch_is_the_place_the_product_uses(self):
        """
        보는 자리가 틀리면 아무것도 못 본다. 제품이 쓰는 그 함수로
        구한 자리인지 확인한다.
        """

        self.assertEqual(
            os.path.normcase(os.path.abspath(REPO_OUTPUT)),
            os.path.normcase(os.path.abspath(
                os.path.join(CLOUD_RUN, runtime_paths.output_root()))),
        )


def _calls(tree):
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == name:
            return node

    return None


def _read(where):
    with open(where, encoding="utf-8") as f:
        return ast.parse(f.read())


class TheBundledExeAlwaysGetsItsOwnHomeTest(unittest.TestCase):
    """
    묶인 exe 를 띄우는 자리는 하나다(test_deployment.Running). 거기서
    제 집을 주지 않으면 그 프로그램은 사람의 %APPDATA% 에 쓴다.
    """

    def setUp(self):
        self.tree = _read(os.path.join(HERE, "test_deployment.py"))

    def test_there_is_only_one_place_that_starts_it(self):
        """
        두 곳이 되면 한쪽만 고쳐지는 날이 온다. 지금은 rc_final_check 도
        이것을 가져다 쓴다.
        """

        with open(os.path.join(HERE, "test_rc_final_check.py"),
                  encoding="utf-8") as f:
            other = f.read()

        self.assertIn("from tests.test_deployment import Running", other)

    def test_it_hands_the_child_an_environment(self):
        running = None

        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == "Running":
                running = node
                break

        self.assertIsNotNone(running, "띄우는 자리를 찾지 못했다")

        popen = [
            node for node in _calls(running)
            if isinstance(node.func, ast.Attribute)
            and node.func.attr == "Popen"
        ]

        self.assertEqual(len(popen), 1)

        given = {word.arg for word in popen[0].keywords}

        self.assertIn("env", given,
                      "제 환경을 주지 않으면 사람의 자리를 쓴다")

    def test_that_environment_names_the_home(self):
        clean = _function(self.tree, "clean_env")

        self.assertIsNotNone(clean)

        written = [
            node for node in ast.walk(clean)
            if isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
        ]

        self.assertIn(
            runtime_paths.HOME_ENV,
            {node.slice.value for node in written},
            "AI_STUDIO_HOME 을 적어 주지 않는다")

    def test_the_home_it_names_is_the_one_the_product_reads(self):
        """
        글자를 따로 적어 두면 제품이 이름을 바꾸는 날 조용히 어긋난다.
        """

        self.assertEqual(runtime_paths.HOME_ENV, "AI_STUDIO_HOME")


def _built() -> bool:
    from tests import test_deployment

    return os.path.isfile(test_deployment.EXE)


@unittest.skipUnless(_built(), "묶은 것이 없다")
class TwoAtOnceDoNotCollideTest(unittest.TestCase):
    """
    같은 프로그램 둘을 나란히 켜 본다.

    격리는 "코드가 그렇게 생겼다"가 아니라 "둘이 동시에 돌아도 서로를
    안 깨뜨린다"로 확인해야 한다. 실제로 이번 회차에서 이 시험 파일
    전체를 두 벌 동시에 돌려 둘 다 통과하는 것을 보았고, 여기서는 그
    핵심만 회귀 안에 남긴다 - 두 벌을 매번 돌리면 회귀가 5분 길어진다.
    """

    def setUp(self):
        import shutil
        import tempfile

        from tests.test_deployment import EXE, Running

        self.EXE = EXE
        self.Running = Running

        self.work = tempfile.mkdtemp(prefix="동시검사_")
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

        self.running = []
        self.addCleanup(self._stop_all)

    def _stop_all(self):
        for one in self.running:
            try:
                one.stop()
            except Exception:
                pass

    def _start(self, name):
        home = os.path.join(self.work, name)

        one = self.Running(self.EXE, home)
        self.running.append(one)

        return home, one

    def test_two_copies_live_side_by_side(self):
        first_home, first = self._start("가")
        second_home, second = self._start("나")

        self.assertIsNotNone(first.url, f"첫째가 안 켜졌다: {first.said}")
        self.assertIsNotNone(second.url, f"둘째가 안 켜졌다: {second.said}")

        # 포트를 고정하지 않으므로 서로 다른 자리에 앉는다.
        self.assertNotEqual(first.url, second.url)

        # 둘 다 실제로 응답한다 - 하나가 다른 하나를 밀어내지 않았다.
        self.assertIsNotNone(first.page(), "첫째가 화면을 안 준다")
        self.assertIsNotNone(second.page(), "둘째가 화면을 안 준다")

    def test_each_one_writes_only_in_its_own_place(self):
        first_home, first = self._start("가")
        second_home, second = self._start("나")

        self.assertIsNotNone(first.url)
        self.assertIsNotNone(second.url)

        for home in (first_home, second_home):
            with self.subTest(home=os.path.basename(home)):
                # 켜면서 제 집을 차린다(launcher._prepare_home).
                self.assertTrue(
                    os.path.isdir(os.path.join(home, "output")),
                    f"제 집을 차리지 않았다: {home}")

    def test_neither_touched_the_shared_places(self):
        """
        이 회차의 물음 그대로다 - 둘을 동시에 켜도 저장소와 사람의
        자리는 그대로여야 한다.
        """

        before_repo = _listing(REPO_OUTPUT)
        before_real = _listing(os.path.join(REAL_HOME, "output"))

        first_home, first = self._start("가")
        second_home, second = self._start("나")

        self.assertIsNotNone(first.url)
        self.assertIsNotNone(second.url)

        self.assertEqual(_listing(REPO_OUTPUT), before_repo)
        self.assertEqual(
            _listing(os.path.join(REAL_HOME, "output")), before_real)


if __name__ == "__main__":
    unittest.main()
