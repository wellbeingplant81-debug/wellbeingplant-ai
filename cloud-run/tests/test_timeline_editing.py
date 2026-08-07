"""
Sprint144 - Timeline에서 scene을 늘린다 (Epic 56, Phase 21).

Sprint142가 Timeline을, Sprint143이 시간을 놓았다. 이번에는 편집이다 -
다만 넷 중 둘만 한다.

무엇을 빼고 왜 빼는지
---------------------
이동과 삭제는 화면만으로 정직하게 만들 수 없다. 코드를 돌려 확인한
것을 그대로 적어 둔다.

    이동   video_builder는 asset_paths를 script.json의 목록 순서로
           모으고, durations는 build_timeline(scene 번호 정렬) 순서로
           만들어 index로 짝짓는다. 번호를 그대로 두고 순서만 바꾸면
           3번 그림에 2번 길이가 붙는다 - 효과가 없는 것이 아니라
           그림과 소리가 어긋난다.

    삭제   subtitle_service는 audio/scenes/scene*.wav를 glob해
           len(scene_audios) != len(scenes)면 멈춘다. script.json에서
           scene을 빼도 wav는 남으므로 렌더가 "Scene 오디오 개수와
           Scene 개수가 다릅니다"로 실패한다.

둘 다 Render 쪽을 고쳐야 풀린다. 이번 스프린트는 그것을 금지하므로
넣지 않는다 - 되는 척하는 버튼을 두느니 없는 편이 낫다.

무엇을 하는가
-------------
추가와 복제, 그리고 저장 전 되돌리기. 셋 다 화면 안에서만 일어나고,
저장은 Sprint121이 만든 PUT /script 하나로 간다.

    timelineDraft   화면이 고치고 있는 scene 목록. 손대기 전에는 null
    sceneDraft      저장하지 않은 글 (Sprint142)

새 scene은 저장되려면 대본과 image_prompt가 둘 다 있어야 한다 -
step01_script_resolve.validate가 그렇게 본다. 그래서 패널에 그 칸을
연다. 없던 값을 만드는 것이 아니라 이미 저장에 실려 가던 값이다.

복제가 그림과 음성까지 가져오지는 않는다
----------------------------------------
그 둘은 scene 번호로 된 파일이고(images/scene{N}.png,
audio/scenes/scene{N}.wav), 복제본은 새 번호를 받는다. 파일을 복사하는
것은 화면이 할 일이 아니므로 대본과 image_prompt만 가져오고, 그림과
음성은 "아직 없음"으로 둔다. 기존 생성 버튼을 누르면 채워진다.
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


class TestTheDraftHoldsTheWorkingList(unittest.TestCase):

    def test_there_is_a_draft(self):
        self.assertIn("let timelineDraft", _script())

    def test_untouched_means_the_server_list(self):
        block = _function("timelineScenes")

        self.assertIn("timelineDraft", block)
        self.assertIn("state.scenes", block)

    def test_everything_draws_from_one_place(self):
        """목록이 두 곳에서 만들어지면 화면이 갈린다."""

        self.assertIn("timelineScenes", _function("sceneTimeline"))

    def test_the_draft_never_touches_the_server(self):
        """저장 전에는 프로젝트 파일이 바뀌지 않는다."""

        for name in ("addScene", "duplicateScene", "revertTimeline"):
            block = _without_comments(_function(name))
            with self.subTest(name=name):
                self.assertNotIn("fetch(", block)
                self.assertNotIn("reviewCall", block)


class TestAddingAScene(unittest.TestCase):

    def test_there_is_a_button_and_a_handler(self):
        script = _script()

        self.assertIn("function addScene(", script)
        self.assertIn("addScene()", script)

    def test_the_number_is_the_next_unused_one(self):
        """번호는 파일 이름이 된다 - 다시 쓰면 남의 그림을 가리킨다."""

        self.assertIn("function nextSceneNumber(", _script())
        self.assertIn("Math.max", _function("nextSceneNumber"))
        self.assertIn("nextSceneNumber", _function("addScene"))

    def test_it_starts_empty(self):
        block = _function("addScene")

        self.assertIn('narration: ""', block)
        self.assertIn('image_prompt: ""', block)

    def test_it_has_no_image_or_voice(self):
        block = _function("addScene")

        self.assertIn("has_image: false", block)
        self.assertIn("has_voice: false", block)

    def test_it_is_marked_as_needing_writing(self):
        script = _script()

        self.assertIn("작성 필요", script)
        self.assertIn("sceneOrigin", _function("addScene"))


class TestDuplicatingAScene(unittest.TestCase):

    def test_there_is_a_handler(self):
        self.assertIn("function duplicateScene(", _script())

    def test_the_card_offers_it(self):
        self.assertIn("duplicateScene(", _function("sceneCard"))

    def test_it_copies_the_words(self):
        block = _function("duplicateScene")

        self.assertIn("narration", block)
        self.assertIn("image_prompt", block)

    def test_it_takes_a_new_number(self):
        self.assertIn("nextSceneNumber", _function("duplicateScene"))

    def test_it_does_not_claim_the_picture_or_the_voice(self):
        """
        그 둘은 scene 번호로 된 파일이다. 복제본은 새 번호를 받으므로
        그 파일이 없다 - 있다고 말하면 화면이 거짓말을 한다.
        """

        block = _function("duplicateScene")

        self.assertIn("has_image: false", block)
        self.assertIn("has_voice: false", block)

    def test_it_generates_nothing_by_itself(self):
        block = _without_comments(_function("duplicateScene"))

        self.assertNotIn("reviewRegenerate", block)
        self.assertNotIn("reviewCall", block)

    def test_it_is_marked_as_needing_a_look(self):
        self.assertIn("수정 필요", _script())


class TestTheDraftStatesAreShown(unittest.TestCase):

    def test_the_origin_is_remembered(self):
        self.assertIn("let sceneOrigin", _script())

    def test_the_status_reads_it(self):
        self.assertIn("sceneOrigin", _function("sceneStatus"))

    def test_the_earlier_states_still_work(self):
        block = _function("sceneStatus")

        for name in ("sceneMark", "sceneDraft", "has_image", "has_voice"):
            with self.subTest(name=name):
                self.assertIn(name, block)


class TestGoingBack(unittest.TestCase):

    def test_there_is_a_way_back(self):
        script = _script()

        self.assertIn("function revertTimeline(", script)
        self.assertIn("revertTimeline()", script)

    def test_it_drops_both_drafts(self):
        block = _function("revertTimeline")

        self.assertIn("timelineDraft = null", block)
        self.assertIn("sceneDraft = {}", block)
        self.assertIn("sceneOrigin = {}", block)

    def test_it_is_only_offered_when_there_is_something_to_undo(self):
        block = _function("sceneTimeline")

        self.assertIn("timelineDirty", block)
        self.assertIn("function timelineDirty(", _script())


class TestSavingUsesWhatAlreadyExists(unittest.TestCase):

    def test_no_new_api_path_was_invented(self):
        paths = set(re.findall(r'"/studio/api/review[^"`]*"', _page()))

        self.assertEqual(paths, {'"/studio/api/review"'})

    def test_it_sends_the_working_list(self):
        block = _function("reviewSaveScript")

        self.assertIn("timelineScenes", block)

    def test_it_sends_the_unsaved_words(self):
        block = _function("reviewSaveScript")

        self.assertIn("sceneDraft[s.scene]", block)

    def test_it_sends_the_image_prompt_the_person_typed(self):
        """새 scene은 그 값이 없으면 저장이 거절된다."""

        block = _function("reviewSaveScript")

        self.assertIn("promptDraft", block)

    def test_saving_clears_the_drafts(self):
        block = _function("reviewSaveScript")

        self.assertIn("timelineDraft = null", block)

    def test_the_panel_lets_the_person_type_the_image_prompt(self):
        block = _function("scenePanel")

        self.assertIn("rimg", block)
        self.assertIn("image_prompt", block)


class TestTheValidatorStillDecides(unittest.TestCase):
    """화면이 통과시킨 대본이 저장에서 걸리면 안 된다."""

    def test_a_new_scene_needs_both_fields(self):
        from app.steps import step01_script_resolve

        self.assertEqual(
            step01_script_resolve.REQUIRED_SCENE_FIELDS,
            ("scene", "narration", "image_prompt"))

    def test_an_empty_new_scene_is_refused_by_the_server(self):
        from app.steps import step01_script_resolve

        data = {"title": "t", "scenes": [
            {"scene": 1, "narration": "a", "image_prompt": "p"},
            {"scene": 2, "narration": "", "image_prompt": ""},
        ]}

        with self.assertRaises(step01_script_resolve.ScriptResolveError):
            step01_script_resolve.validate(data)

    def test_a_filled_new_scene_passes(self):
        from app.steps import step01_script_resolve

        data = {"title": "t", "scenes": [
            {"scene": 1, "narration": "a", "image_prompt": "p"},
            {"scene": 7, "narration": "b", "image_prompt": "q"},
        ]}

        self.assertEqual(
            len(step01_script_resolve.validate(data)["scenes"]), 2)


class TestMovingAndDeletingAreNotHere(unittest.TestCase):
    """
    되는 척하는 버튼을 두지 않는다. 왜 없는지는 이 시험이 근거를
    들고 있다 - 다음에 붙일 사람이 같은 자리를 다시 확인하지 않도록.
    """

    def test_no_move_handler_exists(self):
        script = _script()

        for name in ("moveScene", "dragScene", "reorderScene"):
            with self.subTest(name=name):
                self.assertNotIn(f"function {name}(", script)

    def test_no_delete_handler_exists(self):
        script = _script()

        for name in ("deleteScene", "removeScene"):
            with self.subTest(name=name):
                self.assertNotIn(f"function {name}(", script)

    def test_the_render_still_orders_by_scene_number(self):
        """이동이 왜 안 되는지의 근거."""

        from app.services import scene_timeline

        with open(scene_timeline.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn('sorted(scenes, key=lambda scene: scene["scene"])',
                      source)

    def test_the_subtitles_still_count_the_audio_files(self):
        """삭제가 왜 안 되는지의 근거."""

        from app.services import subtitle_service

        with open(subtitle_service.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("len(scene_audios) != len(scenes)", source)


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

        for name in ("timelineDraft", "작성 필요", "수정 필요"):
            with self.subTest(name=name):
                self.assertNotIn(name, self._constants(studio_review))

    def test_the_router_did_not_change(self):
        from app.routers import studio

        with open(studio.__file__, encoding="utf-8") as f:
            source = f.read()

        for name in ("timelineDraft", "addScene", "duplicateScene"):
            with self.subTest(name=name):
                self.assertNotIn(name, source)

    def test_the_render_path_did_not_change(self):
        from app.services import scene_timeline, subtitle_service, video_builder

        for module in (video_builder, scene_timeline, subtitle_service):
            with self.subTest(module=module.__name__):
                self.assertNotIn("timelineDraft", self._constants(module))


class TestTheOldFeaturesSurvive(unittest.TestCase):

    def test_every_review_action_is_still_reachable(self):
        page = _page()

        for name in ("reviewSaveScript", "reviewRegenerate", "playVoice",
                     "reviewGenerateScript", "reviewGenerateImages",
                     "reviewGenerateVoices", "reviewApprove",
                     "sceneTimeline", "scenePanel", "sceneSeconds",
                     "followVideo"):
            with self.subTest(name=name):
                self.assertIn(name, page)

    def test_every_handler_the_markup_calls_is_declared(self):
        page = _page()
        script = _script()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change|input|timeupdate)="(\w+)\(',
                               page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
