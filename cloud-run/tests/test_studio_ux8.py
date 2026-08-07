"""
Sprint122 - 한 화면에서 아래로 진행한다 (Epic 55, Phase 2).

Sprint121이 만든 승인 흐름은 그대로다. 바뀌는 것은 그것을 보여 주는
방식뿐이다 - 단계마다 화면이 갈아 끼워지는 느낌 대신, 한 페이지에서
접히고 펼쳐진다.

    현재 단계   펼침 · 굵은 테두리
    완료 단계   접힘 · ✓
    예정 단계   접힘 · 회색

승인 뒤에도 페이지를 옮기지 않는다. 같은 자리에서 "✓ 대본 승인 완료 ·
이미지 생성 중…"으로 이어진다.

STEP4의 두 버튼에 대해
----------------------
YouTube는 올릴 수 있다. 다만 Production Queue에서 승인한 뒤에만
올라간다(PV-02에서 정한 것이고, 검수 전에 올라가면 되돌릴 수 없다).
화면이 대신 승인하지 않는다 - 기존 엔드포인트를 부르고 그 결과를
그대로 보여 준다.

Instagram은 오늘 올릴 수 없다. 런타임은 Sprint97~101에 있지만 Meta
자격증명도, 저장소 설정도, 플래그도 없다. 되는 척하지 않고 비활성으로
두고 왜 안 되는지 적는다 - ElevenLabs를 다룬 것과 같은 방식이다.
"""

import ast
import os
import re
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _page():
    return client.get("/studio").text


def _block(page, start, end="\nfunction "):
    cut = page[page.index(start):]
    return cut[:cut.index(end)]


class TestTheProgressHeader(unittest.TestCase):

    def test_it_is_always_there(self):
        page = _page()

        self.assertIn('id="reviewProgress"', page)

    def test_it_shows_the_step_and_a_bar(self):
        page = _page()
        block = _block(page, "function reviewProgress")

        self.assertIn("STEP", block)
        self.assertIn("total", block)
        self.assertIn("%", block)

    def test_the_percent_is_the_step_position(self):
        """STEP1 25% · STEP2 50% · STEP3 75% · STEP4 100%."""

        page = _page()
        block = _block(page, "function reviewProgress")

        self.assertIn("index", block)
        self.assertIn("total", block)


class TestTheAccordion(unittest.TestCase):

    def test_all_four_steps_are_drawn_at_once(self):
        """한 페이지다 - 단계마다 화면을 갈아 끼우지 않는다."""

        page = _page()
        block = _block(page, "function renderReview")

        self.assertIn("REVIEW_STEPS", block)

    def test_the_step_table_covers_the_four(self):
        page = _page()
        block = _block(page, "const REVIEW_STEPS", "\n];")

        for name in ("script", "image", "voice", "video"):
            with self.subTest(name=name):
                self.assertIn(name, block)

    def test_only_the_current_one_is_open(self):
        page = _page()
        block = _block(page, "function reviewSection")

        self.assertIn("open", block)
        self.assertIn("state.step", block)

    def test_a_done_step_is_marked_with_a_check(self):
        page = _page()
        block = _block(page, "function reviewSection")

        self.assertIn("✓", block)

    def test_the_three_states_have_their_own_class(self):
        page = _page()

        for cls in ("s-now", "s-done", "s-todo"):
            with self.subTest(cls=cls):
                self.assertIn(cls, page)

    def test_the_classes_are_styled(self):
        page = _page()
        style = page[page.index("<style>"):page.index("</style>")]

        for cls in ("s-now", "s-done", "s-todo"):
            with self.subTest(cls=cls):
                self.assertIn("." + cls, style)

    def test_the_current_card_is_outlined(self):
        page = _page()
        style = page[page.index("<style>"):page.index("</style>")]

        block = style[style.index(".rsec.s-now"):][:200]

        self.assertIn("border", block)

    def test_a_finished_step_can_be_reopened(self):
        """접힌 것을 다시 볼 수 있어야 한다 - 승인한 뒤에도 확인은 남는다."""

        page = _page()

        self.assertIn("toggleReviewSection", page)


class TestTheApprovalStaysOnTheSamePage(unittest.TestCase):

    def test_it_never_navigates(self):
        page = _page()
        block = _block(page, "async function reviewApprove")

        for forbidden in ("location.href", "location.assign", "window.open"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)

    def test_it_says_what_was_approved_and_what_runs_next(self):
        page = _page()
        block = _block(page, "async function reviewApprove")

        self.assertIn("승인 완료", block)

    def test_the_next_step_opens_by_itself(self):
        """다시 그리면 현재 단계가 바뀌고, 그 단계가 열린다."""

        page = _page()
        block = _block(page, "async function reviewApprove")

        self.assertIn("renderReview", block)


class TestTheReviewFeaturesSurvive(unittest.TestCase):
    """Sprint121의 기능은 하나도 빠지지 않는다."""

    def test_the_scene_edit_is_still_there(self):
        page = _page()

        self.assertIn("reviewSaveScript", page)
        self.assertIn("rnar", page)

    def test_the_per_scene_regeneration_is_still_there(self):
        page = _page()

        self.assertIn("reviewRegenerate", page)
        self.assertIn("'images'", page)
        self.assertIn("'voices'", page)

    def test_the_voice_preview_is_still_there(self):
        page = _page()

        self.assertIn("playVoice", page)

    def test_there_is_still_no_regenerate_everything(self):
        page = _page()

        for forbidden in ("전부 다시", "모두 다시 생성"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, page)


class TestTheFinalStep(unittest.TestCase):

    def test_it_offers_save_and_the_two_platforms(self):
        """Sprint123 - 재생·내려받기·업로드가 영상 카드로 옮겨졌다.
        두 곳에 두지 않는다."""

        page = _page()
        block = _block(page, "function canvasVideo")

        for label in ("다운로드", "YouTube", "Instagram"):
            with self.subTest(label=label):
                self.assertIn(label, block)

    def test_instagram_is_disabled_with_a_reason(self):
        """오늘 올릴 수 없다 - 되는 척하지 않는다."""

        page = _page()
        block = _block(page, "function canvasVideo")

        self.assertIn("disabled", block)
        self.assertIn("Meta", block)

    def test_youtube_uses_the_existing_endpoint(self):
        page = _page()
        block = _block(page, "async function reviewUpload")

        self.assertIn("/upload", block)

    def test_the_screen_does_not_approve_on_its_own(self):
        """검수 전에 올라가면 되돌릴 수 없다(PV-02)."""

        page = _page()
        block = _block(page, "async function reviewUpload")

        self.assertNotIn("approve", block)

    def test_saving_is_a_download_of_what_the_pipeline_made(self):
        page = _page()
        block = _block(page, "function canvasVideo")

        self.assertIn("media/video", block)
        self.assertIn("download", block)


class TestNothingBehindTheScreenMoved(unittest.TestCase):

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_the_pipeline_is_untouched(self):
        import app.pipeline.pipeline as pipeline

        for name in self._imports(pipeline):
            with self.subTest(imported=name):
                self.assertNotIn("app.production", name)
                self.assertNotIn("review", name)

    def test_the_resolvers_are_untouched(self):
        from app.steps import (
            step01_script_resolve, step02_asset_resolve, step03_voice_resolve,
        )

        for module in (step01_script_resolve, step02_asset_resolve,
                       step03_voice_resolve):
            for name in self._imports(module):
                with self.subTest(module=module.__name__, imported=name):
                    self.assertNotIn("review", name)

    def test_the_review_service_did_not_change_shape(self):
        from app.services import studio_review

        for name in ("state", "generate_script", "save_script",
                     "generate_images", "regenerate_image",
                     "generate_voices", "regenerate_voice", "render"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(studio_review, name))

    def test_the_screen_flow_still_uses_the_same_places(self):
        """
        Sprint147이 공개 정보를 고칠 자리를 하나 더했다. 화면 흐름
        자체는 그대로다 - 대본·이미지·음성·승인은 예전 자리로 간다.
        """

        paths = {p for p in app.openapi()["paths"] if "review" in p}

        for path in ("/studio/api/review/{project_id}/script",
                     "/studio/api/review/{project_id}/images",
                     "/studio/api/review/{project_id}/voices",
                     "/studio/api/review/{project_id}/render"):
            with self.subTest(path=path):
                self.assertIn(path, paths)

    def test_the_handlers_the_markup_calls_are_declared(self):
        page = _page()
        script = page[page.index("<script>"):page.rindex("</script>")]

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
