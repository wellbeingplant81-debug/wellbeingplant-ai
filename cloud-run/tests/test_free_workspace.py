"""
Sprint152 - 내 자료 폴더 하나로 끝낸다 (Epic 57, Phase 3).

Sprint150·151이 그림과 소리를 내 PC에서 가져오게 만들었다. 그런데
쓰려면 프로젝트마다 폴더를 다시 훑어야 했고, 무엇이 모자란지는
렌더를 눌러 봐야 알았다.

무엇을 지키는가
---------------
    1. 폴더 하나를 정하면 기억한다        test_workspace_scan
    2. 종류마다 몇 개인지 센다            test_asset_count
    3. Scene마다 무엇이 준비됐는지 말한다  test_scene_preparation_status
    4. 모자란 것을 그 자리에서 말한다      test_missing_asset_report
    5. 그 길에서 밖으로 나가지 않는다      test_free_mode_does_not_call_
                                          external_api

셋째가 이 Sprint의 핵심이다. "만들 수 있다"와 "이미 만들었다"는 다른
말이고, 화면이 둘을 섞으면 사람이 렌더를 누르고 나서야 안다.
"""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import free_workspace, local_library


def _png(path, color=(200, 30, 30)):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (64, 48), color).save(path)


def _tone(path, seconds=1.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}",
         path],
        capture_output=True, check=True,
    )


def _mp4(path, seconds=1.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c=cyan:s=320x240:d={seconds}",
         "-pix_fmt", "yuv420p", path],
        capture_output=True, check=True,
    )


class WorkspaceScanTest(unittest.TestCase):
    """1. 폴더 하나를 정하면 기억한다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.store = os.path.join(tempfile.mkdtemp(), "free_workspace.json")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(
            shutil.rmtree, os.path.dirname(self.store), ignore_errors=True)

    def test_workspace_scan(self):
        _png(os.path.join(self.root, "images", "무릎.png"))
        _tone(os.path.join(self.root, "voices", "scene1.wav"))

        # 정하기 전에는 아무것도 없다. 있는 척하지 않는다.
        self.assertIsNone(free_workspace.remembered(self.store)["root"])

        result = free_workspace.remember(self.store, self.root)

        self.assertEqual(result["root"], self.root)
        self.assertEqual(free_workspace.remembered(self.store)["root"],
                         self.root)

    def test_a_folder_that_is_not_there_is_refused(self):
        """없는 곳을 기억해 두면 나중에 조용히 빈 목록이 된다."""

        with self.assertRaises(free_workspace.WorkspaceError):
            free_workspace.remember(self.store, os.path.join(self.root, "없음"))

        self.assertIsNone(free_workspace.remembered(self.store)["root"])

    def test_voices_and_voice_are_the_same_folder(self):
        """
        사양은 voices/, Sprint150·151이 만든 것은 voice/다.

        둘 다 받는다 - 이미 voice/로 모아 둔 사람의 폴더를 못 쓰게
        만들 이유가 없고, 새로 만드는 사람이 voices/라고 지어도 된다.
        """

        _tone(os.path.join(self.root, "voices", "scene1.wav"))
        _tone(os.path.join(self.root, "voice", "scene2.wav"))

        counts = local_library.counts(local_library.scan(self.root))

        self.assertEqual(counts["voice"], 2)

    def test_a_broken_store_is_read_as_nothing(self):
        """기억한 것이 깨졌다고 화면 전체가 죽을 이유는 없다."""

        os.makedirs(os.path.dirname(self.store), exist_ok=True)

        with open(self.store, "w", encoding="utf-8") as f:
            f.write("{{{ 망가진 것")

        self.assertIsNone(free_workspace.remembered(self.store)["root"])


class AssetCountTest(unittest.TestCase):
    """2. 종류마다 몇 개인가."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_asset_count(self):
        for name in ("무릎.png", "허리.png", "어깨.jpg"):
            _png(os.path.join(self.root, "images", name))

        for name in ("산책.mp4", "요가.mp4"):
            _mp4(os.path.join(self.root, "videos", name), seconds=0.4)

        for name in ("scene1.wav", "scene2.wav", "scene3.mp3", "scene4.wav"):
            _tone(os.path.join(self.root, "voices", name), seconds=0.3)

        _tone(os.path.join(self.root, "music", "차분한.mp3"), seconds=0.3)

        counts = free_workspace.inventory(self.root)

        self.assertEqual(counts, {
            "images": 3, "videos": 2, "voice": 4, "music": 1,
        })

    def test_an_empty_folder_counts_zero_not_missing(self):
        counts = free_workspace.inventory(self.root)

        self.assertEqual(counts, {
            "images": 0, "videos": 0, "voice": 0, "music": 0,
        })

    def test_a_folder_that_is_not_there_counts_zero(self):
        counts = free_workspace.inventory(os.path.join(self.root, "없음"))

        self.assertEqual(sum(counts.values()), 0)


class ScenePreparationTest(unittest.TestCase):
    """3. Scene마다 무엇이 준비됐는가."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.scenes = [
            {"scene": 1, "narration": "무릎을 펴 주세요",
             "image_prompt": "무릎 스트레칭"},
            {"scene": 2, "narration": "허리를 세웁니다",
             "image_prompt": "허리 통증"},
            {"scene": 3, "narration": "숨을 쉽니다",
             "image_prompt": "공원 산책"},
        ]

    def _scan(self):
        local_library.save(self.project, local_library.scan(self.root))

    def test_scene_preparation_status(self):
        _png(os.path.join(self.root, "images", "무릎 스트레칭.png"))
        _png(os.path.join(self.root, "images", "허리 통증.png"))
        _mp4(os.path.join(self.root, "videos", "공원 산책.mp4"), seconds=0.4)

        for number in (1, 2):
            _tone(os.path.join(self.root, "voices", f"scene{number}.wav"),
                  seconds=0.3)

        self._scan()

        report = free_workspace.preparation(self.project, self.scenes)
        rows = {row["scene"]: row for row in report["scenes"]}

        # Scene 1 - 대본·이미지·음성 다 있고 영상은 아니다.
        self.assertTrue(rows[1]["script"])
        self.assertTrue(rows[1]["image"]["ready"])
        self.assertEqual(rows[1]["image"]["from"], "workspace")
        self.assertEqual(rows[1]["image"]["name"], "무릎 스트레칭.png")
        self.assertTrue(rows[1]["voice"]["ready"])
        self.assertFalse(rows[1]["video"])

        # Scene 3 - 그림은 영상에서 온다. 음성이 없다.
        self.assertTrue(rows[3]["image"]["ready"])
        self.assertTrue(rows[3]["video"])
        self.assertEqual(rows[3]["image"]["name"], "공원 산책.mp4")
        self.assertFalse(rows[3]["voice"]["ready"])

    def test_made_and_can_be_made_are_not_the_same_word(self):
        """
        이미 만든 것과 만들 수 있는 것을 섞지 않는다.

        섞으면 "준비됐다"는 말이 두 가지 뜻이 되고, 사람은 어느
        쪽인지 모른 채 렌더를 누른다.
        """

        # 내 자료에는 없지만 이미 만들어져 있는 scene.
        _png(os.path.join(self.project, "images", "scene1.png"))

        from app.services import audio_policy

        _tone(os.path.join(self.project, "audio", "scenes",
                           audio_policy.scene_audio_filename(1)), seconds=0.3)

        self._scan()

        rows = {
            row["scene"]: row
            for row in free_workspace.preparation(
                self.project, self.scenes)["scenes"]
        }

        self.assertTrue(rows[1]["image"]["ready"])
        self.assertEqual(rows[1]["image"]["from"], "made")
        self.assertTrue(rows[1]["voice"]["ready"])
        self.assertEqual(rows[1]["voice"]["from"], "made")

        self.assertFalse(rows[2]["image"]["ready"])
        self.assertIsNone(rows[2]["image"]["from"])

    def test_a_scene_without_narration_is_not_ready(self):
        self._scan()

        rows = {
            row["scene"]: row
            for row in free_workspace.preparation(
                self.project, [{"scene": 1, "narration": "  "}])["scenes"]
        }

        self.assertFalse(rows[1]["script"])

    def test_the_summary_counts_what_is_ready(self):
        _png(os.path.join(self.root, "images", "무릎 스트레칭.png"))
        _mp4(os.path.join(self.root, "videos", "공원 산책.mp4"), seconds=0.4)
        _tone(os.path.join(self.root, "voices", "scene1.wav"), seconds=0.3)

        self._scan()

        report = free_workspace.preparation(self.project, self.scenes)

        # 이미지는 1·3번(3번은 영상에서), 음성은 1번뿐.
        self.assertEqual(report["ready"],
                         {"script": 3, "images": 2, "voice": 1, "videos": 1})
        self.assertEqual(report["total"], 3)


class MissingAssetReportTest(unittest.TestCase):
    """4. 모자란 것을 사람이 읽을 수 있는 말로."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def test_missing_asset_report(self):
        # Sprint156 - 프롬프트마다 낱말이 달라야 한다. 예전에는
        # "프롬프트 1"~"프롬프트 4"를 썼는데, 낱말 뽑기를 고친 뒤로는
        # 넷이 "프롬프트"를 함께 가져 4번도 1번 그림에 걸린다.
        # 실제 대본에서는 Scene마다 다른 것을 말하므로, 그 모양으로
        # 맞춘다 - 여기서 지킬 것은 "없는 것을 없다고 말한다"이다.
        topics = {1: "무릎", 2: "허리", 3: "어깨", 4: "우주선"}

        scenes = [
            {"scene": n, "narration": f"{n}번 문장",
             "image_prompt": topics[n]}
            for n in (1, 2, 3, 4)
        ]

        # 1·2·3번 그림만 있고, 음성은 1번만.
        for n in (1, 2, 3):
            _png(os.path.join(self.root, "images", f"{topics[n]}.png"))

        _tone(os.path.join(self.root, "voices", "scene1.wav"), seconds=0.3)

        local_library.save(self.project, local_library.scan(self.root))

        report = free_workspace.preparation(self.project, scenes)

        self.assertIn("Scene 4 이미지", report["missing"])
        self.assertIn("Scene 2 음성", report["missing"])
        self.assertIn("Scene 3 음성", report["missing"])
        self.assertIn("Scene 4 음성", report["missing"])

        self.assertNotIn("Scene 1 이미지", report["missing"])
        self.assertNotIn("Scene 1 음성", report["missing"])

        # 순서는 Scene 번호대로다 - 사람이 위에서부터 읽는다.
        numbers = [
            int(text.split()[1]) for text in report["missing"]
        ]
        self.assertEqual(numbers, sorted(numbers))

    def test_nothing_missing_is_an_empty_list(self):
        """모자란 것이 없으면 빈 목록이다. "없음"이라 적지 않는다."""

        scenes = [{"scene": 1, "narration": "문장", "image_prompt": "무릎"}]

        _png(os.path.join(self.root, "images", "무릎.png"))
        _tone(os.path.join(self.root, "voices", "scene1.wav"), seconds=0.3)

        local_library.save(self.project, local_library.scan(self.root))

        report = free_workspace.preparation(self.project, scenes)

        self.assertEqual(report["missing"], [])

    def test_without_a_scan_everything_is_missing_and_it_says_so(self):
        scenes = [{"scene": 1, "narration": "문장", "image_prompt": "무릎"}]

        report = free_workspace.preparation(self.project, scenes)

        self.assertIn("Scene 1 이미지", report["missing"])
        self.assertIn("Scene 1 음성", report["missing"])
        self.assertFalse(report["scanned"])


class NoExternalCallTest(unittest.TestCase):
    """5. 준비 상태를 보는 동안 밖으로 나가지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def test_free_mode_does_not_call_external_api(self):
        """
        훑기도 준비 상태 확인도 네트워크를 쓰지 않는다.

        requests가 한 번이라도 불리면 "비용 0원"이 거짓이 될 수 있다.
        """

        import requests

        scenes = [
            {"scene": 1, "narration": "문장", "image_prompt": "무릎"},
            {"scene": 2, "narration": "문장", "image_prompt": "우주선"},
        ]

        _png(os.path.join(self.root, "images", "무릎.png"))
        _tone(os.path.join(self.root, "voices", "scene1.wav"), seconds=0.3)

        with patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post, \
                patch.object(requests, "request") as request:

            local_library.save(self.project, local_library.scan(self.root))

            free_workspace.inventory(self.root)
            report = free_workspace.preparation(self.project, scenes)

            get.assert_not_called()
            post.assert_not_called()
            request.assert_not_called()

        # 그러면서도 실제로 답을 냈다 - 아무것도 안 하고 통과한 것이
        # 아니다.
        self.assertEqual(report["ready"]["images"], 1)
        self.assertIn("Scene 2 이미지", report["missing"])

    def test_the_module_imports_nothing_that_reaches_out(self):
        with open(free_workspace.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        imported = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        for name in sorted(imported):
            for bad in ("requests", "urllib", "http", "socket", "google",
                        "openai", "anthropic"):
                self.assertFalse(
                    name == bad or name.startswith(bad + "."),
                    f"free_workspace가 {name}을 import한다",
                )


class TheProvidersWereNotTouchedTest(unittest.TestCase):
    """
    금지된 것을 건드리지 않았다.

    준비 상태는 Provider의 고르는 함수를 그대로 불러서 낸다 - 여기서
    따로 판정하면 화면이 "있다"고 한 것을 Provider가 못 찾는 날이 온다.
    """

    def test_it_asks_the_providers_instead_of_deciding_itself(self):
        with open(free_workspace.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("local_stock_provider.find", source)
        self.assertIn("local_voice_provider.find", source)

    def test_the_provider_modules_did_not_change(self):
        """
        두 Provider가 free_workspace를 모른다.

        알게 되는 순간 화면을 위한 결정이 엔진 쪽으로 새어 든다.
        """

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
