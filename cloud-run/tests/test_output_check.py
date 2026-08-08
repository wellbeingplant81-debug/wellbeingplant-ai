"""
Sprint163 - 만든 뒤에 결과를 본다 (Epic 57, Phase 14).

Sprint162가 "누르기 전"을 봤다. 이번은 "누른 뒤"다.

앞의 검사와 무엇이 다른가
-------------------------
    final_check   지금 누르면 되는가        자료와 산출물이 있는가
    output_check  나온 것이 쓸 만한가       영상·길이·자막이 있는가

앞의 것은 만들기 전의 재료를 보고, 이것은 만들어진 결과를 본다.
결과가 없으면 FAILED다 - 아직 안 만든 것과 만들었는데 실패한 것을
가르지 않으면, 사람은 "왜 아무 말도 없지"를 묻게 된다.

재지 않는다. 이미 재 둔 것을 읽는다
-----------------------------------
qa_report_service.get_real_durations가 ffprobe로 실측을 모은다. 여기서
다시 재면 같은 파일이 자리마다 다른 길이를 갖는다.

무엇을 지키는가
---------------
    1. 다 되면 문제 없음        test_output_check_ready
    2. 빠진 것을 짚는다          test_output_missing_scene_detected
    3. 길이를 그대로 말한다      test_output_duration_reported
    4. 밖으로 안 나간다          test_output_check_no_external_api
    5. 렌더는 건드리지 않는다    test_render_pipeline_unchanged
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
from app.services import audio_policy, output_check, qa_report_service

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
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.client = TestClient(app)
        self._real = studio_router._project_path
        studio_router._project_path = lambda project_id: self.project
        self.addCleanup(self._restore)

        self.scenes = [
            {"scene": n, "narration": f"{n}번 문장입니다.",
             "image_prompt": f"프롬프트 {n}"}
            for n in (1, 2)
        ]

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": self.scenes}, f,
                      ensure_ascii=False)

    def _restore(self):
        studio_router._project_path = self._real

    def images(self, *numbers):
        for number in numbers:
            _png(os.path.join(self.project, "images", f"scene{number}.png"))

    def voices(self, *numbers, seconds=1.0):
        for number in numbers:
            _wav(os.path.join(self.project, "audio", "scenes",
                              audio_policy.scene_audio_filename(number)),
                 seconds)

    def video(self, seconds=3.0):
        _mp4(os.path.join(self.project, "video", "final_short.mp4"), seconds)

    def subtitle(self, text="1\n00:00:00,000 --> 00:00:01,000\n문장\n"):
        path = os.path.join(self.project, "subtitle", "subtitle.srt")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def whole(self):
        """다 만들어진 상태."""

        self.images(1, 2)
        self.voices(1, 2)
        self.subtitle()
        self.video()

    def check(self):
        return self.client.get("/studio/api/review/p1/output-check").json()


class ReadyTest(Base):
    """1. 다 되면 문제 없음."""

    def test_output_check_ready(self):
        self.whole()

        body = self.check()

        self.assertEqual(body["state"], output_check.READY)
        self.assertTrue(body["video"]["exists"])
        self.assertEqual(body["problems"], [])
        self.assertEqual(body["warnings"], [])

        # 사양이 요구하는 숫자.
        self.assertEqual(body["scenes"], {"ready": 2, "total": 2})
        self.assertEqual(body["voices"], {"ready": 2, "total": 2})
        self.assertTrue(body["subtitle"]["exists"])

    def test_nothing_rendered_is_failed(self):
        """
        아직 안 만든 것과 만들었는데 실패한 것을 가른다.

        영상이 없으면 나머지를 아무리 말해 봐야 쓸 것이 없다.
        """

        self.images(1, 2)
        self.voices(1, 2)

        body = self.check()

        self.assertEqual(body["state"], output_check.FAILED)
        self.assertFalse(body["video"]["exists"])
        self.assertIn("영상", " ".join(body["problems"]))

    def test_an_empty_video_file_is_failed(self):
        """
        파일이 있어도 길이를 못 읽으면 결과가 아니다.

        0바이트 파일을 "완료"라고 하면 사람은 재생해 보고서야 안다.
        """

        self.images(1, 2)
        self.voices(1, 2)
        self.subtitle()

        path = os.path.join(self.project, "video", "final_short.mp4")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").close()

        body = self.check()

        self.assertEqual(body["state"], output_check.FAILED)
        self.assertIsNone(body["video"]["seconds"])


class MissingSceneTest(Base):
    """2. 빠진 것을 짚는다."""

    def test_output_missing_scene_detected(self):
        self.whole()

        os.remove(os.path.join(self.project, "images", "scene2.png"))

        body = self.check()

        self.assertEqual(body["state"], output_check.REVIEW)
        self.assertEqual(body["scenes"], {"ready": 1, "total": 2})

        joined = " ".join(body["warnings"])

        self.assertIn("Scene 2", joined)
        self.assertIn("이미지", joined)

        # 영상은 나왔다 - 실패가 아니다.
        self.assertTrue(body["video"]["exists"])
        self.assertEqual(body["problems"], [])

    def test_a_missing_voice_is_reported_too(self):
        self.whole()

        os.remove(os.path.join(
            self.project, "audio", "scenes",
            audio_policy.scene_audio_filename(1)))

        body = self.check()

        self.assertEqual(body["state"], output_check.REVIEW)
        self.assertEqual(body["voices"], {"ready": 1, "total": 2})
        self.assertIn("음성", " ".join(body["warnings"]))

    def test_a_missing_subtitle_is_reported(self):
        self.images(1, 2)
        self.voices(1, 2)
        self.video()

        body = self.check()

        self.assertEqual(body["state"], output_check.REVIEW)
        self.assertFalse(body["subtitle"]["exists"])
        self.assertIn("자막", " ".join(body["warnings"]))

    def test_an_empty_subtitle_counts_as_missing(self):
        """빈 파일은 자막이 아니다."""

        self.whole()
        self.subtitle("")

        body = self.check()

        self.assertFalse(body["subtitle"]["exists"])


class DurationTest(Base):
    """3. 길이를 그대로 말한다."""

    def test_output_duration_reported(self):
        self.whole()

        body = self.check()

        self.assertAlmostEqual(body["video"]["seconds"], 3.0, delta=0.3)

        # 재는 일은 이미 있는 것이 한다 - 여기서 다시 재지 않는다.
        measured = qa_report_service.get_real_durations(self.project)

        self.assertAlmostEqual(
            body["video"]["seconds"], measured["final_video"], places=2)

    def test_a_short_scene_voice_is_reported(self):
        """
        나레이션이 말하는 길이보다 눈에 띄게 짧으면 말한다.

        허용 오차는 Duration Optimizer가 쓰는 그 값이다 - 새 숫자를
        만들지 않는다.
        """

        from app.services import duration_estimator, duration_optimizer

        long_line = "이 문장은 아주 길어서 읽는 데 시간이 제법 걸립니다. " * 4

        self.scenes[0]["narration"] = long_line

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": self.scenes}, f,
                      ensure_ascii=False)

        self.whole()
        self.voices(1, seconds=0.5)

        expected = duration_estimator.estimate_duration(long_line)

        self.assertGreater(
            expected, 0.5 + duration_optimizer.TOLERANCE_SECONDS)

        body = self.check()

        self.assertEqual(body["state"], output_check.REVIEW)

        joined = " ".join(body["warnings"])

        self.assertIn("Scene 1", joined)
        self.assertIn("짧", joined)

    def test_a_matching_voice_raises_nothing(self):
        self.whole()

        body = self.check()

        self.assertEqual(body["warnings"], [])

    def test_the_scene_seconds_are_listed(self):
        self.whole()

        body = self.check()

        seconds = {row["scene"]: row for row in body["scene_rows"]}

        self.assertAlmostEqual(seconds[1]["seconds"], 1.0, delta=0.2)
        self.assertTrue(seconds[1]["image"])
        self.assertTrue(seconds[1]["voice"])


class NoExternalApiTest(Base):
    """4. 밖으로 안 나간다."""

    def test_output_check_no_external_api(self):
        import requests

        from app.providers import local_stock_provider, local_voice_provider
        from app.services import asset_integration_service

        self.whole()

        before = sorted(os.listdir(self.project))

        with patch.object(
            local_stock_provider, "generate_image") as make_image, \
                patch.object(
                    local_voice_provider, "generate_voice") as make_voice, \
                patch.object(
                    asset_integration_service, "get_candidates") as stock, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            body = self.check()

            for name, mock in (("local_stock", make_image),
                               ("local_voice", make_voice),
                               ("스톡 검색", stock),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()

        self.assertEqual(body["state"], output_check.READY)

        # 읽기만 한다.
        self.assertEqual(sorted(os.listdir(self.project)), before)

    def test_the_module_pulls_in_nothing_that_reaches_out(self):
        import ast

        with open(output_check.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        imported = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        for name in sorted(imported):
            for bad in ("requests", "google", "openai", "anthropic",
                        "vertexai", "urllib"):
                with self.subTest(name=name):
                    self.assertFalse(
                        name == bad or name.startswith(bad + "."))


class RenderPipelineUnchangedTest(Base):
    """5. 렌더는 건드리지 않는다."""

    def test_render_pipeline_unchanged(self):
        """
        검사는 읽기만 한다. 고치지 않는다.

        빠진 것을 우리가 만들어 주면, 사람은 무엇이 빠졌는지 영영
        모른 채 다음에도 같은 자리에서 걸린다.
        """

        self.whole()

        os.remove(os.path.join(self.project, "images", "scene2.png"))

        body = self.check()

        self.assertEqual(body["state"], output_check.REVIEW)

        # 고쳐 주지 않았다.
        self.assertFalse(os.path.exists(
            os.path.join(self.project, "images", "scene2.png")))

    def test_the_measuring_comes_from_the_existing_helper(self):
        with open(output_check.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("qa_report_service.get_real_durations", source)

    def test_the_pipeline_knows_nothing_about_this(self):
        import app.pipeline.pipeline as pipeline

        from app.services import scene_order, video_builder

        for module in (pipeline, scene_order, video_builder):
            with open(module.__file__, encoding="utf-8") as f:
                source = f.read()

            for word in ("output_check", "FAILED"):
                with self.subTest(module=module.__name__, word=word):
                    self.assertNotIn(word, source)

    def test_the_screen_reads_it(self):
        source = _script_source()

        for name in ("outputCheck", "scene_rows"):
            with self.subTest(name=name):
                self.assertIn(name, source)


if __name__ == "__main__":
    unittest.main()
