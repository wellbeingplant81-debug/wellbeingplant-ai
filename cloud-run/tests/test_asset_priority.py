"""
Sprint159 - 사람이 정한 것이 맨 앞이다 (Epic 57, Phase 10).

Sprint158이 override를 만들었다. 그런데 준비 표는 이미 만들어 둔
파일을 먼저 봤다.

    이전: 만들어 둔 것 > 사람이 정한 것 > 자동으로 고른 것
    지금: 사람이 정한 것 > 만들어 둔 것 > 자동으로 고른 것

그 차이가 실제로 드러나는 자리
------------------------------
Sprint158 실측에서 이미 나왔다. 사람이 자연광.png를 고르고 한 번
만들고 나면, 화면은 "만들어 둠 · scene1.png"이라고만 했다. 말 자체는
참이지만 사람이 정한 것이 아직 살아 있는지는 알 수 없었다.

만드는 쪽은 이미 override를 따르고 있었다 - collect_assets는 기존
파일을 건너뛰지 않는다. 그러니 이 Sprint에서 뒤집는 것은 화면의
순서이고, 렌더 결과는 예전부터 사람이 고른 것이었다.

무엇을 지키는가
---------------
    1. 사람이 정한 것이 이긴다      test_override_beats_generated_asset
    2. 없으면 만들어 둔 것을 쓴다   test_generated_asset_used_without_override
    3. 지우면 자동으로 돌아간다     test_delete_override_restores_match
    4. 다시 열어도 남아 있다        test_override_survives_reload
    5. 실제로 그것이 렌더된다       test_render_uses_override

다섯째가 경계다. 화면 순서만 바꾸고 실제 결과가 다르면, 이 Sprint는
글자만 고친 것이 된다.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from app.main import app
from app.providers import local_stock_provider
from app.routers import studio as studio_router
from app.services import (
    asset_integration_service, asset_override, free_workspace, local_library,
)


def _png(path, color):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (64, 64), color).save(path)


def _mp4(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=cyan:s=160x120:d=0.3",
         "-pix_fmt", "yuv420p", path],
        capture_output=True, check=True,
    )


def _digest(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


class Base(unittest.TestCase):
    AUTO = (220, 40, 40)
    PICKED = (240, 230, 120)
    MADE = (10, 10, 200)

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.client = TestClient(app)
        self._real = studio_router._project_path
        studio_router._project_path = lambda project_id: self.project
        self.addCleanup(self._restore)

        self.scenes = [
            {"scene": 1, "narration": "무릎을 펴 주세요",
             "image_prompt": "40대 남성, 무릎 스트레칭, 거실, 자연광"},
        ]

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": self.scenes}, f,
                      ensure_ascii=False)

        self.auto = os.path.join(self.root, "images", "무릎 스트레칭.png")
        self.picked = os.path.join(self.root, "images", "자연광.png")

        _png(self.auto, self.AUTO)
        _png(self.picked, self.PICKED)

        self.scan()

    def _restore(self):
        studio_router._project_path = self._real

    def scan(self):
        local_library.save(self.project, local_library.scan(self.root))

    def made(self, color=None):
        """이미 만들어 둔 scene 이미지를 놓는다."""

        path = os.path.join(self.project, "images", "scene1.png")
        _png(path, color or self.MADE)

        return path

    def choose(self, path=None):
        return self.client.put("/studio/api/review/p1/scenes/1/asset",
                               json={"path": path or self.picked})

    def status(self):
        return free_workspace.preparation(
            self.project, self.scenes)["scenes"][0]["image"]

    def render_image(self):
        """실제로 이미지 단계를 돌린다. 만드는 쪽이 무엇을 쓰는가."""

        target = os.path.join(self.project, "images", "scene1.png")

        asset_integration_service._select_ai_first(
            self.scenes[0]["image_prompt"], target, "wellbeing", False,
            scene=self.scenes[0], provider="local_stock")

        return target


class OverrideBeatsGeneratedTest(Base):
    """1. 사람이 정한 것이 이긴다."""

    def test_override_beats_generated_asset(self):
        self.made()
        self.choose()

        image = self.status()

        self.assertEqual(image["asset_source"], "override")
        self.assertEqual(image["from"], "override")
        self.assertEqual(image["name"], "자연광.png")

        # 무엇 대신 쓰이는지도 말한다 - 사람이 그 사실을 알아야
        # "왜 만들어 둔 것이 안 나오지"를 묻지 않는다.
        self.assertEqual(image["instead_of"]["source"], "generated")
        self.assertEqual(image["instead_of"]["file"], "scene1.png")

    def test_it_says_what_the_automatic_one_would_have_been(self):
        """
        사양의 화면이 요구하는 것.

            상태      직접 선택됨
            자동 매칭  무릎 스트레칭.png (사용 안 함)
        """

        self.choose()

        image = self.status()

        self.assertEqual(image["asset_source"], "override")
        self.assertEqual(image["instead_of"]["source"], "matched")
        self.assertEqual(image["instead_of"]["file"], "무릎 스트레칭.png")

    def test_nothing_is_hidden_when_there_is_no_override(self):
        """정한 것이 없으면 대신 쓰였을 것도 없다."""

        image = self.status()

        self.assertEqual(image["asset_source"], "matched")
        self.assertIsNone(image["instead_of"])

    def test_the_decision_carries_when_and_who(self):
        """
        새로운 사실만 적는다.

        "언제 누가 정했는가"는 어디서도 읽어 낼 수 없다. asset_source는
        읽어 낼 수 있으므로 적지 않는다.
        """

        self.choose()

        image = self.status()

        self.assertEqual(image["selected_by"], "user")
        self.assertTrue(image["selected_at"])

        stored = json.load(open(
            os.path.join(self.project, asset_override.FILENAME),
            encoding="utf-8"))

        self.assertEqual(set(stored["scenes"]["1"]),
                         {"path", "selected_at", "selected_by"})

        # asset_source는 파일에 없다 - 지금 상태에서 나온다.
        self.assertNotIn("asset_source", stored["scenes"]["1"])


class GeneratedWithoutOverrideTest(Base):
    """2. 정한 것이 없으면 만들어 둔 것을 쓴다."""

    def test_generated_asset_used_without_override(self):
        self.made()

        image = self.status()

        self.assertEqual(image["asset_source"], "generated")
        self.assertEqual(image["from"], "made")
        self.assertEqual(image["name"], "scene1.png")

        # 만들어 둔 것은 고른 것이 아니라 그 scene의 제 파일이다.
        self.assertIsNone(image["matched_count"])
        self.assertIsNone(image["selected_at"])

    def test_without_anything_it_is_the_automatic_match(self):
        image = self.status()

        self.assertEqual(image["asset_source"], "matched")
        self.assertEqual(image["name"], "무릎 스트레칭.png")
        self.assertEqual(image["matched_count"], 2)


class DeleteRestoresMatchTest(Base):
    """3. 지우면 자동으로 돌아간다."""

    def test_delete_override_restores_match(self):
        self.choose()

        self.assertEqual(self.status()["asset_source"], "override")

        self.client.delete("/studio/api/review/p1/scenes/1/asset")

        image = self.status()

        self.assertEqual(image["asset_source"], "matched")
        self.assertEqual(image["name"], "무릎 스트레칭.png")
        self.assertIsNone(image["instead_of"])

    def test_delete_goes_back_to_the_generated_one_if_there_is_one(self):
        """만들어 둔 것이 있으면 그쪽으로 돌아간다 - 자동보다 먼저다."""

        self.made()
        self.choose()

        self.client.delete("/studio/api/review/p1/scenes/1/asset")

        image = self.status()

        self.assertEqual(image["asset_source"], "generated")
        self.assertEqual(image["name"], "scene1.png")

    def test_a_vanished_override_falls_back_and_says_so(self):
        self.choose()
        os.remove(self.picked)
        self.scan()

        image = self.status()

        self.assertEqual(image["asset_source"], "matched")

        report = free_workspace.preparation(self.project, self.scenes)

        self.assertIn("자연광.png", " ".join(report["review"]))


class OverrideSurvivesTest(Base):
    """4. 다시 열어도 남아 있다."""

    def test_override_survives_reload(self):
        self.made()
        self.choose()

        # 새 요청에서도 같은 답이 온다.
        body = self.client.get(
            "/studio/api/review/p1/requirements").json()

        row = [r for r in body["requirements"]
               if r["scene"] == 1 and r["required_asset"] == "image"][0]

        self.assertEqual(row["found"], "자연광.png")

        # 파일에 남았고, 다시 읽어도 같다.
        self.assertEqual(
            asset_override.for_scene(self.project, 1), self.picked)

        self.assertEqual(self.status()["asset_source"], "override")

    def test_an_old_store_is_still_read(self):
        """
        Sprint158이 적어 둔 모양(경로 문자열)도 읽는다.

        못 읽으면 그때 정한 사람들의 결정이 조용히 사라진다.
        """

        with open(os.path.join(self.project, asset_override.FILENAME), "w",
                  encoding="utf-8") as f:
            json.dump({"version": 1, "scenes": {"1": self.picked}}, f,
                      ensure_ascii=False)

        self.assertEqual(
            asset_override.for_scene(self.project, 1), self.picked)

        image = self.status()

        self.assertEqual(image["asset_source"], "override")
        self.assertEqual(image["name"], "자연광.png")

        # 언제 정했는지는 모른다. 지어내지 않는다.
        self.assertIsNone(image["selected_at"])

    def test_rescanning_does_not_undo_it(self):
        self.choose()

        _png(os.path.join(self.root, "images", "무릎 스트레칭 거실 자연광.png"),
             (1, 1, 1))
        self.scan()

        self.assertEqual(self.status()["name"], "자연광.png")


class RenderUsesOverrideTest(Base):
    """5. 실제로 그것이 렌더된다."""

    def test_render_uses_override(self):
        """
        화면 순서만 바꾸고 실제 결과가 다르면 글자만 고친 것이 된다.

        이미 만들어 둔 파일이 있어도, 다시 만들면 사람이 정한 것이
        나와야 한다.
        """

        self.made()
        self.choose()

        made = self.render_image()

        self.assertEqual(_digest(made), _digest(self.picked))

        from PIL import Image

        self.assertEqual(
            Image.open(made).convert("RGB").getpixel((32, 32)), self.PICKED)

    def test_without_an_override_the_automatic_one_is_rendered(self):
        made = self.render_image()

        self.assertEqual(_digest(made), _digest(self.auto))

    def test_a_video_override_is_rendered_as_its_first_frame(self):
        video = os.path.join(self.root, "videos", "걷기.mp4")
        _mp4(video)
        self.scan()

        self.choose(video)

        from PIL import Image

        made = self.render_image()
        pixel = Image.open(made).convert("RGB").getpixel((80, 60))

        self.assertGreater(pixel[1], 180)
        self.assertGreater(pixel[2], 180)
        self.assertLess(pixel[0], 80)

    def test_render_checks_were_not_taught_about_priority(self):
        """
        렌더 검사에 이 순서를 심지 않았다.

        심으면 화면을 위한 결정이 파이프라인으로 새어 든다.
        """

        from app.services import scene_order

        with open(scene_order.__file__, encoding="utf-8") as f:
            source = f.read()

        for word in ("override", "asset_source", "instead_of"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)

    def test_nothing_external_was_called(self):
        import requests

        with patch.object(
            asset_integration_service, "get_candidates") as stock, \
                patch.object(
                    asset_integration_service.best_of_n_service,
                    "generate_candidates") as imagen, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            self.choose()
            self.render_image()
            self.status()

            for name, mock in (("스톡 검색", stock), ("Imagen", imagen),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
