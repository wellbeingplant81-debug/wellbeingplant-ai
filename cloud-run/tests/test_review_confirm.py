"""
Sprint161 - 봤고 괜찮다고 말할 수 있게 한다 (Epic 57, Phase 12).

Sprint160이 REVIEW를 만들었다. 그런데 사람이 보고 "이대로 괜찮다"고
해도 화면은 계속 검토 필요라고 했다. 볼 것이 하나라도 있으면 대시보드가
영영 노란색인 셈이다.

확인은 "무엇을"에 묶인다
------------------------
"이 scene은 괜찮다"가 아니라 "이 scene에 이 파일이 이런 까닭으로
걸린 것이 괜찮다"이다. 그래서 무엇을 확인했는지 함께 적는다.

    파일이 바뀌면      확인이 더 이상 그것을 가리키지 않는다
    새 까닭이 생기면   사람이 아직 못 본 사실이다

첫째가 사양의 "파일 변경하면 review 자동 해제"다. 따로 지우는 코드를
두지 않는다 - 확인이 다른 파일을 가리키게 되므로 저절로 풀린다.

무엇을 지키는가
---------------
    1. 확인하면 READY가 된다      test_review_scene_can_be_confirmed
    2. 다시 열어도 남는다          test_confirmation_survives_reload
    3. 확인 안 하면 그대로 REVIEW  test_unconfirmed_review_stays_review
    4. 파일을 바꾸면 풀린다        test_override_clears_review
    5. 없는 것은 확인할 수 없다    test_blocked_is_not_confirmable

다섯째가 경계다. 없는 파일을 "봤고 괜찮다"고 넘기면 렌더가 막히는데
화면은 준비 완료라고 말한다.
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
    asset_override, free_workspace, local_library, review_confirm, scene_order,
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
    # 낱말 하나("자연광")로만 걸리는 프롬프트.
    WEAK = "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광"
    WEAK2 = "40대 여성, 허리 세우기, 침실, 클로즈업, 측면, 자연광"

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

    def report(self, scenes):
        return free_workspace.preparation(self.project, scenes)

    def row(self, scenes, number=1):
        return {r["scene"]: r for r in self.report(scenes)["scenes"]}[number]

    def confirm(self, number):
        return self.client.post(
            f"/studio/api/review/p1/scenes/{number}/confirm")

    def weak_setup(self):
        """낱말 하나로만 걸린 Scene 하나."""

        self.image("자연광.png", (240, 230, 120))
        self.voices(1)
        self.scan()

        return self.scenes([self.WEAK])


class ConfirmTest(Base):
    """1. 확인하면 READY가 된다."""

    def test_review_scene_can_be_confirmed(self):
        scenes = self.weak_setup()

        before = self.report(scenes)

        self.assertEqual(before["state"], free_workspace.REVIEW)
        self.assertEqual(before["counts"]["review"], 1)

        response = self.confirm(1)

        self.assertEqual(response.status_code, 200)

        after = self.report(scenes)

        self.assertEqual(after["state"], free_workspace.READY)
        self.assertEqual(after["counts"], {"ready": 1, "review": 0,
                                           "blocked": 0})

        row = after["scenes"][0]

        self.assertEqual(row["state"], free_workspace.READY)

        # 볼 것이 없어진 것이 아니라 사람이 봤다는 뜻이다 - 그 사실을
        # 지우지 않는다.
        self.assertEqual(row["reasons"], [])
        self.assertEqual(row["confirmed"]["confirmed_by"], "user")
        self.assertTrue(row["confirmed"]["confirmed_at"])
        self.assertEqual(sorted(row["confirmed"]["reasons"]), ["weak"])

    def test_the_automatic_match_is_not_touched(self):
        """
        확인은 무엇도 바꾸지 않는다.

        확인했다고 우리가 더 나은 파일로 바꿔 주면 사람이 확인한 것과
        쓰이는 것이 달라진다.
        """

        scenes = self.weak_setup()

        before = self.row(scenes)["image"]
        self.confirm(1)
        after = self.row(scenes)["image"]

        self.assertEqual(after["name"], before["name"])
        self.assertEqual(after["path"], before["path"])
        self.assertEqual(after["asset_source"], "matched")
        self.assertEqual(after["matched_count"], before["matched_count"])

    def test_confirming_one_scene_leaves_the_other(self):
        self.image("자연광.png")
        self.voices(1, 2)
        self.scan()

        scenes = self.scenes([self.WEAK, self.WEAK2])

        self.confirm(1)

        rows = {r["scene"]: r for r in self.report(scenes)["scenes"]}

        self.assertEqual(rows[1]["state"], free_workspace.READY)
        self.assertEqual(rows[2]["state"], free_workspace.REVIEW)

    def test_a_new_reason_undoes_the_confirmation(self):
        """
        확인한 뒤에 생긴 사실은 사람이 아직 못 본 것이다.

        1번을 확인해 두었는데 2번이 같은 파일을 쓰기 시작하면, 1번에
        "같은 파일 사용"이 새로 붙는다.
        """

        self.image("자연광.png")
        self.voices(1, 2)
        self.scan()

        one = self.scenes([self.WEAK])
        self.confirm(1)

        self.assertEqual(self.row(one)["state"], free_workspace.READY)

        both = self.scenes([self.WEAK, self.WEAK2])
        row = self.row(both)

        self.assertEqual(row["state"], free_workspace.REVIEW)
        self.assertIn("shared", row["reasons"])

    def test_unconfirming_puts_it_back(self):
        scenes = self.weak_setup()

        self.confirm(1)
        self.assertEqual(self.row(scenes)["state"], free_workspace.READY)

        self.client.delete("/studio/api/review/p1/scenes/1/confirm")

        self.assertEqual(self.row(scenes)["state"], free_workspace.REVIEW)
        self.assertIsNone(self.row(scenes)["confirmed"])


class ConfirmationSurvivesTest(Base):
    """2. 다시 열어도 남는다."""

    def test_confirmation_survives_reload(self):
        scenes = self.weak_setup()

        self.confirm(1)

        stored = json.load(open(
            os.path.join(self.project, review_confirm.FILENAME),
            encoding="utf-8"))

        self.assertEqual(set(stored["scenes"]["1"]),
                         {"path", "reasons", "confirmed_at", "confirmed_by"})

        # 새 요청에서도 같은 답이 온다.
        body = self.client.get("/studio/api/review/p1/requirements").json()

        self.assertEqual(body["state"], free_workspace.READY)
        self.assertEqual(body["counts"]["ready"], 1)

        self.assertEqual(self.row(scenes)["state"], free_workspace.READY)

    def test_a_broken_store_is_read_as_nothing(self):
        scenes = self.weak_setup()

        with open(os.path.join(self.project, review_confirm.FILENAME), "w",
                  encoding="utf-8") as f:
            f.write("{{{ 망가진 것")

        self.assertEqual(review_confirm.load(self.project), {})
        self.assertEqual(self.row(scenes)["state"], free_workspace.REVIEW)

    def test_rescanning_does_not_undo_it(self):
        """자료가 늘어도 확인이 사라지지 않는다 - 같은 것이 걸린다면."""

        scenes = self.weak_setup()
        self.confirm(1)

        self.image("주방.png")
        self.scan()

        self.assertEqual(self.row(scenes)["state"], free_workspace.READY)


class UnconfirmedStaysReviewTest(Base):
    """3. 확인 안 하면 그대로 REVIEW."""

    def test_unconfirmed_review_stays_review(self):
        scenes = self.weak_setup()

        row = self.row(scenes)

        self.assertEqual(row["state"], free_workspace.REVIEW)
        self.assertIsNone(row["confirmed"])
        self.assertIn("weak", row["reasons"])

    def test_confirming_a_ready_scene_changes_nothing(self):
        """볼 것이 없으면 확인할 것도 없다."""

        self.image("무릎 스트레칭.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes(["무릎 스트레칭 거실"])

        self.assertEqual(self.row(scenes)["state"], free_workspace.READY)

        response = self.confirm(1)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(review_confirm.load(self.project), {})


class OverrideClearsReviewTest(Base):
    """4. 파일을 바꾸면 풀린다."""

    def test_override_clears_review(self):
        """
        사양의 "override 저장 -> review 자동 해제".

        지우는 코드를 따로 두지 않는다 - 확인이 다른 파일을 가리키게
        되므로 저절로 풀린다.
        """

        self.image("자연광.png")
        picked = self.image("무릎 운동.png", (30, 180, 90))
        self.voices(1)
        self.scan()

        scenes = self.scenes([self.WEAK])

        self.confirm(1)
        self.assertEqual(self.row(scenes)["state"], free_workspace.READY)

        self.client.put("/studio/api/review/p1/scenes/1/asset",
                        json={"path": picked})

        row = self.row(scenes)

        # 사람이 정한 것은 검토 대상이 아니므로 READY다(Sprint160).
        self.assertEqual(row["state"], free_workspace.READY)
        self.assertEqual(row["image"]["asset_source"], "override")

        # 그러나 예전 확인은 더 이상 이 파일을 가리키지 않는다.
        self.assertIsNone(row["confirmed"])

    def test_the_old_confirmation_does_not_come_back(self):
        """
        바꿨다가 되돌리면 확인이 되살아나는가.

        되살아나야 한다 - 사람이 확인한 그 상황으로 돌아온 것이다.
        지우지 않았으므로 가리키던 것이 다시 맞는다.
        """

        self.image("자연광.png")
        picked = self.image("무릎 운동.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes([self.WEAK])

        self.confirm(1)
        self.client.put("/studio/api/review/p1/scenes/1/asset",
                        json={"path": picked})

        self.assertIsNone(self.row(scenes)["confirmed"])

        self.client.delete("/studio/api/review/p1/scenes/1/asset")

        self.assertIsNotNone(self.row(scenes)["confirmed"])
        self.assertEqual(self.row(scenes)["state"], free_workspace.READY)

    def test_a_vanished_file_undoes_the_confirmation(self):
        """
        확인한 그 파일이 사라지면 확인이 풀린다.

        무엇이 걸렸는지는 고르는 쪽에 물어서 그것을 지운다 - 여기서
        짐작하면 엉뚱한 것을 지우고 테스트가 아무것도 안 보게 된다.
        """

        self.image("자연광.png")
        self.image("무릎 운동.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes([self.WEAK])
        self.confirm(1)

        picked = self.row(scenes)["image"]["path"]
        self.assertIsNotNone(self.row(scenes)["confirmed"])

        os.remove(picked)
        self.scan()

        row = self.row(scenes)

        self.assertIsNone(row["confirmed"])
        self.assertNotEqual(row["image"]["path"], picked)


class BlockedIsNotConfirmableTest(Base):
    """5. 없는 것은 확인할 수 없다."""

    def test_blocked_is_not_confirmable(self):
        """
        없는 파일을 "봤고 괜찮다"고 넘기면 렌더가 막히는데 화면은
        준비 완료라고 말한다.
        """

        self.voices(1)
        self.scan()

        scenes = self.scenes(["우주선 착륙"])

        self.assertEqual(self.row(scenes)["state"], free_workspace.BLOCKED)

        response = self.confirm(1)

        self.assertEqual(response.status_code, 400)
        self.assertIn("없", response.json()["detail"])

        self.assertEqual(self.row(scenes)["state"], free_workspace.BLOCKED)
        self.assertEqual(review_confirm.load(self.project), {})

    def test_a_confirmed_scene_that_loses_its_voice_goes_back_to_blocked(self):
        """확인해 두었어도 파일이 사라지면 막힌다."""

        scenes = self.weak_setup()
        self.confirm(1)

        os.remove(os.path.join(self.root, "voices", "scene1.wav"))
        self.scan()

        self.assertEqual(self.row(scenes)["state"], free_workspace.BLOCKED)

    def test_confirming_a_scene_that_is_not_there_is_refused(self):
        self.weak_setup()

        self.assertEqual(self.confirm(9).status_code, 404)


class NoSideEffectTest(Base):
    """6. 확인은 아무것도 바꾸지 않는다."""

    def test_nothing_external_is_called(self):
        import requests

        from app.providers import local_stock_provider, local_voice_provider
        from app.services import asset_integration_service

        scenes = self.weak_setup()

        with patch.object(
            local_stock_provider, "generate_image") as make_image, \
                patch.object(
                    local_voice_provider, "generate_voice") as make_voice, \
                patch.object(
                    asset_integration_service, "get_candidates") as stock, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            self.confirm(1)
            self.report(scenes)

            for name, mock in (("local_stock", make_image),
                               ("local_voice", make_voice),
                               ("스톡 검색", stock),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()

    def test_only_the_decision_file_is_written(self):
        scenes = self.weak_setup()

        before = set(os.listdir(self.project))

        self.report(scenes)
        self.assertEqual(set(os.listdir(self.project)), before)

        self.confirm(1)

        self.assertEqual(set(os.listdir(self.project)) - before,
                         {review_confirm.FILENAME})

    def test_the_asset_files_are_untouched(self):
        import hashlib

        scenes = self.weak_setup()
        path = os.path.join(self.root, "images", "자연광.png")

        with open(path, "rb") as f:
            before = hashlib.md5(f.read()).hexdigest()

        self.confirm(1)

        with open(path, "rb") as f:
            self.assertEqual(hashlib.md5(f.read()).hexdigest(), before)

    def test_render_still_knows_nothing_about_this(self):
        with open(scene_order.__file__, encoding="utf-8") as f:
            source = f.read()

        for word in ("confirm", "review_status", "confirmed_by"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)

    def test_render_is_not_blocked_by_an_unconfirmed_review(self):
        from app.services import asset_integration_service, scene_tts_service

        scenes = self.weak_setup()

        target = os.path.join(self.project, "images", "scene1.png")
        asset_integration_service._select_ai_first(
            scenes[0]["image_prompt"], target, "wellbeing", False,
            scene=scenes[0], provider="local_stock")

        scene_tts_service.create_scene_tts(
            scenes, self.project, provider="local_voice")

        self.assertEqual(
            scene_order.render_problems(self.project, scenes), [])

    def test_the_screen_has_the_two_buttons(self):
        source = _script_source()

        self.assertIn("confirmScene", source)
        self.assertIn("openAlternatives", source)


if __name__ == "__main__":
    unittest.main()
