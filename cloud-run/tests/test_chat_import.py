"""
Sprint104 - Chat Import (Epic 54, Phase 3).

ChatGPT / Claude / Gemini / DeepSeek에서 만든 대본을 붙여넣어 그대로
쓴다. AI를 부르지 않으므로 비용이 0이다.

여기 있는 입력 모양은 실제 채팅 출력에서 나오는 것들이다 - 앞뒤에
붙는 설명 문장, 코드 펜스, 마크다운 제목, 스마트 따옴표, 후행 쉼표.
모델별 파서를 만들지 않은 이유는 이 차이들이 모델이 아니라 그날 그
대화의 성질이기 때문이다.

가장 중요한 계약은 "못 읽으면 거절한다"이다. 없는 narration을
지어내면 아무도 만들라고 하지 않은 영상이 나온다.
"""

import ast
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import source_modes, stages
from app.production.chat_script_parser import ChatImportError, parse_script
from app.production.providers import bootstrap
from app.production.providers.chat_import import (
    CHAT_IMPORT,
    ChatImportScriptProvider,
)
from app.production.registry import StageProviderRegistry
from app.production.stage_provider import StageProviderError
from app.production.stage_request import StageRequest


class TestRealChatOutputShapes(unittest.TestCase):
    """네 모델에서 실제로 나오는 모양들."""

    def test_a_json_fence_wrapped_in_prose(self):
        """"물론입니다!" 로 시작해서 "도움이 되셨길" 로 끝나는 그것."""

        raw = '''물론입니다! 요청하신 대본입니다.

```json
{"title": "혈관 건강", "hook": "훅", "script": "본문",
 "scenes": [{"scene": 1, "narration": "첫 문장.",
             "subject": "a man", "action": "drinking water"}]}
```

도움이 되셨길 바랍니다!'''

        script = parse_script(raw)

        self.assertEqual(script["title"], "혈관 건강")
        self.assertEqual(len(script["scenes"]), 1)
        self.assertEqual(script["scenes"][0]["narration"], "첫 문장.")

    def test_bare_json_without_a_fence(self):
        raw = '{"title":"제목","scenes":[{"narration":"문장."}]}'

        self.assertEqual(parse_script(raw)["title"], "제목")

    def test_korean_keys(self):
        raw = '{"제목":"당뇨 예방","훅":"훅","장면":[{"내레이션":"문장.","배경":"kitchen"}]}'

        script = parse_script(raw)

        self.assertEqual(script["title"], "당뇨 예방")
        self.assertEqual(script["hook"], "훅")
        self.assertEqual(script["scenes"][0]["environment"], "kitchen")

    def test_markdown_headings_and_bold_labels(self):
        """"## 제목:" 을 못 읽어서 Gemini 출력이 통째로 실패했었다."""

        raw = '''## 제목: 뇌 건강을 지키는 3가지

**훅:** 치매는 예방할 수 있습니다

### Scene 1
내레이션: 하루 30분 걷기부터 시작하세요.
이미지: an elderly woman walking

### Scene 2
내레이션: 대화하는 시간을 늘리세요.
'''

        script = parse_script(raw)

        self.assertEqual(script["title"], "뇌 건강을 지키는 3가지")
        self.assertEqual(script["hook"], "치매는 예방할 수 있습니다")
        self.assertEqual(len(script["scenes"]), 2)
        self.assertEqual(
            script["scenes"][0]["image_prompt"], "an elderly woman walking",
        )

    def test_plain_labels_with_unlabelled_narration_lines(self):
        """모델이 "Scene 1" 다음 줄에 대사만 적는 경우."""

        raw = '''제목: 브로콜리
본문: 설포라판이 염증을 낮춥니다.

Scene 1
브로콜리를 데치면 영양소가 살아납니다.

Scene 2
매일 한 컵이면 충분합니다.
'''

        script = parse_script(raw)

        self.assertEqual(script["title"], "브로콜리")
        self.assertEqual(script["script"], "설포라판이 염증을 낮춥니다.")
        self.assertEqual(
            script["scenes"][0]["narration"], "브로콜리를 데치면 영양소가 살아납니다.",
        )

    def test_a_scenes_array_alone_with_a_default_title(self):
        raw = '[{"narration":"첫 문장."},{"narration":"둘째 문장."}]'

        script = parse_script(raw, default_title="혈관 건강")

        self.assertEqual(script["title"], "혈관 건강")
        self.assertEqual(len(script["scenes"]), 2)

    def test_trailing_commas_and_smart_quotes(self):
        raw = '{"title": "따옴표 섞인 대본", "scenes": [{"narration": "첫 문장.",},],}'

        self.assertEqual(parse_script(raw)["title"], "따옴표 섞인 대본")

    def test_a_fence_without_a_language_tag(self):
        raw = '```\n{"title":"제목","scenes":[{"narration":"문장."}]}\n```'

        self.assertEqual(parse_script(raw)["title"], "제목")


class TestTheResultMatchesTheEngineFormat(unittest.TestCase):
    """엔진이 쓰는 그 모양이어야 뒤 단계들이 구분하지 않아도 된다."""

    def _script(self):
        return parse_script(
            '{"title":"제목","hook":"훅","script":"본문","character":"인물",'
            '"scenes":[{"narration":"문장.","subject":"a man",'
            '"action":"walking","environment":"park","camera":"close-up",'
            '"composition":"centered","lighting":"soft"}]}'
        )

    def test_the_top_level_keys_match_step01_output(self):
        self.assertEqual(
            sorted(self._script().keys()),
            sorted(["title", "hook", "script", "character", "scenes"]),
        )

    def test_the_image_prompt_is_derived_by_the_engine_function(self):
        """프롬프트를 여기서 조립하지 않는다 - 엔진의 그 함수를 쓴다."""

        from app.services import scene_prompt_service

        scene = self._script()["scenes"][0]
        expected = scene_prompt_service.derived_image_prompt(
            scene_prompt_service.scene_elements(scene),
        )

        self.assertEqual(scene["image_prompt"], expected)

    def test_scenes_are_renumbered_from_one(self):
        """모델이 0부터 세거나 건너뛰는 일이 있다. 엔진은 1부터
        이어지는 번호를 전제한다."""

        raw = ('{"title":"t","scenes":['
               '{"scene":0,"narration":"a"},'
               '{"scene":7,"narration":"b"},'
               '{"scene":9,"narration":"c"}]}')

        numbers = [s["scene"] for s in parse_script(raw)["scenes"]]

        self.assertEqual(numbers, [1, 2, 3])

    def test_a_missing_body_is_built_from_the_narrations(self):
        """script_service가 Writer에게 요구하는 정의와 같다 -
        "narration 전체를 이어붙인 내용"."""

        raw = '{"title":"t","scenes":[{"narration":"첫."},{"narration":"둘."}]}'

        self.assertEqual(parse_script(raw)["script"], "첫. 둘.")


class TestItRefusesRatherThanInventing(unittest.TestCase):
    """반쯤 읽은 결과로 영상을 만들지 않는다."""

    def test_empty_input(self):
        for raw in ("", "   ", None):
            with self.subTest(raw=raw):
                with self.assertRaises(ChatImportError):
                    parse_script(raw)

    def test_chat_small_talk_is_not_a_script(self):
        with self.assertRaises(ChatImportError) as caught:
            parse_script("안녕하세요! 무엇을 도와드릴까요?")

        self.assertIn("구조를 찾지 못했습니다", str(caught.exception))

    def test_a_missing_title_says_so(self):
        with self.assertRaises(ChatImportError) as caught:
            parse_script('{"scenes":[{"narration":"문장"}]}')

        self.assertIn("제목", str(caught.exception))

    def test_an_empty_narration_names_the_scene(self):
        with self.assertRaises(ChatImportError) as caught:
            parse_script('{"title":"t","scenes":[{"narration":"a"},{"narration":""}]}')

        self.assertIn("[2]", str(caught.exception))

    def test_no_scenes_says_so(self):
        with self.assertRaises(ChatImportError) as caught:
            parse_script('{"title":"제목만 있음"}')

        self.assertIn("scene", str(caught.exception))

    def test_every_message_is_actionable(self):
        """사람이 그 문장을 보고 다시 붙여넣을 수 있어야 한다."""

        for raw in ("", "잡담입니다", '{"scenes":[{"narration":"a"}]}',
                    '{"title":"t"}'):
            with self.subTest(raw=raw[:20]):
                try:
                    parse_script(raw)
                except ChatImportError as exc:
                    self.assertGreater(len(str(exc)), 15)


class TestNoAiIsCalled(unittest.TestCase):

    def test_the_parser_imports_nothing_but_stdlib_and_the_engine_helper(self):
        from app.production import chat_script_parser

        tree = ast.parse(open(chat_script_parser.__file__, encoding="utf-8").read())

        top_level = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                top_level.add(node.module or "")

        self.assertEqual(top_level, {"json", "re", "typing"})

    def test_no_network_module_anywhere_in_the_import_path(self):
        from app.production import chat_script_parser
        from app.production.providers import chat_import

        for module in (chat_script_parser, chat_import):
            tree = ast.parse(open(module.__file__, encoding="utf-8").read())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    with self.subTest(module=module.__name__, imported=name):
                        for banned in ("requests", "genai", "openai",
                                       "anthropic", "urllib", "httpx"):
                            self.assertNotIn(banned, name)


class TestTheProvider(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = os.path.join(self._tmp.name, "20260101_000001")

    def test_it_declares_import_only(self):
        capabilities = ChatImportScriptProvider().capabilities

        self.assertEqual(
            capabilities.supported_source_modes, (source_modes.IMPORT,),
        )
        self.assertEqual(capabilities.stage, stages.SCRIPT)

    def test_generate_is_refused(self):
        """이 Provider는 만들지 않는다. 받기만 한다."""

        with self.assertRaises(StageProviderError):
            ChatImportScriptProvider().generate(StageRequest())

    def test_it_writes_script_json_where_step01_does(self):
        raw = '{"title":"제목","scenes":[{"narration":"문장."}]}'

        ChatImportScriptProvider().import_content(
            raw, StageRequest(project_path=self.project),
        )

        path = os.path.join(self.project, "script.json")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["title"], "제목")

    def test_the_topic_fills_a_missing_title(self):
        """지어내는 것이 아니다 - 사용자가 이미 준 값이다."""

        raw = '[{"narration":"문장."}]'

        script = ChatImportScriptProvider().import_content(
            raw, StageRequest(topic="혈관 건강", project_path=self.project),
        )

        self.assertEqual(script["title"], "혈관 건강")

    def test_without_a_topic_a_missing_title_still_refuses(self):
        with self.assertRaises(ChatImportError):
            ChatImportScriptProvider().import_content(
                '[{"narration":"문장."}]', StageRequest(),
            )

    def test_it_works_without_a_request_at_all(self):
        script = ChatImportScriptProvider().import_content(
            '{"title":"제목","scenes":[{"narration":"문장."}]}',
        )

        self.assertEqual(script["title"], "제목")

    def test_a_failed_parse_writes_nothing(self):
        with self.assertRaises(ChatImportError):
            ChatImportScriptProvider().import_content(
                "잡담", StageRequest(project_path=self.project),
            )

        self.assertFalse(
            os.path.exists(os.path.join(self.project, "script.json")),
        )

    def test_the_cost_is_zero(self):
        estimate = ChatImportScriptProvider().estimate_cost(
            StageRequest(), source_modes.IMPORT,
        )

        self.assertEqual(estimate.amount, 0.0)
        self.assertTrue(estimate.free)


class TestRegistryIntegration(unittest.TestCase):

    def _registry(self):
        reg = StageProviderRegistry()
        bootstrap.register_current_providers(reg)
        return reg

    def test_both_script_providers_are_registered(self):
        names = [p.name for p in self._registry().for_stage(stages.SCRIPT)]

        self.assertIn("current", names)
        self.assertIn(CHAT_IMPORT, names)

    def test_auto_modes_never_pick_chat_import(self):
        """GENERATE를 지원하지 않으므로 select()가 먼저 거른다."""

        from app.production import production_modes
        from app.production.production_plan import build_automatic_plan

        reg = self._registry()

        for mode in (production_modes.AUTO_PREMIUM,
                     production_modes.AUTO_STANDARD,
                     production_modes.AUTO_ECONOMY):
            with self.subTest(mode=mode):
                plan = build_automatic_plan(mode, reg)
                self.assertEqual(plan.selections[stages.SCRIPT].provider, "current")

    def test_import_offers_only_chat_import(self):
        reg = self._registry()

        self.assertEqual(
            [p.name for p in reg.available(stages.SCRIPT, source_modes.IMPORT)],
            [CHAT_IMPORT],
        )

    def test_the_pipeline_still_does_not_know_about_any_of_this(self):
        import app.pipeline.pipeline as pipeline

        tree = ast.parse(open(pipeline.__file__, encoding="utf-8").read())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                with self.subTest(imported=name):
                    self.assertNotIn("app.production", name)


if __name__ == "__main__":
    unittest.main()
