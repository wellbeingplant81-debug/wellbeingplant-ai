"""
Sprint158 - 고른 것을 보고, 마음에 안 들면 바꾼다 (Epic 57, Phase 9).

Sprint157이 "왜 걸렸는지"를 말하게 했다. 사람은 이제 1/8로 걸린 것을
알아볼 수 있다. 그런데 알아본 다음에 할 수 있는 일이 없었다 - 파일
이름을 고쳐 다시 훑는 것뿐이었다.

무엇을 지키는가
---------------
    1. 무엇이 걸렸는지 눈으로 본다   test_asset_preview_exists
    2. 다른 후보를 보여 준다         test_alternative_assets_returned
    3. 고르면 그것이 쓰인다          test_user_override_selected
    4. 다시 열어도 남아 있다         test_override_survives_reload
    5. 밖으로 안 나간다              test_free_mode_no_external_api

셋째가 경계다. 고르기만 하고 안 쓰이면 되는 척이 된다 - 사람은
바꿨다고 믿고 렌더를 누르는데 예전 그림이 나온다.

자동으로 다시 고르지 않는다
---------------------------
사람이 정한 것은 사람이 지울 때까지 남는다. 자료가 늘었다고 우리가
더 나은 것으로 바꿔 주면, 사람이 정한 것이 조용히 사라진다.
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

from fastapi.testclient import TestClient

from app.main import app
from app.providers import local_stock_provider
from app.routers import studio as studio_router
from app.services import asset_override, free_workspace, local_library


def _png(path, color=(200, 30, 30)):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (64, 64), color).save(path)


def _mp4(path, seconds=0.3):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c=cyan:s=160x120:d={seconds}", "-pix_fmt", "yuv420p",
         path],
        capture_output=True, check=True,
    )


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

        self.client = TestClient(app)
        self._real = studio_router._project_path
        studio_router._project_path = lambda project_id: self.project
        self.addCleanup(self._restore)

        self.scenes = [
            {"scene": 1, "narration": "무릎을 펴 주세요",
             "image_prompt": "40대 남성, 무릎 스트레칭, 거실, 자연광"},
            {"scene": 2, "narration": "허리를 세웁니다",
             "image_prompt": "40대 남성, 허리 세우기, 침실, 자연광"},
        ]

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": self.scenes}, f,
                      ensure_ascii=False)

    def _restore(self):
        studio_router._project_path = self._real

    def image(self, name, color=(200, 30, 30)):
        path = os.path.join(self.root, "images", name)
        _png(path, color)
        return path

    def video(self, name):
        path = os.path.join(self.root, "videos", name)
        _mp4(path)
        return path

    def scan(self):
        local_library.save(self.project, local_library.scan(self.root))


class AssetPreviewTest(Base):
    """1. 무엇이 걸렸는지 눈으로 본다."""

    def test_asset_preview_exists(self):
        target = self.image("무릎 스트레칭.png")
        self.scan()

        info = local_stock_provider.match(
            self.project, self.scenes[0]["image_prompt"])

        # 미리 볼 것이 어디 있는지 함께 온다.
        self.assertEqual(info["thumbnail_path"], target)
        self.assertEqual(info["kind"], "images")

        # 화면이 그 파일을 실제로 받아 볼 수 있다.
        response = self.client.get(
            "/studio/api/review/p1/asset", params={"path": target})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content)

    def test_a_video_previews_as_itself(self):
        """
        영상은 따로 썸네일을 만들지 않는다.

        만들면 "읽기만 한다"던 자리가 파일을 쓰기 시작한다. 화면이
        kind를 보고 video 태그로 그리면 된다.
        """

        target = self.video("무릎 스트레칭.mp4")
        self.scan()

        info = local_stock_provider.match(
            self.project, self.scenes[0]["image_prompt"])

        self.assertEqual(info["kind"], "videos")
        self.assertEqual(info["thumbnail_path"], target)

    def test_a_file_outside_the_library_is_refused(self):
        """
        훑어 둔 목록에 없는 경로는 내주지 않는다.

        없으면 요청 하나로 이 컴퓨터의 아무 파일이나 읽어 갈 수 있다.
        """

        self.image("무릎 스트레칭.png")
        self.scan()

        secret = os.path.join(self.root, "비밀.txt")

        with open(secret, "w", encoding="utf-8") as f:
            f.write("남의 것")

        for path in (secret, os.path.join(self.project, "script.json"),
                     "C:/Windows/win.ini", "../../etc/passwd"):
            with self.subTest(path=path):
                response = self.client.get(
                    "/studio/api/review/p1/asset", params={"path": path})

                self.assertEqual(response.status_code, 404)


class AlternativesTest(Base):
    """2. 다른 후보를 보여 준다."""

    def test_alternative_assets_returned(self):
        self.image("무릎 스트레칭.png")
        self.image("허리 운동.png")
        self.video("걷기.mp4")
        self.scan()

        response = self.client.get(
            "/studio/api/review/p1/scenes/1/alternatives")

        self.assertEqual(response.status_code, 200)

        body = response.json()
        names = [item["file"] for item in body["alternatives"]]

        # 지금 걸린 것이 무엇인지 말하고,
        self.assertEqual(body["chosen"]["file"], "무릎 스트레칭.png")

        # 고를 수 있는 것을 모두 준다 - 낱말이 안 겹치는 것도 포함한다.
        # 안 겹치는 것만 가진 사람이 바로 그것을 바꾸고 싶어 한다.
        self.assertIn("허리 운동.png", names)
        self.assertIn("걷기.mp4", names)

        # 그림과 영상 둘 다 쓸 수 있다.
        kinds = {item["kind"] for item in body["alternatives"]}

        self.assertEqual(kinds, {"images", "videos"})

        # 몇 낱말이 겹치는지도 함께 - 사람이 고를 근거가 된다.
        for item in body["alternatives"]:
            with self.subTest(file=item["file"]):
                self.assertIn("matched_count", item)

    def test_the_matched_ones_come_first(self):
        """겹치는 것이 위에 온다 - 사람이 위에서부터 읽는다."""

        self.image("주방.png")
        self.image("무릎 운동.png")
        self.scan()

        body = self.client.get(
            "/studio/api/review/p1/scenes/1/alternatives").json()

        counts = [item["matched_count"] for item in body["alternatives"]]

        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_the_chosen_one_is_not_listed_again(self):
        self.image("무릎 스트레칭.png")
        self.image("허리 운동.png")
        self.scan()

        body = self.client.get(
            "/studio/api/review/p1/scenes/1/alternatives").json()

        names = [item["file"] for item in body["alternatives"]]

        self.assertNotIn("무릎 스트레칭.png", names)

    def test_nothing_scanned_gives_an_empty_list(self):
        body = self.client.get(
            "/studio/api/review/p1/scenes/1/alternatives").json()

        self.assertEqual(body["alternatives"], [])
        self.assertIsNone(body["chosen"])


class UserOverrideTest(Base):
    """3. 고르면 그것이 쓰인다."""

    def test_user_override_selected(self):
        self.image("자연광.png", (240, 230, 120))
        chosen = self.image("무릎 운동.png", (30, 180, 90))
        self.scan()

        # 그냥 두면 약하게 걸린 것이 온다.
        before = local_stock_provider.match(
            self.project, self.scenes[0]["image_prompt"])

        self.assertEqual(before["file"], "무릎 운동.png")

        # 사람이 다른 것을 고른다.
        response = self.client.put(
            "/studio/api/review/p1/scenes/1/asset",
            json={"path": os.path.join(self.root, "images", "자연광.png")})

        self.assertEqual(response.status_code, 200)

        after = local_stock_provider.match(
            self.project, self.scenes[0]["image_prompt"], 1)

        self.assertEqual(after["file"], "자연광.png")
        self.assertEqual(after["chosen_by"], "user")

        # 실제로 만들어지는 것도 그것이다 - 여기가 되는 척과 갈리는 자리다.
        import hashlib

        target = os.path.join(self.project, "images", "scene1.png")
        local_stock_provider.generate_image(
            self.scenes[0]["image_prompt"], target)

        with open(target, "rb") as made, \
                open(os.path.join(self.root, "images", "자연광.png"),
                     "rb") as picked:
            self.assertEqual(
                hashlib.md5(made.read()).hexdigest(),
                hashlib.md5(picked.read()).hexdigest())

        self.assertNotEqual(chosen, after["path"])

    def test_a_path_outside_the_library_is_refused(self):
        self.image("무릎 스트레칭.png")
        self.scan()

        response = self.client.put(
            "/studio/api/review/p1/scenes/1/asset",
            json={"path": os.path.join(self.project, "script.json")})

        self.assertEqual(response.status_code, 400)
        self.assertIsNone(asset_override.for_scene(self.project, 1))

    def test_choosing_a_video_works_too(self):
        self.image("무릎 스트레칭.png")
        video = self.video("걷기.mp4")
        self.scan()

        self.client.put("/studio/api/review/p1/scenes/1/asset",
                        json={"path": video})

        info = local_stock_provider.match(
            self.project, self.scenes[0]["image_prompt"], 1)

        self.assertEqual(info["file"], "걷기.mp4")
        self.assertEqual(info["kind"], "videos")

        # 영상은 첫 프레임을 꺼내 쓴다 - 예전 그대로다.
        target = os.path.join(self.project, "images", "scene1.png")
        local_stock_provider.generate_image(
            self.scenes[0]["image_prompt"], target)

        self.assertTrue(os.path.exists(target))

    def test_clearing_goes_back_to_the_automatic_one(self):
        self.image("자연광.png")
        self.image("무릎 운동.png")
        self.scan()

        path = os.path.join(self.root, "images", "자연광.png")

        self.client.put("/studio/api/review/p1/scenes/1/asset",
                        json={"path": path})

        self.assertEqual(
            local_stock_provider.match(
                self.project, self.scenes[0]["image_prompt"], 1)["file"],
            "자연광.png")

        self.client.delete("/studio/api/review/p1/scenes/1/asset")

        info = local_stock_provider.match(
            self.project, self.scenes[0]["image_prompt"], 1)

        self.assertEqual(info["file"], "무릎 운동.png")
        self.assertEqual(info["chosen_by"], "match")

    def test_only_that_scene_changes(self):
        self.image("자연광.png")
        self.image("무릎 운동.png")
        self.image("허리 세우기.png")
        self.scan()

        self.client.put(
            "/studio/api/review/p1/scenes/1/asset",
            json={"path": os.path.join(self.root, "images", "자연광.png")})

        self.assertEqual(
            local_stock_provider.match(
                self.project, self.scenes[1]["image_prompt"], 2)["file"],
            "허리 세우기.png")

    def test_a_deleted_override_file_falls_back_and_says_so(self):
        """
        고른 파일이 사라지면 자동으로 고른 것으로 돌아간다.

        조용히 실패하면 사람은 왜 다른 그림이 나오는지 모른다 -
        준비 상태가 그 사실을 말한다.
        """

        self.image("자연광.png")
        self.image("무릎 운동.png")
        self.scan()

        path = os.path.join(self.root, "images", "자연광.png")
        self.client.put("/studio/api/review/p1/scenes/1/asset",
                        json={"path": path})

        os.remove(path)
        self.scan()

        info = local_stock_provider.match(
            self.project, self.scenes[0]["image_prompt"], 1)

        self.assertEqual(info["file"], "무릎 운동.png")
        self.assertEqual(info["chosen_by"], "match")

        report = free_workspace.preparation(self.project, self.scenes)
        message = " ".join(report["review"])

        self.assertIn("자연광.png", message)


class OverrideSurvivesTest(Base):
    """4. 다시 열어도 남아 있다."""

    def test_override_survives_reload(self):
        self.image("자연광.png")
        self.image("무릎 운동.png")
        self.scan()

        path = os.path.join(self.root, "images", "자연광.png")

        self.client.put("/studio/api/review/p1/scenes/1/asset",
                        json={"path": path})

        # 파일에 남았는가 - 프로세스가 죽어도 살아남아야 한다.
        #
        # Sprint159가 "언제 누가"를 함께 적게 되었다. 여기서 지킬 것은
        # 그 경로가 파일에 남는다는 사실이므로, 모양을 통째로 못 박지
        # 않고 읽는 함수로 확인한다 - 적는 모양이 또 바뀌어도 이
        # 테스트가 남의 Sprint를 막지 않는다.
        self.assertTrue(os.path.exists(
            os.path.join(self.project, asset_override.FILENAME)))

        self.assertEqual(asset_override.for_scene(self.project, 1), path)

        # 새 요청에서도 그대로 온다.
        report = self.client.get(
            "/studio/api/review/p1/requirements").json()

        row = [r for r in report["requirements"]
               if r["scene"] == 1 and r["required_asset"] == "image"][0]

        self.assertEqual(row["found"], "자연광.png")

        state = free_workspace.preparation(self.project, self.scenes)
        image = state["scenes"][0]["image"]

        self.assertEqual(image["name"], "자연광.png")
        self.assertEqual(image["from"], "override")

    def test_rescanning_does_not_undo_it(self):
        """
        자료가 늘어도 우리가 다시 고르지 않는다.

        사람이 정한 것이 조용히 사라지면 안 된다.
        """

        self.image("자연광.png")
        self.scan()

        self.client.put(
            "/studio/api/review/p1/scenes/1/asset",
            json={"path": os.path.join(self.root, "images", "자연광.png")})

        # 더 잘 맞는 것을 나중에 넣는다.
        self.image("무릎 스트레칭 거실.png")
        self.scan()

        self.assertEqual(
            local_stock_provider.match(
                self.project, self.scenes[0]["image_prompt"], 1)["file"],
            "자연광.png")

    def test_a_broken_store_is_read_as_nothing(self):
        with open(os.path.join(self.project, asset_override.FILENAME), "w",
                  encoding="utf-8") as f:
            f.write("{{{ 망가진 것")

        self.assertEqual(asset_override.load(self.project), {})
        self.assertIsNone(asset_override.for_scene(self.project, 1))


class NoExternalApiTest(Base):
    """5. 밖으로 안 나간다."""

    def test_free_mode_no_external_api(self):
        import requests

        from app.providers import local_voice_provider
        from app.services import asset_integration_service

        self.image("자연광.png")
        self.image("무릎 운동.png")
        self.scan()

        with patch.object(
            local_voice_provider, "generate_voice") as make_voice, \
                patch.object(
                    asset_integration_service, "get_candidates") as stock, \
                patch.object(
                    asset_integration_service.best_of_n_service,
                    "generate_candidates") as imagen, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            self.client.get("/studio/api/review/p1/scenes/1/alternatives")
            self.client.put(
                "/studio/api/review/p1/scenes/1/asset",
                json={"path": os.path.join(self.root, "images", "자연광.png")})
            self.client.get("/studio/api/review/p1/requirements")
            local_stock_provider.match(
                self.project, self.scenes[0]["image_prompt"], 1)

            for name, mock in (("local_voice", make_voice),
                               ("스톡 검색", stock), ("Imagen", imagen),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()

    def test_nothing_but_the_decision_is_written(self):
        """
        사람의 결정 하나만 적는다.

        미리보기를 위해 썸네일을 만들면 "읽기만 한다"던 자리가 파일을
        쓰기 시작한다.
        """

        self.image("무릎 스트레칭.png")
        self.scan()

        before = set(os.listdir(self.project))

        self.client.get("/studio/api/review/p1/scenes/1/alternatives")
        self.client.get("/studio/api/review/p1/requirements")

        self.assertEqual(set(os.listdir(self.project)), before)

        self.client.put(
            "/studio/api/review/p1/scenes/1/asset",
            json={"path": os.path.join(self.root, "images", "무릎 스트레칭.png")})

        self.assertEqual(
            set(os.listdir(self.project)) - before, {asset_override.FILENAME})

    def test_the_module_pulls_in_nothing_new(self):
        with open(asset_override.__file__, encoding="utf-8") as f:
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

    def test_render_still_knows_nothing_about_this(self):
        from app.services import scene_order

        with open(scene_order.__file__, encoding="utf-8") as f:
            source = f.read()

        for word in ("override", "alternatives", "thumbnail"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)


if __name__ == "__main__":
    unittest.main()
