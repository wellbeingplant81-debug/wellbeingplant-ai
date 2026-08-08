"""
Sprint156 - 잘못 고른 것을 잘못 골랐다고 말한다 (Epic 57, Phase 7).

Sprint155 실측에서 드러난 것
----------------------------
한국어 대본의 image_prompt는 요소를 이어 붙인 것이다.

    "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광"

extract_search_query는 Pexels 검색용이라 영문·숫자만 남긴다. 그래서
위 프롬프트에서 남는 것은 "40" 하나뿐이었고, Scene이 몇 개든 전부
같은 낱말을 찾았다. 파일 하나("40.png")를 넣으면 세 Scene이 모두
같은 그림이 되는데, 화면은 "이미지 3/3 준비 완료"라고 말했다.

Sprint150이 한국어 폴백을 만들어 두긴 했다. 다만 조건이 "낱말이
하나도 없을 때"라, 숫자 한 조각만 나와도 열리지 않았다.

무엇을 지키는가
---------------
    1. 한국어 프롬프트에서 낱말이 나온다
                              test_korean_prompt_extracts_keywords
    2. 숫자만인 토큰은 낱말로 치지 않는다
                              test_numeric_token_is_not_keyword
    3. 여러 Scene이 같은 파일을 쓰면 말한다
                              test_duplicate_asset_warning
    4. 그래도 만들 수는 있다    test_same_asset_can_still_render
    5. 그 길에서 밖으로 안 나간다
                              test_free_mode_no_external_provider

넷째가 경계다. 같은 그림을 쓰는 것이 틀린 것은 아니다 - 사람이
일부러 그렇게 할 수도 있다. 우리가 막을 일이 아니라 말할 일이다.
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

from app.providers import local_stock_provider
from app.services import free_workspace, local_library, scene_order


def _png(path, color=(200, 30, 30)):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (64, 64), color).save(path)


def _tone(path, seconds=0.3):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", path],
        capture_output=True, check=True,
    )


class KoreanKeywordTest(unittest.TestCase):
    """1·2. 한국어에서 낱말이 나온다. 숫자는 낱말이 아니다."""

    def test_korean_prompt_extracts_keywords(self):
        """
        Sprint155에서 ['40']만 나오던 그 프롬프트다.

        요소를 이어 붙인 한국어 프롬프트에서 실제 낱말이 나와야
        Scene마다 다른 그림이 걸린다.
        """

        prompt = "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광"

        words = local_stock_provider._keywords(prompt)

        for word in ("무릎", "스트레칭", "거실"):
            with self.subTest(word=word):
                self.assertIn(word, words)

        # 숫자 하나만 남는 일은 이제 없다.
        self.assertNotEqual(words, ["40"])

    def test_different_scenes_get_different_keywords(self):
        """
        이것이 Sprint155에서 무너져 있던 것이다.

        세 Scene의 낱말이 같으면 같은 파일이 셋 다 걸린다.
        """

        prompts = [
            "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광",
            "40대 남성, 허리 세우기, 거실, 미디엄, 중앙, 자연광",
            "40대 남성, 공원 산책, 공원, 와이드, 중앙, 자연광",
        ]

        found = [set(local_stock_provider._keywords(p)) for p in prompts]

        for index, words in enumerate(found):
            for other in found[index + 1:]:
                with self.subTest(index=index):
                    self.assertNotEqual(words, other)

    def test_numeric_token_is_not_keyword(self):
        """
        숫자만인 토큰으로는 무엇도 고를 수 없다.

        "40"이나 "2026"은 그림의 내용을 가리키지 않는다. 그것 하나로
        고르면 아무 파일이나 걸린다.
        """

        for prompt in ("40", "2026", "40 2026", "  2026  "):
            with self.subTest(prompt=prompt):
                words = local_stock_provider._keywords(prompt)

                self.assertEqual(
                    [w for w in words if w.isdigit()], [],
                    f"{prompt!r}에서 숫자가 낱말로 남았다: {words}",
                )

    def test_an_english_prompt_still_works_the_same(self):
        """
        영문 프롬프트의 동작을 바꾸지 않는다.

        Sprint150부터 돌던 길이다 - 한국어를 고치면서 그쪽을 망가뜨리면
        안 된다.
        """

        words = local_stock_provider._keywords(
            "a woman stretching her knee in a bright living room")

        for word in ("woman", "stretching", "knee"):
            with self.subTest(word=word):
                self.assertIn(word, words)

        # 불용어는 여전히 빠진다.
        for word in ("a", "her", "in"):
            with self.subTest(word=word):
                self.assertNotIn(word, words)

    def test_a_prompt_with_nothing_usable_gives_nothing(self):
        """
        쓸 낱말이 없으면 빈 목록이다.

        억지로 무언가를 내놓으면 아무 파일이나 걸린다.
        """

        for prompt in ("", "   ", "40", "2026", "!!! ,,, ..."):
            with self.subTest(prompt=prompt):
                self.assertEqual(local_stock_provider._keywords(prompt), [])

    def test_the_extractor_itself_was_not_changed(self):
        """
        Pexels 검색이 쓰는 그 추출기는 그대로다.

        영문·숫자만 남기는 것은 그쪽에서는 맞는 동작이다 - 여기서
        고치면 스톡 검색이 한국어를 그대로 보내게 된다.
        """

        from app.services.search_query_extractor import extract_search_query

        self.assertEqual(
            extract_search_query("40대 남성, 무릎 스트레칭"), "40")


class DuplicateAssetTest(unittest.TestCase):
    """3. 여러 Scene이 같은 파일을 쓰면 말한다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def _scan(self):
        local_library.save(self.project, local_library.scan(self.root))

    def _scenes(self, prompts):
        return [
            {"scene": n, "narration": f"{n}번 문장", "image_prompt": prompt}
            for n, prompt in enumerate(prompts, start=1)
        ]

    def test_duplicate_asset_warning(self):
        """
        한 파일이 세 Scene에 걸리면 그 사실을 적는다.

        Sprint155에서는 조용히 넘어갔다 - 화면은 "3/3 준비 완료"라고만
        했고, 사람은 렌더가 끝난 뒤에야 같은 그림 셋을 봤다.
        """

        # 셋 다 "남성"이 들어간 프롬프트. 파일은 하나뿐이다.
        _png(os.path.join(self.root, "images", "남성.png"))

        for n in (1, 2, 3):
            _tone(os.path.join(self.root, "voices", f"scene{n}.wav"))

        self._scan()

        scenes = self._scenes([
            "남성, 무릎 스트레칭", "남성, 허리 세우기", "남성, 공원 산책",
        ])

        report = free_workspace.preparation(self.project, scenes)

        # 준비는 됐다. 없는 것이 아니다.
        self.assertEqual(report["ready"]["images"], 3)
        self.assertEqual(report["missing"], [])

        # 그러나 검토가 필요하다.
        self.assertTrue(report["review"])

        message = " ".join(report["review"])

        self.assertIn("3개 Scene", message)
        self.assertIn("남성.png", message)

        # 어느 Scene들인지 줄마다 알 수 있다.
        rows = {row["scene"]: row for row in report["scenes"]}

        self.assertEqual(rows[1]["image"]["shared_with"], [2, 3])
        self.assertEqual(rows[2]["image"]["shared_with"], [1, 3])

    def test_distinct_files_raise_no_warning(self):
        """서로 다른 그림이면 아무 말도 하지 않는다."""

        for name in ("무릎 스트레칭.png", "허리 세우기.png", "공원 산책.png"):
            _png(os.path.join(self.root, "images", name))

        for n in (1, 2, 3):
            _tone(os.path.join(self.root, "voices", f"scene{n}.wav"))

        self._scan()

        report = free_workspace.preparation(self.project, self._scenes([
            "무릎 스트레칭", "허리 세우기", "공원 산책",
        ]))

        self.assertEqual(report["review"], [])

        for row in report["scenes"]:
            with self.subTest(scene=row["scene"]):
                self.assertEqual(row["image"]["shared_with"], [])

    def test_two_scenes_sharing_is_reported_too(self):
        """셋이 아니라 둘이어도 말한다."""

        _png(os.path.join(self.root, "images", "거실.png"))
        _png(os.path.join(self.root, "images", "공원 산책.png"))

        for n in (1, 2, 3):
            _tone(os.path.join(self.root, "voices", f"scene{n}.wav"))

        self._scan()

        report = free_workspace.preparation(self.project, self._scenes([
            "거실", "거실", "공원 산책",
        ]))

        message = " ".join(report["review"])

        self.assertIn("2개 Scene", message)
        self.assertIn("거실.png", message)

    def test_a_scene_made_already_is_not_counted_as_shared(self):
        """
        이미 만들어 둔 파일은 Scene마다 제 것이다.

        scene1.png과 scene2.png은 이름이 다르므로 겹칠 수가 없다.
        """

        for n in (1, 2):
            _png(os.path.join(self.project, "images", f"scene{n}.png"))
            _tone(os.path.join(self.project, "audio", "scenes",
                               f"scene{n}.wav"))

        self._scan()

        report = free_workspace.preparation(
            self.project, self._scenes(["가", "나"]))

        self.assertEqual(report["review"], [])

    def test_the_state_says_which_of_the_three(self):
        """
        준비 완료 / 검토 필요 / 부족 - 셋을 구분한다.

        검토 필요를 부족으로 처리하면 자동 실패가 된다. 그것은 사람이
        정할 일이다.
        """

        # 파일이 하나뿐이라 둘 다 그것을 쓴다.
        _png(os.path.join(self.root, "images", "운동.png"))
        self._scan()

        scenes = self._scenes(["무릎 운동", "허리 운동"])
        report = free_workspace.preparation(self.project, scenes)

        # 음성이 없으니 아직 부족이다.
        self.assertEqual(report["state"], "missing")

        for n in (1, 2):
            _tone(os.path.join(self.root, "voices", f"scene{n}.wav"))

        self._scan()
        report = free_workspace.preparation(self.project, scenes)

        # 이제 다 있으나 같은 그림을 쓴다.
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["state"], "review")

        # Scene마다 제 그림을 넣으면 완료다.
        #
        # Sprint157 - 낱말 하나로만 걸린 것도 검토 대상이 되었으므로,
        # 둘 다 낱말 둘이 겹치게 넣는다. "허리 운동.png"만 넣으면
        # 1번이 "운동" 하나로만 걸려 여전히 검토 필요다 - 그것도
        # 맞는 판정이다.
        _png(os.path.join(self.root, "images", "무릎 운동.png"))
        _png(os.path.join(self.root, "images", "허리 운동.png"))
        self._scan()

        report = free_workspace.preparation(self.project, scenes)

        self.assertEqual(report["state"], "ready")
        self.assertEqual(report["review"], [])

        for row in report["scenes"]:
            with self.subTest(scene=row["scene"]):
                self.assertEqual(row["image"]["matched_count"], 2)

    def test_the_requirement_rows_carry_it_too(self):
        """요구 목록도 같은 말을 한다 - 두 화면이 갈리지 않는다."""

        _png(os.path.join(self.root, "images", "남성.png"))

        for n in (1, 2):
            _tone(os.path.join(self.root, "voices", f"scene{n}.wav"))

        self._scan()

        report = free_workspace.requirements(
            self.project, self._scenes(["남성 하나", "남성 둘"]))

        self.assertEqual(report["state"], "review")
        self.assertTrue(report["review"])

        images = [r for r in report["requirements"]
                  if r["required_asset"] == "image"]

        for row in images:
            with self.subTest(scene=row["scene"]):
                self.assertEqual(row["status"], "ready")
                self.assertIn("Scene", row["message"])


class SameAssetStillRendersTest(unittest.TestCase):
    """4. 검토가 필요해도 만들 수는 있다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def test_same_asset_can_still_render(self):
        """
        같은 그림을 쓰는 것이 틀린 것은 아니다.

        사람이 일부러 그렇게 할 수도 있다. 우리가 막을 일이 아니라
        말할 일이다 - 렌더 검사는 그대로 통과해야 한다.
        """

        from app.services import asset_integration_service

        _png(os.path.join(self.root, "images", "남성.png"))

        for n in (1, 2):
            _tone(os.path.join(self.root, "voices", f"scene{n}.wav"))

        local_library.save(self.project, local_library.scan(self.root))

        scenes = [
            {"scene": 1, "narration": "하나", "image_prompt": "남성 하나"},
            {"scene": 2, "narration": "둘", "image_prompt": "남성 둘"},
        ]

        # 검토 필요라고 말은 한다.
        self.assertEqual(
            free_workspace.preparation(self.project, scenes)["state"],
            "review")

        # 그래도 실제로 만들어진다.
        from app.services import scene_tts_service

        for scene in scenes:
            target = os.path.join(
                self.project, "images", f"scene{scene['scene']}.png")

            asset_integration_service._select_ai_first(
                scene["image_prompt"], target, "wellbeing", False,
                scene=scene, provider="local_stock")

            self.assertTrue(os.path.exists(target))

        scene_tts_service.create_scene_tts(
            scenes, self.project, provider="local_voice")

        # 렌더도 막히지 않는다.
        self.assertEqual(
            scene_order.render_problems(self.project, scenes), [])

    def test_render_problems_was_not_taught_about_duplicates(self):
        """
        렌더 검사에 이 판단을 심지 않았다.

        심으면 자동 실패가 되고, 그것은 이 Sprint가 금지한 것이다.
        """

        with open(scene_order.__file__, encoding="utf-8") as f:
            source = f.read()

        for word in ("shared_with", "review", "중복"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)


class NoExternalProviderTest(unittest.TestCase):
    """5. 그 길에서 밖으로 안 나간다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def test_free_mode_no_external_provider(self):
        import requests

        from app.providers import local_voice_provider
        from app.services import asset_integration_service

        _png(os.path.join(self.root, "images", "남성.png"))
        local_library.save(self.project, local_library.scan(self.root))

        scenes = [
            {"scene": 1, "narration": "하나", "image_prompt": "남성 하나"},
            {"scene": 2, "narration": "둘", "image_prompt": "남성 둘"},
        ]

        with patch.object(
            local_stock_provider, "generate_image") as make_image, \
                patch.object(
                    local_voice_provider, "generate_voice") as make_voice, \
                patch.object(
                    asset_integration_service, "get_candidates") as stock, \
                patch.object(
                    asset_integration_service.best_of_n_service,
                    "generate_candidates") as imagen, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            report = free_workspace.preparation(self.project, scenes)
            free_workspace.requirements(self.project, scenes)

            for name, mock in (("local_stock", make_image),
                               ("local_voice", make_voice),
                               ("스톡 검색", stock), ("Imagen", imagen),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()

        self.assertEqual(report["state"], "missing")
        self.assertTrue(report["review"])

    def test_the_keyword_rule_pulls_in_nothing_new(self):
        """낱말을 고르는 데 모델이 끼어들지 않았다."""

        with open(local_stock_provider.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        imported = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        for name in sorted(imported):
            for bad in ("google", "openai", "anthropic", "requests",
                        "vertexai"):
                with self.subTest(name=name):
                    self.assertFalse(
                        name == bad or name.startswith(bad + "."))

    def test_the_provider_contract_did_not_change(self):
        """
        부르는 모양은 그대로다.

        generate_image(prompt, output_file) · find(project_path, prompt).
        이 둘이 바뀌면 다리와 등록소가 함께 깨진다.
        """

        import inspect

        self.assertEqual(
            list(inspect.signature(
                local_stock_provider.generate_image).parameters),
            ["prompt", "output_file"])

        self.assertEqual(
            list(inspect.signature(local_stock_provider.find).parameters),
            ["project_path", "image_prompt"])


if __name__ == "__main__":
    unittest.main()
