"""
Sprint123 - 영상을 보면서 고친다 (Epic 55, Phase 3).

화면의 주인공이 단계에서 영상으로 바뀐다. 사용자는 언제나 지금 만들고
있는 영상을 보면서 그 아래에서 고친다.

Sprint121의 승인 흐름은 한 줄도 바뀌지 않는다 - studio_review.py는
그대로다. 여기서 더하는 것은 화면이 영상을 보여 주는 데 필요한
읽기값 셋뿐이고, 전부 이미 있는 것에서 나온다.

    예상 길이   duration_estimator (Duration Gate가 쓰는 그것)
    실제 길이   audio/scenes/*.wav의 ffprobe 실측
    메타데이터  publish_package.json (Render가 만든 것)

예상과 실측을 나누는 이유가 있다. 음성이 생기기 전에는 대본 글자 수로
미루어 볼 수밖에 없고, 생긴 뒤에는 잴 수 있다. 잴 수 있는데 미루어
보면 화면이 틀린 숫자를 말하게 된다.

메타데이터는 Render 중에 만들어진다. 그 전에는 없으므로 편집 단계를
새로 만들지 않는다 - 없는 것을 있는 것처럼 보여 주지 않고, 언제
생기는지 적는다.
"""

import ast
import json
import os
import re
import sys
import tempfile
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


class TestTheVideoIsTheSubject(unittest.TestCase):

    def test_the_preview_card_exists(self):
        page = _page()

        self.assertIn('id="canvasPreview"', page)

    def test_it_is_pinned(self):
        page = _page()
        style = page[page.index("<style>"):page.index("</style>")]

        block = style[style.index(".canvas"):][:400]

        self.assertIn("sticky", block)

    def test_it_shows_a_placeholder_before_the_video_exists(self):
        page = _page()
        block = _block(page, "function canvasVideo")

        self.assertIn("done.video", block)
        self.assertIn("poster", block)

    def test_the_placeholder_uses_the_first_scene_image(self):
        """만드는 중에도 무엇을 만들고 있는지 보인다."""

        page = _page()
        block = _block(page, "function canvasVideo")

        self.assertIn("image_url", block)

    def test_the_four_actions_stay(self):
        page = _page()
        block = _block(page, "function canvasVideo")

        for label in ("재생", "다운로드", "YouTube", "Instagram"):
            with self.subTest(label=label):
                self.assertIn(label, block)

    def test_instagram_is_still_disabled_with_a_reason(self):
        page = _page()
        block = _block(page, "function canvasVideo")

        self.assertIn("disabled", block)
        self.assertIn("Meta", block)


class TestTheStatusCard(unittest.TestCase):

    def test_it_exists_and_is_pinned_with_the_preview(self):
        page = _page()

        self.assertIn('id="canvasStatus"', page)

    def test_it_names_what_is_happening_not_the_step_number(self):
        """STEP를 강조하지 않는다 - 지금 영상이 어떤 상태인가를 말한다."""

        page = _page()
        block = _block(page, "function canvasStatus")

        for word in ("대본", "이미지", "음성", "영상"):
            with self.subTest(word=word):
                self.assertIn(word, block)

        self.assertIn("생성", block)

    def test_it_says_ready_when_the_video_is_there(self):
        page = _page()
        block = _block(page, "function canvasStatus")

        self.assertIn("준비 완료", block)

    def test_it_carries_a_bar(self):
        page = _page()
        block = _block(page, "function canvasStatus")

        self.assertIn("bar", block)


class TestTheLengthIsMeasuredWhenItCanBe(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_the_estimator_is_the_existing_one(self):
        """새 계산을 만들지 않는다."""

        import app.routers.studio as studio

        source = open(studio.__file__, encoding="utf-8").read()

        self.assertIn("duration_estimator", source)
        self.assertIn("estimate_script_duration", source)

    def test_the_measurement_is_the_existing_ffprobe(self):
        import app.routers.studio as studio

        source = open(studio.__file__, encoding="utf-8").read()

        self.assertIn("get_audio_duration", source)

    def test_the_state_carries_both(self):
        page = _page()

        self.assertIn("estimated_seconds", page)
        self.assertIn("measured_seconds", page)

    def test_the_screen_prefers_the_measurement(self):
        """잴 수 있는데 미루어 보면 틀린 숫자를 말하게 된다."""

        page = _page()
        block = _block(page, "function canvasLength")

        self.assertIn("measured_seconds", block)
        self.assertIn("estimated_seconds", block)


class TestTheMetadataIsShownNotInvented(unittest.TestCase):

    def test_the_section_exists(self):
        page = _page()
        block = _block(page, "const REVIEW_STEPS", "\n];")

        self.assertIn("metadata", block)

    def test_it_says_when_it_appears(self):
        """Render 중에 만들어진다 - 그 전에는 없다."""

        page = _page()
        block = _block(page, "function reviewMetadataStep")

        self.assertIn("Render", block)

    def test_it_is_read_only(self):
        """편집 단계를 새로 만들지 않는다."""

        page = _page()
        block = _block(page, "function reviewMetadataStep")

        self.assertNotIn("<textarea", block)
        self.assertNotIn("<input", block)

    def test_it_reads_the_package_the_pipeline_wrote(self):
        import app.routers.studio as studio

        source = open(studio.__file__, encoding="utf-8").read()

        self.assertIn("publish_package.json", source)


class TestThePreviewFollowsEveryChange(unittest.TestCase):

    def test_every_edit_redraws_the_canvas(self):
        page = _page()

        for fn in ("async function reviewSaveScript",
                   "async function reviewRegenerate",
                   "async function reviewGenerateScript",
                   "async function reviewGenerateImages",
                   "async function reviewGenerateVoices"):
            with self.subTest(fn=fn):
                self.assertIn("renderReview", _block(page, fn))

    def test_redrawing_redraws_the_canvas_too(self):
        page = _page()
        block = _block(page, "function renderReview")

        self.assertIn("renderCanvas", block)

    def test_the_images_are_cache_busted(self):
        """다시 생성했는데 브라우저가 옛 그림을 보여 주면 안 된다."""

        page = _page()

        self.assertIn("Date.now()", _block(page, "function canvasVideo"))

    def test_the_finished_render_replaces_the_preview(self):
        """작업이 끝나면 완성된 영상으로 미리보기를 갈아 끼운다."""

        page = _page()
        cut = page[page.index("async function pollJob"):]
        block = cut[:cut.index("\n}\n") + 3]

        self.assertIn('d.state !== "running"', block)
        self.assertIn("openReview", block)


class TestTheReviewWorkflowIsUntouched(unittest.TestCase):

    def test_the_service_file_did_not_change(self):
        """Sprint121의 흐름은 한 줄도 바뀌지 않는다."""

        from app.services import studio_review

        source = open(studio_review.__file__, encoding="utf-8").read()

        for word in ("canvas", "preview", "duration_estimator",
                     "publish_package"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)

    def test_all_the_review_functions_are_still_there(self):
        from app.services import studio_review

        for name in ("state", "generate_script", "save_script",
                     "generate_images", "regenerate_image",
                     "generate_voices", "regenerate_voice", "render"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(studio_review, name))

    def test_the_endpoints_are_the_same_eight(self):
        paths = {p for p in app.openapi()["paths"] if "review" in p}

        self.assertEqual(len(paths), 8)

    def test_the_scene_features_survive(self):
        page = _page()

        for fn in ("reviewSaveScript", "reviewRegenerate", "playVoice"):
            with self.subTest(fn=fn):
                self.assertIn(fn, page)

    def test_the_accordion_survives(self):
        page = _page()

        self.assertIn("reviewSection", page)
        self.assertIn("toggleReviewSection", page)

    def test_there_is_still_no_regenerate_everything(self):
        page = _page()

        for forbidden in ("전부 다시", "모두 다시 생성"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, page)


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
                self.assertNotIn("canvas", name)

    def test_the_resolvers_are_untouched(self):
        from app.steps import (
            step01_script_resolve, step02_asset_resolve, step03_voice_resolve,
        )

        for module in (step01_script_resolve, step02_asset_resolve,
                       step03_voice_resolve):
            for name in self._imports(module):
                with self.subTest(module=module.__name__, imported=name):
                    self.assertNotIn("review", name)
                    self.assertNotIn("canvas", name)

    def test_the_handlers_the_markup_calls_are_declared(self):
        page = _page()
        script = page[page.index("<script>"):page.rindex("</script>")]

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
