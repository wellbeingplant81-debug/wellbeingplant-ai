"""
Sprint142 - Scene을 목록이 아니라 Timeline에서 고친다 (Epic 56, Phase 19).

Sprint121~123이 만든 검토 화면은 단계마다 scene을 세로로 늘어놓았다.
대본 여섯 줄, 이미지 여섯 장, 음성 여섯 줄 - 같은 scene이 세 곳에
흩어져 있어서 "3번 scene이 지금 어떤 상태인가"를 한눈에 볼 수 없었다.

이번에는 한 줄로 편다. 그리고 고르면 그 scene 하나만 아래에서
고친다.

기능은 하나도 새로 만들지 않는다
--------------------------------
대본 수정 · 이미지 재생성 · 음성 재생성 · 미리듣기는 Sprint121이
이미 만들어 둔 것을 그대로 부른다. 새 API도 만들지 않는다.

    reviewSaveScript      rnar{N} 텍스트를 읽어 PUT /script
    reviewRegenerate      POST /images/{N} · /voices/{N}
    playVoice             voice_url 재생

상태는 Review가 이미 아는 것만 쓴다
-----------------------------------
서버가 scene마다 주는 사실은 둘뿐이다.

    has_image · has_voice

그래서 준비됨/일부/아직 없음은 그 둘에서 나온다. 생성 중과 실패는
화면이 스스로 겪은 일이다 - 방금 그 scene의 재생성을 눌렀고, 그것이
실패로 돌아왔다. 수정됨도 화면이 안다 - 글상자의 글이 불러온 것과
다르다.

셋 다 서버에 없는 상태를 지어낸 것이 아니라, 화면이 실제로 아는
것이다.

만들지 않은 것 - 정직하게 적어 둔다
-----------------------------------
scene 하나의 길이는 지금 화면에 오지 않는다. 서버는 영상 전체의
예상·실측만 준다(_review_length가 scene별로 재지만 합만 돌려준다).
scene마다 적으려면 응답에 칸을 더해야 하는데 이번 스프린트는 API를
바꾸지 않는다. 그래서 전체 길이만 적고 scene 칸은 비운다.

같은 이유로 재생 위치와 scene을 잇지 않는다. scene별 길이를 모르면
"지금 몇 번 scene인가"를 알 수 없고, 균등하게 나누면 틀린 자리를
가리킨다.
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

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _script():
    page = _page()
    return page[page.index("<script>"):]


def _function(name):
    script = _script()
    block = script[script.index(f"function {name}("):]
    end = block.find("\nfunction ", 1)

    return block if end < 0 else block[:end]


def _without_comments(block):
    return re.sub(r"//.*", "", block)


class TestTheTimelineExists(unittest.TestCase):

    def test_there_is_a_timeline(self):
        self.assertIn("function sceneTimeline(", _script())

    def test_it_is_drawn_with_the_review(self):
        self.assertIn("sceneTimeline", _function("renderReview"))

    def test_a_card_is_drawn_per_scene(self):
        self.assertIn("function sceneCard(", _script())
        self.assertIn("sceneCard", _function("sceneTimeline"))

    def test_the_card_shows_the_number(self):
        block = _function("sceneCard")

        self.assertIn("s.scene", block)

    def test_the_card_shows_the_thumbnail(self):
        block = _function("sceneCard")

        self.assertIn("image_url", block)

    def test_the_card_shows_the_first_line_of_the_script(self):
        block = _function("sceneCard")

        self.assertIn("narration", block)
        self.assertIn("function sceneFirstLine(", _script())

    def test_the_card_can_be_picked(self):
        block = _function("sceneCard")

        self.assertIn("pickScene(", block)
        self.assertIn("function pickScene(", _script())

    def test_the_card_has_an_edit_button(self):
        block = _function("sceneCard")

        self.assertIn("수정", block)


class TestTheStatusComesFromWhatReviewKnows(unittest.TestCase):

    def test_there_is_one_function_that_decides(self):
        self.assertIn("function sceneStatus(", _script())

    def test_ready_comes_from_the_two_facts_the_server_sends(self):
        block = _function("sceneStatus")

        self.assertIn("has_image", block)
        self.assertIn("has_voice", block)

    def test_busy_and_failed_are_what_the_screen_itself_saw(self):
        """서버에 없는 상태를 지어낸 것이 아니다."""

        script = _script()

        self.assertIn("sceneMark", script)
        self.assertIn("sceneMark", _function("sceneStatus"))

    def test_the_screen_records_what_it_fired_and_what_came_back(self):
        block = _function("reviewRegenerate")

        self.assertIn("sceneMark", block)

    def test_edited_is_the_unsaved_text(self):
        """
        고친 글은 화면이 들고 있는다. 예전 목록은 글상자가 전부 떠
        있어 다른 scene을 봐도 남았지만, Timeline은 하나만 열리므로
        들고 있지 않으면 scene을 바꾸는 순간 조용히 사라진다.
        """

        script = _script()

        self.assertIn("let sceneDraft", script)
        self.assertIn("sceneDraft", _function("sceneStatus"))
        self.assertIn("sceneDraft", _function("scenePanel"))

    def test_an_unsaved_edit_survives_switching_scenes(self):
        """열려 있지 않은 scene의 글도 저장에 함께 실린다."""

        block = _function("reviewSaveScript")

        self.assertIn("sceneDraft[s.scene]", block)
        self.assertIn("sceneDraft = {}", block)

    def test_the_status_is_shown_as_a_colour_class(self):
        block = _function("sceneCard")

        self.assertIn("sceneStatus", block)

    def test_no_status_the_server_does_not_know_is_invented(self):
        """
        서버가 scene마다 주는 것은 has_image · has_voice 둘뿐이다.
        다른 이름을 읽으면 없는 칸을 읽는 것이 된다.
        """

        block = _without_comments(
            _function("sceneStatus") + _function("sceneCard"))

        for absent in ("s.status", "s.state", "s.failed", "s.progress"):
            with self.subTest(name=absent):
                self.assertNotIn(absent, block)


class TestThePanelReusesEverything(unittest.TestCase):

    def test_there_is_a_panel(self):
        self.assertIn("function scenePanel(", _script())
        self.assertIn("scenePanel", _function("sceneTimeline"))

    def test_the_script_box_keeps_its_name(self):
        """reviewSaveScript가 그 이름으로 읽는다."""

        block = _function("scenePanel")

        self.assertIn("rnar", block)

    def test_saving_uses_the_function_that_already_exists(self):
        self.assertIn("reviewSaveScript", _function("scenePanel"))

    def test_regenerating_uses_the_endpoints_that_already_exist(self):
        block = _function("scenePanel")

        self.assertIn("reviewRegenerate('images'", block)
        self.assertIn("reviewRegenerate('voices'", block)

    def test_the_preview_uses_the_player_that_already_exists(self):
        self.assertIn("playVoice", _function("scenePanel"))

    def test_saving_still_sends_every_scene(self):
        """
        한 scene만 열려 있어도 나머지 문장이 사라지면 안 된다.

        Sprint144에서 보낼 목록이 화면이 고치고 있는 그것
        (timelineScenes)으로 바뀌었다 - 손대지 않았으면 서버가 준
        목록과 같다.
        """

        block = _function("reviewSaveScript")

        self.assertIn("timelineScenes(reviewState).map", block)
        self.assertIn("value: s.narration", block)

    def test_no_new_api_path_was_invented(self):
        paths = set(re.findall(r'"/studio/api/review[^"`]*"', _page()))

        # Sprint242 - 자료 사용 방식을 화면에서 고르게 하면서 review
        # 엔드포인트가 하나 늘었다. 그 Sprint 가 **의도적으로** 더한
        # 것이고, 이 시험이 그것을 알아챈 것이 곧 이 가드가 제 일을
        # 한 것이다.
        #
        # 정규식을 비켜 가거나(백틱 템플릿) 검사를 지우지 않는다 -
        # 늘어난 것을 이름으로 적어 다음에 또 조용히 늘면 여전히
        # 걸리게 둔다.
        self.assertEqual(paths, {
            '"/studio/api/review"',
            '"/studio/api/review/"',
        })


class TestPickingASceneMovesTheCanvas(unittest.TestCase):

    def test_picking_redraws(self):
        block = _function("pickScene")

        self.assertIn("renderReview", block)

    def test_the_canvas_shows_the_picked_scene(self):
        self.assertIn("function canvasScene(", _script())
        self.assertIn("canvasScene", _function("canvasVideo"))

    def test_the_finished_video_still_shows(self):
        block = _function("canvasVideo")

        self.assertIn("state.done.video", block)
        self.assertIn("<video controls", block)

    def test_the_picked_scene_is_marked_on_the_timeline(self):
        """고른 것과 그리는 것이 같은 자리에서 정해져야 한다."""

        script = _script()

        self.assertIn("function sceneCurrent(", script)
        self.assertIn("scenePick", _function("sceneCurrent"))
        self.assertIn("sceneCurrent(state)", _function("sceneTimeline"))

        card = _function("sceneCard")

        self.assertIn("s.scene === picked", card)
        self.assertIn('on?"on":""', card)


class TestItInventsNoNumbers(unittest.TestCase):

    def test_no_per_scene_duration_is_made_up(self):
        """
        서버는 영상 전체의 예상·실측만 준다. scene으로 나누면 지어내는
        것이 된다 - scene마다 길이가 다르기 때문이다.
        """

        block = _without_comments(
            _function("sceneCard") + _function("sceneTimeline")
            + _function("scenePanel"))

        for made_up in ("estimated_seconds", "measured_seconds"):
            with self.subTest(name=made_up):
                self.assertNotIn(made_up, block)

    def test_the_whole_video_length_is_still_shown(self):
        """전체 길이는 원래 알던 것이다 - 그대로 둔다."""

        block = _function("canvasLength")

        self.assertIn("measured_seconds", block)
        self.assertIn("estimated_seconds", block)

    def test_playback_position_is_only_mapped_when_the_lengths_are_known(self):
        """
        Sprint142에는 scene별 길이가 없어 재생 위치를 이을 수 없었다.
        Sprint143이 그 값을 열었으므로 이제 잇는다 - 다만 값이 없으면
        여전히 답하지 않는다. 균등하게 나누면 틀린 자리를 가리킨다.
        """

        block = _function("sceneAtTime")

        self.assertIn("scene_seconds", block)
        self.assertIn("return null", block)


class TestNothingBelowTheScreenMoved(unittest.TestCase):

    def _constants(self, module):
        with open(module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        return {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_the_review_service_did_not_change(self):
        from app.services import studio_review

        constants = self._constants(studio_review)

        for name in ("timeline", "sceneMark", "생성 중", "수정됨"):
            with self.subTest(name=name):
                self.assertNotIn(name, constants)

    def test_the_router_did_not_change(self):
        from app.routers import studio

        with open(studio.__file__, encoding="utf-8") as f:
            source = f.read()

        for name in ("sceneTimeline", "sceneStatus", "scenePanel"):
            with self.subTest(name=name):
                self.assertNotIn(name, source)

    def test_the_review_payload_keys_are_unchanged(self):
        from fastapi.testclient import TestClient

        from app.main import app
        import app.routers.studio as studio_router
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as project:
            with patch.object(studio_router, "_project_path",
                              lambda project_id: project):
                state = TestClient(app).get(
                    "/studio/api/review/p1").json()

        self.assertEqual(
            set(state),
            {"project_id", "step", "label", "title", "index", "total",
             "done", "scenes", "providers", "estimated_seconds",
             "measured_seconds", "scene_seconds", "timeline",
             "metadata", "publish_problems", "thumbnail_url",
             # Sprint150 - 훑어 둔 내 PC 자료의 요약.
             "library",
             "queue_status"})

    def test_the_pipeline_and_steps_did_not_change(self):
        import app.pipeline.pipeline as pipeline
        from app.steps import step01_script, step02_asset_resolve

        for module in (pipeline, step01_script, step02_asset_resolve):
            with self.subTest(module=module.__name__):
                self.assertNotIn("timeline", self._constants(module))


class TestTheOldFeaturesSurvive(unittest.TestCase):
    """Sprint121의 기능은 하나도 빠지지 않는다."""

    def test_every_review_action_is_still_reachable(self):
        page = _page()

        for name in ("reviewSaveScript", "reviewRegenerate", "playVoice",
                     "reviewGenerateScript", "reviewGenerateImages",
                     "reviewGenerateVoices", "reviewApprove",
                     "reviewPickProvider", "reviewUpload"):
            with self.subTest(name=name):
                self.assertIn(name, page)

    def test_the_provider_pickers_are_still_there(self):
        script = _script()

        self.assertRegex(script, r'reviewProviders\(\s*state\s*,\s*"image"')
        self.assertRegex(script, r'reviewProviders\(\s*state\s*,\s*"voice"')

    def test_the_whole_batch_buttons_are_still_there(self):
        script = _script()

        for name in ("reviewGenerateImages", "reviewGenerateVoices"):
            with self.subTest(name=name):
                self.assertIn(f"{name}()", script)

    def test_every_handler_the_markup_calls_is_declared(self):
        page = _page()
        script = _script()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
