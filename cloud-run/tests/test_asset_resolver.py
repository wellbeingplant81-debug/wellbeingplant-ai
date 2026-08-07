"""
Sprint111 - Asset Resolver (Epic 54, Phase 10).

step02 앞에 선다. Sprint106의 Script Resolver와 같은 자리, 같은 원칙이다.

step02_assets.py는 손대지 않는다. 그 파일은 "AI가 이미지를 구해 온다"는
한 가지 일만 하고, 사용자가 놓아 둔 이미지를 쓸지 말지는 그 파일이
알 바가 아니다.

Resolver는 만들지 않는다 - 있는지 보고, 쓸 수 있는지 확인하고, 어느
쪽을 쓸지 고르는 데까지다. 이미지를 만들지도 고치지도 변환하지도
않는다.

장수가 모자라면 거절한다. WARN으로 넘기면 그 scene은 렌더에서
파일을 못 찾아 실패하고, 그때는 이미 이미지 값과 TTS 값을 다 쓴
뒤다 - 여기서 멈추는 편이 훨씬 싸다. 남는 장수는 경고만 한다.
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

from app.steps import step02_asset_resolve as resolver
from app.steps import step02_assets
from app.steps.step02_asset_resolve import AssetResolveError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _scenes(count=3):
    return [
        {"scene": n, "narration": f"{n}번", "image_prompt": "a man"}
        for n in range(1, count + 1)
    ]


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name
        os.makedirs(os.path.join(self.project, "images"))

    def _place(self, numbers):
        for number in numbers:
            with open(
                os.path.join(self.project, "images", f"scene{number}.png"), "wb",
            ) as f:
                f.write(PNG)

    def _mark(self, source):
        with open(
            os.path.join(self.project, "project.json"), "w", encoding="utf-8",
        ) as f:
            json.dump({"project_id": "p", "image_source": source}, f)


class TestAutoIsUnchanged(_Case):
    """예전과 완전히 같아야 한다."""

    def test_it_calls_step02_with_the_same_arguments(self):
        scenes = _scenes()

        with patch.object(step02_assets, "collect_assets",
                          return_value=scenes) as collect:
            result = resolver.run(scenes, self.project, "foodbeat")

        collect.assert_called_once_with(scenes, self.project, "foodbeat")
        self.assertIs(result, scenes)

    def test_it_calls_step02_exactly_once(self):
        with patch.object(step02_assets, "collect_assets",
                          return_value=[]) as collect:
            resolver.run(_scenes(), self.project, "wellbeing")

        self.assertEqual(collect.call_count, 1)

    def test_an_empty_images_folder_means_auto(self):
        """create_project()는 images/를 비운 채로 만든다."""

        self.assertEqual(resolver.detect_source(self.project), resolver.AUTO)

    def test_an_explicit_auto_ignores_placed_images(self):
        self._place([1, 2, 3])

        with patch.object(step02_assets, "collect_assets",
                          return_value=[]) as collect:
            resolver.run(_scenes(), self.project, "wellbeing",
                         source=resolver.AUTO)

        collect.assert_called_once()


class TestPlacedImagesSkipStep02(_Case):

    def test_step02_is_not_called(self):
        self._place([1, 2, 3])

        with patch.object(step02_assets, "collect_assets") as collect:
            result = resolver.run(_scenes(), self.project, "wellbeing")

        collect.assert_not_called()
        self.assertEqual(len(result), 3)

    def test_the_scene_keys_match_what_step02_writes(self):
        self._place([1, 2, 3])

        scene = resolver.run(_scenes(), self.project, "wellbeing")[0]

        for key in ("asset_path", "asset_type", "provider", "confidence"):
            with self.subTest(key=key):
                self.assertIn(key, scene)

        self.assertEqual(
            scene["asset_path"],
            os.path.join(self.project, "images", "scene1.png"),
        )
        self.assertEqual(scene["asset_type"], "image")

    def test_the_original_scene_fields_survive(self):
        self._place([1, 2, 3])

        scene = resolver.run(_scenes(), self.project, "wellbeing")[0]

        self.assertEqual(scene["narration"], "1번")
        self.assertEqual(scene["image_prompt"], "a man")

    def test_the_input_scenes_are_not_mutated(self):
        import copy

        self._place([1, 2, 3])
        scenes = _scenes()
        before = copy.deepcopy(scenes)

        resolver.run(scenes, self.project, "wellbeing")

        self.assertEqual(scenes, before)

    def test_the_image_files_are_left_alone(self):
        self._place([1, 2, 3])
        path = os.path.join(self.project, "images", "scene1.png")
        before = open(path, "rb").read()

        resolver.run(_scenes(), self.project, "wellbeing")

        self.assertEqual(open(path, "rb").read(), before)

    def test_no_ai_module_is_imported(self):
        """step02_assets는 읽는 것만으로 265개 모듈을 끌고 온다."""

        import subprocess

        self._place([1, 2, 3])

        code = (
            "import sys, json\n"
            "from app.steps import step02_asset_resolve as r\n"
            "scenes=[{'scene':n,'narration':'n','image_prompt':'p'} "
            "for n in (1,2,3)]\n"
            f"r.run(scenes, {self.project!r}, 'wellbeing')\n"
            "print(len([m for m in sys.modules "
            "if m.startswith(('google.genai','vertexai','moviepy'))]))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertEqual(result.stdout.strip().splitlines()[-1], "0")


class TestSourceIsRecordedNotGuessed(_Case):

    def test_the_marked_source_wins_over_disk(self):
        self._mark("manual")

        self.assertEqual(resolver.detect_source(self.project), "manual")

    def test_disk_is_the_fallback(self):
        self._place([1])

        self.assertEqual(resolver.detect_source(self.project), resolver.IMPORT)

    def test_an_explicit_argument_wins_over_everything(self):
        self._mark("import")
        self._place([1, 2, 3])

        with patch.object(step02_assets, "collect_assets",
                          return_value=[]) as collect:
            resolver.run(_scenes(), self.project, "wellbeing",
                         source=resolver.AUTO)

        collect.assert_called_once()

    def test_an_unknown_source_is_refused(self):
        with self.assertRaises(AssetResolveError):
            resolver.run(_scenes(), self.project, "wellbeing", source="whatever")


class TestCountMismatch(_Case):
    """자동 수정 금지."""

    def test_too_few_images_refuses_before_burning_more_budget(self):
        """WARN으로 넘기면 렌더에서 파일을 못 찾아 실패하고, 그때는
        이미 TTS 값을 다 쓴 뒤다."""

        self._place([1, 2])

        with self.assertRaises(AssetResolveError) as caught:
            resolver.run(_scenes(6), self.project, "wellbeing")

        message = str(caught.exception)
        self.assertIn("3", message)
        self.assertIn("6", message)

    def test_extra_images_only_warn(self):
        self._place([1, 2, 3, 4, 5])

        result = resolver.run(_scenes(3), self.project, "wellbeing")

        self.assertEqual(len(result), 3)

    def test_a_gap_in_the_middle_is_named(self):
        self._place([1, 3])

        with self.assertRaises(AssetResolveError) as caught:
            resolver.run(_scenes(3), self.project, "wellbeing")

        self.assertIn("2", str(caught.exception))

    def test_nothing_is_created_to_fill_the_gap(self):
        self._place([1])

        with self.assertRaises(AssetResolveError):
            resolver.run(_scenes(3), self.project, "wellbeing")

        self.assertEqual(
            sorted(os.listdir(os.path.join(self.project, "images"))),
            ["scene1.png"],
        )


class TestStep02WasNotTouched(unittest.TestCase):
    """"step02 안에 if IMPORT 같은 분기 넣지 말 것"."""

    def test_step02_has_no_branch_on_existing_images(self):
        tree = ast.parse(open(step02_assets.__file__, encoding="utf-8").read())

        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)

        for name in names:
            with self.subTest(imported=name):
                self.assertNotIn("resolve", name)
                self.assertNotIn("image_import", name)

    def test_the_resolver_does_not_produce_images(self):
        tree = ast.parse(open(resolver.__file__, encoding="utf-8").read())

        top_level = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                top_level.add(node.module or "")
            elif isinstance(node, ast.Import):
                top_level.update(a.name for a in node.names)

        for forbidden in ("step02_assets", "image_service",
                          "asset_integration", "genai", "app.production"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in n for n in top_level), forbidden,
                )

    def test_it_agrees_with_the_provider_that_placed_the_files(self):
        """import하지 않는 대신 여기서 잠근다.

        Provider가 놓는 자리와 Resolver가 찾는 자리가 갈라지면 준
        이미지를 못 찾는다. 런타임 의존을 만들지 않고 어긋남만
        막는다 - 테스트는 경계를 넘어도 된다."""

        from app.production.providers import image_import

        for name in ("IMAGES_DIRNAME", "SCENE_FILENAME", "CONFIDENCE"):
            with self.subTest(constant=name):
                self.assertEqual(
                    getattr(resolver, name), getattr(image_import, name),
                )

        self.assertEqual(resolver.IMAGE_IMPORT, image_import.IMAGE_IMPORT)

    def test_it_writes_no_image(self):
        tree = ast.parse(open(resolver.__file__, encoding="utf-8").read())

        called = {
            node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
        }

        for forbidden in ("copyfile", "copyfileobj", "move", "write"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, called)


class TestThePipelineChangedInOnePlace(unittest.TestCase):

    def test_the_pipeline_calls_the_resolver_not_step02(self):
        import app.pipeline.pipeline as pipeline

        tree = ast.parse(open(pipeline.__file__, encoding="utf-8").read())

        called = {
            f"{node.func.value.id}.{node.func.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        }

        self.assertIn("step02_asset_resolve.run", called)
        self.assertNotIn("step02_assets.collect_assets", called)

    def test_the_later_steps_are_untouched(self):
        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        for call in ("step03_voice_resolve.run(", "step04_subtitle.run(",
                     "step05_video.run(", "step06_thumbnail.run(",
                     "step07_quality.run("):
            with self.subTest(call=call):
                self.assertIn(call, source)


if __name__ == "__main__":
    unittest.main()
