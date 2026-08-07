"""
Sprint143 - Timeline을 시간 위에 놓는다 (Epic 56, Phase 20).

Sprint142에서 Timeline을 만들며 두 가지를 못 했다고 적었다.

    scene 하나의 길이     서버가 합만 돌려준다
    재생 위치 -> scene    scene별 길이를 모르면 알 수 없다

둘 다 같은 원인이었다. 이번에 그 칸 하나를 연다.

새로 계산하지 않는다
--------------------
_review_length는 이미 scene마다 값을 구하고 있었다. 합만 돌려주고
버렸을 뿐이다.

    실측  get_audio_duration(scene{N}.wav)      - 합이 measured_seconds
    예상  estimate_duration(narration)          - 합이 estimated_seconds

estimate_script_duration은 문자 그대로 scene별 estimate_duration의
합이다(sum(...)). 그러니 scene별 값을 내보내는 것은 새 계산이 아니라
버리던 것을 살리는 일이다.

영상과 어긋나지 않는다
----------------------
실측값은 render가 쓰는 그 값이다. scene_timeline.build_timeline도 같은
get_audio_duration을 부르고, 그 경계로 영상이 만들어진다("빈틈도 겹침도
없다. 전체 합은 나레이션 오디오 전체 길이와 같다"). 그래서 앞에서부터
더한 것이 곧 영상 속 그 scene의 시작 시각이다.

무엇을 돌려주는지 섞지 않는다
-----------------------------
scene_seconds는 그때 돌려준 총합과 같은 종류다.

    measured_seconds가 있으면   실측 목록(합 = measured_seconds)
    없으면                      예상 목록(합 = estimated_seconds)

화면은 이미 measured_seconds != null로 둘을 가른다(canvasLength).
새 칸을 더 만들지 않는다.
"""

import ast
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

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


NARRATIONS = [
    "무릎이 아플 때 천천히 따라 하십시오.",
    "열 번씩 반복합니다.",
    "무리하지 마십시오. 숨을 고르게 쉽니다.",
]


def _state(has_voice):
    return {
        "scenes": [
            {"scene": n, "narration": text, "has_image": True,
             "has_voice": has_voice}
            for n, text in enumerate(NARRATIONS, start=1)
        ],
    }


class TestTheServerStopsThrowingThemAway(unittest.TestCase):

    def test_it_returns_the_per_scene_list_too(self):
        from app.routers.studio import _review_length

        result = _review_length("x", _state(False))

        self.assertEqual(len(result), 3)

    def test_the_estimated_list_sums_to_the_estimated_total(self):
        from app.routers.studio import _review_length

        estimated, measured, seconds = _review_length("x", _state(False))

        self.assertIsNone(measured)
        self.assertEqual(len(seconds), len(NARRATIONS))
        self.assertAlmostEqual(sum(seconds), estimated, places=1)

    def test_each_estimated_value_is_the_one_the_estimator_gives(self):
        """새 공식을 만들지 않는다 - 총합이 쓰는 그 함수다."""

        from app.routers.studio import _review_length
        from app.services.duration_estimator import estimate_duration

        _, _, seconds = _review_length("x", _state(False))

        for value, text in zip(seconds, NARRATIONS):
            with self.subTest(text=text):
                self.assertAlmostEqual(value, estimate_duration(text),
                                       places=2)

    def test_the_measured_list_sums_to_the_measured_total(self):
        from app.routers import studio

        lengths = {1: 4.8, 2: 5.2, 3: 4.5}

        def fake(path):
            number = int(os.path.basename(path).split("scene")[1].split(".")[0])
            return lengths[number]

        with patch("app.services.duration_optimizer.get_audio_duration",
                   side_effect=fake):
            estimated, measured, seconds = studio._review_length(
                "x", _state(True))

        self.assertEqual(seconds, [4.8, 5.2, 4.5])
        self.assertAlmostEqual(sum(seconds), measured, places=2)
        self.assertNotEqual(measured, estimated)

    def test_no_scenes_means_no_list(self):
        from app.routers.studio import _review_length

        estimated, measured, seconds = _review_length("x", {"scenes": []})

        self.assertEqual(seconds, [])
        self.assertEqual(estimated, 0.0)
        self.assertIsNone(measured)

    def test_it_calls_no_new_measuring_function(self):
        """실측은 Duration Optimizer의 ffprobe, 예상은 그 estimator."""

        from app.routers import studio

        with open(studio.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        source = ast.get_source_segment(
            open(studio.__file__, encoding="utf-8").read(),
            next(n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef)
                 and n.name == "_review_length"))

        self.assertIn("get_audio_duration", source)
        self.assertIn("estimate_duration", source)


class TestThePayloadCarriesIt(unittest.TestCase):

    def _state_for(self, project):
        from fastapi.testclient import TestClient

        import app.routers.studio as studio_router
        from app.main import app

        with patch.object(studio_router, "_project_path",
                          lambda project_id: project):
            return TestClient(app).get("/studio/api/review/p1").json()

    def test_the_field_is_there(self):
        with tempfile.TemporaryDirectory() as project:
            self.assertIn("scene_seconds", self._state_for(project))

    def test_it_is_one_value_per_scene(self):
        import json

        with tempfile.TemporaryDirectory() as project:
            with open(os.path.join(project, "script.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"title": "t", "scenes": [
                    {"scene": n, "narration": text, "image_prompt": "p"}
                    for n, text in enumerate(NARRATIONS, start=1)]}, f,
                    ensure_ascii=False)

            state = self._state_for(project)

        self.assertEqual(len(state["scene_seconds"]),
                         len(state["scenes"]))

    def test_nothing_else_in_the_payload_changed(self):
        with tempfile.TemporaryDirectory() as project:
            state = self._state_for(project)

        self.assertEqual(
            set(state),
            {"project_id", "step", "label", "title", "index", "total",
             "done", "scenes", "providers", "estimated_seconds",
             "measured_seconds", "scene_seconds", "timeline",
             "metadata", "publish_problems", "thumbnail_url",
             # Sprint150 - 훑어 둔 내 PC 자료의 요약.
             "library",
             "queue_status"})


class TestTheCardShowsTheLength(unittest.TestCase):

    def test_there_is_one_function_that_reads_it(self):
        self.assertIn("function sceneSeconds(", _script())

    def test_it_reads_the_field_and_invents_nothing(self):
        block = _without_comments(_function("sceneSeconds"))

        self.assertIn("scene_seconds", block)
        self.assertNotIn("length /", block)
        self.assertNotIn("/ state.scenes.length", block)

    def test_the_card_shows_it(self):
        block = _function("sceneCard")

        self.assertIn("sceneSeconds", block)

    def test_it_says_whether_it_was_measured(self):
        """실측과 예상을 섞으면 화면이 틀린 말을 한다."""

        script = _script()

        self.assertIn("measured_seconds", _function("sceneLengthLabel"))

    def test_the_whole_length_is_still_shown(self):
        block = _function("canvasLength")

        self.assertIn("measured_seconds", block)
        self.assertIn("estimated_seconds", block)


class TestTheVideoAndTheTimelineAgree(unittest.TestCase):

    def test_a_scene_knows_where_it_starts(self):
        self.assertIn("function sceneStart(", _script())

    def test_the_start_is_the_sum_of_what_came_before(self):
        """build_timeline이 정한 그대로다 - 앞 end가 다음 start다."""

        block = _function("sceneStart")

        self.assertIn("sceneSeconds", block)

    def test_a_time_maps_to_a_scene(self):
        """시작 시각과 재생 위치가 같은 값을 읽어야 어긋나지 않는다."""

        self.assertIn("function sceneAtTime(", _script())

        for name in ("sceneStart", "sceneAtTime"):
            with self.subTest(name=name):
                self.assertIn("sceneSeconds", _function(name))

    def test_playing_moves_the_highlight(self):
        script = _script()

        self.assertIn("function followVideo(", script)
        self.assertIn("ontimeupdate", script)
        self.assertIn("sceneAtTime", _function("followVideo"))

    def test_picking_moves_the_video(self):
        block = _function("pickScene")

        self.assertIn("sceneStart", block)
        self.assertIn("currentTime", block)

    def test_following_does_not_rebuild_the_player(self):
        """다시 그리면 재생이 끊긴다."""

        block = _function("followVideo")

        self.assertNotIn("renderReview", block)
        self.assertIn("paintTimeline", block)

    def test_there_is_a_partial_repaint(self):
        script = _script()

        self.assertIn("function paintTimeline(", script)
        self.assertNotIn("renderReview", _function("paintTimeline"))

    def test_it_does_not_steal_the_cursor_while_typing(self):
        block = _function("paintTimeline")

        self.assertIn("activeElement", block)


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

        self.assertNotIn("scene_seconds", self._constants(studio_review))

    def test_the_render_timeline_did_not_change(self):
        from app.services import scene_timeline

        self.assertNotIn("scene_seconds", self._constants(scene_timeline))

    def test_the_pipeline_and_builder_did_not_change(self):
        import app.pipeline.pipeline as pipeline
        from app.services import video_builder

        for module in (pipeline, video_builder):
            with self.subTest(module=module.__name__):
                self.assertNotIn("scene_seconds", self._constants(module))

    def test_no_new_api_path_was_invented(self):
        paths = set(re.findall(r'"/studio/api/review[^"`]*"', _page()))

        self.assertEqual(paths, {'"/studio/api/review"'})


class TestTheOldFeaturesSurvive(unittest.TestCase):

    def test_every_review_action_is_still_reachable(self):
        page = _page()

        for name in ("reviewSaveScript", "reviewRegenerate", "playVoice",
                     "reviewGenerateScript", "reviewGenerateImages",
                     "reviewGenerateVoices", "reviewApprove",
                     "reviewPickProvider", "sceneTimeline", "scenePanel"):
            with self.subTest(name=name):
                self.assertIn(name, page)

    def test_the_unsaved_edit_still_survives(self):
        block = _function("reviewSaveScript")

        self.assertIn("sceneDraft[s.scene]", block)

    def test_every_handler_the_markup_calls_is_declared(self):
        page = _page()
        script = _script()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change|timeupdate)="(\w+)\(',
                               page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
