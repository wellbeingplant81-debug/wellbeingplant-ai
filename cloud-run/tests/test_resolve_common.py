"""
Sprint114 - Resolver들이 공유하는 어휘 (Epic 54, Phase 13).

Sprint113 보고서의 결론을 그대로 실행한다. 세 Resolver에서 같은 것은
*데이터와 얕은 골격*이고, 다른 것은 *각 단계의 본질*이다.

그래서 꺼내는 것은 상태 없는 함수뿐이다. 클래스도 상속도 만들지
않는다 - 03의 폴백과 조립을 담으려면 훅이 두세 개 더 생기고, 그
훅은 01과 02에서 비어 있게 된다. 상속으로 빈칸을 만드는 구조다.

각 Resolver는 자기 시그니처, 자기 반환값, 자기 판정을 계속 소유한다.
여기서 얻는 것은 코드 줄 수가 아니라 어휘와 우선순위가 갈라지지
않는다는 보장이다.
"""

import ast
import inspect
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.steps import resolve_common
from app.steps import step01_script_resolve as script
from app.steps import step02_asset_resolve as asset
from app.steps import step03_voice_resolve as voice

RESOLVERS = (script, asset, voice)


class TestItIsNotAFramework(unittest.TestCase):
    """StageResolver / BaseResolver / 상속 금지."""

    def test_the_common_module_defines_no_class(self):
        tree = ast.parse(open(resolve_common.__file__, encoding="utf-8").read())

        self.assertEqual(
            [n.name for n in tree.body if isinstance(n, ast.ClassDef)], [],
        )

    def test_no_resolver_defines_a_base_class(self):
        for module in RESOLVERS:
            tree = ast.parse(open(module.__file__, encoding="utf-8").read())
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                with self.subTest(module=module.__name__, cls=node.name):
                    # 예외 클래스 하나씩만 있고, 그것은 ValueError를
                    # 상속한다 - Resolver끼리 상속하지 않는다.
                    bases = [
                        b.id for b in node.bases if isinstance(b, ast.Name)
                    ]
                    self.assertEqual(bases, ["ValueError"])

    def test_the_forbidden_names_are_never_defined_or_used(self):
        """산문이 아니라 코드를 본다.

        "StageResolver를 만들지 않는다"라고 적어 둔 문장까지 걸면
        설명을 지워야 통과하는 테스트가 된다."""

        import pathlib

        forbidden = ("StageResolver", "BaseResolver", "AbstractResolver",
                     "Mixin", "Interface")
        root = pathlib.Path(resolve_common.__file__).parent

        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))

            used = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    used.add(node.name)
                elif isinstance(node, ast.Name):
                    used.add(node.id)
                elif isinstance(node, ast.Attribute):
                    used.add(node.attr)
                elif isinstance(node, ast.alias):
                    used.add(node.asname or node.name)

            for name in forbidden:
                with self.subTest(file=path.name, forbidden=name):
                    self.assertFalse(
                        any(name in u for u in used), f"{path.name}: {name}",
                    )

    def test_it_holds_no_state(self):
        """상태 없는 함수만. 모듈 변수는 전부 불변이어야 한다."""

        for name, value in vars(resolve_common).items():
            if name.startswith("__") or callable(value):
                continue
            if inspect.ismodule(value):
                continue
            with self.subTest(name=name):
                self.assertIsInstance(value, (str, tuple, frozenset, int))


class TestTheSharedVocabulary(unittest.TestCase):

    def test_every_resolver_uses_the_same_objects(self):
        """값이 같은 것으로는 부족하다 - 같은 것을 봐야 갈라지지 않는다."""

        for module in RESOLVERS:
            with self.subTest(module=module.__name__):
                self.assertIs(module.AUTO, resolve_common.AUTO)
                self.assertIs(module.IMPORT, resolve_common.IMPORT)
                self.assertIs(module.MANUAL, resolve_common.MANUAL)
                self.assertIs(module.SOURCES, resolve_common.SOURCES)
                self.assertIs(
                    module.PREPARED_SOURCES, resolve_common.PREPARED_SOURCES,
                )

    def test_the_values_did_not_change(self):
        self.assertEqual(resolve_common.AUTO, "auto")
        self.assertEqual(resolve_common.IMPORT, "import")
        self.assertEqual(resolve_common.MANUAL, "manual")
        self.assertEqual(
            resolve_common.SOURCES, ("auto", "import", "manual"),
        )
        self.assertEqual(
            resolve_common.PREPARED_SOURCES, ("import", "manual"),
        )

    def test_each_resolver_still_owns_its_metadata_field(self):
        fields = {m.SOURCE_FIELD for m in RESOLVERS}

        self.assertEqual(
            sorted(fields),
            ["image_source", "production_source", "voice_source"],
        )


class TestSourceFromMetadata(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name

    def _write(self, payload):
        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump(payload, f)

    def test_it_reads_the_named_field(self):
        self._write({"voice_source": "manual", "image_source": "import"})

        self.assertEqual(
            resolve_common.source_from_metadata(self.project, "voice_source"),
            "manual",
        )
        self.assertEqual(
            resolve_common.source_from_metadata(self.project, "image_source"),
            "import",
        )

    def test_a_missing_file_is_not_an_error(self):
        self.assertIsNone(
            resolve_common.source_from_metadata(self.project, "voice_source"),
        )

    def test_an_unreadable_file_is_not_an_error(self):
        """읽을 수 없는 project.json 때문에 제작이 멈추지는 않는다."""

        with open(os.path.join(self.project, "project.json"), "w") as f:
            f.write("{not json")

        self.assertIsNone(
            resolve_common.source_from_metadata(self.project, "voice_source"),
        )

    def test_a_non_object_json_is_not_an_error(self):
        """step01이 isinstance로 막아 두던 경우다."""

        with open(os.path.join(self.project, "project.json"), "w") as f:
            f.write("[1, 2, 3]")

        self.assertIsNone(
            resolve_common.source_from_metadata(self.project, "voice_source"),
        )

    def test_an_unknown_value_is_ignored(self):
        self._write({"voice_source": "whatever"})

        self.assertIsNone(
            resolve_common.source_from_metadata(self.project, "voice_source"),
        )

    def test_a_missing_field_is_ignored(self):
        self._write({"project_id": "p"})

        self.assertIsNone(
            resolve_common.source_from_metadata(self.project, "voice_source"),
        )


class TestResolveSource(unittest.TestCase):
    """적힌 것 > 디스크 > AUTO. 세 Resolver가 같은 우선순위를 쓴다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name

    def _write(self, payload):
        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump(payload, f)

    def test_the_recorded_value_wins_over_disk(self):
        self._write({"voice_source": "manual"})

        self.assertEqual(
            resolve_common.resolve_source(
                self.project, "voice_source", lambda: True,
            ),
            "manual",
        )

    def test_disk_is_the_fallback(self):
        self.assertEqual(
            resolve_common.resolve_source(
                self.project, "voice_source", lambda: True,
            ),
            resolve_common.IMPORT,
        )

    def test_nothing_placed_means_auto(self):
        self.assertEqual(
            resolve_common.resolve_source(
                self.project, "voice_source", lambda: False,
            ),
            resolve_common.AUTO,
        )

    def test_the_disk_check_is_not_run_when_it_is_recorded(self):
        """적혀 있으면 디스크를 볼 이유가 없다."""

        self._write({"voice_source": "auto"})
        looked = []

        resolve_common.resolve_source(
            self.project, "voice_source",
            lambda: looked.append(True) or True,
        )

        self.assertEqual(looked, [])


class TestNumberedFiles(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = self._tmp.name

    def _touch(self, name):
        with open(os.path.join(self.directory, name), "wb") as f:
            f.write(b"x")

    def test_it_returns_the_numbers_that_exist(self):
        for name in ("scene1.png", "scene3.png"):
            self._touch(name)

        self.assertEqual(
            resolve_common.numbered_files(self.directory, "scene{number}.png"),
            [1, 3],
        )

    def test_the_numbers_are_sorted_numerically(self):
        for name in ("scene10.png", "scene2.png", "scene1.png"):
            self._touch(name)

        self.assertEqual(
            resolve_common.numbered_files(self.directory, "scene{number}.png"),
            [1, 2, 10],
        )

    def test_the_pattern_decides_what_counts(self):
        self._touch("scene1.png")
        self._touch("scene1.wav")

        self.assertEqual(
            resolve_common.numbered_files(self.directory, "scene{number}.wav"),
            [1],
        )

    def test_non_numbered_names_are_ignored(self):
        for name in ("scene.png", "sceneA.png", "voice.png"):
            self._touch(name)

        self.assertEqual(
            resolve_common.numbered_files(self.directory, "scene{number}.png"),
            [],
        )

    def test_a_missing_directory_is_not_an_error(self):
        self.assertEqual(
            resolve_common.numbered_files(
                os.path.join(self.directory, "nope"), "scene{number}.png",
            ),
            [],
        )


class TestTheResolversStayDifferent(unittest.TestCase):
    """run()은 공통화하지 않는다."""

    def test_the_signatures_are_unchanged(self):
        self.assertEqual(
            str(inspect.signature(script.run)),
            "(topic: str, project_path: str, source: str = None) -> dict",
        )
        self.assertEqual(
            str(inspect.signature(asset.run)),
            "(scenes, project_path, channel, source=None)",
        )
        self.assertEqual(
            str(inspect.signature(voice.run)),
            "(scenes, project_path, source=None)",
        )

    def test_each_run_is_still_its_own(self):
        dumps = []
        for module in RESOLVERS:
            source = open(module.__file__, encoding="utf-8").read()
            for node in ast.parse(source).body:
                if isinstance(node, ast.FunctionDef) and node.name == "run":
                    dumps.append(ast.dump(ast.parse(ast.unparse(node))))

        self.assertEqual(len(dumps), 3)
        self.assertEqual(len(set(dumps)), 3)

    def test_no_resolver_imports_another(self):
        names = {m.__name__.rsplit(".", 1)[-1] for m in RESOLVERS}

        for module in RESOLVERS:
            tree = ast.parse(open(module.__file__, encoding="utf-8").read())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    imported.update(a.name for a in node.names)
                elif isinstance(node, ast.Import):
                    imported.update(a.name for a in node.names)

            for other in names - {module.__name__.rsplit(".", 1)[-1]}:
                with self.subTest(module=module.__name__, other=other):
                    self.assertNotIn(other, imported)

    def test_each_resolver_keeps_its_own_error_type(self):
        types = {
            script.ScriptResolveError,
            asset.AssetResolveError,
            voice.VoiceResolveError,
        }

        self.assertEqual(len(types), 3)


class TestTheEngineStepsWereNotTouched(unittest.TestCase):
    """공통화는 Resolver들 사이의 일이다 - 엔진은 모른다."""

    def test_no_engine_step_knows_the_common_module(self):
        from app.steps import step01_script, step02_assets, step03_tts

        for module in (step01_script, step02_assets, step03_tts):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("resolve_common", source)
                self.assertNotIn("resolve", source.split('"""')[-1])

    def test_the_pipeline_still_calls_the_three_resolvers(self):
        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        for call in ("step01_script_resolve.run(",
                     "step02_asset_resolve.run(",
                     "step03_voice_resolve.run("):
            with self.subTest(call=call):
                self.assertIn(call, source)

        self.assertNotIn("resolve_common", source)


if __name__ == "__main__":
    unittest.main()
