"""
Sprint145 - 정한 차례대로 만든다 (Epic 56, Phase 22).

Sprint144에서 이동과 삭제를 넣지 못한 이유가 둘이었고, 이번에 그
둘을 푼다.

    이동   build_timeline이 scene 번호로 다시 정렬해 목록 순서를
           덮어썼다. video_builder는 asset을 목록 순서로 모으므로
           둘이 어긋나 3번 그림에 2번 길이가 붙었다.

    삭제   subtitle_service가 wav 파일 개수와 scene 개수를 맞췄다.
           지운 scene의 wav가 남아 렌더가 멈췄다.

번호와 파일은 그대로 둔다
-------------------------
    번호   한 번 준 것을 다시 쓰지 않는다
    파일   images/scene{N}.png · audio/scenes/scene{N}.wav 그대로
    순서   timeline.json에 따로 적는다

없으면 예전 그대로다. 손대지 않은 프로젝트는 아무것도 달라지지 않는다.
"""

import json
import os
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import scene_order, scene_timeline

NARRATIONS = {
    1: "첫 번째 문장입니다.",
    2: "두 번째 문장입니다.",
    3: "세 번째 문장입니다.",
    4: "네 번째 문장입니다.",
}

LENGTHS = {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0}


def _project(numbers=(1, 2, 3), with_media=True):
    path = tempfile.mkdtemp()

    os.makedirs(os.path.join(path, "images"), exist_ok=True)
    os.makedirs(os.path.join(path, "audio", "scenes"), exist_ok=True)

    scenes = [
        {"scene": n, "narration": NARRATIONS[n], "image_prompt": f"p{n}"}
        for n in numbers
    ]

    with open(os.path.join(path, "script.json"), "w", encoding="utf-8") as f:
        json.dump({"title": "t", "scenes": scenes}, f, ensure_ascii=False)

    if with_media:
        for n in numbers:
            open(os.path.join(path, "images", f"scene{n}.png"), "wb").close()

            wav = wave.open(
                os.path.join(path, "audio", "scenes", f"scene{n}.wav"), "wb")
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"\x00\x00" * int(24000 * LENGTHS[n]))
            wav.close()

    return path, scenes


class TestTimelineReorderAffectsRenderOrder(unittest.TestCase):

    def test_timeline_reorder_affects_render_order(self):
        """[1,2,3] -> [3,1,2] -> 렌더도 3 · 1 · 2"""

        path, scenes = _project()

        scene_order.save(path, order=[3, 1, 2])

        ordered = scene_order.for_render(path, scenes)

        self.assertEqual([s["scene"] for s in ordered], [3, 1, 2])

    def test_the_timeline_the_render_builds_follows_it(self):
        path, scenes = _project()

        scene_order.save(path, order=[3, 1, 2])

        timeline = scene_timeline.build_timeline(
            path, scene_order.for_render(path, scenes))

        self.assertEqual([slot["scene"] for slot in timeline], [3, 1, 2])
        self.assertEqual([slot["duration"] for slot in timeline],
                         [3.0, 1.0, 2.0])

    def test_the_boundaries_have_no_gap(self):
        """앞의 끝이 다음의 시작이어야 소리와 그림이 붙는다."""

        path, scenes = _project()

        scene_order.save(path, order=[3, 1, 2])

        timeline = scene_timeline.build_timeline(
            path, scene_order.for_render(path, scenes))

        self.assertEqual([slot["start"] for slot in timeline],
                         [0.0, 3.0, 4.0])

        for before, after in zip(timeline, timeline[1:]):
            with self.subTest(scene=before["scene"]):
                self.assertEqual(before["end"], after["start"])

    def test_the_video_builder_asks_for_the_same_order(self):
        from app.services import video_builder

        with open(video_builder.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("scene_order.for_render", source)


class TestSceneNumberIsNotReused(unittest.TestCase):

    def test_scene_number_is_not_reused(self):
        """번호가 곧 파일 이름이다 - 되쓰면 남의 그림을 가리킨다."""

        path, scenes = _project()

        scene_order.save(path, deleted=[2])

        ordered = scene_order.for_render(path, scenes)

        self.assertEqual([s["scene"] for s in ordered], [1, 3])

        # 남은 것들의 번호가 다시 매겨지지 않는다.
        self.assertEqual(
            [s["narration"] for s in ordered],
            [NARRATIONS[1], NARRATIONS[3]])

    def test_the_files_keep_their_names(self):
        path, _ = _project()

        scene_order.save(path, order=[3, 1, 2], deleted=[2])

        for n in (1, 2, 3):
            with self.subTest(scene=n):
                self.assertTrue(os.path.exists(
                    os.path.join(path, "images", f"scene{n}.png")))
                self.assertTrue(os.path.exists(os.path.join(
                    path, "audio", "scenes", f"scene{n}.wav")))

    def test_the_screen_never_reuses_a_number(self):
        page = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "static", "studio.html")

        with open(page, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("function nextSceneNumber(", source)
        self.assertIn("Math.max", source)


class TestDeletedSceneNotRendered(unittest.TestCase):

    def test_deleted_scene_not_rendered(self):
        path, scenes = _project()

        scene_order.save(path, deleted=[2])

        ordered = scene_order.for_render(path, scenes)

        self.assertNotIn(2, [s["scene"] for s in ordered])

    def test_deleting_removes_no_file(self):
        """되돌릴 수 있어야 한다."""

        path, _ = _project()

        scene_order.save(path, deleted=[2])

        self.assertTrue(os.path.exists(
            os.path.join(path, "audio", "scenes", "scene2.wav")))
        self.assertTrue(os.path.exists(
            os.path.join(path, "images", "scene2.png")))

    def test_the_script_still_holds_the_words(self):
        path, _ = _project()

        scene_order.save(path, deleted=[2])

        with open(os.path.join(path, "script.json"), encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual([s["scene"] for s in saved["scenes"]], [1, 2, 3])

    def test_undeleting_brings_it_back(self):
        path, scenes = _project()

        scene_order.save(path, deleted=[2])
        scene_order.save(path, deleted=[])

        self.assertEqual(
            [s["scene"] for s in scene_order.for_render(path, scenes)],
            [1, 2, 3])

    def test_the_leftover_audio_no_longer_stops_the_subtitles(self):
        """예전에는 wav 개수가 안 맞아 렌더가 멈췄다."""

        from app.services import subtitle_service

        with open(subtitle_service.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn("len(scene_audios) != len(scenes)", source)
        self.assertIn("scene_order.for_render", source)


class TestAudioImageSubtitleOrderFollowTimeline(unittest.TestCase):

    def test_audio_image_subtitle_order_follow_timeline(self):
        """넷이 한 차례를 봐야 어긋나지 않는다."""

        path, scenes = _project()
        scene_order.save(path, order=[3, 1, 2])

        ordered = scene_order.for_render(path, scenes)
        expected = [3, 1, 2]

        # 이미지 - video_builder가 목록 순서로 모은다
        self.assertEqual([s["scene"] for s in ordered], expected)

        # 음성 - step03이 받은 목록 순서로 이어 붙인다
        self.assertEqual(
            [s.get("scene", i + 1) for i, s in enumerate(ordered)], expected)

        # 자막·길이 - build_timeline이 받은 차례를 그대로 쓴다
        timeline = scene_timeline.build_timeline(path, ordered)
        self.assertEqual([slot["scene"] for slot in timeline], expected)

    def test_the_pipeline_hands_the_ordered_list_to_the_voice_step(self):
        import app.pipeline.pipeline as pipeline

        with open(pipeline.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("render_scenes = scene_order.for_render(", source)
        self.assertIn("step03_voice_resolve.run(\n        render_scenes,",
                      source)

    def test_the_script_file_is_saved_before_the_order_is_applied(self):
        """차례를 대본에 섞지 않는다."""

        import app.pipeline.pipeline as pipeline

        with open(pipeline.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertLess(source.index("_save_script(project_path, data)"),
                        source.index("render_scenes = scene_order.for_render("))


class TestOldPipelineKeepsDefaultOrder(unittest.TestCase):

    def test_old_pipeline_keeps_default_order(self):
        """timeline.json이 없으면 아무것도 달라지지 않는다."""

        path, scenes = _project()

        self.assertFalse(os.path.exists(
            os.path.join(path, scene_order.TIMELINE_FILENAME)))

        ordered = scene_order.for_render(path, scenes)

        self.assertEqual(ordered, scenes)

    def test_an_empty_plan_changes_nothing(self):
        path, scenes = _project()

        scene_order.save(path, order=[], deleted=[])

        self.assertEqual(
            [s["scene"] for s in scene_order.for_render(path, scenes)],
            [1, 2, 3])

    def test_an_unreadable_plan_changes_nothing(self):
        path, scenes = _project()

        with open(os.path.join(path, scene_order.TIMELINE_FILENAME), "w",
                  encoding="utf-8") as f:
            f.write("{망가진")

        self.assertEqual(
            [s["scene"] for s in scene_order.for_render(path, scenes)],
            [1, 2, 3])

    def test_a_scene_missing_from_the_order_is_kept(self):
        """대본에 새로 생긴 scene을 잃지 않는다."""

        path, scenes = _project(numbers=(1, 2, 3, 4))

        scene_order.save(path, order=[3, 1])

        self.assertEqual(
            [s["scene"] for s in scene_order.for_render(path, scenes)],
            [3, 1, 2, 4])

    def test_the_build_timeline_no_longer_decides_the_order(self):
        """차례를 정하는 것은 부르는 쪽의 일이다."""

        with open(scene_timeline.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn('sorted(scenes, key=lambda scene: scene["scene"])',
                         source)


class TestTheRenderGateSpeaksPlainly(unittest.TestCase):

    def test_it_says_which_scene_and_what_is_missing(self):
        path, scenes = _project(with_media=False)

        problems = scene_order.render_problems(path, scenes)

        self.assertIn("Scene 1 이미지가 없습니다", problems)
        self.assertIn("Scene 1 음성이 없습니다", problems)

    def test_a_ready_project_has_nothing_to_say(self):
        path, scenes = _project()

        self.assertEqual(scene_order.render_problems(path, scenes), [])

    def test_it_does_not_complain_about_deleted_scenes(self):
        path, scenes = _project(numbers=(1, 2, 3))

        os.remove(os.path.join(path, "images", "scene2.png"))
        scene_order.save(path, deleted=[2])

        self.assertEqual(scene_order.render_problems(path, scenes), [])

    def test_an_empty_narration_is_caught(self):
        path, scenes = _project()
        scenes[1]["narration"] = "  "

        self.assertIn("Scene 2 대본이 없습니다",
                      scene_order.render_problems(path, scenes))

    def test_the_endpoint_refuses_before_starting(self):
        from fastapi.testclient import TestClient

        import app.routers.studio as studio_router
        from app.main import app

        path, _ = _project(with_media=False)

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            with patch("app.services.studio_review.render") as render:
                response = TestClient(app).post(
                    "/studio/api/review/p1/render")

        self.assertEqual(response.status_code, 400)
        self.assertIn("이미지가 없습니다", response.json()["detail"])
        render.assert_not_called()

    def test_a_ready_project_still_starts(self):
        from fastapi.testclient import TestClient

        import app.routers.studio as studio_router
        from app.main import app

        path, _ = _project()

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            with patch("app.services.studio_review.render",
                       return_value="job-1") as render:
                response = TestClient(app).post(
                    "/studio/api/review/p1/render")

        self.assertEqual(response.status_code, 200)
        render.assert_called_once()


class TestTheSaveKeepsTheTwoFilesApart(unittest.TestCase):

    def _put(self, path, body):
        from fastapi.testclient import TestClient

        import app.routers.studio as studio_router
        from app.main import app

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            return TestClient(app).put(
                "/studio/api/review/p1/script", json=body)

    def test_the_order_lands_in_its_own_file(self):
        path, scenes = _project()

        response = self._put(path, {
            "data": {"title": "t", "scenes": scenes},
            "timeline": {"order": [3, 1, 2], "deleted": [2]},
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(scene_order.load(path),
                         {"order": [3, 1, 2], "deleted": [2]})

    def test_the_script_file_holds_no_order(self):
        path, scenes = _project()

        self._put(path, {
            "data": {"title": "t", "scenes": scenes},
            "timeline": {"order": [3, 1, 2], "deleted": []},
        })

        with open(os.path.join(path, "script.json"), encoding="utf-8") as f:
            saved = json.load(f)

        self.assertNotIn("order", saved)
        for scene in saved["scenes"]:
            with self.subTest(scene=scene["scene"]):
                self.assertNotIn("order", scene)
                self.assertNotIn("position", scene)

    def test_saving_without_a_timeline_leaves_it_alone(self):
        path, scenes = _project()

        scene_order.save(path, order=[3, 1, 2])
        self._put(path, {"data": {"title": "t", "scenes": scenes}})

        self.assertEqual(scene_order.load(path)["order"], [3, 1, 2])

    def test_a_refused_script_writes_no_order(self):
        """거절당한 대본의 차례를 남기면 다음에 어긋난 것을 읽는다."""

        path, _ = _project()

        response = self._put(path, {
            "data": {"title": "t", "scenes": [{"scene": 1}]},
            "timeline": {"order": [3, 1, 2], "deleted": []},
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(scene_order.load(path)["order"], [])

    def test_the_screen_is_told_the_order(self):
        from fastapi.testclient import TestClient

        import app.routers.studio as studio_router
        from app.main import app

        path, _ = _project()
        scene_order.save(path, order=[3, 1, 2], deleted=[2])

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            state = TestClient(app).get("/studio/api/review/p1").json()

        self.assertEqual(state["timeline"],
                         {"order": [3, 1, 2], "deleted": [2]})


if __name__ == "__main__":
    unittest.main()
