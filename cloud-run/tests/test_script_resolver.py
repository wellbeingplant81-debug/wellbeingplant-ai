"""
Sprint106 - Script Resolver (Epic 54, Phase 5).

파이프라인이 대본을 어디서 얻을지 정하는 자리다. step01 앞에 선다.

지켜야 할 것이 셋이다.

  AUTO는 예전과 완전히 같다.
    step01_script.run(topic, project_path)를 인자 그대로, 한 번만
    부른다. 산출물도 그 함수가 남기던 그대로다.

  IMPORT/MANUAL은 step01을 절대 부르지 않는다.
    Writer도 Gemini도 건드리지 않는다. 부르면 돈이 나가고, 사용자가
    준 대본이 아닌 다른 대본이 만들어진다.

  step01_script.py는 손대지 않는다.
    그 파일은 "AI가 대본을 쓴다"는 한 가지 일만 한다. if문이 거기
    들어가면 Writer가 Writer가 아니게 된다.
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

from app.steps import step01_script, step01_script_resolve as resolver
from app.steps.step01_script_resolve import ScriptResolveError


def _valid(title="붙여넣은 대본", scenes=2):
    return {
        "title": title,
        "hook": "훅",
        "script": "본문",
        "character": "인물",
        "scenes": [
            {
                "scene": index,
                "narration": f"{index}번 문장.",
                "image_prompt": "a middle-aged Korean man, drinking water",
            }
            for index in range(1, scenes + 1)
        ],
    }


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name

    def _place(self, payload):
        with open(
            os.path.join(self.project, "script.json"), "w", encoding="utf-8",
        ) as f:
            json.dump(payload, f, ensure_ascii=False)


class TestAutoIsUnchanged(_Case):
    """예전과 완전히 같아야 한다."""

    def test_it_calls_step01_with_the_same_arguments(self):
        with patch.object(step01_script, "run",
                          return_value={"title": "t"}) as run:
            result = resolver.run("혈관 건강", self.project)

        run.assert_called_once_with("혈관 건강", self.project)
        self.assertEqual(result, {"title": "t"})

    def test_it_calls_step01_exactly_once(self):
        with patch.object(step01_script, "run", return_value={}) as run:
            resolver.run("t", self.project)

        self.assertEqual(run.call_count, 1)

    def test_auto_is_what_a_fresh_project_resolves_to(self):
        self.assertEqual(resolver.detect_source(self.project), resolver.AUTO)

    def test_a_fresh_project_really_has_no_script(self):
        """Resolver가 출처를 판단하는 근거다 - create_project()는
        타임스탬프로 새 디렉터리를 만들고 script.json을 넣지 않는다.
        추측이 아니라 그 코드가 그렇다."""

        from app.services import project_service

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(project_service, "OUTPUT_ROOT", tmp):
                path = project_service.create_project("주제", "wellbeing")

            self.assertFalse(
                os.path.exists(os.path.join(str(path), "script.json")),
            )

    def test_an_explicit_auto_ignores_a_placed_script(self):
        """명시적으로 AUTO라고 했으면 놓여 있어도 새로 만든다."""

        self._place(_valid())

        with patch.object(step01_script, "run", return_value={"t": 1}) as run:
            resolver.run("t", self.project, source=resolver.AUTO)

        run.assert_called_once()


class TestPreparedSourcesNeverCallStep01(_Case):
    """부르면 돈이 나가고, 사용자가 준 대본이 아닌 것이 만들어진다."""

    def test_import_does_not_call_step01(self):
        self._place(_valid())

        with patch.object(step01_script, "run") as run:
            result = resolver.run("t", self.project)

        run.assert_not_called()
        self.assertEqual(result["title"], "붙여넣은 대본")

    def test_manual_does_not_call_step01(self):
        self._place(_valid("직접 쓴 대본"))

        with patch.object(step01_script, "run") as run:
            result = resolver.run("t", self.project, source=resolver.MANUAL)

        run.assert_not_called()
        self.assertEqual(result["title"], "직접 쓴 대본")

    def test_no_ai_module_is_even_imported(self):
        """script_service는 모듈을 읽는 것만으로 genai.Client를
        만든다. 미리 놓인 대본을 쓸 때는 그 비용도 내지 않는다."""

        import subprocess

        self._place(_valid())

        code = (
            "import sys, json\n"
            "from app.steps import step01_script_resolve as r\n"
            f"r.run('t', {self.project!r})\n"
            "print(len([m for m in sys.modules "
            "if m.startswith(('google.genai','vertexai'))]))\n"
        )
        # Sprint194 - 읽는 인코딩을 못 박는다.
        #
        # text=True는 PYTHONIOENCODING이 아니라 로케일로 읽는다. 이
        # 머신에서는 그 둘이 다르고(utf-8 대 cp949), 자식이 한글을 내는
        # 순간 읽는 스레드가 죽어 stdout이 None이 된다. 여기서 보는
        # 것은 마지막 줄의 "0"이라, 못 읽는 바이트가 와도 replace로
        # 넘기면 판정에는 영향이 없다.
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertEqual(result.stdout.strip().splitlines()[-1], "0")

    def test_the_placed_script_is_returned_unchanged(self):
        """자동 수정 금지 - 사용자가 준 대본을 우리가 고치면 그것은
        더 이상 사용자가 준 대본이 아니다."""

        payload = _valid()
        self._place(payload)

        result = resolver.run("t", self.project)

        self.assertEqual(result, payload)

    def test_the_file_is_not_rewritten(self):
        payload = _valid()
        self._place(payload)
        path = os.path.join(self.project, "script.json")
        before = open(path, "rb").read()

        resolver.run("t", self.project)

        self.assertEqual(open(path, "rb").read(), before)


class TestValidationOnly(_Case):
    """존재/형식/필수 필드만 본다. 내용은 다시 만들지 않는다."""

    def test_a_missing_file_fails_clearly(self):
        with self.assertRaises(ScriptResolveError) as caught:
            resolver.run("t", self.project, source=resolver.IMPORT)

        self.assertIn("script.json이 없습니다", str(caught.exception))

    def test_broken_json_fails_clearly(self):
        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            f.write("{ broken")

        with self.assertRaises(ScriptResolveError):
            resolver.run("t", self.project)

    def test_a_missing_title_is_named(self):
        self._place({"scenes": [{"scene": 1, "narration": "n",
                                 "image_prompt": "p"}]})

        with self.assertRaises(ScriptResolveError) as caught:
            resolver.run("t", self.project)

        self.assertIn("title", str(caught.exception))

    def test_no_scenes_is_named(self):
        self._place({"title": "t", "scenes": []})

        with self.assertRaises(ScriptResolveError) as caught:
            resolver.run("t", self.project)

        self.assertIn("scene", str(caught.exception))

    def test_the_fields_the_engine_reads_with_brackets_are_required(self):
        """뒤 단계가 대괄호로 꺼내는 것들이다. 없으면 KeyError로
        터지므로 여기서 먼저 잡는다.

            scene["narration"]     scene_tts_service
            scene["image_prompt"]  asset_integration_service
            scene["scene"]         step02_assets
        """

        for missing in ("scene", "narration", "image_prompt"):
            payload = _valid(scenes=1)
            del payload["scenes"][0][missing]
            self._place(payload)

            with self.subTest(missing=missing):
                with self.assertRaises(ScriptResolveError) as caught:
                    resolver.run("t", self.project)
                self.assertIn(missing, str(caught.exception))

    def test_the_failing_scene_is_named(self):
        payload = _valid(scenes=3)
        del payload["scenes"][1]["narration"]
        self._place(payload)

        with self.assertRaises(ScriptResolveError) as caught:
            resolver.run("t", self.project)

        self.assertIn("scene 2", str(caught.exception))

    def test_it_does_not_judge_quality(self):
        """품질 판단은 step07이 할 일이다. Resolver는 쓸 수 있는지만
        본다."""

        payload = _valid(scenes=1)
        payload["scenes"][0]["narration"] = "짧"
        self._place(payload)

        self.assertEqual(resolver.run("t", self.project)["title"], "붙여넣은 대본")

    def test_an_unknown_source_is_refused(self):
        with self.assertRaises(ScriptResolveError):
            resolver.run("t", self.project, source="whatever")


class TestChatImportOutputPassesTheResolver(_Case):
    """Sprint104가 만든 것을 Sprint106이 읽을 수 있어야 한다.
    두 스프린트가 다른 모양을 전제하면 붙는 순간 터진다."""

    def test_a_pasted_script_resolves(self):
        from app.production.providers.chat_import import ChatImportScriptProvider
        from app.production.stage_request import StageRequest

        raw = ('{"title":"혈관 건강","scenes":[{"narration":"첫 문장.",'
               '"subject":"a man","action":"drinking water"}]}')

        ChatImportScriptProvider().import_content(
            raw, StageRequest(project_path=self.project),
        )

        with patch.object(step01_script, "run") as run:
            result = resolver.run("혈관 건강", self.project)

        run.assert_not_called()
        self.assertEqual(result["title"], "혈관 건강")


class TestStep01WasNotTouched(unittest.TestCase):
    """"step01에 if문 추가 금지"."""

    def test_step01_has_no_branch_on_an_existing_script(self):
        tree = ast.parse(open(step01_script.__file__, encoding="utf-8").read())

        run = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )

        self.assertEqual(
            [n for n in ast.walk(run) if isinstance(n, ast.If)], [],
        )

    def test_step01_still_only_generates(self):
        """원문을 문자열로 훑지 않는다 - "import"를 찾으면 `from ...
        import ...`에 걸린다. 무엇을 부르는지는 호출식이 말한다."""

        tree = ast.parse(open(step01_script.__file__, encoding="utf-8").read())

        called = set()
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                if isinstance(target, ast.Attribute):
                    called.add(target.attr)
                elif isinstance(target, ast.Name):
                    called.add(target.id)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)

        # 여전히 Writer를 부른다.
        self.assertIn("generate_script_within_duration", called)
        # 대본을 어디서 가져올지는 모른다.
        for name in imported:
            with self.subTest(imported=name):
                self.assertNotIn("resolve", name)

    def test_the_resolver_does_not_generate(self):
        """Resolver는 어디서 가져올지만 정한다."""

        tree = ast.parse(open(resolver.__file__, encoding="utf-8").read())

        top_level = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                top_level.add(node.module or "")
            elif isinstance(node, ast.Import):
                top_level.update(a.name for a in node.names)

        for forbidden in ("step01_script", "script_service", "duration_gate",
                          "genai"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in n for n in top_level), forbidden,
                )


class TestThePipelineChangedInExactlyOnePlace(unittest.TestCase):

    def test_the_pipeline_calls_the_resolver_not_step01(self):
        import app.pipeline.pipeline as pipeline

        tree = ast.parse(open(pipeline.__file__, encoding="utf-8").read())

        called = {
            f"{node.func.value.id}.{node.func.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        }

        self.assertIn("step01_script_resolve.run", called)
        self.assertNotIn("step01_script.run", called)

    def test_the_later_steps_are_still_called_the_same_way(self):
        """step02 이후는 손대지 않는다."""

        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        for call in ("step02_asset_resolve.run(", "step03_voice_resolve.run(",
                     "step04_subtitle.run(", "step05_video.run(",
                     "step06_thumbnail.run(", "step07_quality.run("):
            with self.subTest(call=call):
                self.assertIn(call, source)

    def test_the_resolver_is_called_with_the_original_arguments(self):
        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        self.assertIn(
            "step01_script_resolve.run(\n        topic,\n        project_path,\n    )",
            source,
        )


if __name__ == "__main__":
    unittest.main()
