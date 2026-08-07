"""
Sprint153 - 무엇을 어디에 넣으면 되는지 말한다 (Epic 57, Phase 4).

Sprint152는 "Scene 4 이미지"가 없다고 말했다. 맞는 말이지만 사람이
그 다음에 무엇을 해야 하는지는 알려 주지 않았다 - 어느 폴더에, 어떤
이름으로 넣어야 찾아지는지가 빠져 있었다.

무엇을 지키는가
---------------
    1. Scene마다 필요한 것을 줄로 적는다   test_requirement_report
    2. 그 파일을 어디에 두면 되는지 말한다  test_expected_asset_path
    3. 없을 때 사람이 읽을 말로 말한다      test_missing_asset_message
    4. Workspace 상태를 그대로 보여 준다    test_workspace_status
    5. 아무것도 만들지 않는다               test_free_mode_no_external_
                                            provider

둘째가 이 Sprint의 핵심이다. 그리고 그 경로는 지어내면 안 된다 -
local_stock이 실제로 찾는 방식과 다른 이름을 알려 주면, 사람이 그대로
넣어도 안 찾힌다.
"""

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import audio_policy, free_workspace, local_library


def _png(path):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (32, 32)).save(path)


def _tone(path, seconds=0.3):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", path],
        capture_output=True, check=True,
    )


class RequirementReportTest(unittest.TestCase):
    """1. Scene마다 필요한 것을 줄로 적는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.scenes = [
            {"scene": 1, "narration": "무릎을 펴 주세요",
             "image_prompt": "무릎 스트레칭"},
            {"scene": 2, "narration": "허리를 세웁니다",
             "image_prompt": "우주선 착륙"},
        ]

    def _scan(self):
        local_library.save(self.project, local_library.scan(self.root))

    def test_requirement_report(self):
        _png(os.path.join(self.root, "images", "무릎 스트레칭.png"))
        _tone(os.path.join(self.root, "voices", "scene1.wav"))
        self._scan()

        report = free_workspace.requirements(self.project, self.scenes)
        rows = report["requirements"]

        # 사양이 정한 네 칸이 모든 줄에 있다.
        for row in rows:
            with self.subTest(row=row):
                for key in ("scene", "required_asset", "expected_path",
                            "status"):
                    self.assertIn(key, row)

        got = {(r["scene"], r["required_asset"]): r["status"] for r in rows}

        self.assertEqual(got[(1, "image")], "ready")
        self.assertEqual(got[(1, "voice")], "ready")
        self.assertEqual(got[(2, "image")], "missing")
        self.assertEqual(got[(2, "voice")], "missing")

    def test_the_rows_are_in_scene_order(self):
        """사람이 위에서부터 읽는다."""

        self._scan()

        rows = free_workspace.requirements(
            self.project, self.scenes)["requirements"]

        numbers = [row["scene"] for row in rows]

        self.assertEqual(numbers, sorted(numbers))

    def test_a_scene_without_narration_needs_a_script(self):
        """대본은 파일이 아니다. 둘 곳이 없으므로 경로가 없다."""

        rows = free_workspace.requirements(
            self.project, [{"scene": 1, "narration": "  "}],
        )["requirements"]

        script = [r for r in rows if r["required_asset"] == "script"]

        self.assertEqual(len(script), 1)
        self.assertEqual(script[0]["status"], "missing")
        self.assertIsNone(script[0]["expected_path"])

    def test_a_scene_with_narration_does_not_ask_for_one(self):
        self._scan()

        rows = free_workspace.requirements(
            self.project, self.scenes)["requirements"]

        scripts = [r for r in rows if r["required_asset"] == "script"]

        self.assertEqual(scripts, [])

    def test_the_summary_matches_preparation(self):
        """
        같은 사실을 두 곳이 다르게 말하면 안 된다.

        요구 목록과 준비 상태는 같은 판정에서 나와야 한다.
        """

        _png(os.path.join(self.root, "images", "무릎 스트레칭.png"))
        self._scan()

        report = free_workspace.requirements(self.project, self.scenes)
        prepared = free_workspace.preparation(self.project, self.scenes)

        missing = [
            r for r in report["requirements"] if r["status"] == "missing"
        ]

        self.assertEqual(len(missing), len(prepared["missing"]))
        self.assertEqual(report["ready"], prepared["ready"])


class ExpectedAssetPathTest(unittest.TestCase):
    """2. 그 파일을 어디에 어떤 이름으로 두면 되는가."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def _scan(self):
        local_library.save(self.project, local_library.scan(self.root))

    def test_expected_asset_path(self):
        """
        알려 준 이름을 그대로 넣으면 실제로 찾아진다.

        이 테스트가 이 Sprint의 값어치다 - 경로를 지어내면 사람이
        시킨 대로 해도 안 된다.
        """

        scenes = [
            {"scene": 1, "narration": "문장", "image_prompt": "우주선 착륙"},
        ]

        _tone(os.path.join(self.root, "voices", "scene1.wav"))
        self._scan()

        rows = free_workspace.requirements(
            self.project, scenes)["requirements"]

        image = [r for r in rows if r["required_asset"] == "image"][0]

        self.assertEqual(image["status"], "missing")
        self.assertTrue(image["expected_path"].startswith("images/"))
        self.assertEqual(image["expected_root"], self.root)

        # 알려 준 그대로 넣는다.
        target = os.path.join(self.root, *image["expected_path"].split("/"))
        _png(target)
        self._scan()

        again = free_workspace.requirements(
            self.project, scenes)["requirements"]
        image = [r for r in again if r["required_asset"] == "image"][0]

        self.assertEqual(image["status"], "ready")

    def test_the_voice_path_is_the_scene_number(self):
        """local_voice는 번호로 고른다. 그러니 번호가 든 이름을 준다."""

        scenes = [{"scene": 4, "narration": "문장", "image_prompt": "무릎"}]

        _png(os.path.join(self.root, "images", "무릎.png"))
        self._scan()

        rows = free_workspace.requirements(
            self.project, scenes)["requirements"]
        voice = [r for r in rows if r["required_asset"] == "voice"][0]

        self.assertEqual(voice["expected_path"], "voices/scene4.wav")

        target = os.path.join(self.root, "voices", "scene4.wav")
        _tone(target)
        self._scan()

        again = free_workspace.requirements(
            self.project, scenes)["requirements"]
        voice = [r for r in again if r["required_asset"] == "voice"][0]

        self.assertEqual(voice["status"], "ready")

    def test_without_a_workspace_it_points_at_the_project(self):
        """
        고를 폴더가 없으면 프로젝트에 직접 두는 길을 알려 준다.

        내 자료 폴더를 안 정했는데 "images/무릎.png에 넣으세요"라고
        하면 어느 images인지 알 수 없다.
        """

        scenes = [{"scene": 3, "narration": "문장", "image_prompt": "무릎"}]

        rows = free_workspace.requirements(
            self.project, scenes)["requirements"]

        image = [r for r in rows if r["required_asset"] == "image"][0]
        voice = [r for r in rows if r["required_asset"] == "voice"][0]

        self.assertEqual(image["expected_path"], "images/scene3.png")
        self.assertEqual(image["expected_root"], self.project)
        self.assertEqual(image["location"], "project")

        self.assertEqual(
            voice["expected_path"],
            f"audio/scenes/{audio_policy.scene_audio_filename(3)}",
        )
        self.assertEqual(voice["location"], "project")

    def test_a_prompt_with_no_words_points_at_the_project(self):
        """
        낱말이 없으면 내 자료에서는 영영 못 찾는다.

        그때 "images/<빈 이름>.png"를 알려 주면 시킨 대로 해도 안 된다.
        """

        scenes = [{"scene": 2, "narration": "문장", "image_prompt": ""}]

        _tone(os.path.join(self.root, "voices", "scene2.wav"))
        self._scan()

        rows = free_workspace.requirements(
            self.project, scenes)["requirements"]
        image = [r for r in rows if r["required_asset"] == "image"][0]

        self.assertEqual(image["location"], "project")
        self.assertEqual(image["expected_path"], "images/scene2.png")

    def test_a_video_says_the_videos_folder(self):
        """
        영상에서 온 그림은 videos/에 있다. images/라고 적으면 안 된다.

        사람이 그 줄을 읽고 images/를 열어 보면 없다 - 알려 준 경로가
        틀린 것이고, 그러면 이 Sprint가 하려던 일이 뒤집힌다.
        """

        scenes = [{"scene": 1, "narration": "문장", "image_prompt": "공원 산책"}]

        path = os.path.join(self.root, "videos", "공원 산책.mp4")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", "color=c=cyan:s=160x120:d=0.3", "-pix_fmt", "yuv420p",
             path], capture_output=True, check=True,
        )

        self._scan()

        rows = free_workspace.requirements(
            self.project, scenes)["requirements"]
        image = [r for r in rows if r["required_asset"] == "image"][0]

        self.assertEqual(image["status"], "ready")
        self.assertEqual(image["expected_path"], "videos/공원 산책.mp4")

        # 알려 준 경로에 실제로 있다.
        self.assertTrue(os.path.exists(
            os.path.join(self.root, *image["expected_path"].split("/"))
        ))

    def test_a_ready_asset_says_where_it_actually_is(self):
        """이미 있는 것은 어디 있는지 그대로 말한다."""

        scenes = [{"scene": 1, "narration": "문장", "image_prompt": "무릎"}]

        _png(os.path.join(self.root, "images", "무릎.png"))
        self._scan()

        rows = free_workspace.requirements(
            self.project, scenes)["requirements"]
        image = [r for r in rows if r["required_asset"] == "image"][0]

        self.assertEqual(image["status"], "ready")
        self.assertEqual(image["expected_path"], "images/무릎.png")
        self.assertEqual(image["found"], "무릎.png")


class MissingAssetMessageTest(unittest.TestCase):
    """3. 사람이 읽을 수 있는 말."""

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def test_missing_asset_message(self):
        scenes = [{"scene": 4, "narration": "문장", "image_prompt": "우주선"}]

        rows = free_workspace.requirements(
            self.project, scenes)["requirements"]

        image = [r for r in rows if r["required_asset"] == "image"][0]

        # 무엇이 없는지, 그리고 무엇을 하면 되는지 둘 다 있다.
        self.assertIn("이미지", image["message"])
        self.assertIn("없", image["message"])
        self.assertIn(image["expected_path"], image["message"])

    def test_a_ready_asset_says_it_is_ready(self):
        scenes = [{"scene": 1, "narration": "문장", "image_prompt": "무릎"}]

        _png(os.path.join(self.project, "images", "scene1.png"))

        rows = free_workspace.requirements(
            self.project, scenes)["requirements"]
        image = [r for r in rows if r["required_asset"] == "image"][0]

        self.assertEqual(image["status"], "ready")
        self.assertNotIn("없", image["message"])

    def test_the_message_never_promises_to_make_it(self):
        """
        "만들어 드릴까요"라고 하지 않는다.

        이 Sprint는 표시만 한다. 만들자고 권하는 순간 사람은 눌러
        보고, 그러면 돈이 든다.
        """

        scenes = [
            {"scene": n, "narration": "문장", "image_prompt": f"주제 {n}"}
            for n in (1, 2, 3)
        ]

        rows = free_workspace.requirements(
            self.project, scenes)["requirements"]

        for row in rows:
            with self.subTest(row=row):
                for word in ("생성", "자동", "만들어 드", "AI가"):
                    self.assertNotIn(word, row["message"])


class WorkspaceStatusTest(unittest.TestCase):
    """4. Workspace를 있는 그대로."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.store = os.path.join(tempfile.mkdtemp(), "free_workspace.json")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(
            shutil.rmtree, os.path.dirname(self.store), ignore_errors=True)

    def test_workspace_status(self):
        for name in ("a.png", "b.png"):
            _png(os.path.join(self.root, "images", name))

        _tone(os.path.join(self.root, "voices", "scene1.wav"))
        _tone(os.path.join(self.root, "music", "bgm.mp3"))

        free_workspace.remember(self.store, self.root)
        status = free_workspace.status(self.store)

        self.assertEqual(status["root"], self.root)
        self.assertEqual(status["counts"]["images"], 2)
        self.assertEqual(status["counts"]["voice"], 1)
        self.assertEqual(status["counts"]["music"], 1)
        self.assertEqual(status["counts"]["videos"], 0)

        # 폴더가 어디 있어야 하는지도 말한다 - 처음 쓰는 사람은
        # 무엇을 만들어야 하는지 모른다.
        self.assertEqual(
            set(status["folders"]), {"images", "videos", "voices", "music"},
        )

    def test_without_a_workspace_it_says_so(self):
        status = free_workspace.status(self.store)

        self.assertIsNone(status["root"])
        self.assertEqual(sum(status["counts"].values()), 0)


class NoExternalProviderTest(unittest.TestCase):
    """5. 아무것도 만들지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def test_free_mode_no_external_provider(self):
        """
        요구 목록을 내는 동안 만드는 함수가 한 번도 불리지 않는다.

        AI 이미지도, TTS도, 스톡 검색 폴백도 없다.
        """

        import requests

        from app.providers import local_stock_provider, local_voice_provider
        from app.services import asset_integration_service

        scenes = [
            {"scene": 1, "narration": "문장", "image_prompt": "무릎"},
            {"scene": 2, "narration": "문장", "image_prompt": "우주선"},
        ]

        _png(os.path.join(self.root, "images", "무릎.png"))
        local_library.save(self.project, local_library.scan(self.root))

        with patch.object(
            local_stock_provider, "generate_image",
        ) as make_image, patch.object(
            local_voice_provider, "generate_voice",
        ) as make_voice, patch.object(
            asset_integration_service, "get_candidates",
        ) as stock, patch.object(
            asset_integration_service.best_of_n_service, "generate_candidates",
        ) as imagen, patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            report = free_workspace.requirements(self.project, scenes)

            make_image.assert_not_called()
            make_voice.assert_not_called()
            stock.assert_not_called()
            imagen.assert_not_called()
            get.assert_not_called()
            post.assert_not_called()

        # 그러면서도 실제로 답을 냈다.
        got = {
            (r["scene"], r["required_asset"]): r["status"]
            for r in report["requirements"]
        }

        self.assertEqual(got[(1, "image")], "ready")
        self.assertEqual(got[(2, "image")], "missing")

    def test_nothing_was_written_to_the_project(self):
        """읽기만 한다. 파일이 하나도 안 생긴다."""

        scenes = [{"scene": 1, "narration": "문장", "image_prompt": "무릎"}]

        before = sorted(os.listdir(self.project))

        free_workspace.requirements(self.project, scenes)
        free_workspace.status(os.path.join(self.root, "store.json"))

        self.assertEqual(sorted(os.listdir(self.project)), before)

    def test_it_asks_the_providers_for_the_naming_rule(self):
        """
        경로를 지어내지 않는다.

        local_stock이 낱말을 뽑는 그 함수를 그대로 써야, 알려 준
        이름을 넣었을 때 실제로 찾아진다.
        """

        with open(free_workspace.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("local_stock_provider._keywords", source)

    def test_the_provider_modules_still_do_not_know_this_one(self):
        from app.providers import local_stock_provider, local_voice_provider

        for module in (local_stock_provider, local_voice_provider):
            with open(module.__file__, encoding="utf-8") as f:
                tree = ast.parse(f.read())

            for node in ast.walk(tree):
                names = []

                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]

                for name in names:
                    with self.subTest(module=module.__name__, name=name):
                        self.assertNotIn("free_workspace", name)


if __name__ == "__main__":
    unittest.main()
