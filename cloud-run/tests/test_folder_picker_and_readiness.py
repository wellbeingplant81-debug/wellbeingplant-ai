"""
Sprint222 후속 - 폴더는 골라서 정하고, 준비도는 실제 관문을 말한다.

무엇이 있었나
-------------
1. 자료 폴더를 정하는 유일한 길이 prompt() 였다.

   데스크톱 앱에서 사람에게 "C:\\... 경로를 적어 주세요" 라고 요구하면
   그 자리에서 흐름이 끊긴다. 브라우저에는 폴더의 **경로**를 주는
   표준 API 가 없어서 그랬던 것이지, 그렇게 하고 싶었던 것이 아니다.

2. [영상 생성 (준비도 100%)] 의 그 숫자가 재료와 무관했다.

   readiness() 가 세는 것은 **각 단계를 무엇으로 만들지 정해졌는가**다.
   대본도 이미지도 음성도 없이 100% 가 된다. 그런데 그 숫자가 생성
   단추에 붙어 있어 사람은 "재료가 다 있다"로 읽었다.

무엇을 새로 만들지 않았는가
---------------------------
판정기를 만들지 않았다. 재료 쪽 판정은 이미 final_check 가 하고 있고
(Sprint162), 그것은 실제로 막는 검사(scene_order.render_problems)를
그대로 읽어 옮긴다 - "두 곳에서 따로 판정하면 화면이 '가능'이라고 한
것을 서버가 거절하는 날이 온다".

폴더 저장소도 만들지 않았다. free_workspace.json 과
GET/PUT /studio/api/workspace 를 그대로 쓴다.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import host_desktop

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _page() -> str:
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _markup() -> str:
    """줄 주석을 걷어낸 화면. 설명이 가드를 속이지 않게 한다."""

    return re.sub(r"(?m)^[ \t]*//.*$", "", _page())


def _block(page: str, start: str, length: int = 1600) -> str:
    at = page.index(start)

    return page[at:at + length]


class TheBridgeIsNarrowTest(unittest.TestCase):
    """
    화면이 부를 수 있는 것은 폴더 선택 하나뿐이다.

    여기에 하나를 더 넣기 시작하면 같은 기능이 서버와 브리지 두 곳에
    살게 되고, 어느 날 한쪽만 고쳐진다.
    """

    def test_문은_폴더_선택_하나뿐이다(self):
        """
        **클래스가 아니라 인스턴스**를 본다.

        pywebview 는 js_api 객체의 인스턴스 속성까지 화면에 내보낸다.
        클래스만 보면 self.window 같은 것이 새어 나가는 것을 놓친다 -
        실제로 놓쳤고, WebView2 에서 문이 두 개로 보였다.
        """

        bridge = host_desktop.Bridge()

        public = sorted(name for name in dir(bridge)
                        if not name.startswith("_"))

        self.assertEqual(public, ["pick_folder"], public)

    def test_창이_없으면_빈_값을_준다(self):
        """
        None 을 주면 화면 쪽에서 "문이 없다"와 구별되지 않는다 -
        브라우저 모드로 잘못 떨어진다.
        """

        self.assertEqual(host_desktop.Bridge().pick_folder(), "")

    def test_창이_거절해도_던지지_않는다(self):
        """여기서 예외가 나면 화면의 await 가 깨지고 창이 멈춘다."""

        class Broken:
            def create_file_dialog(self, *args, **kwargs):
                raise RuntimeError("열 수 없다")

        bridge = host_desktop.Bridge()
        bridge._window = Broken()

        self.assertEqual(bridge.pick_folder(), "")

    def test_취소하면_빈_값(self):
        class Cancelled:
            def create_file_dialog(self, *args, **kwargs):
                return None

        bridge = host_desktop.Bridge()
        bridge._window = Cancelled()

        self.assertEqual(bridge.pick_folder(), "")

    def test_고르면_절대_경로_하나(self):
        class Picked:
            def create_file_dialog(self, *args, **kwargs):
                return (r"D:\내 자료", )

        bridge = host_desktop.Bridge()
        bridge._window = Picked()

        self.assertEqual(bridge.pick_folder(), r"D:\내 자료")

    def test_시작_폴더를_그대로_넘긴다(self):
        seen = {}

        class Watching:
            def create_file_dialog(self, kind, directory="", **kwargs):
                seen["kind"] = kind
                seen["directory"] = directory

                return ("C:\\고른곳",)

        bridge = host_desktop.Bridge()
        bridge._window = Watching()
        bridge.pick_folder(r"C:\예전")

        self.assertEqual(seen["directory"], r"C:\예전")
        self.assertEqual(seen["kind"], host_desktop.FOLDER_DIALOG)

    def test_폴더_대화상자_상수가_pywebview_와_같다(self):
        """
        숫자를 적어 두었으므로 실제 값과 어긋나면 다른 창이 열린다.
        pywebview 가 없는 자리에서는 잴 수 없으니 건너뛴다.
        """

        try:
            import webview
        except ImportError:
            self.skipTest("pywebview 가 없는 자리")

        self.assertEqual(host_desktop.FOLDER_DIALOG,
                         int(webview.FileDialog.FOLDER))


class TheScreenPrefersTheNativePickerTest(unittest.TestCase):

    def test_먼저_네이티브_창을_연다(self):
        block = _block(_markup(), "async function chooseWorkspace(){")

        self.assertIn("pickFolderNatively", block)

        at_native = block.index("pickFolderNatively")
        at_prompt = block.index("prompt(")

        self.assertLess(at_native, at_prompt,
                        "prompt 가 먼저 오면 예전 UX 그대로다")

    def test_브라우저에서는_예전_길이_남아_있다(self):
        """pywebview 가 없다고 죽으면 브라우저 모드가 통째로 막힌다."""

        block = _block(_markup(), "async function pickFolderNatively(")

        self.assertIn("window.pywebview", block)
        self.assertIn("return undefined", block)

        chooser = _block(_markup(), "async function chooseWorkspace(){")

        self.assertIn("root === undefined", chooser)
        self.assertIn("prompt(", chooser)

    def test_취소는_아무_일도_아니다(self):
        chooser = _block(_markup(), "async function chooseWorkspace(){")

        self.assertIn('root === ""', chooser)

    def test_저장은_기존_workspace_API_그대로(self):
        chooser = _block(_markup(), "async function chooseWorkspace(){")

        self.assertIn("/studio/api/workspace", chooser)
        self.assertIn('"PUT"', chooser)


class TheReadinessSaysWhatItMeansTest(unittest.TestCase):

    def test_생성_단추에_그_숫자를_붙이지_않는다(self):
        """
        readiness() 가 세는 것은 제작 방식이고, 이 단추의 관문은
        주제·과금 확인·대본 계약이다. 서로 다른 것을 한 단추에 붙이면
        사람은 "재료가 다 있다"로 읽는다.
        """

        block = _block(_markup(), "function renderReadiness()")

        self.assertNotIn("영상 생성 (준비도", block)
        self.assertIn('$("go").textContent = "영상 생성"', block)

    def test_무엇을_세는지_화면이_밝힌다(self):
        block = _block(_markup(), "function renderReadiness()")

        self.assertIn("무엇으로 만들지 정해진 정도", block)

    def test_재료는_final_check_가_말한다(self):
        """새 판정기를 만들지 않았다는 것을 여기서 못 박는다."""

        block = _block(_markup(), "function renderReadiness()")

        self.assertIn("finalCheckPanel()", block)

    def test_final_check_는_막는_검사를_그대로_읽는다(self):
        """
        화면이 "가능"이라 한 것을 서버가 거절하지 않으려면, 판정이
        한 곳이어야 한다.
        """

        from app.services import final_check

        source = open(final_check.__file__, encoding="utf-8").read()

        self.assertIn("scene_order.render_problems", source)

    def test_준비도는_여전히_막지_않는다(self):
        """정보만 준다 - 짧은 영상이 필요한 날도 있다."""

        block = _block(_markup(), "function renderReadiness()")

        self.assertNotIn("disabled = true", block)


if __name__ == "__main__":
    unittest.main()
