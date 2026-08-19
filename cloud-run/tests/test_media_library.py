"""
Sprint231 - 자료가 어디 있고 무엇이 있는지 화면이 말한다 (Epic 69).

무엇이 있었나
-------------
사람이 보는 것은 "배경음악 없음" 한 줄이었다. 어디서 받아 어디에
넣어야 하는지는 어디에도 없었다 - 폴더 구조를 아는 사람만 쓸 수 있는
프로그램이었다.

무엇을 새로 만들지 않았는가
---------------------------
    저장소   free_workspace.json 그대로. 새 DB 를 만들지 않았다.
    개수     free_workspace.inventory 가 이미 센다.
    판정     final_check 그대로. 개수는 판정이 아니다.

배경음악만 다른 자리를 본다
---------------------------
자료 폴더 아래의 music 과, 렌더가 실제로 쓰는 자리는 **같은 곳이
아니다**. runtime_paths.music_root 는 이 순서로 본다.

    1. AI_STUDIO_BGM
    2. <사용자 자리>/music
    3. <프로그램>/assets/music

자료 폴더의 music 개수를 "BGM N개"로 보여 주면, 12개 있다고 해놓고
렌더가 "배경음악이 없습니다"로 죽는다. 그래서 배경음악만은
/studio/api/about 이 주는 것(렌더가 보는 그 자리)을 쓴다.

효과음은 없다
-------------
local_library.KINDS 는 (images, videos, music, voice) 넷이다. 효과음을
읽는 provider 도, 렌더에서 쓰는 자리도 없다. 그래서 폴더를 만들지
않고 "준비 중"이라고만 적는다 - 눌러도 아무 데도 쓰이지 않는 폴더를
열어 주는 것이 가장 나쁜 거짓말이다.
"""

import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import host_desktop

from app.services import free_workspace, local_library

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _page() -> str:
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _markup() -> str:
    """
    주석을 걷어낸 화면. 설명이 가드를 속이지 않게 한다.

    Sprint232 - 덩어리 주석(슬래시-별)도 걷는다. 줄 주석만 걷던 때,
    무엇을 고쳤는지 설명한 주석 안에 잘못된 읽기의 이름을 그대로 적어
    두었더니 "그 이름을 쓰지 않는다"는 가드가 제 설명에 걸렸다. 같은
    일을 이 저장소에서 두 번 겪었다.
    """

    page = re.sub(r"(?m)^[ \t]*//.*$", "", _page())

    return re.sub(r"/\*.*?\*/", "", page, flags=re.S)


def _block(page: str, start: str, length: int = 2600) -> str:
    at = page.index(start)

    return page[at:at + length]


class TheEngineKnowsFourKindsTest(unittest.TestCase):
    """화면이 보여 주는 종류가 엔진이 아는 것과 같아야 한다."""

    def test_종류는_넷이고_효과음은_없다(self):
        self.assertEqual(set(local_library.KINDS),
                         {"images", "videos", "music", "voice"})

        self.assertNotIn("sfx", local_library.KINDS)
        self.assertNotIn("effects", local_library.KINDS)


class TheCountsComeFromWhatIsAlreadyThereTest(unittest.TestCase):
    """개수를 새로 세지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _put(self, folder: str, names) -> None:
        where = os.path.join(self.root, folder)
        os.makedirs(where, exist_ok=True)

        for name in names:
            with open(os.path.join(where, name), "wb") as f:
                f.write(b"0")

    def test_빈_폴더는_전부_0(self):
        counts = free_workspace.inventory(self.root)

        self.assertEqual(set(counts), set(local_library.KINDS))
        self.assertTrue(all(v == 0 for v in counts.values()), counts)

    def test_이미지와_영상을_센다(self):
        self._put("images", ["1.png", "2.jpg", "메모.txt"])
        self._put("videos", ["a.mp4"])

        counts = free_workspace.inventory(self.root)

        self.assertEqual(counts["images"], 2, "확장자가 아닌 것은 세지 않는다")
        self.assertEqual(counts["videos"], 1)

    def test_없는_폴더로_물어도_던지지_않는다(self):
        counts = free_workspace.inventory(os.path.join(self.root, "없는곳"))

        self.assertTrue(all(v == 0 for v in counts.values()))


class TheDoorOpensOnlyOurFoldersTest(unittest.TestCase):
    """
    문이 아무 데나 열면, 화면의 실수 하나로 이 프로그램이 남의 폴더를
    여는 도구가 된다.
    """

    def setUp(self):
        self.allowed = tempfile.mkdtemp()
        self.outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.allowed, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.outside, ignore_errors=True)

        self.bridge = host_desktop.Bridge()

        self._real = host_desktop.Bridge._allowed
        host_desktop.Bridge._allowed = staticmethod(
            lambda wanted: wanted == os.path.abspath(self.allowed)
            or wanted.startswith(os.path.abspath(self.allowed) + os.sep))
        self.addCleanup(self._restore)

        self.opened = []
        self._real_start = os.startfile if hasattr(os, "startfile") else None
        os.startfile = self.opened.append

    def _restore(self):
        host_desktop.Bridge._allowed = self._real

        if self._real_start is not None:
            os.startfile = self._real_start

    def test_문은_두_개뿐이다(self):
        """
        Sprint222 는 문이 하나였다. 하나 늘리되 늘어난 것이 정확히
        무엇인지 여기서 못 박는다 - 인스턴스를 본다(pywebview 는
        인스턴스 속성까지 화면에 내보낸다).
        """

        public = sorted(name for name in dir(host_desktop.Bridge())
                        if not name.startswith("_"))

        self.assertEqual(public, ["open_folder", "pick_folder"], public)

    def test_우리_폴더는_연다(self):
        said = self.bridge.open_folder(self.allowed)

        self.assertEqual(said, "", said)
        self.assertEqual(self.opened, [os.path.abspath(self.allowed)])

    def test_그_아래도_연다(self):
        under = os.path.join(self.allowed, "images")
        os.makedirs(under, exist_ok=True)

        self.assertEqual(self.bridge.open_folder(under), "")

    def test_바깥은_열지_않는다(self):
        said = self.bridge.open_folder(self.outside)

        self.assertIn("자료 폴더만", said)
        self.assertEqual(self.opened, [], "열면 안 되는 것을 열었다")

    def test_없는_폴더는_그렇다고_말한다(self):
        said = self.bridge.open_folder(
            os.path.join(self.allowed, "없는곳"))

        self.assertIn("없습니다", said)
        self.assertEqual(self.opened, [])

    def test_빈_경로는_지금_폴더로_해석되지_않는다(self):
        """
        os.path.abspath("") 는 **지금 디렉터리**를 돌려준다. abspath 뒤에
        비었는지 보면 그 검사는 영원히 참이 되지 않고, 빈 경로가 조용히
        현재 폴더로 해석된다 - 실제로 저장소 폴더가 열렸다.

        _allowed 를 가짜로 바꾼 채로만 재면 이것을 놓친다. 그래서
        여기서는 진짜 _allowed 로 잰다.
        """

        host_desktop.Bridge._allowed = self._real

        bridge = host_desktop.Bridge()

        for empty in ("", "   ", None):
            with self.subTest(value=empty):
                said = bridge.open_folder(empty)

                self.assertIn("비어 있습니다", said, f"{empty!r} -> {said!r}")

        self.assertEqual(self.opened, [], "빈 경로로 무언가를 열었다")

    def test_pick_folder_계약은_그대로(self):
        """Sprint222 가 정한 것 - 창이 없으면 빈 문자열."""

        self.assertEqual(host_desktop.Bridge().pick_folder(), "")


class TheScreenShowsWhereThingsAreTest(unittest.TestCase):

    def test_자료_관리가_첫_화면에_있다(self):
        page = _markup()

        self.assertIn('id="mediaLibrary"', page)

    def test_배경음악은_렌더가_보는_자리를_쓴다(self):
        """
        자료 폴더의 music 개수를 쓰면, 12개 있다고 해놓고 렌더가
        "배경음악이 없습니다"로 죽는다.
        """

        block = _block(_markup(), "function renderMediaLibrary(")

        self.assertIn("aboutInfo", block)
        self.assertNotIn("counts.music", block)

    def test_이미지와_영상은_workspace_개수를_쓴다(self):
        block = _block(_markup(), "function renderMediaLibrary(")

        self.assertIn("counts.images", block)
        self.assertIn("counts.videos", block)

    def test_효과음은_준비_중이라고만_적는다(self):
        block = _block(_markup(), "function renderMediaLibrary(")

        self.assertIn("효과음", block)
        self.assertIn("준비 중", block)

        # 열 수 없는 폴더를 열어 주지 않는다.
        after = block[block.index("효과음"):block.index("효과음") + 500]

        self.assertNotIn("openMediaFolder('sfx'", after)

    def test_폴더_열기는_브리지가_없으면_경로_복사로_간다(self):
        """
        EXE 는 브라우저 모드라 문이 없다. 그때 아무 일도 안 일어나면
        사람은 프로그램이 멈춘 줄 안다.
        """

        block = _block(_markup(), "async function openMediaFolder(")

        self.assertIn("window.pywebview", block)
        self.assertIn("복사", block)

    def test_무료_리소스_목록은_한_곳에_있다(self):
        """
        주소를 함수 안에 흩어 두면 어느 날 한쪽만 고쳐진다. 상수 하나에
        모으고, 카드는 그것을 읽는다.
        """

        page = _markup()
        sites = _block(page, "const SITES = {", 600)

        for site in ("Pixabay", "Unsplash", "Pexels", "Mixkit"):
            self.assertIn(site, sites)

        card = _block(page, "function mediaHelpCard(")

        self.assertIn("SITES[kind]", card,
                      "카드가 그 목록을 읽어야 한다")

    def test_모자랄_때만_말한다(self):
        """늘 떠 있으면 안내가 아니라 광고가 된다."""

        card = _block(_markup(), "function mediaHelpCard(")

        self.assertIn("if (!missing.length) return", card)

    def test_다운로드를_대신_하지_않는다(self):
        """받아 오는 일은 사람이 한다 - 크롤러를 만들지 않는다."""

        block = _block(_markup(), "function mediaHelpCard(", 1800)

        self.assertNotIn("fetch(\"https://", block)
        self.assertNotIn("fetch('https://", block)


class TheWizardMusicStepStillTellsTheTruthTest(unittest.TestCase):
    """Sprint223 이 정한 것이 그대로여야 한다."""

    def test_고르는_단추를_만들지_않는다(self):
        block = _block(_markup(), "function wizCardMusic()")

        self.assertNotIn('type="radio"', block)

    def test_렌더가_보는_자리를_말한다(self):
        block = _block(_markup(), "function wizCardMusic()")

        self.assertIn("aboutInfo", block)

    def test_AI_음악은_준비_중이다(self):
        block = _block(_markup(), "function wizCardMusic()")

        self.assertIn("준비 중", block)


class TheCardReadsTheScreensOwnStateTest(unittest.TestCase):
    """
    Sprint232 - 카드가 화면의 상태를 그대로 읽는다 (E2E 후속).

    무엇이 있었나
    -------------
    카드는 전역 객체를 거쳐 상태를 읽었다. 그런데 studio.html 은
    `let aboutInfo` · `let workspace` 로 들고 있고, **최상위 let 은
    전역 객체의 속성이 되지 않는다**. 그 읽기는 영영 undefined 였고,
    배경음악 줄이 늘 "확인 중…" 이었다 - 서버는 ready 를 주고 있었는데
    카드만 못 보았다.

    실제 영상 E2E 에서 드러났다. 그 전의 시험은 renderMediaLibrary 안에
    "aboutInfo" 라는 **글자가 있는지**만 보았고, 그 글자는 잘못된
    읽기에도 들어 있었다. 이름이 있는지가 아니라 값이 닿는지를 봐야
    한다.
    """

    def _card(self) -> str:
        """
        카드 묶음만 잘라 온다. 주석이 걷힌 뒤에도 남는 것에 기대야
        한다 - 설명 문장을 표지로 삼으면 주석을 걷는 순간 사라진다
        (실제로 그렇게 걸렸다).
        """

        page = _markup()
        at = page.index("const SITES = {")

        return page[at:page.index("</script>", at)]

    def test_전역_객체를_거쳐_읽지_않는다(self):
        card = self._card()

        for wrong in ("window.aboutInfo", "window.workspace"):
            with self.subTest(reading=wrong):
                self.assertNotIn(wrong, card,
                                 "최상위 let 은 전역 객체에 없다")

    def test_제_사본을_만들지_않는다(self):
        """
        두 곳이 같은 것을 따로 들고 있으면 어느 날 두 값이 갈라진다.
        카드는 화면이 이미 들고 있는 것을 읽기만 한다.
        """

        card = self._card()

        self.assertNotIn("window.workspace =", card)
        self.assertNotIn("window.aboutInfo =", card)

    def test_이미_있는_loader_를_쓴다(self):
        """새 API 도, 두 번째 fetch 도 만들지 않는다."""

        card = self._card()
        at = card.index("async function refresh(")
        block = card[at:at + 700]

        self.assertIn("loadWorkspace", block)
        self.assertIn("wizLoadAbout", block)

        self.assertNotIn('fetch("/studio/api/workspace")', block,
                         "loadWorkspace 가 이미 그것을 부른다")

    def test_자료_폴더가_바뀌면_카드도_따라간다(self):
        """
        workspace 에 값이 들어가는 자리는 loadWorkspace 와
        chooseWorkspace 둘뿐이고, 둘 다 renderWorkspace 로 끝난다.
        그 하나에 얹는다 - 새 신호를 만들지 않는다.
        """

        card = self._card()

        self.assertIn("function followWorkspace(", card)

        at = card.index("function followWorkspace(")
        block = card[at:at + 700]

        self.assertIn("renderWorkspace", block)
        self.assertIn("renderMediaLibrary()", block)

        # 두 번 얹으면 그릴 때마다 겹쳐 부른다.
        self.assertIn("__mlib", block, "이미 얹혔는지 보고 한 번만 얹는다")

        self.assertIn("followWorkspace();", card, "mount 에서 불러야 한다")

    def test_화면의_선언은_여전히_let_이다(self):
        """
        이 시험이 지키는 것은 "전역 객체로 읽지 마라"이고, 그 이유는
        선언이 let 이기 때문이다. 언젠가 화면이 전역 객체에 얹도록
        바뀌면 이유가 사라진다 - 그때 이 시험이 알려 준다.
        """

        page = _page()

        self.assertIn("let aboutInfo = null;", page)
        self.assertIn("let workspace = null;", page)


if __name__ == "__main__":
    unittest.main()
