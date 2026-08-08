"""
Sprint167 - 처음부터 끝까지 실제로 밟아 본다 (Epic 57, Phase 18).

Sprint150~166이 무료 제작을 조각으로 만들었다. 조각마다 테스트가
있지만, 조각 사이가 이어지는지는 아무도 보지 않았다.

여기서는 새 기능을 만들지 않는다. 사람이 브라우저에서 누르는 그
순서대로 엔드포인트를 부르고, 중간에 끊거나 망가뜨려 본다.

왜 화면이 부르는 것만 쓰는가
----------------------------
서비스 함수를 직접 부르면 라우터가 빠뜨린 자리를 못 본다. 사람이
겪는 것은 HTTP이고, 그 길로만 가야 실제로 이어지는지 알 수 있다.

프로젝트는 진짜로 만든다
------------------------
_project_path를 가짜로 바꾸지 않는다. create_project가 output/ 아래에
실제로 만들고, 끝나면 지운다 - 그래야 경로 해석까지 함께 검증된다.

다만 내 자료 폴더를 적어 두는 자리는 바꾼다. 실제 자리에 쓰면 이
컴퓨터를 쓰는 사람이 정해 둔 폴더를 지우게 된다.

무엇을 지키는가
---------------
    1. 처음부터 끝까지 이어진다   test_free_mode_full_journey
    2. 다시 열어도 남아 있다      test_free_mode_survives_reload
    3. 모자란 것을 말한다         test_free_mode_reports_missing_assets
    4. 고치면 따라온다            test_free_mode_recheck_after_file_change
    5. Provider를 바꿀 수 있다    test_free_mode_provider_switch
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
from app.services import audio_policy, free_workspace, output_check


def _png(path, color=(200, 30, 30)):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (1080, 1920), color).save(path)


def _wav(path, seconds=1.5):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}"]
        + audio_policy.pcm_output_args() + [path],
        capture_output=True, check=True,
    )


def _mp4(path, seconds=4.5):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c=cyan:s=1080x1920:d={seconds}",
         "-f", "lavfi", "-i", f"sine=f=440:d={seconds}",
         "-pix_fmt", "yuv420p", "-shortest", path],
        capture_output=True, check=True,
    )


class Journey(unittest.TestCase):
    """사람이 누르는 그 순서대로만 부른다."""

    TOPIC = "40대 허리 건강 운동"

    ACTIONS = ["무릎 스트레칭", "허리 세우기", "공원 걷기"]
    PLACES = ["거실", "침실", "공원"]

    def setUp(self):
        self.workspace = tempfile.mkdtemp(prefix="ws_")
        self.store = os.path.join(
            tempfile.mkdtemp(), ".workflow", "free_workspace.json")

        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.addCleanup(
            shutil.rmtree, os.path.dirname(os.path.dirname(self.store)),
            ignore_errors=True)

        # 내 자료 폴더를 적어 두는 자리만 바꾼다. 실제 자리에 쓰면 이
        # 컴퓨터를 쓰는 사람이 정해 둔 폴더를 지우게 된다.
        self._real_store = studio_router._workspace_store
        studio_router._workspace_store = lambda: self.store
        self.addCleanup(self._restore)

        self.client = TestClient(app)
        self.project_id = None
        self.project = None

    def _restore(self):
        studio_router._workspace_store = self._real_store

    # ---- 사람이 누르는 것들 -------------------------------------------

    def choose_workspace(self, root=None):
        return self.client.put("/studio/api/workspace",
                               json={"root": root or self.workspace})

    def build_prompt(self, topic=None):
        return self.client.post("/studio/api/script-prompt",
                                json={"topic": topic or self.TOPIC,
                                      "scene_count": 3})

    def preview(self, raw):
        return self.client.post("/studio/api/production/import",
                                json={"raw": raw, "topic": self.TOPIC})

    def create(self, raw):
        response = self.client.post(
            "/studio/api/production/project",
            json={"raw": raw, "topic": self.TOPIC, "channel": "wellbeing",
                  "source": "import"})

        if response.status_code == 200:
            self.project_id = response.json()["project_id"]
            self.project = response.json()["project_path"]
            self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        return response

    def pick_free_providers(self):
        return self.client.put(
            f"/studio/api/review/{self.project_id}/providers",
            json={"providers": {"image": "local_stock",
                                "voice": "local_voice"}})

    def scan(self):
        return self.client.post(
            f"/studio/api/review/{self.project_id}/library", json={})

    def preparation(self):
        return self.client.get(
            f"/studio/api/review/{self.project_id}/preparation").json()

    def requirements(self):
        return self.client.get(
            f"/studio/api/review/{self.project_id}/requirements").json()

    def final_check(self):
        return self.client.get(
            f"/studio/api/review/{self.project_id}/final-check").json()

    def output(self):
        return self.client.get(
            f"/studio/api/review/{self.project_id}/output-check").json()

    def completion(self):
        return self.client.get(
            f"/studio/api/review/{self.project_id}/completion").json()

    def confirm(self, number):
        return self.client.post(
            f"/studio/api/review/{self.project_id}/scenes/{number}/confirm")

    def choose_asset(self, number, path):
        return self.client.put(
            f"/studio/api/review/{self.project_id}/scenes/{number}/asset",
            json={"path": path})

    # ---- 재료 ----------------------------------------------------------

    def answer(self, count=3):
        """요청문이 적어 준 뼈대를 그대로 채운 답."""

        return json.dumps({
            "title": "40대 허리, 이 동작 하나면 됩니다",
            "hook": "허리가 아프신가요?",
            "script": "전체 대본",
            "character": "40대 남성",
            "scenes": [
                {"scene": n, "narration": f"{n}번째 문장입니다.",
                 "subject": "40대 남성", "action": self.ACTIONS[n - 1],
                 "environment": self.PLACES[n - 1], "camera": "미디엄 샷",
                 "composition": "중앙", "lighting": "자연광"}
                for n in range(1, count + 1)
            ],
        }, ensure_ascii=False)

    def fill_workspace(self, images=(), voices=()):
        for name in images:
            _png(os.path.join(self.workspace, "images", name))

        for number in voices:
            _wav(os.path.join(self.workspace, "voices", f"scene{number}.wav"))

    def produce(self, scenes=None, seconds=4.5):
        """이미지·음성·자막·영상을 만든다. 렌더가 끝난 뒤의 자리다."""

        from app.services import asset_integration_service, scene_tts_service

        with open(os.path.join(self.project, "script.json"),
                  encoding="utf-8") as f:
            scenes = scenes or json.load(f)["scenes"]

        for scene in scenes:
            target = os.path.join(
                self.project, "images", f"scene{scene['scene']}.png")

            asset_integration_service._select_ai_first(
                scene["image_prompt"], target, "wellbeing", False,
                scene=scene, provider="local_stock")

        scene_tts_service.create_scene_tts(
            scenes, self.project, provider="local_voice")

        srt = os.path.join(self.project, "subtitle", "subtitle.srt")
        os.makedirs(os.path.dirname(srt), exist_ok=True)

        with open(srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,500\n첫 문장\n")

        _mp4(os.path.join(self.project, "video", "final_short.mp4"), seconds)

        return scenes

    def ready_project(self):
        """제작할 수 있는 상태까지 만들어 둔다."""

        self.fill_workspace(
            images=[f"{name}.png" for name in self.ACTIONS],
            voices=(1, 2, 3),
        )

        self.choose_workspace()
        self.create(self.answer(3))
        self.pick_free_providers()
        self.scan()


class FullJourneyTest(Journey):
    """1. 처음부터 끝까지 이어진다."""

    def test_free_mode_full_journey(self):
        # STEP 1 - 내 자료 폴더
        self.fill_workspace(
            images=[f"{name}.png" for name in self.ACTIONS],
            voices=(1, 2, 3),
        )

        chosen = self.choose_workspace()

        self.assertEqual(chosen.status_code, 200)
        self.assertEqual(chosen.json()["counts"]["images"], 3)
        self.assertEqual(chosen.json()["counts"]["voice"], 3)

        # STEP 2 - 요청문
        prompt = self.build_prompt()

        self.assertEqual(prompt.status_code, 200)
        self.assertIn(self.TOPIC, prompt.json()["prompt"])

        # STEP 3 - 붙여넣기
        raw = self.answer(3)

        self.assertEqual(self.preview(raw).json()["scene_count"], 3)
        self.assertEqual(self.create(raw).status_code, 200)

        # STEP 4 - 무료 Provider
        self.assertEqual(self.pick_free_providers().status_code, 200)
        self.assertEqual(self.scan().status_code, 200)

        # STEP 5 - 준비 상태
        prepared = self.preparation()

        self.assertEqual(prepared["state"], free_workspace.READY)
        self.assertEqual(prepared["counts"],
                         {"ready": 3, "review": 0, "blocked": 0})

        # 아직 만들지 않았으니 렌더는 막힌다 - 자료는 다 있는데도.
        check = self.final_check()

        self.assertFalse(check["can_render"])
        self.assertEqual(check["assets"]["state"], free_workspace.READY)
        self.assertTrue(check["outputs"])

        # STEP 6 - 만든다
        self.produce()

        check = self.final_check()

        self.assertTrue(check["can_render"])
        self.assertEqual(check["state"], free_workspace.READY)

        # STEP 7 - 렌더. 관문을 지나 작업이 걸리는 데까지 본다 -
        # 실제 인코딩은 Sprint146이 이미 실측했다.
        with patch.object(studio_router.studio_jobs, "start") as start:
            start.return_value = "job1"

            rendered = self.client.post(
                f"/studio/api/review/{self.project_id}/render")

        self.assertEqual(rendered.status_code, 200)
        self.assertTrue(start.called)

        # STEP 8 - 결과 확인
        result = self.output()

        self.assertEqual(result["state"], output_check.READY)
        self.assertEqual(result["scenes"], {"ready": 3, "total": 3})
        self.assertEqual(result["voices"], {"ready": 3, "total": 3})
        self.assertTrue(result["subtitle"]["exists"])
        self.assertAlmostEqual(result["video"]["seconds"], 4.5, delta=0.3)

        # STEP 9 - 무엇으로 만들어졌는가
        report = self.completion()

        self.assertEqual(report["script"]["source"], "import")
        self.assertEqual(report["image"]["provider"], "local_stock")
        self.assertEqual(report["voice"]["provider"], "local_voice")
        self.assertTrue(report["cost"]["no_api_call"])
        self.assertEqual(report["output"]["state"], output_check.READY)

        # 값어치를 말하지 않는다.
        text = json.dumps(report, ensure_ascii=False)

        for word in ("무료", "저렴", "가성비", "추천", "점수"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_the_journey_calls_no_model(self):
        """전 구간에서 모델을 한 번도 부르지 않는다."""

        import requests

        from app.services import asset_integration_service

        self.fill_workspace(
            images=[f"{name}.png" for name in self.ACTIONS],
            voices=(1, 2, 3),
        )

        with patch.object(
            asset_integration_service, "get_candidates") as stock, \
                patch.object(
                    asset_integration_service.best_of_n_service,
                    "generate_candidates") as imagen, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            self.choose_workspace()
            self.build_prompt()

            raw = self.answer(3)
            self.preview(raw)
            self.create(raw)
            self.pick_free_providers()
            self.scan()
            self.preparation()
            self.requirements()
            self.produce()
            self.final_check()
            self.output()
            self.completion()

            for name, mock in (("스톡 검색", stock), ("Imagen", imagen),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()


class SurvivesReloadTest(Journey):
    """2. 다시 열어도 남아 있다."""

    def test_free_mode_survives_reload(self):
        self.ready_project()

        picked = os.path.join(self.workspace, "images", "공원 걷기.png")

        self.choose_asset(1, picked)
        self.produce()

        before = self.completion()

        # 브라우저를 새로 연다 - 화면이 든 것은 아무것도 없다.
        fresh = TestClient(app)

        self.assertEqual(
            fresh.get("/studio/api/workspace").json()["root"], self.workspace)

        after = fresh.get(
            f"/studio/api/review/{self.project_id}/completion").json()

        self.assertEqual(after["image"]["provider"], "local_stock")
        self.assertEqual(after["voice"]["provider"], "local_voice")
        self.assertEqual(after["script"]["source"], "import")

        row = {r["scene"]: r for r in after["scene_rows"]}[1]

        self.assertEqual(row["image_source"], before["scene_rows"][0]
                         ["image_source"])

    def test_it_survives_a_server_restart(self):
        """
        서버를 다시 띄워도 남는다.

        프로세스 안의 값이 아니라 파일에 적혀 있어야 한다 - 등록소를
        비워 처음 뜬 것처럼 만든다.
        """

        self.ready_project()

        self.confirm_all_reviews()
        self.produce()

        # 프로세스가 들고 있던 것을 버린다.
        studio_router._production_registry = None

        fresh = TestClient(app)

        workspace = fresh.get("/studio/api/workspace").json()

        self.assertEqual(workspace["root"], self.workspace)

        report = fresh.get(
            f"/studio/api/review/{self.project_id}/completion").json()

        self.assertTrue(report["cost"]["no_api_call"])
        self.assertEqual(report["output"]["state"], output_check.READY)

    def confirm_all_reviews(self):
        for row in self.preparation()["scenes"]:
            if row["state"] == free_workspace.REVIEW:
                self.confirm(row["scene"])

    def test_an_unsaved_change_is_simply_not_there(self):
        """
        저장하지 않은 것은 남지 않는다.

        화면이 들고 있던 초안은 서버에 오지 않았으므로, 다시 열면
        없다. 그것이 맞다 - 저장하지 않은 것이 저장된 것처럼 보이면
        사람은 무엇이 진짜인지 알 수 없다.
        """

        self.ready_project()

        picked = os.path.join(self.workspace, "images", "공원 걷기.png")

        # 고르기는 눌러야 서버에 온다. 누르지 않았다.
        row = {r["scene"]: r for r in self.preparation()["scenes"]}[1]

        self.assertNotEqual(row["image"]["path"], picked)
        self.assertEqual(row["image"]["asset_source"], "matched")

        # 누르면 그때 남는다.
        self.choose_asset(1, picked)

        row = {r["scene"]: r for r in self.preparation()["scenes"]}[1]

        self.assertEqual(row["image"]["asset_source"], "override")


class MissingAssetsTest(Journey):
    """3. 모자란 것을 말한다."""

    def test_free_mode_reports_missing_assets(self):
        # 폴더가 없으면 고를 수 없다.
        missing = self.choose_workspace(
            os.path.join(self.workspace, "없는폴더"))

        self.assertEqual(missing.status_code, 400)

        # 이미지 하나, 음성 하나만 둔다.
        self.fill_workspace(images=["무릎 스트레칭.png"], voices=(1,))
        self.choose_workspace()
        self.create(self.answer(3))
        self.pick_free_providers()
        self.scan()

        prepared = self.preparation()

        self.assertEqual(prepared["state"], free_workspace.BLOCKED)
        self.assertEqual(prepared["counts"]["blocked"], 2)

        missing_text = " ".join(prepared["missing"])

        self.assertIn("Scene 2 이미지", missing_text)
        self.assertIn("Scene 3 음성", missing_text)

        # 무엇을 어디에 넣으면 되는지도 말한다.
        rows = self.requirements()["requirements"]
        need = [r for r in rows if r["status"] == "missing"][0]

        self.assertTrue(need["expected_path"])
        self.assertTrue(need["expected_root"])

        # 확인으로 넘길 수 없다.
        self.assertEqual(self.confirm(2).status_code, 400)

        # 렌더도 막힌다.
        self.assertFalse(self.final_check()["can_render"])

        blocked = self.client.post(
            f"/studio/api/review/{self.project_id}/render")

        self.assertEqual(blocked.status_code, 400)

    def test_a_weak_match_is_review_not_blocked(self):
        """
        약하게 걸린 것은 막지 않는다. 말하고 사람이 정한다.

        파일 이름은 "남성"으로 둔다 - 낱말은 앞에서 여덟 개만 쓰므로
        (Sprint156, 추출기가 쓰는 그 한도), 뒤쪽 요소인 "자연광"은
        Scene에 따라 잘려 나간다. 세 Scene에 모두 걸리는 것을 써야
        "약한 매칭"만 남는 상태가 된다.
        """

        self.fill_workspace(images=["남성.png"], voices=(1, 2, 3))
        self.choose_workspace()
        self.create(self.answer(3))
        self.pick_free_providers()
        self.scan()

        prepared = self.preparation()

        self.assertEqual(prepared["state"], free_workspace.REVIEW)
        self.assertEqual(prepared["counts"]["review"], 3)
        self.assertEqual(prepared["missing"], [])

        # 확인하면 열린다.
        for number in (1, 2, 3):
            self.assertEqual(self.confirm(number).status_code, 200)

        self.assertEqual(self.preparation()["state"], free_workspace.READY)


class RecheckAfterChangeTest(Journey):
    """4. 고치면 따라온다."""

    def test_free_mode_recheck_after_file_change(self):
        self.ready_project()
        self.produce()

        self.assertEqual(self.output()["state"], output_check.READY)

        # 결과 파일을 지운다.
        os.remove(os.path.join(self.project, "images", "scene2.png"))

        result = self.output()

        self.assertEqual(result["state"], output_check.REVIEW)
        self.assertEqual(result["issues"][0]["scene"], 2)
        self.assertEqual(result["issues"][0]["kind"], "image")

        # 보고서도 따라온다.
        self.assertEqual(
            self.completion()["output"]["state"], output_check.REVIEW)

        # 손으로 되돌린다.
        _png(os.path.join(self.project, "images", "scene2.png"))

        self.assertEqual(self.output()["state"], output_check.READY)
        self.assertEqual(
            self.completion()["output"]["state"], output_check.READY)

    def test_a_lost_video_is_failed_and_comes_back(self):
        self.ready_project()
        self.produce()

        video = os.path.join(self.project, "video", "final_short.mp4")
        os.remove(video)

        self.assertEqual(self.output()["state"], output_check.FAILED)

        _mp4(video, 4.5)

        self.assertEqual(self.output()["state"], output_check.READY)

    def test_rechecking_writes_nothing(self):
        self.ready_project()
        self.produce()

        before = sorted(os.listdir(self.project))

        for _ in range(3):
            self.output()
            self.completion()

        self.assertEqual(sorted(os.listdir(self.project)), before)


class ProviderSwitchTest(Journey):
    """5. Provider를 바꿀 수 있다."""

    def test_free_mode_provider_switch(self):
        self.ready_project()
        self.produce()

        report = self.completion()

        self.assertEqual(report["image"]["provider"], "local_stock")
        self.assertTrue(report["cost"]["no_api_call"])

        # API Provider로 바꾼다.
        switched = self.client.put(
            f"/studio/api/review/{self.project_id}/providers",
            json={"providers": {"image": "flux", "voice": "elevenlabs"}})

        self.assertEqual(switched.status_code, 200)

        report = self.completion()

        self.assertEqual(report["image"]["provider"], "flux")
        self.assertEqual(report["voice"]["provider"], "elevenlabs")
        self.assertFalse(report["cost"]["no_api_call"])
        self.assertTrue(report["cost"]["stages"]["image"]["calls_api"])

        # 다시 무료로 돌아올 수 있다.
        self.assertEqual(self.pick_free_providers().status_code, 200)

        report = self.completion()

        self.assertEqual(report["image"]["provider"], "local_stock")
        self.assertTrue(report["cost"]["no_api_call"])

    def test_switching_does_not_touch_the_files(self):
        """고른 것을 바꿔도 만들어 둔 것은 그대로다."""

        import hashlib

        self.ready_project()
        self.produce()

        target = os.path.join(self.project, "images", "scene1.png")

        with open(target, "rb") as f:
            before = hashlib.md5(f.read()).hexdigest()

        self.client.put(
            f"/studio/api/review/{self.project_id}/providers",
            json={"providers": {"image": "flux"}})

        with open(target, "rb") as f:
            self.assertEqual(hashlib.md5(f.read()).hexdigest(), before)

    def test_an_unknown_provider_is_refused(self):
        self.ready_project()

        response = self.client.put(
            f"/studio/api/review/{self.project_id}/providers",
            json={"providers": {"image": "그런거없음"}})

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
