"""
Sprint222 - 실사용에서 나온 결함 두 가지를 못 박는다 (Epic 64).

무엇이 있었나
-------------
1. 붙여넣은 대본이 [읽어 보기] 한 번에 사라졌다.

   wizReadScript 가 끝나면서 renderFreeWizard 를 부르고, 그 렌더가
   <textarea id="wizRaw"> 를 **빈 채로** 다시 만들었다. 사람이 붙여넣은
   글이 그 순간 없어졌고, 이어 도는 checkScript('wizRaw', ...) 는 빈
   칸을 읽어 검사 결과까지 거짓이 됐다 - 증상 둘이 한 원인이었다.

2. [장면에 연결] 이 "script.json 이 없습니다" 라고 말했다.

   그건 우리 파일 이름이지 사람이 할 일이 아니다. 자료를 먼저 넣는
   흐름을 만들어 놓고, 막히는 자리에서 내부 구조를 요구하면 그 흐름은
   거기서 끝난다.

왜 글자로 재는가
----------------
이 저장소의 화면 가드들이 그렇게 한다(test_studio_ux6 등). 브라우저가
있어야만 재는 것은 tests/ 밖의 스모크가 맡고, 여기서는 "그 자리가
아직 그렇게 적혀 있는가" 를 지킨다 - 되돌아가는 것을 막는 데는 이것이
가장 싸고 확실하다.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _page() -> str:
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _markup() -> str:
    """줄 주석을 걷어낸 화면.

    이 가드가 처음 걸린 것이 제 주석이었다 - 결함을 설명하려고 주석에
    <textarea id="wizRaw"> 라고 적어 두었더니, 가드가 그 예시를 진짜
    마크업으로 알고 "원문을 되돌리지 않는다"고 말했다.

    test_studio_ux6 이 같은 이유로 주석을 먼저 지운다("코드를 보는
    가드인데 주석을 읽으면 … 실제로 걸렸다"). 이 저장소가 여러 번
    겪은 모양이고, 여기서도 같은 것을 밟았다.
    """

    return re.sub(r"(?m)^[ 	]*//.*$", "", _page())


class PastedScriptSurvivesTest(unittest.TestCase):
    """사람이 붙여넣은 것은 사람이 지울 때까지 남는다."""

    def test_붙여넣는_칸을_다시_그릴_때_원문을_되돌린다(self):
        found = re.search(r'<textarea id="wizRaw"[^>]*>(.*?)</textarea>',
                          _markup(), re.S)

        self.assertIsNotNone(found, "wizRaw 칸을 찾지 못했습니다")

        inside = found.group(1)

        self.assertIn("wizRawText", inside,
                      "다시 그릴 때 원문을 되돌리지 않으면 [읽어 보기] "
                      "한 번에 사람이 붙여넣은 글이 사라진다")

    def test_붙여넣는_칸이_사람의_입력을_담아_둔다(self):
        found = re.search(r'<textarea id="wizRaw"([^>]*)>', _markup())

        self.assertIsNotNone(found)
        self.assertIn("wizRawText=this.value", found.group(1),
                      "치는 동안에도 담아 두지 않으면 다시 그릴 때 잃는다")

    def test_읽기_전에_원문을_붙잡는다(self):
        page = _page()

        start = page.index("async function wizReadScript")
        body = page[start:start + 700]

        self.assertIn("wizRawText = raw", body,
                      "렌더가 칸을 다시 만들기 전에 붙잡아 두어야 한다")

    def test_원문을_담는_자리가_선언되어_있다(self):
        self.assertIn("let wizRawText", _page())


class NoInternalFileNamesInGuidanceTest(unittest.TestCase):
    """사람에게 우리 파일 구조를 요구하지 않는다."""

    def test_대본이_없을_때_다음_행동을_준다(self):
        page = _page()

        start = page.index("function needScript()")
        body = page[start:start + 900]

        self.assertIn("먼저 대본이 필요합니다", body)
        self.assertIn("chooseFree()", body,
                      "대본을 쓰러 갈 자리가 없으면 안내가 막다른 길이 된다")
        self.assertIn("chooseFullAuto()", body,
                      "AI 에게 맡기는 길도 함께 준다")

    def test_script_json_을_사람에게_요구하지_않는다(self):
        page = _page()

        start = page.index("  async function apply()")
        body = page[start:start + 1800]

        # 서버 문장을 그대로 흘려보내는 자리가 남아 있으면 안 된다.
        self.assertIn("needScript()", body,
                      "대본이 없을 때는 사람 말로 바꿔 말해야 한다")

        said = re.findall(r'say\("([^"]*script\.json[^"]*)"', body)

        self.assertEqual(said, [],
                         f"안내에 내부 파일 이름이 남아 있습니다: {said}")


if __name__ == "__main__":
    unittest.main()
