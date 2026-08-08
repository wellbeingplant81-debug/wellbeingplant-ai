"""
Sprint164 - 문제에서 그 자리로 바로 간다 (Epic 57, Phase 15).

Sprint163이 "무엇이 잘못됐는가"를 말했다. 그런데 그것은 글이었다.

    "Scene 2 이미지 없음"

사람은 그것을 읽고 Timeline을 스스로 뒤져야 했다. Scene이 여섯이면
할 만하지만, 그때마다 화면 어디를 열어야 하는지도 기억해야 했다.

같은 사실을 두 번 관리하지 않는다
---------------------------------
글(warnings)과 구조(issues)를 따로 만들면 한쪽만 바뀌는 날이 온다.
issues가 원본이고 warnings는 거기서 뽑는다.

자막은 Scene이 없다
-------------------
자막은 영상 하나에 하나다. 그 사실에 Scene 번호를 붙이면 지어내는
것이 된다 - scene을 None으로 두고, 화면은 그때 Scene을 고르지 않는다.

무엇을 지키는가
---------------
    1. 문제마다 어느 Scene인지 있다   test_output_issue_has_scene
    2. 누르면 그 Scene이 골라진다     test_click_issue_selects_scene
    3. 이미지 문제는 이미지 자리로    test_missing_image_navigation
    4. 음성 문제는 음성 자리로        test_missing_audio_navigation
    5. 판정은 그대로다                test_output_check_unchanged
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
from app.services import audio_policy, output_check

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
    LONG = ("이 문장은 아주 길어서 읽는 데 시간이 제법 걸립니다. "
            "천천히 따라 해 보십시오. 그리고 숨을 깊게 들이마십니다.")

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
            for n in (1, 2, 3)
        ]

        self.save_script()

    def _restore(self):
        studio_router._project_path = self._real

    def save_script(self):
        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": self.scenes}, f,
                      ensure_ascii=False)

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

    def subtitle(self):
        path = os.path.join(self.project, "subtitle", "subtitle.srt")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\n문장\n")

    def whole(self):
        self.images(1, 2, 3)
        self.voices(1, 2, 3)
        self.subtitle()
        self.video()

    def check(self):
        return self.client.get("/studio/api/review/p1/output-check").json()

    def issues(self):
        return self.check()["issues"]


class IssueHasSceneTest(Base):
    """1. 문제마다 어느 Scene인지 있다."""

    def test_output_issue_has_scene(self):
        self.whole()

        os.remove(os.path.join(self.project, "images", "scene2.png"))

        found = self.issues()

        self.assertEqual(len(found), 1)

        issue = found[0]

        self.assertEqual(issue["scene"], 2)
        self.assertEqual(issue["kind"], "image")
        self.assertIn("Scene 2", issue["message"])

    def test_a_subtitle_issue_has_no_scene(self):
        """
        자막은 영상 하나에 하나다.

        Scene 번호를 붙이면 지어내는 것이 된다.
        """

        self.images(1, 2, 3)
        self.voices(1, 2, 3)
        self.video()

        found = [i for i in self.issues() if i["kind"] == "subtitle"]

        self.assertEqual(len(found), 1)
        self.assertIsNone(found[0]["scene"])

    def test_every_issue_carries_the_three_things(self):
        self.images(1)
        self.voices(2)
        self.video()

        for issue in self.issues():
            with self.subTest(issue=issue):
                self.assertIn("scene", issue)
                self.assertIn("kind", issue)
                self.assertTrue(issue["message"])

    def test_the_kinds_are_the_ones_the_screen_knows(self):
        """
        화면이 모르는 종류를 서버가 내면 그 줄은 갈 곳이 없다.
        """

        self.scenes[0]["narration"] = self.LONG
        self.save_script()

        self.voices(1, seconds=0.3)
        self.voices(2)
        self.images(3)
        self.video()

        kinds = {issue["kind"] for issue in self.issues()}

        self.assertLessEqual(kinds, set(output_check.ISSUE_KINDS))
        self.assertTrue(kinds)

    def test_warnings_are_drawn_from_the_issues(self):
        """
        같은 사실을 두 번 관리하지 않는다.

        글과 구조를 따로 만들면 한쪽만 바뀌는 날이 온다.
        """

        self.images(1)
        self.voices(2)
        self.video()

        body = self.check()

        self.assertEqual(
            body["warnings"], [i["message"] for i in body["issues"]])


class NavigationTest(Base):
    """2·3·4. 누르면 그 자리로 간다."""

    def test_click_issue_selects_scene(self):
        source = _script_source()

        # 이동은 Timeline이 이미 가진 자리를 쓴다.
        self.assertIn("function goToIssue", source)

        body = source[source.index("function goToIssue"):]
        body = body[:body.index("\n}")]

        self.assertIn("goToScene", body)

    def test_missing_image_navigation(self):
        """이미지 문제는 이미지 자리로 연다."""

        source = _script_source()

        self.assertIn("ISSUE_SECTION", source)

        declared = source[source.index("const ISSUE_SECTION"):]
        declared = declared[:declared.index("};")]

        self.assertIn('image: "image"', declared)

    def test_missing_audio_navigation(self):
        """음성 문제는 음성 자리로 연다. 길이 문제도 같은 자리다."""

        source = _script_source()

        declared = source[source.index("const ISSUE_SECTION"):]
        declared = declared[:declared.index("};")]

        self.assertIn('voice: "voice"', declared)
        self.assertIn('voice_short: "voice"', declared)
        self.assertIn('subtitle: "script"', declared)

    def test_the_screen_knows_every_kind_the_server_sends(self):
        source = _script_source()

        declared = source[source.index("const ISSUE_SECTION"):]
        declared = declared[:declared.index("};")]

        for kind in output_check.ISSUE_KINDS:
            with self.subTest(kind=kind):
                self.assertIn(f"{kind}:", declared)

    def test_the_button_is_drawn(self):
        source = _script_source()

        self.assertIn("Scene ${issue.scene} 수정", source)


class OutputCheckUnchangedTest(Base):
    """5. 판정은 그대로다."""

    def test_output_check_unchanged(self):
        """
        이 Sprint는 같은 사실에 자리를 붙였을 뿐이다.

        상태와 숫자가 달라지면 그것은 다른 일을 한 것이다.
        """

        self.whole()

        body = self.check()

        self.assertEqual(body["state"], output_check.READY)
        self.assertEqual(body["issues"], [])
        self.assertEqual(body["warnings"], [])

        os.remove(os.path.join(self.project, "images", "scene2.png"))

        body = self.check()

        self.assertEqual(body["state"], output_check.REVIEW)
        self.assertEqual(body["scenes"], {"ready": 2, "total": 3})
        self.assertEqual(body["problems"], [])

        os.remove(os.path.join(self.project, "video", "final_short.mp4"))

        body = self.check()

        self.assertEqual(body["state"], output_check.FAILED)
        self.assertEqual(body["problems"], ["영상이 없습니다"])

    def test_nothing_is_fixed(self):
        """읽기 전용이다. 고쳐 주지 않는다."""

        self.whole()

        os.remove(os.path.join(self.project, "images", "scene2.png"))

        before = sorted(os.listdir(self.project))

        self.check()
        self.check()

        self.assertEqual(sorted(os.listdir(self.project)), before)
        self.assertFalse(os.path.exists(
            os.path.join(self.project, "images", "scene2.png")))

    def test_nothing_external_is_called(self):
        import requests

        from app.providers import local_stock_provider, local_voice_provider
        from app.services import asset_integration_service

        self.whole()
        os.remove(os.path.join(self.project, "images", "scene2.png"))

        with patch.object(
            local_stock_provider, "generate_image") as make_image, \
                patch.object(
                    local_voice_provider, "generate_voice") as make_voice, \
                patch.object(
                    asset_integration_service, "get_candidates") as stock, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            found = self.issues()

            for name, mock in (("local_stock", make_image),
                               ("local_voice", make_voice),
                               ("스톡 검색", stock),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()

        self.assertEqual(found[0]["scene"], 2)

    def test_the_pipeline_knows_nothing_about_this(self):
        import app.pipeline.pipeline as pipeline

        from app.services import scene_order, video_builder

        for module in (pipeline, scene_order, video_builder):
            with open(module.__file__, encoding="utf-8") as f:
                source = f.read()

            for word in ("issues", "ISSUE_KINDS", "goToIssue"):
                with self.subTest(module=module.__name__, word=word):
                    self.assertNotIn(word, source)


if __name__ == "__main__":
    unittest.main()
