"""
Sprint165 - 고친 뒤에 같은 자리에서 다시 본다 (Epic 57, Phase 16).

Sprint163·164가 결과를 보고 그 자리로 가게 했다. 그런데 고치고 나서
다시 보려면 화면을 새로 열어야 했다.

이 Sprint에서 만드는 것은 단추 하나다
-------------------------------------
검사 자체는 이미 무상태다. output_check.build는 부를 때마다 지금 있는
파일을 읽고, 아무것도 적어 두지 않는다.

그래서 "다시 검사"는 같은 것을 한 번 더 부르는 일이고, 이 Sprint가
지켜야 할 것은 "정말로 다시 읽는가"이다. 어딘가에 결과를 캐시해 두면
고쳤는데도 예전 답이 나오고, 사람은 자기가 고친 것이 안 먹혔다고
생각한다.

무엇을 지키는가
---------------
    1. 부를 때마다 지금 파일을 읽는다
                        test_output_recheck_reads_current_files
    2. 고치면 사라진다   test_issue_disappears_after_manual_fix
    3. 안 고치면 남는다  test_issue_remains_without_fix
    4. 검사가 만들지 않는다
                        test_recheck_never_generates
    5. 다 고치면 READY   test_ready_after_all_issues_fixed

넷째가 경계다. 검사가 빠진 것을 만들어 주면 그것은 검사가 아니라
생성이고, 사람은 무엇이 빠졌는지 영영 모른다.
"""

import hashlib
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


def _tree(path):
    """폴더 안의 파일과 그 내용. 검사가 무엇도 바꾸지 않았는지 본다."""

    found = {}

    for base, _, names in os.walk(path):
        for name in names:
            full = os.path.join(base, name)

            with open(full, "rb") as f:
                found[os.path.relpath(full, path)] = \
                    hashlib.md5(f.read()).hexdigest()

    return found


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

    def image(self, number):
        _png(os.path.join(self.project, "images", f"scene{number}.png"))

    def voice(self, number, seconds=1.0):
        _wav(os.path.join(self.project, "audio", "scenes",
                          audio_policy.scene_audio_filename(number)), seconds)

    def video(self, seconds=3.0):
        _mp4(os.path.join(self.project, "video", "final_short.mp4"), seconds)

    def subtitle(self):
        path = os.path.join(self.project, "subtitle", "subtitle.srt")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\n문장\n")

    def whole(self):
        for number in (1, 2, 3):
            self.image(number)
            self.voice(number)

        self.subtitle()
        self.video()

    def check(self):
        return self.client.get("/studio/api/review/p1/output-check").json()

    def kinds(self):
        return [(i["scene"], i["kind"]) for i in self.check()["issues"]]


class ReadsCurrentFilesTest(Base):
    """1. 부를 때마다 지금 파일을 읽는다."""

    def test_output_recheck_reads_current_files(self):
        """
        어딘가에 결과를 캐시해 두면 고쳤는데도 예전 답이 나온다.

        같은 프로젝트를 두 번 묻되, 사이에 파일을 바꾼다.
        """

        self.whole()

        self.assertEqual(self.check()["state"], output_check.READY)

        os.remove(os.path.join(self.project, "images", "scene2.png"))

        self.assertEqual(self.check()["state"], output_check.REVIEW)

        self.image(2)

        self.assertEqual(self.check()["state"], output_check.READY)

    def test_the_measured_length_follows_the_file(self):
        self.whole()

        first = self.check()["video"]["seconds"]

        self.assertAlmostEqual(first, 3.0, delta=0.3)

        # 다른 길이의 영상으로 바꾼다.
        self.video(6.0)

        second = self.check()["video"]["seconds"]

        self.assertAlmostEqual(second, 6.0, delta=0.3)
        self.assertNotAlmostEqual(first, second, places=1)

    def test_nothing_is_remembered_between_calls(self):
        """
        검사 결과를 적어 두지 않는다.

        적어 두면 그 파일이 곧 또 하나의 진실이 되고, 실제 파일과
        갈리는 날이 온다.
        """

        self.whole()

        before = sorted(os.listdir(self.project))

        for _ in range(3):
            self.check()

        self.assertEqual(sorted(os.listdir(self.project)), before)

        # 모듈에도 남는 것이 없다.
        import ast

        with open(output_check.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                self.fail(f"전역을 쓴다: {node.names}")


class IssueDisappearsTest(Base):
    """2. 고치면 사라진다."""

    def test_issue_disappears_after_manual_fix(self):
        self.whole()

        os.remove(os.path.join(self.project, "images", "scene2.png"))

        self.assertEqual(self.kinds(), [(2, "image")])

        # 사람이 손으로 넣는다.
        self.image(2)

        self.assertEqual(self.kinds(), [])
        self.assertEqual(self.check()["state"], output_check.READY)

    def test_only_the_fixed_one_disappears(self):
        self.whole()

        os.remove(os.path.join(self.project, "images", "scene2.png"))
        os.remove(os.path.join(self.project, "audio", "scenes",
                               audio_policy.scene_audio_filename(3)))

        self.assertEqual(sorted(self.kinds()),
                         [(2, "image"), (3, "voice")])

        self.image(2)

        self.assertEqual(self.kinds(), [(3, "voice")])

    def test_a_short_voice_disappears_when_it_gets_longer(self):
        self.scenes[0]["narration"] = self.LONG
        self.save_script()

        self.whole()
        self.voice(1, seconds=0.5)

        self.assertEqual(self.kinds(), [(1, "voice_short")])

        self.voice(1, seconds=9.0)

        self.assertEqual(self.kinds(), [])

    def test_a_subtitle_comes_back(self):
        self.whole()

        os.remove(os.path.join(self.project, "subtitle", "subtitle.srt"))

        self.assertEqual(self.kinds(), [(None, "subtitle")])

        self.subtitle()

        self.assertEqual(self.kinds(), [])


class IssueRemainsTest(Base):
    """3. 안 고치면 남는다."""

    def test_issue_remains_without_fix(self):
        """
        다시 눌렀다고 없어지지 않는다.

        누른 것만으로 초록이 되면 사람은 고치지 않은 채 다음으로 간다.
        """

        self.whole()

        os.remove(os.path.join(self.project, "images", "scene2.png"))

        for _ in range(3):
            self.assertEqual(self.kinds(), [(2, "image")])
            self.assertEqual(self.check()["state"], output_check.REVIEW)

    def test_an_empty_file_does_not_count_as_fixed(self):
        """0바이트를 놓아 두고 고쳤다고 하면 안 된다."""

        self.whole()

        os.remove(os.path.join(self.project, "subtitle", "subtitle.srt"))

        path = os.path.join(self.project, "subtitle", "subtitle.srt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").close()

        self.assertEqual(self.kinds(), [(None, "subtitle")])


class NeverGeneratesTest(Base):
    """4. 검사가 만들지 않는다."""

    def test_recheck_never_generates(self):
        """
        빠진 것을 검사가 만들어 주면 그것은 검사가 아니라 생성이고,
        사람은 무엇이 빠졌는지 영영 모른다.
        """

        import requests

        from app.providers import local_stock_provider, local_voice_provider
        from app.services import (
            asset_integration_service, scene_tts_service, subtitle_service,
        )

        self.whole()

        os.remove(os.path.join(self.project, "images", "scene2.png"))
        os.remove(os.path.join(self.project, "audio", "scenes",
                               audio_policy.scene_audio_filename(3)))
        os.remove(os.path.join(self.project, "subtitle", "subtitle.srt"))

        before = _tree(self.project)

        with patch.object(
            local_stock_provider, "generate_image") as make_image, \
                patch.object(
                    local_voice_provider, "generate_voice") as make_voice, \
                patch.object(
                    scene_tts_service, "create_scene_tts") as tts, \
                patch.object(
                    subtitle_service, "create_subtitle") as subtitle, \
                patch.object(
                    asset_integration_service, "get_candidates") as stock, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            for _ in range(3):
                self.check()

            for name, mock in (("local_stock", make_image),
                               ("local_voice", make_voice),
                               ("create_scene_tts", tts),
                               ("create_subtitle", subtitle),
                               ("스톡 검색", stock),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()

        # 파일 하나도 안 생기고 안 바뀌었다.
        self.assertEqual(_tree(self.project), before)

    def test_the_screen_only_reloads(self):
        """
        다시 검사 단추가 만드는 자리를 부르지 않는다.

        부르면 검사 단추가 곧 생성 단추가 된다.
        """

        source = _script_source()

        self.assertIn("function recheckOutput", source)

        body = source[source.index("function recheckOutput"):]
        body = body[:body.index("\n}")]

        for forbidden in ("/images", "/voices", "/render", "POST"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, body)

        self.assertIn("loadOutputCheck", body)


class ReadyAfterFixTest(Base):
    """5. 다 고치면 READY."""

    def test_ready_after_all_issues_fixed(self):
        self.whole()

        os.remove(os.path.join(self.project, "images", "scene2.png"))
        os.remove(os.path.join(self.project, "audio", "scenes",
                               audio_policy.scene_audio_filename(3)))
        os.remove(os.path.join(self.project, "subtitle", "subtitle.srt"))

        body = self.check()

        self.assertEqual(body["state"], output_check.REVIEW)
        self.assertEqual(len(body["issues"]), 3)

        self.image(2)
        self.assertEqual(len(self.check()["issues"]), 2)

        self.voice(3)
        self.assertEqual(len(self.check()["issues"]), 1)

        self.subtitle()

        body = self.check()

        self.assertEqual(body["state"], output_check.READY)
        self.assertEqual(body["issues"], [])
        self.assertEqual(body["scenes"], {"ready": 3, "total": 3})
        self.assertEqual(body["voices"], {"ready": 3, "total": 3})

    def test_a_lost_video_goes_back_to_failed(self):
        """영상이 사라지면 다시 실패다 - 고친 것이 남아 있어도."""

        self.whole()

        os.remove(os.path.join(self.project, "video", "final_short.mp4"))

        self.assertEqual(self.check()["state"], output_check.FAILED)

    def test_the_screen_has_the_button(self):
        source = _script_source()

        self.assertIn("다시 검사", source)


if __name__ == "__main__":
    unittest.main()
