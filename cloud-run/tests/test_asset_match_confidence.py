"""
Sprint157 - 왜 이 파일이 걸렸는지 말한다 (Epic 57, Phase 8).

Sprint156이 낱말을 넓게 뽑게 하면서 맞는 파일을 찾을 확률이 올라갔다.
그런데 엉뚱한 파일이 걸릴 확률도 함께 올라갔다.

    프롬프트  "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광"
    파일      "자연광.png"

한 낱말이 겹쳤으니 걸린다. 화면은 "준비 완료"라고 말하고, 사람은
렌더가 끝난 뒤에야 엉뚱한 그림을 본다.

Sprint156은 그런 경우 중 "여러 Scene이 같은 파일을 쓸 때"만 잡아냈다.
홀로 엉뚱하게 걸린 것은 조용히 넘어갔다.

무엇을 지키는가
---------------
    1. 왜 걸렸는지 함께 온다      test_match_reason_returned
    2. 화면이 그것을 보여 준다    test_match_score_displayed
    3. 근거가 약하면 말한다       test_low_match_warning
    4. 중복 표시는 그대로다       test_duplicate_warning_kept
    5. 밖으로 안 나간다           test_free_mode_no_external_api

셋째의 기준을 지어내지 않는다
-----------------------------
"몇 퍼센트 이하면 약하다"는 숫자를 만들지 않았다. 그런 숫자는 근거가
없다.

대신 셀 수 있는 사실만 쓴다 - 낱말 하나로만 걸렸는데 프롬프트에는
낱말이 더 있었다면, 그것이 우리가 가진 가장 약한 근거다. 0개는
아예 안 걸린 것이므로 1개가 최소값이다.
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

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _script_source():
    with open(PAGE, encoding="utf-8") as f:
        page = f.read()

    return page[page.index("<script>"):]


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


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def images(self, *names):
        for name in names:
            _png(os.path.join(self.root, "images", name))

    def voices(self, *numbers):
        for number in numbers:
            _tone(os.path.join(self.root, "voices", f"scene{number}.wav"))

    def scan(self):
        local_library.save(self.project, local_library.scan(self.root))

    def scenes(self, prompts):
        return [
            {"scene": n, "narration": f"{n}번 문장", "image_prompt": prompt}
            for n, prompt in enumerate(prompts, start=1)
        ]


class MatchReasonTest(Base):
    """1. 왜 걸렸는지 함께 온다."""

    def test_match_reason_returned(self):
        self.images("무릎 스트레칭.png")
        self.scan()

        prompt = "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광"
        info = local_stock_provider.match(self.project, prompt)

        self.assertIsNotNone(info)
        self.assertEqual(info["file"], "무릎 스트레칭.png")

        self.assertEqual(sorted(info["matched_keywords"]), ["무릎", "스트레칭"])
        self.assertEqual(info["matched_count"], 2)
        self.assertEqual(
            info["total_keywords"],
            len(local_stock_provider._keywords(prompt)))

    def test_no_match_returns_nothing(self):
        self.images("주방.png")
        self.scan()

        self.assertIsNone(
            local_stock_provider.match(self.project, "우주선 착륙"))

    def test_find_and_match_pick_the_same_file(self):
        """
        고르는 규칙은 하나뿐이다.

        둘이 따로 고르면 화면이 말하는 파일과 실제로 쓰이는 파일이
        달라진다.
        """

        self.images("무릎.png", "무릎 스트레칭.png", "거실.png")
        self.scan()

        prompt = "40대 남성, 무릎 스트레칭, 거실"

        picked = local_stock_provider.find(self.project, prompt)
        info = local_stock_provider.match(self.project, prompt)

        self.assertEqual(picked["name"], info["file"])
        self.assertEqual(picked["path"], info["path"])

    def test_the_matched_words_are_really_in_the_name(self):
        """
        적어 준 낱말이 실제로 그 파일 이름에 있다.

        지어내면 사람이 "왜 이게 걸렸지"를 영영 알 수 없다.
        """

        self.images("무릎 스트레칭.png")
        self.scan()

        info = local_stock_provider.match(
            self.project, "40대 남성, 무릎 스트레칭, 거실")

        for word in info["matched_keywords"]:
            with self.subTest(word=word):
                self.assertIn(word, "무릎 스트레칭.png".lower())

    def test_a_video_carries_it_too(self):
        import subprocess as sp

        path = os.path.join(self.root, "videos", "공원 산책.mp4")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sp.run(["ffmpeg", "-y", "-f", "lavfi",
                "-i", "color=c=cyan:s=160x120:d=0.3", "-pix_fmt", "yuv420p",
                path], capture_output=True, check=True)

        self.scan()

        info = local_stock_provider.match(self.project, "공원 산책")

        self.assertEqual(info["file"], "공원 산책.mp4")
        self.assertEqual(info["kind"], "videos")
        self.assertEqual(info["matched_count"], 2)

    def test_the_contract_did_not_change(self):
        """부르는 모양은 그대로다. 새 함수가 하나 늘었을 뿐이다."""

        import inspect

        self.assertEqual(
            list(inspect.signature(
                local_stock_provider.generate_image).parameters),
            ["prompt", "output_file"])

        self.assertEqual(
            list(inspect.signature(local_stock_provider.find).parameters),
            ["project_path", "image_prompt"])


class MatchScoreDisplayTest(Base):
    """2. 화면이 그것을 보여 준다."""

    def test_match_score_displayed(self):
        self.images("무릎 스트레칭.png")
        self.voices(1)
        self.scan()

        report = free_workspace.preparation(self.project, self.scenes([
            "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광",
        ]))

        image = report["scenes"][0]["image"]

        self.assertEqual(image["matched_count"], 2)
        self.assertEqual(image["total_keywords"], 8)
        self.assertEqual(sorted(image["matched_keywords"]),
                         ["무릎", "스트레칭"])

    def test_an_already_made_file_has_no_match_score(self):
        """
        이미 만들어 둔 것은 고른 것이 아니다.

        scene1.png은 그 scene의 것이라 "몇 낱말로 걸렸다"는 말이
        성립하지 않는다 - 없는 사실을 적지 않는다.
        """

        _png(os.path.join(self.project, "images", "scene1.png"))
        self.scan()

        report = free_workspace.preparation(
            self.project, self.scenes(["무릎"]))

        image = report["scenes"][0]["image"]

        self.assertEqual(image["from"], "made")
        self.assertIsNone(image["matched_count"])
        self.assertEqual(image["matched_keywords"], [])

    def test_a_missing_one_has_no_match_score(self):
        self.scan()

        image = free_workspace.preparation(
            self.project, self.scenes(["우주선"]))["scenes"][0]["image"]

        self.assertFalse(image["ready"])
        self.assertIsNone(image["matched_count"])

    def test_the_screen_draws_what_the_server_sent(self):
        """화면이 다시 세지 않는다."""

        source = _script_source()

        for name in ("matched_count", "total_keywords", "matched_keywords"):
            with self.subTest(name=name):
                self.assertIn(name, source)


class LowMatchTest(Base):
    """3. 근거가 약하면 말한다."""

    def test_low_match_warning(self):
        """
        낱말 하나로만 걸렸는데 프롬프트에는 낱말이 더 있었다.

        "자연광.png"이 무릎 scene에 걸린 경우다 - 걸리긴 했으나
        그림의 내용과는 상관이 없다.
        """

        self.images("자연광.png")
        self.voices(1)
        self.scan()

        report = free_workspace.preparation(self.project, self.scenes([
            "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광",
        ]))

        image = report["scenes"][0]["image"]

        # 없는 것이 아니다. 걸리긴 했다.
        self.assertTrue(image["ready"])
        self.assertEqual(image["matched_count"], 1)
        self.assertEqual(report["missing"], [])

        # 그러나 검토가 필요하다.
        self.assertEqual(report["state"], "review")
        self.assertTrue(image["weak"])

        message = " ".join(report["review"])

        self.assertIn("자연광.png", message)
        self.assertIn("1", message)

    def test_a_full_match_is_not_weak(self):
        self.images("무릎.png")
        self.voices(1)
        self.scan()

        # 낱말이 하나뿐인 프롬프트. 1/1은 전부 맞은 것이다.
        report = free_workspace.preparation(
            self.project, self.scenes(["무릎"]))

        image = report["scenes"][0]["image"]

        self.assertEqual(image["matched_count"], 1)
        self.assertEqual(image["total_keywords"], 1)
        self.assertFalse(image["weak"])
        self.assertEqual(report["state"], "ready")

    def test_two_of_eight_is_not_flagged(self):
        """
        기준을 지어내지 않았다.

        "몇 퍼센트 이하"라는 숫자를 만들면 근거가 없다. 셀 수 있는
        사실만 쓴다 - 하나로만 걸렸는가.
        """

        self.images("무릎 스트레칭.png")
        self.voices(1)
        self.scan()

        report = free_workspace.preparation(self.project, self.scenes([
            "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광",
        ]))

        self.assertEqual(report["scenes"][0]["image"]["matched_count"], 2)
        self.assertFalse(report["scenes"][0]["image"]["weak"])
        self.assertEqual(report["state"], "ready")

    def test_a_weak_match_still_renders(self):
        """자동으로 실패시키지 않는다. 그것은 사람이 정할 일이다."""

        from app.services import asset_integration_service, scene_tts_service

        self.images("자연광.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes([
            "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광",
        ])

        self.assertEqual(
            free_workspace.preparation(self.project, scenes)["state"],
            "review")

        target = os.path.join(self.project, "images", "scene1.png")

        asset_integration_service._select_ai_first(
            scenes[0]["image_prompt"], target, "wellbeing", False,
            scene=scenes[0], provider="local_stock")

        scene_tts_service.create_scene_tts(
            scenes, self.project, provider="local_voice")

        self.assertEqual(
            scene_order.render_problems(self.project, scenes), [])

    def test_render_problems_still_knows_nothing_about_this(self):
        with open(scene_order.__file__, encoding="utf-8") as f:
            source = f.read()

        for word in ("weak", "matched_count", "review"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)


class DuplicateWarningKeptTest(Base):
    """4. Sprint156의 중복 표시가 그대로다."""

    def test_duplicate_warning_kept(self):
        self.images("운동.png")
        self.voices(1, 2)
        self.scan()

        report = free_workspace.preparation(
            self.project, self.scenes(["무릎 운동", "허리 운동"]))

        self.assertEqual(report["state"], "review")

        message = " ".join(report["review"])

        self.assertIn("2개 Scene이 같은 이미지를 사용합니다", message)
        self.assertIn("운동.png", message)

        rows = {row["scene"]: row for row in report["scenes"]}

        self.assertEqual(rows[1]["image"]["shared_with"], [2])
        self.assertEqual(rows[2]["image"]["shared_with"], [1])

    def test_both_reasons_can_appear_together(self):
        """
        약한 매칭이면서 겹치기도 하면 둘 다 적는다.

        하나만 적으면 사람이 나머지 하나를 모른 채 넘어간다.
        """

        self.images("자연광.png")
        self.voices(1, 2)
        self.scan()

        report = free_workspace.preparation(self.project, self.scenes([
            "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광",
            "40대 여성, 허리 세우기, 침실, 클로즈업, 측면, 자연광",
        ]))

        message = " ".join(report["review"])

        self.assertIn("같은 이미지를 사용합니다", message)
        self.assertIn("낱말", message)

        self.assertEqual(report["state"], "review")
        self.assertEqual(report["missing"], [])

    def test_nothing_to_say_stays_quiet(self):
        self.images("무릎 스트레칭.png", "허리 세우기.png")
        self.voices(1, 2)
        self.scan()

        report = free_workspace.preparation(self.project, self.scenes([
            "무릎 스트레칭 거실", "허리 세우기 침실",
        ]))

        self.assertEqual(report["review"], [])
        self.assertEqual(report["state"], "ready")


class NoExternalApiTest(Base):
    """5. 밖으로 안 나간다."""

    def test_free_mode_no_external_api(self):
        import requests

        from app.providers import local_voice_provider
        from app.services import asset_integration_service

        self.images("자연광.png")
        self.scan()

        scenes = self.scenes([
            "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광",
            "우주선 착륙",
        ])

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

            local_stock_provider.match(
                self.project, scenes[0]["image_prompt"])

            report = free_workspace.preparation(self.project, scenes)
            free_workspace.requirements(self.project, scenes)

            for name, mock in (("local_stock", make_image),
                               ("local_voice", make_voice),
                               ("스톡 검색", stock), ("Imagen", imagen),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()

        self.assertEqual(report["scenes"][0]["image"]["matched_count"], 1)

    def test_match_writes_nothing(self):
        """읽기만 한다."""

        self.images("무릎.png")
        self.scan()

        before = sorted(os.listdir(self.project))

        local_stock_provider.match(self.project, "무릎")
        free_workspace.preparation(self.project, self.scenes(["무릎"]))

        self.assertEqual(sorted(os.listdir(self.project)), before)

    def test_the_module_pulls_in_nothing_new(self):
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


if __name__ == "__main__":
    unittest.main()
