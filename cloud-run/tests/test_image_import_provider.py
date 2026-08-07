"""
Sprint110 - 사용자가 만든 이미지를 쓴다 (Epic 54, Phase 9).

AI 이미지를 생성하지 않는다. 사용자가 준 파일을 엔진이 쓰는 자리에
그대로 놓는다.

출력은 step02가 만드는 것과 같은 모양이어야 한다. 다르면 뒤 단계가
"이건 어디서 온 이미지지"를 알아야 하고, 그 순간 경로가 둘이 된다.

    파일        output/{project}/images/scene{N}.png
    scene 키    asset_path / asset_type / provider / confidence

scene 수와 이미지 수가 맞지 않으면 경고한다. 고쳐 주지 않는다 -
없는 scene의 이미지를 우리가 지어낼 수는 없고, 남는 이미지를 조용히
버리면 사용자가 준 것이 사라진다.
"""

import ast
import io
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import source_modes, stages
from app.production.providers.image_import import (
    IMAGE_IMPORT,
    ImageImportProvider,
    ImageImportError,
)
from app.production.stage_provider import StageProviderError
from app.production.stage_request import StageRequest

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = os.path.join(self._tmp.name, "20260101_000001")
        os.makedirs(os.path.join(self.project, "images"))
        self.source = os.path.join(self._tmp.name, "given")
        os.makedirs(self.source)

    def _files(self, names):
        paths = []
        for name in names:
            path = os.path.join(self.source, name)
            with open(path, "wb") as f:
                f.write(PNG)
            paths.append(path)
        return paths

    def _zip(self, names):
        path = os.path.join(self._tmp.name, "images.zip")
        with zipfile.ZipFile(path, "w") as archive:
            for name in names:
                archive.writestr(name, PNG)
        return path

    def _request(self, scenes=3):
        return StageRequest(
            project_path=self.project,
            scenes=[{"scene": n, "narration": f"{n}번"} for n in range(1, scenes + 1)],
        )


class TestTheContract(unittest.TestCase):

    def test_it_supports_import_and_manual_only(self):
        capabilities = ImageImportProvider().capabilities

        self.assertEqual(
            sorted(capabilities.supported_source_modes),
            sorted([source_modes.IMPORT, source_modes.MANUAL]),
        )
        self.assertEqual(capabilities.stage, stages.IMAGE)

    def test_generate_is_refused(self):
        """AI 이미지를 만들지 않는다."""

        with self.assertRaises(StageProviderError):
            ImageImportProvider().generate(StageRequest())

    def test_the_cost_is_zero(self):
        estimate = ImageImportProvider().estimate_cost(
            StageRequest(), source_modes.MANUAL,
        )

        self.assertEqual(estimate.amount, 0.0)
        self.assertTrue(estimate.free)

    def test_it_calls_no_api(self):
        from app.production.providers import image_import

        tree = ast.parse(open(image_import.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")

        for forbidden in ("requests", "genai", "image_service",
                          "asset_integration", "step02"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(any(forbidden in n for n in names), forbidden)


class TestAcceptingFiles(_Case):

    def test_individual_files_in_order(self):
        paths = self._files(["a.png", "b.png", "c.png"])

        result = ImageImportProvider().accept_manual(paths, self._request(3))

        self.assertEqual(len(result["scenes"]), 3)
        self.assertEqual(result["warnings"], [])

    def test_a_folder(self):
        self._files(["0001.png", "0002.png", "0003.png"])

        result = ImageImportProvider().accept_manual(self.source, self._request(3))

        self.assertEqual(len(result["scenes"]), 3)

    def test_a_zip(self):
        archive = self._zip(["0001.png", "0002.png", "0003.png"])

        result = ImageImportProvider().accept_manual(archive, self._request(3))

        self.assertEqual(len(result["scenes"]), 3)

    def test_a_zip_with_a_folder_inside(self):
        archive = self._zip(["images/0001.png", "images/0002.png",
                             "images/0003.png"])

        result = ImageImportProvider().accept_manual(archive, self._request(3))

        self.assertEqual(len(result["scenes"]), 3)

    def test_import_mode_works_the_same_way(self):
        paths = self._files(["a.png", "b.png", "c.png"])

        result = ImageImportProvider().import_content(paths, self._request(3))

        self.assertEqual(len(result["scenes"]), 3)


class TestOrdering(_Case):
    """번호 순서로 scene에 붙는다 - 사람이 파일 이름으로 순서를
    정할 수 있어야 한다."""

    def test_numeric_names_sort_numerically_not_alphabetically(self):
        self._files(["2.png", "10.png", "1.png"])

        result = ImageImportProvider().accept_manual(self.source, self._request(3))

        given = [os.path.basename(s["source"]) for s in result["scenes"]]
        self.assertEqual(given, ["1.png", "2.png", "10.png"])

    def test_an_explicit_list_keeps_its_order(self):
        paths = self._files(["b.png", "a.png"])

        result = ImageImportProvider().accept_manual(paths, self._request(2))

        self.assertEqual(
            [os.path.basename(s["source"]) for s in result["scenes"]],
            ["b.png", "a.png"],
        )


class TestTheOutputMatchesTheEngine(_Case):
    """다르면 뒤 단계가 출처를 알아야 하고, 그 순간 경로가 둘이 된다."""

    def _result(self):
        self._files(["a.png", "b.png", "c.png"])
        return ImageImportProvider().accept_manual(self.source, self._request(3))

    def test_the_files_land_where_step02_puts_them(self):
        self._result()

        for number in (1, 2, 3):
            with self.subTest(scene=number):
                self.assertTrue(os.path.exists(
                    os.path.join(self.project, "images", f"scene{number}.png"),
                ))

    def test_the_scene_keys_are_the_ones_step02_writes(self):
        scene = self._result()["scenes"][0]

        for key in ("scene", "asset_path", "asset_type", "provider",
                    "confidence"):
            with self.subTest(key=key):
                self.assertIn(key, scene)

    def test_the_asset_path_is_built_the_same_way(self):
        scene = self._result()["scenes"][0]

        self.assertEqual(
            scene["asset_path"],
            os.path.join(self.project, "images", "scene1.png"),
        )

    def test_the_provider_says_where_it_came_from(self):
        scene = self._result()["scenes"][0]

        self.assertEqual(scene["asset_type"], "image")
        self.assertEqual(scene["provider"], IMAGE_IMPORT)
        self.assertEqual(scene["confidence"], 1.0)

    def test_the_original_file_is_left_alone(self):
        paths = self._files(["a.png"])
        before = open(paths[0], "rb").read()

        ImageImportProvider().accept_manual(paths, self._request(1))

        self.assertEqual(open(paths[0], "rb").read(), before)

    def test_every_format_becomes_a_png_name(self):
        """엔진은 scene{N}.png만 찾는다."""

        for name in ("a.jpg", "a.jpeg", "a.webp"):
            with self.subTest(name=name):
                path = os.path.join(self.source, name)
                with open(path, "wb") as f:
                    f.write(PNG)

                result = ImageImportProvider().accept_manual(
                    [path], self._request(1),
                )

                self.assertTrue(result["scenes"][0]["asset_path"].endswith(".png"))


class TestCountMismatchWarnsWithoutFixing(_Case):
    """고쳐 주지 않는다. 없는 이미지를 지어낼 수 없고, 남는 것을
    조용히 버리면 사용자가 준 것이 사라진다."""

    def test_too_few_images_names_the_missing_scenes(self):
        self._files(["a.png", "b.png"])

        result = ImageImportProvider().accept_manual(self.source, self._request(6))

        self.assertTrue(result["warnings"])
        self.assertIn("6", " ".join(result["warnings"]))
        self.assertEqual(len(result["scenes"]), 2)

    def test_too_many_images_says_which_are_unused(self):
        self._files(["a.png", "b.png", "c.png", "d.png"])

        result = ImageImportProvider().accept_manual(self.source, self._request(2))

        self.assertTrue(result["warnings"])
        self.assertIn("2", " ".join(result["warnings"]))
        # 남는 것을 버리지 않는다 - 놓은 것은 scene 수만큼이다.
        self.assertEqual(len(result["scenes"]), 2)

    def test_a_matching_count_has_no_warning(self):
        self._files(["a.png", "b.png", "c.png"])

        result = ImageImportProvider().accept_manual(self.source, self._request(3))

        self.assertEqual(result["warnings"], [])

    def test_the_counts_are_reported(self):
        self._files(["a.png", "b.png"])

        result = ImageImportProvider().accept_manual(self.source, self._request(5))

        self.assertEqual(result["scene_count"], 5)
        self.assertEqual(result["image_count"], 2)


class TestRefusals(_Case):

    def test_an_unsupported_format_is_refused(self):
        path = os.path.join(self.source, "a.gif")
        with open(path, "wb") as f:
            f.write(PNG)

        with self.assertRaises(ImageImportError) as caught:
            ImageImportProvider().accept_manual([path], self._request(1))

        self.assertIn("gif", str(caught.exception).lower())

    def test_no_images_at_all_is_refused(self):
        with self.assertRaises(ImageImportError):
            ImageImportProvider().accept_manual(self.source, self._request(1))

    def test_a_missing_path_is_refused(self):
        with self.assertRaises(ImageImportError):
            ImageImportProvider().accept_manual("/nope/here", self._request(1))

    def test_without_scenes_it_refuses(self):
        paths = self._files(["a.png"])

        with self.assertRaises(ValueError):
            ImageImportProvider().accept_manual(
                paths, StageRequest(project_path=self.project),
            )

    def test_a_refusal_copies_nothing(self):
        path = os.path.join(self.source, "a.gif")
        with open(path, "wb") as f:
            f.write(PNG)

        with self.assertRaises(ImageImportError):
            ImageImportProvider().accept_manual([path], self._request(1))

        self.assertEqual(os.listdir(os.path.join(self.project, "images")), [])


class TestRegistryAndPipeline(unittest.TestCase):

    def test_it_is_registered_for_the_image_stage(self):
        from app.production.providers import bootstrap
        from app.production.registry import StageProviderRegistry

        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        self.assertEqual(
            [p.name for p in registry.available(stages.IMAGE, source_modes.MANUAL)],
            [IMAGE_IMPORT],
        )
        self.assertNotIn(
            IMAGE_IMPORT,
            [p.name for p in registry.available(stages.IMAGE, source_modes.GENERATE)],
        )

    def test_step02_was_not_touched(self):
        from app.steps import step02_assets

        source = open(step02_assets.__file__, encoding="utf-8").read()

        self.assertNotIn("image_import", source)

    def test_the_pipeline_does_not_import_it(self):
        import app.pipeline.pipeline as pipeline

        tree = ast.parse(open(pipeline.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)

        for name in names:
            with self.subTest(imported=name):
                self.assertNotIn("app.production", name)


if __name__ == "__main__":
    unittest.main()
