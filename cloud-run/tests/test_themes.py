"""
Sprint218 - 화면 테마 (Epic 62).

이 스위트의 중심은 "네 가지가 있다"가 아니다.

    **라이트 테마에 다크 전용 색이 남아 있지 않은가.**

Sprint216 이전의 CSS에는 박힌 색이 133곳 있었다. 그 상태에서 배경만
흰색으로 바꾸면 흰 바탕에 어두운 회색 글자와 남색 테두리가 남아
아무것도 안 보인다. 그래서 여기서 세는 것은 토큰이 아니라 **박힌
색이 남았는가**이고, 재는 것은 각 테마의 실제 대비다.
"""

import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import runtime_paths, settings

_PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html")


def _raw_page():
    with open(_PAGE, encoding="utf-8") as f:
        return f.read()


def _served_page():
    from app.routers import studio as studio_router

    return studio_router.studio_page().body.decode("utf-8")


def _style_block(page):
    return page[page.index("<style>"):page.index("</style>")]


def _palette_end(style):
    """테마 정의가 끝나는 자리. 그 아래가 본문 CSS다."""

    return style.index("*{box-sizing")


def _tokens_of(style, selector):
    """
    그 선택자 블록들이 정의하는 {토큰: 값}.

    :root 는 두 번 나온다(팔레트 하나, 테마 견본 색 하나) - CSS가
    둘을 합치므로 여기서도 합친다. 앞의 것만 읽으면 뒤에 있는 것이
    "정의되지 않은 토큰"으로 보인다.
    """

    found = {}
    at = style.find(selector)

    while at != -1:
        block = style[at:style.index("}", at)]
        found.update(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", block))
        at = style.find(selector, at + 1)

    return found


# ══ 1. 네 테마가 있다 ═══════════════════════════════════════════════

class TheFourThemesTest(unittest.TestCase):

    def test_there_are_exactly_four(self):
        self.assertEqual(list(settings.THEMES),
                         ["dark", "light", "podo", "blue"])

    def test_every_theme_has_a_korean_label(self):
        self.assertEqual(
            [settings.THEME_LABELS[t] for t in settings.THEMES],
            ["다크", "라이트", "포도", "블루"])

    def test_the_default_is_dark(self):
        """
        쓰던 사람의 화면이 판올림 한 번에 바뀌면 그것대로 놀란다.
        """

        self.assertEqual(settings.DEFAULTS[settings.THEME],
                         settings.THEME_DARK)

    def test_each_theme_has_its_own_palette_block(self):
        style = _style_block(_raw_page())

        # 다크는 :root 가 곧 팔레트다.
        self.assertIn(":root{", style)

        for theme in ("light", "podo", "blue"):
            with self.subTest(theme=theme):
                self.assertIn(f'html[data-theme="{theme}"]', style)


# ══ 2. 박힌 색이 남지 않았다 ════════════════════════════════════════

class NoHardcodedColourSurvivesTest(unittest.TestCase):
    """
    이 시험이 이 Sprint의 핵심이다.

    팔레트 블록 아래의 본문 CSS에는 색 값이 한 글자도 없어야 한다 -
    있으면 그 색은 어느 테마에서도 바뀌지 않고, 라이트에서 반드시
    대비가 깨진다.
    """

    def test_the_body_css_names_no_colour(self):
        style = _style_block(_raw_page())
        body = style[_palette_end(style):]

        found = re.findall(r"#[0-9a-fA-F]{3,8}\b", body)

        self.assertEqual(found, [], f"본문 CSS에 박힌 색: {set(found)}")

    def test_the_body_css_uses_no_rgb_literal(self):
        style = _style_block(_raw_page())
        body = style[_palette_end(style):]

        self.assertEqual(re.findall(r"rgba?\(", body), [])

    def test_the_body_css_names_no_colour_word(self):
        style = _style_block(_raw_page())
        body = style[_palette_end(style):]

        for word in ("white", "black", "silver", "gray", "grey"):
            with self.subTest(word=word):
                self.assertIsNone(
                    re.search(r"(?:color|background)\s*:\s*" + word, body))

    def test_the_scripts_name_no_colour_either(self):
        """
        JS 템플릿이 색을 적어도 같은 문제가 난다 - 실제로 SNS 상태
        표시와 완료 문구에 박혀 있었다.
        """

        page = _raw_page()
        script = page[page.rfind("<script"):]

        # 테마 견본은 그 테마의 색을 보여 주는 자리라 예외다 - 그것은
        # CSS의 .themes .sw[data-t=...] 에 있고 script 안에는 없다.
        found = re.findall(r"#[0-9a-fA-F]{3,8}\b", script)

        self.assertEqual(found, [], f"script에 박힌 색: {set(found)}")


# ══ 3. 모든 테마가 같은 토큰을 채운다 ═══════════════════════════════

class EveryThemeFillsEveryTokenTest(unittest.TestCase):
    """
    한 토큰이 빠지면 그 자리는 다크 값을 그대로 물려받는다 - 라이트에서
    검은 배경 조각이 남는 경로가 정확히 그것이다.
    """

    def setUp(self):
        self.style = _style_block(_raw_page())
        self.base = _tokens_of(self.style, ":root{")

    def test_the_base_defines_every_token_the_body_uses(self):
        body = self.style[_palette_end(self.style):]
        used = set(re.findall(r"var\((--[a-z0-9-]+)\)", body))

        # 테마 견본이 쓰는 두 개는 견본 안에서 정의된다.
        used -= {"--s1", "--s2"}

        missing = sorted(used - set(self.base))

        self.assertEqual(missing, [], f":root 에 없는 토큰: {missing}")

    # 테마마다 바꾸지 않기로 한 것들. 이 목록이 늘어나는 것이 곧
    # "라이트에 다크 값이 남는" 구멍이므로, 무엇이 왜 여기 있는지
    # 한 줄씩 적어 둔다.
    SHARED = {
        "--radius",    # 색이 아니라 모양이다
        "--media",     # 영상·썸네일 자리. 어느 테마에서도 어둡게 둔다
        "--overlay",   # 겹쳐 뜨는 안내의 뒷막. 밝으면 안내가 안 읽힌다
    }

    def test_every_theme_overrides_every_colour_token(self):
        # 견본 색(--sw-*)은 "다른 테마로 바꾸면 무슨 색이 되는가"를
        # 보여 주는 자리라 지금 테마를 따르지 않는다 - 따르게 만들면
        # 견본 넷이 전부 같은 색이 되어 고를 수가 없다.
        expected = {
            t for t in self.base
            if t not in self.SHARED and not t.startswith("--sw-")
        }

        for theme in ("light", "podo", "blue"):
            given = set(_tokens_of(
                self.style, f'html[data-theme="{theme}"]'))
            missing = sorted(expected - given)

            with self.subTest(theme=theme):
                self.assertEqual(
                    missing, [],
                    f"{theme} 가 안 채운 토큰(다크 값이 남는다): {missing}")

    def test_no_theme_invents_a_token_nobody_reads(self):
        for theme in ("light", "podo", "blue"):
            given = set(_tokens_of(
                self.style, f'html[data-theme="{theme}"]'))
            extra = sorted(given - set(self.base))

            with self.subTest(theme=theme):
                self.assertEqual(extra, [], f"{theme} 의 남는 토큰: {extra}")

    def test_the_shared_tokens_are_only_the_ones_we_declared(self):
        """
        이 목록이 조용히 늘어나는 것이 곧 "라이트에 다크 값이 남는"
        구멍이다. 늘리려면 이 시험을 함께 고쳐야 한다.
        """

        overridden = set(_tokens_of(self.style, 'html[data-theme="light"]'))
        # 견본 색은 팔레트 옆의 두 번째 :root 에 있고 테마를 안 탄다.
        shared = {
            t for t in self.base
            if t not in overridden and not t.startswith("--sw-")
        }

        self.assertEqual(shared, self.SHARED)


# ══ 4. 대비 ═════════════════════════════════════════════════════════

def _rgb(value):
    said = value.strip()

    if not said.startswith("#"):
        return None

    said = said[1:]

    if len(said) == 3:
        said = "".join(c * 2 for c in said)

    if len(said) == 4:          # #rgba
        said = "".join(c * 2 for c in said[:3])

    if len(said) == 8:          # #rrggbbaa - 알파는 대비 계산에서 뺀다
        said = said[:6]

    if len(said) != 6:
        return None

    return tuple(int(said[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb):
    def channel(c):
        c /= 255.0

        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)

    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)

    return (hi + 0.05) / (lo + 0.05)


class TheContrastHoldsInEveryThemeTest(unittest.TestCase):
    """
    "라이트에서 글자가 안 보인다"를 눈이 아니라 숫자로 막는다.

    기준은 WCAG AA다 - 본문 글자 4.5:1, 큰 글자·보조 설명 3:1.
    보조 설명(--dim)에 4.5를 요구하면 어느 테마에서도 회색을 쓸 수
    없게 되므로 3.0으로 둔다.
    """

    # (글자 토큰, 바탕 토큰, 최소 대비, 무엇인가)
    PAIRS = (
        ("--text", "--bg", 4.5, "본문 글자"),
        ("--text", "--panel", 4.5, "카드 안 글자"),
        ("--text", "--panel2", 4.5, "입력창 글자"),
        ("--text", "--raised", 4.5, "고른 칸의 글자"),
        ("--dim", "--panel", 3.0, "보조 설명"),
        ("--dim", "--panel2", 3.0, "칸 안 보조 설명"),
        ("--dim", "--sunken", 3.0, "콘솔 글자"),
        ("--faint", "--panel", 2.5, "가장 옅은 글자"),
        ("--accent-on", "--accent", 4.5, "주요 단추 글자"),
        ("--ok-text", "--ok-soft", 3.0, "성공 표시"),
        ("--warn-text", "--warn-soft", 3.0, "경고 표시"),
        ("--warn-strong", "--warn-soft", 3.0, "경고 강조"),
        ("--bad-text", "--bad-soft", 3.0, "오류 표시"),
        # .na-note 의 글자다. 안내문이라 본문 기준을 적용한다 -
        # 라이트에서 실제로 4.48이 나와 한 번 걸렸다.
        ("--warn", "--warn-soft", 4.5, "안내 배너 글자"),
        ("--ok", "--ok-soft", 4.5, "성공 배너 글자"),
        ("--bad", "--bad-soft", 4.5, "오류 배너 글자"),
        ("--accent", "--panel", 3.0, "링크와 강조"),
        ("--ok", "--panel", 3.0, "성공 점"),
        ("--warn", "--panel", 3.0, "경고 점"),
        ("--bad", "--panel", 3.0, "오류 점"),
        ("--edit", "--panel", 3.0, "사람이 고친 표시"),
        ("--todo", "--panel", 3.0, "아직 안 한 표시"),
    )

    def setUp(self):
        style = _style_block(_raw_page())
        self.palettes = {"dark": _tokens_of(style, ":root{")}

        for theme in ("light", "podo", "blue"):
            found = dict(self.palettes["dark"])
            found.update(_tokens_of(style, f'html[data-theme="{theme}"]'))
            self.palettes[theme] = found

    def test_text_is_readable_on_every_surface_in_every_theme(self):
        for theme, palette in self.palettes.items():
            for fg, bg, floor, what in self.PAIRS:
                a, b = _rgb(palette[fg]), _rgb(palette[bg])

                if a is None or b is None:
                    continue

                ratio = _contrast(a, b)

                with self.subTest(theme=theme, what=what):
                    self.assertGreaterEqual(
                        round(ratio, 2), floor,
                        f"{theme}: {what}({fg} on {bg}) 대비 "
                        f"{ratio:.2f} < {floor}")

    def test_borders_are_visible_against_their_surface(self):
        """테두리가 안 보이면 칸의 경계가 사라진다."""

        for theme, palette in self.palettes.items():
            for line, surface in (("--line", "--panel"),
                                  ("--line", "--bg"),
                                  ("--line2", "--panel")):
                a, b = _rgb(palette[line]), _rgb(palette[surface])

                if a is None or b is None:
                    continue

                with self.subTest(theme=theme, pair=f"{line}/{surface}"):
                    self.assertGreaterEqual(
                        round(_contrast(a, b), 2), 1.15,
                        f"{theme}: {line} 이 {surface} 위에서 안 보인다")

    def test_focus_is_visible_and_follows_the_theme(self):
        """
        키보드로 옮겨 다니는 사람이 지금 어디에 있는지 보여야 한다.
        이 화면에는 :focus 규칙이 하나도 없었다.
        """

        style = _style_block(_raw_page())
        body = style[_palette_end(style):]

        self.assertIn(":focus-visible", body)

        at = body.index(":focus-visible")
        rule = body[at:body.index("}", at)]

        self.assertIn("outline", rule)
        # 테마를 따라야 한다 - 고정 색이면 어느 바탕에서는 안 보인다.
        self.assertIn("var(--", rule)

    def test_the_focus_ring_reads_on_every_surface(self):
        for theme, palette in self.palettes.items():
            for surface in ("--bg", "--panel", "--panel2"):
                a, b = _rgb(palette["--accent"]), _rgb(palette[surface])

                with self.subTest(theme=theme, surface=surface):
                    self.assertGreaterEqual(
                        round(_contrast(a, b), 2), 3.0,
                        f"{theme}: 초점 테두리가 {surface} 위에서 안 보인다")

    def test_light_is_actually_light_and_the_others_are_not(self):
        """이름과 실제가 어긋나지 않는지 본다."""

        bright = {
            theme: _luminance(_rgb(palette["--bg"]))
            for theme, palette in self.palettes.items()
        }

        self.assertGreater(bright["light"], 0.5, "라이트가 밝지 않다")

        for theme in ("dark", "podo", "blue"):
            with self.subTest(theme=theme):
                self.assertLess(bright[theme], 0.15, f"{theme} 가 어둡지 않다")

    def test_each_theme_has_its_own_look(self):
        """넷이 실질적으로 같은 색이면 고르는 의미가 없다."""

        seen = {}

        for theme, palette in self.palettes.items():
            key = (palette["--bg"], palette["--accent"])

            self.assertNotIn(
                key, seen, f"{theme} 와 {seen.get(key)} 가 같은 색이다")

            seen[key] = theme


# ══ 5. 고른 것이 저장되고 되살아난다 ════════════════════════════════

class TheChoiceIsRememberedTest(unittest.TestCase):

    def setUp(self):
        self._home = tempfile.TemporaryDirectory()
        self.addCleanup(self._home.cleanup)

        patcher = patch.dict(
            os.environ, {runtime_paths.HOME_ENV: self._home.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_fresh_install_reads_dark(self):
        self.assertEqual(settings.theme(), settings.THEME_DARK)

    def test_what_was_saved_comes_back(self):
        for theme in settings.THEMES:
            with self.subTest(theme=theme):
                settings.save({settings.THEME: theme})

                self.assertEqual(settings.theme(), theme)

    def test_it_survives_a_restart(self):
        """
        같은 자리를 새로 읽는다 - 프로그램을 다시 켠 것과 같다.
        """

        settings.save({settings.THEME: settings.THEME_PODO})

        import importlib

        importlib.reload(settings)

        self.assertEqual(settings.theme(), settings.THEME_PODO)

    def test_saving_the_theme_keeps_the_other_settings(self):
        """통째로 덮지 않는다 - 우리가 모르는 열쇠가 그때 사라진다."""

        settings.save({"내가_넣어둔_것": "그대로", settings.OPEN_BROWSER: False})
        settings.save({settings.THEME: settings.THEME_BLUE})

        found = settings.load()

        self.assertEqual(found["내가_넣어둔_것"], "그대로")
        self.assertFalse(found[settings.OPEN_BROWSER])
        self.assertEqual(found[settings.THEME], settings.THEME_BLUE)

    def test_a_typo_in_the_file_falls_back_to_dark(self):
        """
        설정 파일은 사람이 손으로 고칠 수 있는 자리다. 오타 하나에
        화면이 안 뜨면 고칠 방법이 없다.
        """

        settings.save({settings.THEME: "네온"})

        self.assertEqual(settings.theme(), settings.THEME_DARK)

    def test_ensure_does_not_overwrite_a_chosen_theme(self):
        """새 판을 덮어씌워도 고른 것은 남는다."""

        settings.save({settings.THEME: settings.THEME_LIGHT})
        settings.ensure()

        self.assertEqual(settings.theme(), settings.THEME_LIGHT)


# ══ 6. HTTP 와 화면 ═════════════════════════════════════════════════

class TheHttpSurfaceTest(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

        self._home = tempfile.TemporaryDirectory()
        self.addCleanup(self._home.cleanup)

        patcher = patch.dict(
            os.environ, {runtime_paths.HOME_ENV: self._home.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_it_reports_the_current_theme_and_the_choices(self):
        body = self.client.get("/studio/api/settings").json()

        self.assertEqual(body["theme"], "dark")
        self.assertEqual([t["key"] for t in body["themes"]],
                         list(settings.THEMES))

    def test_choosing_a_theme_saves_it(self):
        response = self.client.put("/studio/api/settings/theme",
                                   json={"theme": "podo"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["theme"], "podo")
        self.assertEqual(
            self.client.get("/studio/api/settings").json()["theme"], "podo")

    def test_an_unknown_theme_is_refused(self):
        """
        조회는 오타를 다크로 되돌려 주지만, 적는 자리에서까지 조용히
        받아 주면 사람은 "골랐는데 안 바뀐다"를 겪는다.
        """

        response = self.client.put("/studio/api/settings/theme",
                                   json={"theme": "네온"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("네온", response.json()["detail"])

    def test_a_failure_to_save_is_not_reported_as_success(self):
        with patch("app.settings.save", side_effect=OSError("디스크 꽉 찼다")):
            response = self.client.put("/studio/api/settings/theme",
                                       json={"theme": "blue"})

        self.assertEqual(response.status_code, 500)
        self.assertIn("저장하지 못했습니다", response.json()["detail"])


class TheServedPageCarriesTheThemeTest(unittest.TestCase):
    """
    자바스크립트가 켜진 뒤에 칠하면, 라이트를 고른 사람은 켤 때마다
    검은 화면이 한 번 번쩍이는 것을 본다.
    """

    def setUp(self):
        self._home = tempfile.TemporaryDirectory()
        self.addCleanup(self._home.cleanup)

        patcher = patch.dict(
            os.environ, {runtime_paths.HOME_ENV: self._home.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_token_is_replaced(self):
        page = _served_page()

        self.assertNotIn(settings.THEME_TOKEN, page)

    def test_the_html_element_carries_the_saved_theme(self):
        for theme in settings.THEMES:
            settings.save({settings.THEME: theme})

            with self.subTest(theme=theme):
                self.assertIn(f'<html lang="ko" data-theme="{theme}"',
                              _served_page())

    def test_a_broken_setting_still_serves_a_page(self):
        settings.save({settings.THEME: "네온"})

        self.assertIn('data-theme="dark"', _served_page())


class TheThemePickerTest(unittest.TestCase):

    def test_it_has_a_place_in_the_header(self):
        page = _served_page()
        header = page[page.index("<header>"):page.index("</header>")]

        self.assertIn('id="themePicker"', header)

    def test_it_applies_without_a_reload(self):
        page = _served_page()
        at = page.index("async function pickTheme")
        block = page[at:at + 700]

        self.assertIn("setAttribute(\"data-theme\"", block)
        self.assertNotIn("location.reload", block)

    def test_it_saves_the_choice(self):
        page = _served_page()
        at = page.index("async function pickTheme")

        self.assertIn("/studio/api/settings/theme", page[at:at + 700])

    def test_a_failed_save_rolls_the_screen_back(self):
        """
        이번 화면만 바뀌고 다음에 없으면 사람은 "저장이 안 되는
        프로그램"을 겪는다.
        """

        page = _served_page()
        at = page.index("async function pickTheme")
        block = page[at:at + 900]

        self.assertIn("before", block)
        self.assertIn("console.error", block)

    def test_the_handlers_are_declared(self):
        page = _served_page()

        for name in ("pickTheme", "loadThemes", "renderThemePicker",
                     "currentTheme"):
            with self.subTest(name=name):
                self.assertIn(f"function {name}(", page)


if __name__ == "__main__":
    unittest.main()
