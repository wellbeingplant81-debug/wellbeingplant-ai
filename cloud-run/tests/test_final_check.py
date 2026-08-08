"""
Sprint162 - 누르기 전에 마지막으로 본다 (Epic 57, Phase 13).

Sprint160·161이 자료 준비 상태를 만들었다. 그런데 그것과 "지금 렌더를
누르면 되는가"는 다른 물음이다.

    자료 준비   내 자료로 만들 수 있는가        free_workspace
    산출물      scene1.png·scene1.wav이 있는가  scene_order.render_problems

둘은 갈릴 수 있다. 내 자료가 다 있어도 아직 만들지 않았으면 렌더는
막힌다(Sprint145의 검사가 그렇게 한다). 그때 화면이 "준비 완료"라고만
하면 사람은 버튼을 누르고 400을 본다.

그래서 최종 확인은 둘 다 본다. 무엇을 해야 하는지가 다르기 때문이다.

    자료가 없다   폴더에 파일을 넣어라
    산출물이 없다 이미지·음성을 만들어라

무엇을 지키는가
---------------
    1. 다 되면 제작 가능        test_final_check_ready
    2. 없으면 막는다            test_final_check_blocked
    3. 검토는 막지 않되 말한다  test_final_check_review_warning
    4. 확인한 것을 보여 준다    test_confirmed_asset_visible
    5. 렌더 규칙은 그대로다     test_render_rule_unchanged

다섯째가 경계다. 최종 확인은 읽고 말할 뿐이고, 막는 일은 예전부터
있던 그 검사가 한다.
"""

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
from app.routers import studio as studio_router
from app.services import (
    asset_integration_service, final_check, free_workspace, local_library,
    scene_order, scene_tts_service,
)

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
    WEAK = "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광"

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.client = TestClient(app)
        self._real = studio_router._project_path
        studio_router._project_path = lambda project_id: self.project
        self.addCleanup(self._restore)

    def _restore(self):
        studio_router._project_path = self._real

    def image(self, name, color=(200, 30, 30)):
        path = os.path.join(self.root, "images", name)
        _png(path, color)
        return path

    def voices(self, *numbers):
        for number in numbers:
            _tone(os.path.join(self.root, "voices", f"scene{number}.wav"))

    def scan(self):
        local_library.save(self.project, local_library.scan(self.root))

    def scenes(self, prompts):
        found = [
            {"scene": n, "narration": f"{n}번 문장", "image_prompt": prompt}
            for n, prompt in enumerate(prompts, start=1)
        ]

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": found}, f, ensure_ascii=False)

        return found

    def produce(self, scenes):
        """이미지·음성을 실제로 만든다. 산출물이 있는 상태."""

        for scene in scenes:
            target = os.path.join(
                self.project, "images", f"scene{scene['scene']}.png")

            asset_integration_service._select_ai_first(
                scene["image_prompt"], target, "wellbeing", False,
                scene=scene, provider="local_stock")

        scene_tts_service.create_scene_tts(
            scenes, self.project, provider="local_voice")

    def check(self):
        return self.client.get("/studio/api/review/p1/final-check").json()


class ReadyTest(Base):
    """1. 다 되면 제작 가능."""

    def test_final_check_ready(self):
        self.image("무릎 스트레칭.png")
        self.image("허리 세우기.png")
        self.voices(1, 2)
        self.scan()

        scenes = self.scenes(["무릎 스트레칭 거실", "허리 세우기 침실"])
        self.produce(scenes)

        body = self.check()

        self.assertEqual(body["state"], free_workspace.READY)
        self.assertTrue(body["can_render"])
        self.assertEqual(body["problems"], [])

        # 사양이 요구하는 숫자.
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["images"], {"ready": 2, "total": 2})
        self.assertEqual(body["voices"], {"ready": 2, "total": 2})
        self.assertEqual(body["review"], 0)

    def test_materials_alone_are_not_enough(self):
        """
        내 자료가 다 있어도 아직 만들지 않았으면 렌더는 막힌다.

        그때 "준비 완료"라고만 하면 사람은 버튼을 누르고 400을 본다.
        """

        self.image("무릎 스트레칭.png")
        self.voices(1)
        self.scan()

        self.scenes(["무릎 스트레칭 거실"])

        # 자료 쪽은 다 되었다.
        self.assertEqual(
            free_workspace.preparation(
                self.project, self.scenes(["무릎 스트레칭 거실"]),
            )["state"],
            free_workspace.READY)

        body = self.check()

        self.assertEqual(body["state"], free_workspace.BLOCKED)
        self.assertFalse(body["can_render"])

        # 무엇을 해야 하는지 갈라 말한다.
        self.assertEqual(body["assets"]["state"], free_workspace.READY)
        self.assertTrue(body["outputs"])
        self.assertIn("Scene 1 이미지가 없습니다", body["outputs"])


class BlockedTest(Base):
    """2. 없으면 막는다."""

    def test_final_check_blocked(self):
        self.image("무릎 스트레칭.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes(["무릎 스트레칭 거실", "우주선 착륙"])
        self.produce(scenes[:1])

        body = self.check()

        self.assertEqual(body["state"], free_workspace.BLOCKED)
        self.assertFalse(body["can_render"])

        # 사양의 "제작할 수 없습니다" 목록.
        joined = " ".join(body["problems"])

        self.assertIn("Scene 2", joined)
        self.assertIn("이미지", joined)

        self.assertEqual(body["images"], {"ready": 1, "total": 2})

    def test_a_missing_voice_blocks_too(self):
        self.image("무릎 스트레칭.png")
        self.scan()

        scenes = self.scenes(["무릎 스트레칭 거실"])

        body = self.check()

        self.assertEqual(body["state"], free_workspace.BLOCKED)
        self.assertEqual(body["voices"], {"ready": 0, "total": 1})

    def test_no_scenes_is_blocked(self):
        self.scenes([])

        body = self.check()

        self.assertEqual(body["state"], free_workspace.BLOCKED)
        self.assertFalse(body["can_render"])
        self.assertEqual(body["total"], 0)

    def test_blocked_wins_over_review(self):
        self.image("자연광.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes([self.WEAK, "우주선 착륙"])
        self.produce(scenes[:1])

        body = self.check()

        self.assertEqual(body["state"], free_workspace.BLOCKED)
        self.assertEqual(body["review"], 1)


class ReviewWarningTest(Base):
    """3. 검토는 막지 않되 말한다."""

    def test_final_check_review_warning(self):
        self.image("자연광.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes([self.WEAK])
        self.produce(scenes)

        body = self.check()

        self.assertEqual(body["state"], free_workspace.REVIEW)

        # 막지 않는다.
        self.assertTrue(body["can_render"])

        # 그러나 말한다.
        self.assertEqual(body["review"], 1)
        self.assertTrue(body["warnings"])

        joined = " ".join(body["warnings"])

        self.assertIn("Scene 1", joined)

        # 막는 것이 아니므로 problems에는 없다.
        self.assertEqual(body["problems"], [])

    def test_confirming_turns_it_into_ready(self):
        self.image("자연광.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes([self.WEAK])
        self.produce(scenes)

        self.assertEqual(self.check()["state"], free_workspace.REVIEW)

        self.client.post("/studio/api/review/p1/scenes/1/confirm")

        body = self.check()

        self.assertEqual(body["state"], free_workspace.READY)
        self.assertEqual(body["review"], 0)
        self.assertEqual(body["warnings"], [])


class ConfirmedAssetVisibleTest(Base):
    """4. 확인한 것을 보여 준다."""

    def test_confirmed_asset_visible(self):
        """
        사양의 화면.

            Scene 2
            사용자 확인 완료
            파일: 자연광.png
            확인 이유: 같은 파일 사용
        """

        self.image("자연광.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes([self.WEAK])
        self.produce(scenes)

        self.client.post("/studio/api/review/p1/scenes/1/confirm")

        body = self.check()

        self.assertEqual(len(body["confirmed"]), 1)

        found = body["confirmed"][0]

        self.assertEqual(found["scene"], 1)
        self.assertEqual(found["file"], "자연광.png")
        self.assertIn("weak", found["reasons"])
        self.assertTrue(found["confirmed_at"])
        self.assertEqual(found["confirmed_by"], "user")

    def test_nothing_confirmed_is_an_empty_list(self):
        self.image("무릎 스트레칭.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes(["무릎 스트레칭 거실"])
        self.produce(scenes)

        self.assertEqual(self.check()["confirmed"], [])

    def test_the_screen_reads_it(self):
        source = _script_source()

        for name in ("finalCheck", "can_render", "confirmed"):
            with self.subTest(name=name):
                self.assertIn(name, source)


class RenderRuleUnchangedTest(Base):
    """5. 렌더 규칙은 그대로다."""

    def test_render_rule_unchanged(self):
        """
        막는 일은 예전부터 있던 그 검사가 한다.

        최종 확인은 그것을 읽어 옮길 뿐이다 - 두 곳에서 따로 판정하면
        화면이 "가능"이라고 한 것을 서버가 거절하는 날이 온다.
        """

        self.image("무릎 스트레칭.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes(["무릎 스트레칭 거실"])

        # 아직 안 만들었을 때 - 화면도 서버도 막는다.
        self.assertFalse(self.check()["can_render"])

        response = self.client.post("/studio/api/review/p1/render")

        self.assertEqual(response.status_code, 400)

        # 만들고 나면 둘 다 연다.
        self.produce(scenes)

        self.assertTrue(self.check()["can_render"])
        self.assertEqual(
            scene_order.render_problems(self.project, scenes), [])

    def test_a_weak_match_does_not_block_the_render_endpoint(self):
        self.image("자연광.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes([self.WEAK])
        self.produce(scenes)

        self.assertEqual(self.check()["state"], free_workspace.REVIEW)
        self.assertEqual(
            scene_order.render_problems(self.project, scenes), [])

    def test_scene_order_knows_nothing_about_the_final_check(self):
        with open(scene_order.__file__, encoding="utf-8") as f:
            source = f.read()

        for word in ("final_check", "can_render", "warnings"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)

    def test_the_outputs_list_comes_from_the_existing_check(self):
        """
        산출물 목록을 여기서 다시 만들지 않는다.

        새로 만들면 화면이 말하는 것과 렌더가 거절하는 것이 갈린다.
        """

        with open(final_check.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("scene_order.render_problems", source)

    def test_nothing_is_changed(self):
        import requests

        from app.providers import local_stock_provider, local_voice_provider

        self.image("자연광.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes([self.WEAK])
        self.produce(scenes)

        before = sorted(os.listdir(self.project))

        with patch.object(
            local_stock_provider, "generate_image") as make_image, \
                patch.object(
                    local_voice_provider, "generate_voice") as make_voice, \
                patch.object(
                    asset_integration_service, "get_candidates") as stock, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            self.check()

            for name, mock in (("local_stock", make_image),
                               ("local_voice", make_voice),
                               ("스톡 검색", stock),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()

        self.assertEqual(sorted(os.listdir(self.project)), before)


if __name__ == "__main__":
    unittest.main()
