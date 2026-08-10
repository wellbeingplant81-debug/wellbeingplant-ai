"""
Sprint215 - 받은 사람의 화면으로 (Epic 59, Phase 27).

머리줄에 누를 것이 열넷이었고 그중 열이 운영자용이었다(Sprint191~211에서
하나씩 붙었다). 받은 사람에게는 "Beta Snapshot"도 "배포 확인 정보"도
무슨 말인지 알 길이 없다.

본문도 그랬다. Topic·Channel·Platform·Length·Language가 먼저 오고
무료 제작은 그 아래 단추 하나였다. API 키가 없는 베타 사용자가 갈 수
있는 길은 무료 제작뿐인데 화면은 그것을 곁가지처럼 두었다.

지우지 않는다 - 옮기기만 한다
-----------------------------
테스트가 화면 문구를 붙잡고 있다(배포 확인 정보 7곳, 정보 복사 6곳,
Beta Snapshot 5곳 …). assertIn(문구, page) 형태라 숨김 영역으로 옮겨도
통과하지만 지우면 깨진다.

그리고 베타 중에는 운영자도 같은 프로그램을 쓴다. 지우면 그 사람이
볼 자리가 사라진다.

onclick 안에 코드를 늘어놓지 않는다
-----------------------------------
머리줄이 부르는 함수가 선언돼 있는지 보는 가드가 14개 파일에 있다.
Sprint204에서 onclick="if(...){...}" 로 그 열넷을 한꺼번에 깨뜨렸다.
"""

import os
import re
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.routers import studio as studio_router

# 받은 사람이 머리줄에서 봐야 하는 것.
#
# 정보 복사와 베타 피드백 복사는 README가 "화면 오른쪽 위 [정보 복사]를
# 누르면"이라고 가리키는 자리다. 옮기면 안내문이 거짓이 된다.
FOR_THE_USER = ("정보 복사", "베타 피드백 복사", "문제 해결")

# 운영자가 보는 것. 숨김 영역 안에 있어야 한다.
FOR_THE_OPERATOR = (
    "처음 사용자 테스트",
    "배포 확인 정보",
    "패키지 확인",
    "Beta Snapshot",
    "Beta Summary",
    "베타 분석",
    "베타 현황",
    "Release Report 복사",
    "사용 기록 복사",
)

# 첫 화면에서 정할 것이 아닌 설정들. 고급 영역 안으로.
SETTINGS = ('id="channel"', 'id="platform"', 'id="length"', 'id="lang"')


def _page():
    return studio_router.studio_page().body.decode("utf-8")


def _between(page, start_mark, end_mark):
    """
    start_mark 로 시작하는 요소부터 end_mark 까지. 주석은 걷어낸다.

    사람이 보는 것을 재는 가드인데 설명 주석을 읽으면, "배포 확인
    정보를 옮겼다"고 적은 것만으로 아직 머리줄에 있는 것처럼 걸린다
    (실제로 걸렸다). 이 저장소가 여러 번 겪은 모양이다.
    """

    at = page.find(start_mark)

    if at == -1:
        return ""

    end = page.find(end_mark, at)
    said = page[at:end if end != -1 else len(page)]

    return re.sub(r"<!--[\s\S]*?-->", "", said)


class TheOperatorAreaTest(unittest.TestCase):
    """1. 운영자 것은 숨김 영역 안으로."""

    def test_there_is_an_operator_area(self):
        self.assertIn('id="operatorArea"', _page())

    def test_it_starts_closed(self):
        page = _page()
        at = page.find('id="operatorArea"')

        self.assertNotEqual(at, -1)
        self.assertIn("display:none", page[at:at + 200])

    def test_a_named_button_opens_it(self):
        page = _page()

        self.assertIn('onclick="toggleOperator()"', page)
        self.assertIn("운영자 확인", page)
        self.assertIn("function toggleOperator", page)

    def test_the_operator_things_are_inside(self):
        page = _page()
        area = _between(page, 'id="operatorArea"', "</section>")

        self.assertTrue(area, "운영자 영역을 찾지 못했습니다")

        for word in FOR_THE_OPERATOR:
            with self.subTest(word=word):
                self.assertIn(word, area)


class TheUserThingsStayTest(unittest.TestCase):
    """2. 받은 사람 것은 머리줄에 그대로."""

    def test_they_are_in_the_header(self):
        page = _page()
        header = _between(page, "<header>", "</header>")

        self.assertTrue(header, "머리줄을 찾지 못했습니다")

        for word in FOR_THE_USER:
            with self.subTest(word=word):
                self.assertIn(word, header)

    def test_the_operator_things_are_not_in_the_header(self):
        page = _page()
        header = _between(page, "<header>", "</header>")

        for word in FOR_THE_OPERATOR:
            with self.subTest(word=word):
                self.assertNotIn(word, header)


class NothingWasDeletedTest(unittest.TestCase):
    """
    3. 지우지 않았다.

    베타 중에는 운영자도 같은 프로그램을 쓴다. 지우면 그 사람이 볼
    자리가 사라지고, 문구를 붙잡고 있는 테스트들도 깨진다.
    """

    def test_every_word_is_still_on_the_page(self):
        page = _page()

        for word in FOR_THE_USER + FOR_THE_OPERATOR:
            with self.subTest(word=word):
                self.assertIn(word, page)

    def test_the_settings_still_exist(self):
        page = _page()

        for what in SETTINGS:
            with self.subTest(what=what):
                self.assertIn(what, page)


class TheMakerLeadsWithFreeModeTest(unittest.TestCase):
    """4. 갈 수 있는 길을 앞에 둔다."""

    def test_free_mode_comes_before_the_settings(self):
        """
        API 키가 없는 사람이 첫 번째로 가는 길이다.
        """

        page = _page()

        free = page.find('id="wizToggle"')
        advanced = page.find('id="advanced"')

        self.assertNotEqual(free, -1)
        self.assertNotEqual(advanced, -1)
        self.assertLess(free, advanced)

    def test_the_settings_moved_into_the_advanced_area(self):
        page = _page()
        area = _between(page, 'id="advanced"', 'id="freeWizard"')

        if not area:
            area = page[page.find('id="advanced"'):]

        for what in SETTINGS:
            with self.subTest(what=what):
                self.assertIn(what, area)


class NoCodeInsideOnclickTest(unittest.TestCase):
    """
    5. onclick 안에 코드를 늘어놓지 않는다.

    Sprint204에서 그것으로 handler 가드 14개를 한꺼번에 깨뜨렸다.
    """

    def test_the_header_and_operator_area_call_one_name(self):
        """
        머리줄과 운영자 영역만 본다.

        본문 아래쪽에는 JS 템플릿이 만들어 내는 마크업이 있고, 거기
        event.stopPropagation() 을 함께 쓰는 것은 이 저장소의 기존
        패턴이다(줄 전체를 누르는 것과 그 안의 단추를 누르는 것을
        가른다). 그것까지 막으면 가드가 제 일을 넘어선다.

        막는 것은 이번에 손대는 자리다.
        """

        page = _page()
        where = _between(page, "<header>", "</header>") + _between(
            page, 'id="operatorArea"', "</section>")

        bad = [said for said in re.findall(r'onclick="([^"]+)"', where)
               if not re.fullmatch(r"[A-Za-z_]\w*\([^()]*\)", said.strip())]

        self.assertEqual(bad, [])

    def test_every_handler_is_declared(self):
        page = _page()

        script = page[page.rfind("<script"):]

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
