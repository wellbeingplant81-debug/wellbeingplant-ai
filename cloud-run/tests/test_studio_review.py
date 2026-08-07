"""
Sprint121 - 승인 기반 제작 (Epic 55, Phase 1).

한 번에 만들지 않는다. AI가 한 단계를 만들고, 사람이 보고 고치고
승인하면 다음 단계로 간다.

이것이 가능한 이유는 Resolver가 이미 그 모양으로 만들어져 있기
때문이다(Sprint106·111·113). 산출물이 디스크에 있으면 그 단계는
건너뛴다 - 그래서 "승인"이란 곧 산출물을 남기는 일이고, 마지막 Render는
run_pipeline을 그대로 부르면 01·02·03이 저절로 건너뛰어진다.

    STEP1 승인  script.json 확정      step01 Resolver가 IMPORT로 읽는다
    STEP2 승인  images/ 확정          step02 Resolver가 IMPORT로 읽는다
    STEP3 승인  audio/scenes/ 확정    step03 Resolver가 조립만 한다
    STEP4       run_pipeline          04~07만 실제로 돈다

그래서 새 상태 파일을 만들지 않는다. 어디까지 왔는지는 디스크가
말한다(Sprint84의 원칙과 같다).

다시 생성은 Scene 단위만 허용한다. 전부 다시 만드는 버튼은 두지
않는다 - 사람이 승인한 것을 우리가 지우는 일이 없어야 한다.
"""

import ast
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import audio_policy, studio_review
from app.services.studio_review import ReviewError

SCRIPT = {
    "title": "제목",
    "hook": "훅",
    "scenes": [
        {"scene": n, "narration": f"{n}번 문장입니다", "image_prompt": "a man"}
        for n in range(1, 4)
    ],
}


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name
        for relative in ("images", os.path.join("audio", "scenes"), "video"):
            os.makedirs(os.path.join(self.project, relative), exist_ok=True)

    def _write_script(self, data=None):
        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump(data or SCRIPT, f, ensure_ascii=False)

    def _place_images(self, numbers):
        for n in numbers:
            with open(os.path.join(self.project, "images", f"scene{n}.png"),
                      "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")

    def _place_voices(self, numbers):
        for n in numbers:
            path = os.path.join(self.project, "audio", "scenes",
                                audio_policy.scene_audio_filename(n))
            with open(path, "wb") as f:
                f.write(b"RIFF____WAVEfmt ")

    def _place_video(self):
        with open(os.path.join(self.project, "video", "final_short.mp4"),
                  "wb") as f:
            f.write(b"\x00\x00\x00\x18ftypmp42")


class TestTheStepComesFromTheDisk(_Case):
    """새 상태 파일을 만들지 않는다 - 어디까지 왔는지는 산출물이 말한다."""

    def test_an_empty_project_is_on_the_script_step(self):
        self.assertEqual(studio_review.state(self.project)["step"], "script")

    def test_a_script_moves_it_to_the_image_step(self):
        self._write_script()

        self.assertEqual(studio_review.state(self.project)["step"], "image")

    def test_all_images_move_it_to_the_voice_step(self):
        self._write_script()
        self._place_images([1, 2, 3])

        self.assertEqual(studio_review.state(self.project)["step"], "voice")

    def test_a_partial_set_of_images_does_not_advance(self):
        self._write_script()
        self._place_images([1, 2])

        self.assertEqual(studio_review.state(self.project)["step"], "image")

    def test_all_voices_move_it_to_the_video_step(self):
        self._write_script()
        self._place_images([1, 2, 3])
        self._place_voices([1, 2, 3])

        self.assertEqual(studio_review.state(self.project)["step"], "video")

    def test_a_finished_video_is_done(self):
        self._write_script()
        self._place_images([1, 2, 3])
        self._place_voices([1, 2, 3])
        self._place_video()

        state = studio_review.state(self.project)

        self.assertEqual(state["step"], "done")
        self.assertTrue(state["done"]["video"])

    def test_it_writes_nothing(self):
        """순수 읽기다."""

        before = sorted(os.listdir(self.project))

        studio_review.state(self.project)

        self.assertEqual(sorted(os.listdir(self.project)), before)

    def test_it_numbers_the_steps_for_the_screen(self):
        self._write_script()

        state = studio_review.state(self.project)

        self.assertEqual(state["index"], 2)
        self.assertEqual(state["total"], 4)
        self.assertEqual(len(studio_review.STEPS), 4)

    def test_it_carries_the_scenes(self):
        self._write_script()

        scenes = studio_review.state(self.project)["scenes"]

        self.assertEqual([s["scene"] for s in scenes], [1, 2, 3])
        self.assertEqual(scenes[0]["narration"], "1번 문장입니다")

    def test_it_says_which_scene_has_what(self):
        self._write_script()
        self._place_images([1])
        self._place_voices([2])

        scenes = studio_review.state(self.project)["scenes"]

        self.assertEqual([s["has_image"] for s in scenes], [True, False, False])
        self.assertEqual([s["has_voice"] for s in scenes], [False, True, False])


class TestTheScriptStep(_Case):

    def test_it_calls_the_existing_writer(self):
        from app.steps import step01_script

        with patch.object(step01_script, "run", return_value=SCRIPT) as run:
            studio_review.generate_script("주제", self.project)

        run.assert_called_once_with("주제", self.project)

    def test_saving_an_edit_keeps_what_the_user_wrote(self):
        edited = json.loads(json.dumps(SCRIPT))
        edited["scenes"][0]["narration"] = "사람이 고친 문장"

        studio_review.save_script(self.project, edited)

        with open(os.path.join(self.project, "script.json"),
                  encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["scenes"][0]["narration"], "사람이 고친 문장")

    def test_saving_calls_no_engine(self):
        """사람이 고친 것을 우리가 다시 만들지 않는다."""

        from app.steps import step01_script

        with patch.object(step01_script, "run") as run:
            studio_review.save_script(self.project, SCRIPT)

        run.assert_not_called()

    def test_a_broken_edit_is_refused_by_the_existing_validator(self):
        broken = {"title": "제목", "scenes": [{"scene": 1}]}

        with self.assertRaises(ReviewError):
            studio_review.save_script(self.project, broken)

    def test_a_refused_edit_does_not_overwrite_what_is_there(self):
        self._write_script()

        with self.assertRaises(ReviewError):
            studio_review.save_script(self.project, {"title": "", "scenes": []})

        with open(os.path.join(self.project, "script.json"),
                  encoding="utf-8") as f:
            self.assertEqual(json.load(f)["title"], "제목")


class TestTheImageStep(_Case):

    def test_it_calls_the_existing_engine_with_the_saved_scenes(self):
        from app.steps import step02_assets

        self._write_script()

        with patch.object(step02_assets, "collect_assets",
                          return_value=SCRIPT["scenes"]) as collect:
            studio_review.generate_images(self.project, "wellbeing")

        collect.assert_called_once()
        given = collect.call_args[0]
        self.assertEqual([s["scene"] for s in given[0]], [1, 2, 3])
        self.assertEqual(given[1], self.project)
        self.assertEqual(given[2], "wellbeing")

    def test_regenerating_one_scene_touches_only_that_scene(self):
        """전부 다시 만드는 일은 없다."""

        from app.steps import step02_assets

        self._write_script()

        with patch.object(step02_assets, "collect_assets",
                          return_value=[SCRIPT["scenes"][1]]) as collect:
            studio_review.regenerate_image(self.project, "wellbeing", 2)

        given = collect.call_args[0][0]
        self.assertEqual([s["scene"] for s in given], [2])

    def test_an_unknown_scene_is_refused(self):
        self._write_script()

        with self.assertRaises(ReviewError):
            studio_review.regenerate_image(self.project, "wellbeing", 9)

    def test_it_needs_a_script_first(self):
        with self.assertRaises(ReviewError):
            studio_review.generate_images(self.project, "wellbeing")


class TestTheVoiceStep(_Case):

    def test_it_calls_the_existing_scene_tts(self):
        from app.services import scene_tts_service

        self._write_script()

        with patch.object(scene_tts_service, "create_scene_tts",
                          return_value=[]) as tts:
            studio_review.generate_voices(self.project)

        tts.assert_called_once()
        self.assertEqual([s["scene"] for s in tts.call_args[0][0]], [1, 2, 3])

    def test_regenerating_one_scene_writes_only_that_file(self):
        """create_scene_tts는 목록의 순서로 파일명을 정한다 - scene 하나만
        넘기면 scene1.wav를 덮어쓴다. 그래서 여기서는 쓰지 않는다."""

        from app.services import studio_review as module

        self._write_script()

        with patch.object(module, "generate_voice") as voice:
            studio_review.regenerate_voice(self.project, 3)

        voice.assert_called_once()
        text, target = voice.call_args[0]
        self.assertEqual(text, "3번 문장입니다")
        self.assertTrue(target.endswith(
            audio_policy.scene_audio_filename(3)))

    def test_it_does_not_use_create_scene_tts_for_one_scene(self):
        from app.services import scene_tts_service

        self._write_script()

        with patch.object(scene_tts_service, "create_scene_tts") as tts:
            with patch.object(studio_review, "generate_voice"):
                studio_review.regenerate_voice(self.project, 2)

        tts.assert_not_called()

    def test_an_unknown_scene_is_refused(self):
        self._write_script()

        with self.assertRaises(ReviewError):
            studio_review.regenerate_voice(self.project, 9)


class TestTheRenderStepReusesWhatExists(_Case):

    def test_it_starts_the_same_job_as_the_generate_button(self):
        from app.services import studio_jobs

        self._write_script()

        with patch.object(studio_jobs, "start", return_value="job1") as start:
            job = studio_review.render("주제", "20260101_000001", "wellbeing")

        start.assert_called_once_with("주제", "wellbeing", "20260101_000001")
        self.assertEqual(job, "job1")

    def test_the_resolvers_will_skip_the_approved_steps(self):
        """승인이란 산출물을 남기는 일이고, Resolver가 그것을 본다."""

        from app.steps import (
            step01_script_resolve, step02_asset_resolve, step03_voice_resolve,
        )

        self._write_script()
        self._place_images([1, 2, 3])
        self._place_voices([1, 2, 3])

        self.assertEqual(
            step01_script_resolve.detect_source(self.project), "import")
        self.assertEqual(
            step02_asset_resolve.detect_source(self.project), "import")
        self.assertEqual(
            step03_voice_resolve.detect_source(self.project), "import")


class TestNothingWasReimplemented(unittest.TestCase):
    """엔진도 Resolver도 고치지 않는다 - 부르기만 한다."""

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
                names.update(a.name for a in node.names)
        return names

    def test_the_engine_steps_are_untouched(self):
        from app.steps import (
            step01_script, step02_assets, step03_tts, step04_subtitle,
            step05_video, step06_thumbnail, step07_quality,
        )

        for module in (step01_script, step02_assets, step03_tts,
                       step04_subtitle, step05_video, step06_thumbnail,
                       step07_quality):
            with self.subTest(module=module.__name__):
                for name in self._imports(module):
                    self.assertNotIn("review", name)

    def test_the_resolvers_are_untouched(self):
        from app.steps import (
            step01_script_resolve, step02_asset_resolve, step03_voice_resolve,
        )

        for module in (step01_script_resolve, step02_asset_resolve,
                       step03_voice_resolve):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("studio_review", source)

    def test_the_pipeline_is_untouched(self):
        """import만 본다. pipeline.py의 Sprint67 주석에 AI Director의
        "accept/review/regenerate 권고"라는 말이 있어서, 산문을 뒤지면
        설명을 지워야 통과하는 테스트가 된다."""

        import app.pipeline.pipeline as pipeline

        for name in self._imports(pipeline):
            with self.subTest(imported=name):
                self.assertNotIn("review", name)

    def test_it_writes_no_new_validator(self):
        """대본 검증은 Sprint106 Resolver의 것을 그대로 쓴다."""

        self.assertIn(
            "step01_script_resolve",
            self._imports(studio_review),
        )

    def test_it_has_no_regenerate_everything(self):
        source = open(studio_review.__file__, encoding="utf-8").read()
        tree = ast.parse(source)

        functions = {n.name for n in tree.body
                     if isinstance(n, ast.FunctionDef)}

        for forbidden in ("regenerate_all", "rebuild", "restart"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, functions)


if __name__ == "__main__":
    unittest.main()
