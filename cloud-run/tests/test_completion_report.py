"""
Sprint166 - 무엇으로 만들어졌는지 말한다 (Epic 57, Phase 17).

만들고 나면 사람은 묻는다. "이 영상, 뭘로 만든 거지?" 대본은 어디서
왔고, 그림은 어느 파일이며, 돈은 나갔는가.

전부 이미 어딘가에 적혀 있다
----------------------------
    project.json            production_source · *_provider
    output_check            영상 길이 · 검사 결과
    free_workspace          Scene마다 무엇이 쓰였는가
    asset_override          사람이 정한 것

새로 적지 않는다. 적어 두면 그것이 또 하나의 진실이 되고, 실제
파일과 갈리는 날이 온다.

지어내지 않는다
---------------
품질 점수도, 예상 비용도, 추천도 없다. 우리가 아는 것은 "어느
Provider를 골랐는가"와 "그것이 API를 부르는가"뿐이다.

"무료"·"저렴"·"가성비"라고 쓰지 않는다. 그것은 값어치에 대한 판단이고,
우리는 값을 모른다. 아는 것은 "API 호출 없음"이라는 사실뿐이다.

무엇을 지키는가
---------------
    1. 실제로 쓰인 것을 읽는다   test_completion_reads_actual_sources
    2. 검사 결과를 그대로 옮긴다 test_completion_shows_output_status
    3. 비용을 지어내지 않는다    test_completion_never_invents_cost
    4. 무료 모드는 호출이 없다   test_completion_free_mode_has_no_api_call
    5. 다시 검사하면 따라온다    test_completion_updates_after_recheck
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from app.main import app
from app.routers import studio as studio_router
from app.services import (
    asset_override, audio_policy, completion_report, local_library,
    output_check, provider_selection,
)

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _script_source():
    with open(PAGE, encoding="utf-8") as f:
        page = f.read()

    return page[page.index("<script>"):]


def _png(path):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (64, 64), (200, 30, 30)).save(path)


def _wav(path, seconds=1.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", path],
        capture_output=True, check=True,
    )


def _mp4(path, seconds=3.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c=cyan:s=160x120:d={seconds}",
         "-f", "lavfi", "-i", f"sine=f=440:d={seconds}",
         "-pix_fmt", "yuv420p", "-shortest", path],
        capture_output=True, check=True,
    )


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.client = TestClient(app)
        self._real = studio_router._project_path
        studio_router._project_path = lambda project_id: self.project
        self.addCleanup(self._restore)

        self.scenes = [
            {"scene": n, "narration": f"{n}번 문장입니다.",
             "image_prompt": f"동작 {n}"}
            for n in (1, 2)
        ]

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "무릎 스트레칭", "scenes": self.scenes}, f,
                      ensure_ascii=False)

        self.meta({"topic": "무릎 통증", "channel": "wellbeing"})

    def _restore(self):
        studio_router._project_path = self._real

    def meta(self, data):
        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def library(self, *names):
        for name in names:
            _png(os.path.join(self.root, "images", name))

        for number in (1, 2):
            _wav(os.path.join(self.root, "voices", f"scene{number}.wav"))

        local_library.save(self.project, local_library.scan(self.root))

    def produced(self, seconds=3.0):
        for number in (1, 2):
            _png(os.path.join(self.project, "images", f"scene{number}.png"))
            _wav(os.path.join(self.project, "audio", "scenes",
                              audio_policy.scene_audio_filename(number)))

        path = os.path.join(self.project, "subtitle", "subtitle.srt")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\n문장\n")

        _mp4(os.path.join(self.project, "video", "final_short.mp4"), seconds)

    def free_mode(self):
        """무료 모드로 고른 프로젝트."""

        self.meta({
            "topic": "무릎 통증", "channel": "wellbeing",
            "production_source": "import",
            "image_provider": "local_stock",
            "voice_provider": "local_voice",
        })

    def report(self):
        return self.client.get("/studio/api/review/p1/completion").json()


class ActualSourcesTest(Base):
    """1. 실제로 쓰인 것을 읽는다."""

    def test_completion_reads_actual_sources(self):
        self.free_mode()
        self.library("동작 1.png", "동작 2.png")
        self.produced()

        body = self.report()

        # 대본은 붙여넣기로 왔다.
        self.assertEqual(body["script"]["source"], "import")

        # 그림과 소리는 고른 Provider가 말한다.
        self.assertEqual(body["image"]["provider"], "local_stock")
        self.assertEqual(body["voice"]["provider"], "local_voice")

        # Scene마다 무엇이 쓰였는지도 온다.
        files = {row["scene"]: row for row in body["scene_rows"]}

        self.assertEqual(files[1]["image"], "scene1.png")
        self.assertEqual(files[2]["image"], "scene2.png")

    def test_a_hand_picked_file_is_named(self):
        """
        사람이 고른 파일은 그 이름이 나온다.

        "직접 고름"이라고만 하면 무엇을 골랐는지 알 수 없다.
        """

        self.free_mode()
        self.library("동작 1.png", "자연광.png")

        asset_override.save(
            self.project, 1, os.path.join(self.root, "images", "자연광.png"))

        body = self.report()

        row = {r["scene"]: r for r in body["scene_rows"]}[1]

        self.assertEqual(row["image"], "자연광.png")
        self.assertEqual(row["image_source"], "override")

    def test_the_default_engine_is_named_as_such(self):
        """고르지 않았으면 현재 엔진이다. 지어내지 않는다."""

        self.produced()

        body = self.report()

        self.assertEqual(body["image"]["provider"], provider_selection.CURRENT)
        self.assertEqual(body["voice"]["provider"], provider_selection.CURRENT)
        self.assertEqual(body["script"]["source"], "auto")

    def test_nothing_is_written(self):
        """읽기만 한다. 적어 두면 실제 파일과 갈리는 날이 온다."""

        self.free_mode()
        self.library("동작 1.png", "동작 2.png")
        self.produced()

        before = sorted(os.listdir(self.project))

        for _ in range(3):
            self.report()

        self.assertEqual(sorted(os.listdir(self.project)), before)


class OutputStatusTest(Base):
    """2. 검사 결과를 그대로 옮긴다."""

    def test_completion_shows_output_status(self):
        self.free_mode()
        self.library("동작 1.png", "동작 2.png")
        self.produced(seconds=4.0)

        body = self.report()

        self.assertEqual(body["output"]["state"], output_check.READY)
        self.assertAlmostEqual(body["video"]["seconds"], 4.0, delta=0.3)
        self.assertEqual(body["output"]["issues"], [])

    def test_it_does_not_judge_the_result(self):
        """
        검사 결과를 옮길 뿐 값어치를 매기지 않는다.

        "잘 만들어졌습니다" 같은 말은 우리가 알 수 없는 것이다.
        """

        self.free_mode()
        self.library("동작 1.png", "동작 2.png")
        self.produced()

        found = self.report()

        for word in ("좋", "훌륭", "우수", "품질 점수", "점"):
            with self.subTest(word=word):
                self.assertNotIn(word, json.dumps(found, ensure_ascii=False))

    def test_a_problem_comes_through(self):
        self.free_mode()
        self.library("동작 1.png", "동작 2.png")
        self.produced()

        os.remove(os.path.join(self.project, "images", "scene2.png"))

        body = self.report()

        self.assertEqual(body["output"]["state"], output_check.REVIEW)
        self.assertEqual(len(body["output"]["issues"]), 1)

    def test_no_video_is_failed(self):
        self.free_mode()

        body = self.report()

        self.assertEqual(body["output"]["state"], output_check.FAILED)
        self.assertIsNone(body["video"]["seconds"])


class NeverInventsCostTest(Base):
    """3. 비용을 지어내지 않는다."""

    def test_completion_never_invents_cost(self):
        """
        값어치에 대한 판단을 쓰지 않는다.

        "무료"·"저렴"·"가성비"는 값을 안다는 뜻인데, 우리는 모른다.
        아는 것은 "API를 부르는가"뿐이다.
        """

        self.free_mode()
        self.library("동작 1.png", "동작 2.png")
        self.produced()

        text = json.dumps(self.report(), ensure_ascii=False)

        for word in ("무료", "저렴", "가성비", "추천", "원", "달러", "$"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_an_api_provider_shows_its_name_not_a_price(self):
        self.meta({
            "topic": "t", "channel": "wellbeing",
            "image_provider": "flux", "voice_provider": "elevenlabs",
        })
        self.produced()

        body = self.report()

        self.assertEqual(body["image"]["provider"], "flux")
        self.assertEqual(body["voice"]["provider"], "elevenlabs")

        # 값 대신 무엇을 요구하는지를 말한다.
        self.assertFalse(body["cost"]["no_api_call"])

        text = json.dumps(body, ensure_ascii=False)

        for word in ("무료", "저렴", "원", "$"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_the_two_layers_agree_on_what_is_free(self):
        """
        서비스 층이 "안 부른다"고 하는 것과 등록소가 "돈이 안 든다"고
        하는 것이 같아야 한다.

        서비스는 등록소를 부를 수 없다(경계). 그래서 같은 사실이 두
        곳에 있고, 갈리지 않는 것은 여기서 잠근다 - 테스트는 두 층을
        다 볼 수 있다.
        """

        from app.production import stages
        from app.production.providers import bootstrap
        from app.production.registry import StageProviderRegistry

        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        for stage in (stages.IMAGE, stages.VOICE):
            free_here = set(provider_selection.FREE_PROVIDERS.get(stage, ()))

            free_there = {
                p.name for p in registry.for_stage(stage)
                if p.capabilities.estimated_cost == 0
                and not p.capabilities.required_settings
            }

            with self.subTest(stage=stage):
                self.assertEqual(free_here, free_there)

    def test_an_unknown_name_is_treated_as_calling(self):
        """
        모르는 이름은 부르는 쪽으로 둔다.

        "안 부른다"고 했다가 조용히 돈이 나가는 편보다, 부른다고
        했다가 안 나가는 편이 낫다.
        """

        self.assertTrue(provider_selection.calls_api("image", "그런거없음"))
        self.assertTrue(provider_selection.calls_api("voice", None))

    def test_the_screen_says_no_such_word_either(self):
        source = _script_source()

        block = source[source.index("function completionPanel"):]
        block = block[:block.index("\n}")]

        for word in ("무료", "저렴", "가성비", "추천"):
            with self.subTest(word=word):
                self.assertNotIn(word, block)

        self.assertIn("API 호출 없음", source)


class FreeModeNoApiCallTest(Base):
    """4. 무료 모드는 호출이 없다."""

    def test_completion_free_mode_has_no_api_call(self):
        """
        "API 호출 없음"은 고른 Provider에서 나온다.

        무료 모드라고 우리가 선언하는 것이 아니라, 고른 것들이 전부
        모델을 부르지 않는다는 사실을 옮기는 것이다.
        """

        self.free_mode()
        self.library("동작 1.png", "동작 2.png")
        self.produced()

        body = self.report()

        self.assertTrue(body["cost"]["no_api_call"])

        # 왜 그런지도 말한다 - 단계마다.
        self.assertTrue(body["cost"]["stages"]["script"]["calls_api"] is False)
        self.assertTrue(body["cost"]["stages"]["image"]["calls_api"] is False)
        self.assertTrue(body["cost"]["stages"]["voice"]["calls_api"] is False)

    def test_one_api_stage_is_enough_to_flip_it(self):
        """하나라도 부르면 "호출 없음"이 아니다."""

        self.meta({
            "topic": "t", "channel": "wellbeing",
            "production_source": "import",
            "image_provider": "local_stock",
            "voice_provider": "current",
        })
        self.produced()

        body = self.report()

        self.assertFalse(body["cost"]["no_api_call"])
        self.assertTrue(body["cost"]["stages"]["voice"]["calls_api"])
        self.assertFalse(body["cost"]["stages"]["image"]["calls_api"])

    def test_the_report_itself_calls_nothing(self):
        import requests

        from app.providers import local_stock_provider, local_voice_provider
        from app.services import asset_integration_service

        self.free_mode()
        self.library("동작 1.png", "동작 2.png")
        self.produced()

        with patch.object(
            local_stock_provider, "generate_image") as make_image, \
                patch.object(
                    local_voice_provider, "generate_voice") as make_voice, \
                patch.object(
                    asset_integration_service, "get_candidates") as stock, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            body = self.report()

            for name, mock in (("local_stock", make_image),
                               ("local_voice", make_voice),
                               ("스톡 검색", stock),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()

        self.assertTrue(body["cost"]["no_api_call"])


class UpdatesAfterRecheckTest(Base):
    """5. 다시 검사하면 따라온다."""

    def test_completion_updates_after_recheck(self):
        """
        보고서를 적어 두지 않으므로, 부를 때마다 지금 상태가 나온다.
        """

        self.free_mode()
        self.library("동작 1.png", "동작 2.png")
        self.produced()

        self.assertEqual(self.report()["output"]["state"], output_check.READY)

        os.remove(os.path.join(self.project, "images", "scene2.png"))

        self.assertEqual(self.report()["output"]["state"], output_check.REVIEW)

        _png(os.path.join(self.project, "images", "scene2.png"))

        self.assertEqual(self.report()["output"]["state"], output_check.READY)

    def test_a_changed_provider_shows_up(self):
        self.free_mode()
        self.produced()

        self.assertEqual(self.report()["image"]["provider"], "local_stock")

        provider_selection.save(self.project, {"image": "flux"})

        self.assertEqual(self.report()["image"]["provider"], "flux")

    def test_the_length_follows_the_file(self):
        self.free_mode()
        self.produced(seconds=3.0)

        first = self.report()["video"]["seconds"]

        self.produced(seconds=6.0)

        second = self.report()["video"]["seconds"]

        self.assertAlmostEqual(first, 3.0, delta=0.3)
        self.assertAlmostEqual(second, 6.0, delta=0.3)

    def test_the_pipeline_knows_nothing_about_this(self):
        import app.pipeline.pipeline as pipeline

        from app.services import scene_order, video_builder

        for module in (pipeline, scene_order, video_builder):
            with open(module.__file__, encoding="utf-8") as f:
                source = f.read()

            with self.subTest(module=module.__name__):
                self.assertNotIn("completion_report", source)


if __name__ == "__main__":
    unittest.main()
