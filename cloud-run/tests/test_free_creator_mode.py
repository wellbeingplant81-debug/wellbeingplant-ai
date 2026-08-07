"""
Sprint150 - 돈이 들지 않는 제작 (Epic 57, Phase 1).

무엇을 지키는가
---------------
    1. 폴더를 훑으면 목록이 생긴다            test_local_asset_scan
    2. scene에 맞는 것이 골라진다            test_local_asset_selected_for_scene
    3. 그 길에서 이미지 API를 부르지 않는다   test_free_mode_never_calls_image_api
    4. 무료 대본 길과 API 대본 길이 갈려 있다 test_gemini_web_provider_separate...
    5. 고른 것이 남는다                       test_provider_selection_saved

세 번째가 이 Sprint의 핵심이다. "무료"라고 해 놓고 자료를 못 찾았을 때
조용히 Imagen을 부르면 그때부터 돈이 든다 - 그 길이 없다는 것을 여기서
못으로 박는다.
"""

import ast
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.providers import local_stock_provider
from app.services import asset_integration_service, local_library
from app.services import provider_selection


def _png(path, color=(200, 30, 30)):
    """진짜 PNG를 만든다 - 빈 파일이면 복사만 되고 그림인지 모른다."""

    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (64, 48), color).save(path)


class LocalLibraryScanTest(unittest.TestCase):
    """1. 폴더를 훑으면 목록이 생긴다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_local_asset_scan(self):
        _png(os.path.join(self.root, "images", "무릎_스트레칭_01.png"))
        _png(os.path.join(self.root, "images", "허리 통증.jpg"))

        os.makedirs(os.path.join(self.root, "videos"))
        with open(os.path.join(self.root, "videos", "walking-park.mp4"),
                  "wb") as f:
            f.write(b"not a real mp4")

        os.makedirs(os.path.join(self.root, "music"))
        with open(os.path.join(self.root, "music", "calm.mp3"), "wb") as f:
            f.write(b"x")

        # 종류 밖의 폴더. 무엇으로 쓸지 알 수 없으므로 세지 않는다.
        os.makedirs(os.path.join(self.root, "etc"))
        with open(os.path.join(self.root, "etc", "메모.png"), "wb") as f:
            f.write(b"x")

        index = local_library.scan(self.root)
        counts = local_library.counts(index)

        self.assertEqual(counts["images"], 2)
        self.assertEqual(counts["videos"], 1)
        self.assertEqual(counts["music"], 1)
        self.assertEqual(counts["voice"], 0)

        paths = [item["path"] for item in index["items"]]
        self.assertNotIn(os.path.join(self.root, "etc", "메모.png"), paths)

        by_name = {item["name"]: item for item in index["items"]}

        # 파일 이름이 곧 낱말이다. 내용은 들여다보지 않는다.
        self.assertEqual(
            by_name["무릎_스트레칭_01.png"]["tags"], ["무릎", "스트레칭", "01"],
        )
        self.assertEqual(by_name["허리 통증.jpg"]["tags"], ["허리", "통증"])
        self.assertEqual(
            by_name["walking-park.mp4"]["tags"], ["walking", "park"],
        )

        # 읽을 수 있는 것은 읽는다.
        self.assertEqual(by_name["무릎_스트레칭_01.png"]["width"], 64)
        self.assertEqual(by_name["무릎_스트레칭_01.png"]["height"], 48)
        self.assertGreater(by_name["calm.mp3"]["size"], 0)

    def test_scan_touches_no_file(self):
        """훑기는 읽기다. 파일이 바뀌면 안 된다."""

        target = os.path.join(self.root, "images", "a.png")
        _png(target)

        before = (os.path.getsize(target), os.path.getmtime(target))
        local_library.scan(self.root)

        self.assertEqual(
            (os.path.getsize(target), os.path.getmtime(target)), before,
        )

    def test_missing_folder_is_not_an_error(self):
        """그림만 모아 둔 사람도 있다."""

        _png(os.path.join(self.root, "images", "a.png"))

        counts = local_library.counts(local_library.scan(self.root))

        self.assertEqual(counts["images"], 1)
        self.assertEqual(counts["videos"], 0)

    def test_load_without_scan_is_empty(self):
        """훑은 적이 없으면 비어 있다. 있는 척하지 않는다."""

        index = local_library.load(self.root)

        self.assertEqual(index["items"], [])
        self.assertIsNone(index["root"])


class LocalAssetResolverTest(unittest.TestCase):
    """2. scene의 프롬프트로 자료를 고른다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def _library(self, names, kind="images"):
        for name in names:
            path = os.path.join(self.root, kind, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)

            if kind == "images":
                _png(path)
            else:
                with open(path, "wb") as f:
                    f.write(b"x")

        local_library.save(self.project, local_library.scan(self.root))

    def test_local_asset_selected_for_scene(self):
        self._library([
            "무릎 스트레칭.png",
            "허리 통증.png",
            "주방.png",
        ])

        picked = local_stock_provider.find(
            self.project, "중년 여성이 무릎 스트레칭을 하는 장면",
        )

        self.assertIsNotNone(picked)
        self.assertEqual(picked["name"], "무릎 스트레칭.png")

    def test_more_words_matched_wins(self):
        """더 많이 겹치는 쪽이 이긴다."""

        self._library(["무릎.png", "무릎 스트레칭.png"])

        picked = local_stock_provider.find(self.project, "무릎 스트레칭")

        self.assertEqual(picked["name"], "무릎 스트레칭.png")

    def test_generate_image_copies_the_picked_file(self):
        """고른 것이 그 자리에 놓인다."""

        self._library(["무릎 스트레칭.png"])

        target = os.path.join(self.project, "images", "scene1.png")
        local_stock_provider.generate_image("무릎 스트레칭 장면", target)

        self.assertTrue(os.path.exists(target))

        source = os.path.join(self.root, "images", "무릎 스트레칭.png")
        with open(source, "rb") as a, open(target, "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_no_match_fails_and_says_why(self):
        """없으면 실패한다. 아무거나 넣지 않는다."""

        self._library(["주방.png"])

        target = os.path.join(self.project, "images", "scene1.png")

        with self.assertRaises(local_stock_provider.LocalStockUnavailable) as e:
            local_stock_provider.generate_image("무릎 스트레칭 장면", target)

        self.assertFalse(os.path.exists(target))

        # 사람이 무엇을 해야 하는지 알 수 있어야 한다.
        message = str(e.exception)
        self.assertIn("찾지 못했습니다", message)

    def test_a_broken_video_still_says_why(self):
        """
        영상이 깨져 있어도 알아볼 수 있는 말로 멈춘다.

        ffmpeg는 UTF-8로 말하는데 Windows 콘솔 기본값은 cp949다. 그
        차이 때문에 stderr를 읽다가 UnicodeDecodeError가 나면, 안내
        대신 엉뚱한 예외가 튄다 - 한국어 파일 이름을 쓰라고 권하는
        기능이 정작 한국어 앞에서 무너지는 셈이다.
        """

        path = os.path.join(self.root, "videos", "깨진 영상.mp4")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # ffmpeg가 파일 이름을 그대로 되뱉으므로 stderr에 한글이 섞인다.
        with open(path, "wb") as f:
            f.write("이건 mp4가 아니다".encode("utf-8") * 20)

        local_library.save(self.project, local_library.scan(self.root))

        target = os.path.join(self.project, "images", "scene1.png")

        with self.assertRaises(local_stock_provider.LocalStockUnavailable) as e:
            local_stock_provider.generate_image("깨진 영상", target)

        self.assertIn("첫 프레임", str(e.exception))

    def test_empty_library_says_scan_first(self):
        """훑은 적이 없으면 그 사실을 말한다."""

        target = os.path.join(self.project, "images", "scene1.png")

        with self.assertRaises(local_stock_provider.LocalStockUnavailable) as e:
            local_stock_provider.generate_image("무릎", target)

        self.assertIn("훑", str(e.exception))


class FreeModeCallsNoImageApiTest(unittest.TestCase):
    """3. 무료 모드에서는 이미지 API가 불리지 않는다.

    이 Sprint에서 가장 중요한 자리다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def _library(self, names):
        for name in names:
            _png(os.path.join(self.root, "images", name))

        local_library.save(self.project, local_library.scan(self.root))

    def test_free_mode_never_calls_image_api(self):
        """
        찾았을 때도, 못 찾았을 때도 유료 쪽은 한 번도 불리지 않는다.

        못 찾았을 때가 더 중요하다 - 그때 몰래 Imagen으로 넘어가면
        "무료"라는 말이 거짓이 된다.
        """

        self._library(["무릎 스트레칭.png"])

        scene = {
            "scene": 1,
            "image_prompt": "무릎 스트레칭 장면",
            "visual_type": "ai",
        }
        staging = os.path.join(self.project, "images", "scene1.png")

        with patch.object(
            asset_integration_service.best_of_n_service, "generate_candidates",
        ) as imagen, patch.object(
            asset_integration_service, "get_candidates",
        ) as stock, patch.object(
            asset_integration_service, "download_candidate",
        ) as download:

            # (가) 자료가 있는 경우
            result = asset_integration_service._select_ai_first(
                scene["image_prompt"], staging, "wellbeing", False,
                scene=scene, provider=provider_selection.LOCAL_STOCK,
            )

            self.assertEqual(result[0]["source"], provider_selection.LOCAL_STOCK)
            self.assertTrue(os.path.exists(staging))

            # (나) 자료가 없는 경우 - 여기서 폴백이 일어나면 안 된다
            os.remove(staging)

            with self.assertRaises(local_stock_provider.LocalStockUnavailable):
                asset_integration_service._select_ai_first(
                    "우주선이 착륙하는 장면", staging, "wellbeing", False,
                    scene={"scene": 2, "image_prompt": "우주선"},
                    provider=provider_selection.LOCAL_STOCK,
                )

            imagen.assert_not_called()
            stock.assert_not_called()
            download.assert_not_called()

        # 실패했으면 파일도 없어야 한다 - 반쯤 된 것을 남기지 않는다.
        self.assertFalse(os.path.exists(staging))

    def test_local_stock_provider_imports_no_paid_engine(self):
        """
        Provider 모듈 자체가 유료 엔진을 끌어오지 않는다.

        import만으로도 붙어 있으면 언젠가 누군가 부른다.
        """

        with open(local_stock_provider.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        imported = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        forbidden = (
            "google", "vertexai", "openai", "anthropic", "requests",
            "app.services.image_service", "app.services.best_of_n_service",
            "app.services.asset_selector",
        )

        for name in sorted(imported):
            for bad in forbidden:
                self.assertFalse(
                    name == bad or name.startswith(bad + "."),
                    f"local_stock_provider가 {name}을 import한다 - "
                    f"무료 경로에 유료 엔진이 붙는다",
                )


class FreeScriptPathIsSeparateTest(unittest.TestCase):
    """
    4. 무료 대본 길은 API 대본 길과 갈려 있다.

    Sprint150 사양은 "Gemini Web Provider - 브라우저 자동화"를 요구했다.
    만들지 않았고, 그 이유는 보고서에 적었다(약관·의존성). 무료 대본은
    이미 있는 붙여넣기 경로(chat_import)로 간다.

    그래서 이 테스트가 지키는 것은 "자동화 Provider가 있다"가 아니라
    "무료 대본 길이 API를 부르지 않으며, API Provider들과 섞이지
    않는다"이다.
    """

    def test_gemini_web_provider_separate_from_api(self):
        from app.production import source_modes
        from app.production.providers import chat_import
        from app.production.providers.generated_script import (
            GENERATED_SCRIPT_PROVIDERS,
        )

        free = chat_import.ChatImportScriptProvider()

        # (가) 붙여넣기다. 만들지 않는다 - 그래서 돈이 들지 않는다.
        self.assertIn(
            source_modes.IMPORT, free.capabilities.supported_source_modes,
        )
        self.assertNotIn(
            source_modes.GENERATE, free.capabilities.supported_source_modes,
        )

        # (나) 키가 필요 없다. API를 부르지 않기 때문이다. API 쪽은
        # 반대로 전부 키를 요구한다 - 그 차이가 곧 비용의 차이다.
        self.assertEqual(free.capabilities.required_settings, ())

        for entry in GENERATED_SCRIPT_PROVIDERS:
            self.assertTrue(
                entry[3], f"{entry[0]}에 필요한 키가 비어 있다",
            )

        # (다) API 쪽 이름과 겹치지 않는다.
        api_names = {entry[0] for entry in GENERATED_SCRIPT_PROVIDERS}

        self.assertNotIn(free.capabilities.name, api_names)
        self.assertEqual(
            api_names, {"gemini", "claude", "openai", "deepseek"},
        )

        # (라) 그 모듈은 어떤 API 사업자 모듈도 끌어오지 않는다.
        with open(chat_import.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            names = []

            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]

            for name in names:
                for bad in ("google", "openai", "anthropic", "vertexai"):
                    self.assertFalse(
                        name == bad or name.startswith(bad + "."),
                        f"chat_import가 {name}을 import한다",
                    )

    def test_free_script_provider_is_not_a_browser_robot(self):
        """
        만들지 않은 것을 만든 척하지 않는다.

        브라우저 자동화 Provider는 이 저장소에 없다. 있는 척하는 자리가
        생기면 사람이 눌러 보고 아무 일도 일어나지 않는다.
        """

        providers_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "providers",
        )

        self.assertFalse(
            os.path.exists(
                os.path.join(providers_dir, "gemini_web_provider.py")
            ),
            "브라우저 자동화 Provider가 생겼다면 Sprint 보고서와 다르다",
        )


class ProviderSelectionSavedTest(unittest.TestCase):
    """5. 고른 것이 프로젝트에 남는다."""

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"topic": "무릎 통증"}, f)

    def test_provider_selection_saved(self):
        provider_selection.save(self.project, {"image": "local_stock"})

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["image_provider"], "local_stock")

        # 다시 읽어도 같다 - 파일이 근거다.
        self.assertEqual(
            provider_selection.selected(self.project, "image"), "local_stock",
        )
        self.assertEqual(
            provider_selection.all_selected(self.project)["image"],
            "local_stock",
        )

        # 다른 단계는 건드리지 않는다.
        self.assertNotIn("script_provider", saved)
        self.assertEqual(saved["topic"], "무릎 통증")

    def test_local_stock_is_a_wired_choice(self):
        """고를 수 있는 것으로 등록돼 있다 - 거절당하지 않는다."""

        self.assertIn("local_stock", provider_selection.WIRED["image"])

        provider_selection.require_wired("image", "local_stock")

    def test_registry_and_bridge_point_at_the_same_module(self):
        """
        등록소가 말하는 모듈과 다리가 실제로 부르는 모듈이 같다.

        갈라지면 화면이 말하는 것과 실제로 도는 것이 달라진다.
        """

        from app.production.providers.generated_image import (
            GENERATED_IMAGE_PROVIDERS,
        )

        registry = {entry[0]: entry[4] for entry in GENERATED_IMAGE_PROVIDERS}

        self.assertEqual(
            registry["local_stock"],
            asset_integration_service.SINGLE_IMAGE_PROVIDERS["local_stock"],
        )


if __name__ == "__main__":
    unittest.main()
