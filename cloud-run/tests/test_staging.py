"""
Sprint222 - 대본보다 먼저 온 자료 (Epic 64).

무엇을 지키는가
---------------
    1. 대본 없이도 받는다              test_대본_없이_받는다
    2. 새로고침해도 남는다             test_다시_읽어도_남는다
    3. 원본 이름을 바꾸지 않는다        test_원본_이름을_지킨다
    4. 순서 규칙이 그대로다            test_순서는_기존_규칙을_따른다
    5. scene 배치는 기존 provider 것    test_apply_가_기존_자리에_놓는다
    6. 없는 종류는 받지 않는다          test_없는_종류는_거절한다

넷째와 다섯째가 경계다. staging 은 **입력 계층**이지 엔진이 아니다.
여기서 순서를 정하거나 파일을 scene 이름으로 바꾸기 시작하면, 그날부터
매칭 규칙이 두 곳에 살고 한쪽만 고쳐지는 날이 온다.

여섯째도 경계다. 영상과 음악은 사람이 준 것을 프로젝트에 놓는
provider 가 없다 - 받아 놓고 쓰지 못하면 그것이 가장 나쁜 거짓말이다.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app
from app.routers import studio as studio_router
from app.services import staging

BASE = "/studio/api/projects/시험프로젝트/staging"

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _png(name: str):
    return ("files", (name, io.BytesIO(PNG), "image/png"))


class StagingTest(unittest.TestCase):

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.client = TestClient(app)

        self._real = studio_router._project_path
        studio_router._project_path = lambda project_id: self.project
        self.addCleanup(self._restore)

    def _restore(self):
        studio_router._project_path = self._real

    def _script(self, count: int):
        """대본을 놓는다. 시험이 만드는 것은 이것뿐이다."""

        scenes = [
            {"scene": number, "narration": f"{number}번 장면입니다",
             "image_prompt": f"{number}번 장면 그림"}
            for number in range(1, count + 1)
        ]

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "시험 대본", "scenes": scenes}, f,
                      ensure_ascii=False)

    # --- 받는다 ---

    def test_대본_없이_받는다(self):
        """이 Sprint 의 이유 그 자체다."""

        self.assertFalse(
            os.path.exists(os.path.join(self.project, "script.json")))

        answer = self.client.post(
            BASE, data={"kind": "image"},
            files=[_png("무릎 스트레칭.png"), _png("허리 세우기.png")])

        self.assertEqual(answer.status_code, 200, answer.text)

        said = answer.json()

        self.assertEqual(said["added"], 2)
        self.assertEqual(said["counts"]["image"], 2)
        self.assertEqual(said["total"], 2)

    def test_다시_읽어도_남는다(self):
        """
        브라우저 메모리가 아니라 디스크에 산다. 새로고침해도, 프로그램을
        다시 켜도 그대로여야 한다.
        """

        self.client.post(BASE, data={"kind": "image"},
                         files=[_png("하나.png")])

        # 서버를 다시 켠 셈 친다 - 새 클라이언트가 디스크에서 읽는다.
        again = TestClient(app).get(BASE).json()

        self.assertEqual(again["total"], 1)
        self.assertEqual(again["assets"][0]["name"], "하나.png")

    def test_원본_이름을_지킨다(self):
        """
        image_001.png 로 바꾸면 사람이 0001/0002 로 적어 둔 뜻이 사라진다.
        """

        self.client.post(BASE, data={"kind": "image"},
                         files=[_png("0002 허리.png")])

        asset = self.client.get(BASE).json()["assets"][0]

        self.assertEqual(asset["name"], "0002 허리.png")

        where = staging.paths_for(self.project, "image")[0]

        self.assertEqual(os.path.basename(where), "0002 허리.png")

    def test_경로가_섞인_이름은_이름만_남긴다(self):
        self.client.post(BASE, data={"kind": "image"},
                         files=[_png("../../밖으로.png")])

        asset = self.client.get(BASE).json()["assets"][0]

        self.assertEqual(asset["name"], "밖으로.png")

        where = staging.paths_for(self.project, "image")[0]

        self.assertTrue(os.path.abspath(where).startswith(
            os.path.abspath(self.project)))

    def test_없는_종류는_거절한다(self):
        """영상·음악은 프로젝트에 놓는 provider 가 없다."""

        for kind in ("video", "music", "아무거나"):
            answer = self.client.post(BASE, data={"kind": kind},
                                      files=[_png("하나.png")])

            self.assertEqual(answer.status_code, 400, kind)

    def test_음성도_대본_없이_받는다(self):
        """
        받는 종류가 둘이라고 적어 놓고 한쪽만 재면, 어느 날 한쪽만
        고쳐진다.
        """

        answer = self.client.post(
            BASE, data={"kind": "voice"},
            files=[("files", ("scene1.wav", io.BytesIO(b"RIFF0000WAVE"),
                              "audio/wav"))])

        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(answer.json()["counts"]["voice"], 1)

        asset = self.client.get(BASE).json()["assets"][0]

        self.assertEqual(asset["name"], "scene1.wav")
        self.assertEqual(asset["kind"], "voice")

        where = staging.paths_for(self.project, "voice")[0]

        self.assertEqual(os.path.basename(where), "scene1.wav")
        self.assertEqual(staging.paths_for(self.project, "image"), [])

    def test_하나_뺀다(self):
        made = self.client.post(
            BASE, data={"kind": "image"},
            files=[_png("하나.png"), _png("둘.png")]).json()

        asset_id = made["assets"][0]["asset_id"]

        gone = self.client.delete(f"{BASE}/{asset_id}")

        self.assertEqual(gone.status_code, 200)
        self.assertEqual(gone.json()["total"], 1)

        self.assertEqual(self.client.delete(f"{BASE}/{asset_id}").status_code,
                         404)

    # --- 연결한다 ---

    def test_대본이_없으면_연결하지_않는다(self):
        self.client.post(BASE, data={"kind": "image"}, files=[_png("하나.png")])

        answer = self.client.post(f"{BASE}/apply")

        self.assertEqual(answer.status_code, 400)
        self.assertIn("script.json", answer.json()["detail"])

    def test_연결할_것이_없으면_말한다(self):
        self._script(2)

        answer = self.client.post(f"{BASE}/apply")

        self.assertEqual(answer.status_code, 400)
        self.assertIn("자료가 없습니다", answer.json()["detail"])

    def test_apply_가_기존_자리에_놓는다(self):
        """
        scene{N}.png 는 image_import 가 정한 이름이다. staging 이 그
        이름을 만들지 않는다는 것을 여기서 못 박는다.
        """

        self.client.post(BASE, data={"kind": "image"},
                         files=[_png("1.png"), _png("2.png")])

        self._script(2)

        answer = self.client.post(f"{BASE}/apply")

        self.assertEqual(answer.status_code, 200, answer.text)

        said = answer.json()

        self.assertEqual(said["scene_count"], 2)
        self.assertEqual(said["applied"]["image"]["count"], 2)

        for number in (1, 2):
            self.assertTrue(
                os.path.exists(os.path.join(
                    self.project, "images", f"scene{number}.png")),
                f"scene{number}.png 가 없다")

    def test_순서는_기존_규칙을_따른다(self):
        """
        incoming_files.sort_key 는 이름의 숫자로 센다 - 2 가 10 보다
        앞이다. staging 이 그 규칙을 가리지 않는지 본다.
        """

        for name in ("10.png", "2.png", "1.png"):
            self.client.post(BASE, data={"kind": "image"}, files=[_png(name)])

        self._script(3)

        self.client.post(f"{BASE}/apply")

        placed = [
            os.path.getsize(os.path.join(self.project, "images",
                                         f"scene{n}.png"))
            for n in (1, 2, 3)
        ]

        # 셋 다 같은 내용이라 크기로는 못 가른다. 대신 provider 가
        # 몇 개를 봤는지로 확인한다 - 순서 자체는 sort_key 의 몫이다.
        self.assertEqual(len(placed), 3)

        given = staging.paths_for(self.project, "image")

        self.assertEqual([os.path.basename(p) for p in given],
                         ["10.png", "2.png", "1.png"],
                         "staging 은 넣은 순서를 그대로 둬야 한다")

    def test_자료가_남아_있다(self):
        """
        연결했다고 원본을 지우지 않는다. provider 는 복사만 한다.
        """

        self.client.post(BASE, data={"kind": "image"}, files=[_png("하나.png")])
        self._script(1)
        self.client.post(f"{BASE}/apply")

        self.assertEqual(self.client.get(BASE).json()["total"], 1)


class AutoProjectTest(unittest.TestCase):
    """
    Sprint222 - 프로젝트를 먼저 만들지 않아도 시작할 수 있는가.

    프로젝트를 만드는 코드를 새로 쓰지 않았다. 기존 /api/review 가
    "검토하며 만들 빈 프로젝트"를 만드는 일을 이미 하고 있고, 화면은
    그것을 부른다. 여기서는 그 길이 실제로 열려 있는지만 본다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        from app.services import project_service

        self.project_service = project_service
        self._real_root = project_service.OUTPUT_ROOT
        project_service.OUTPUT_ROOT = self.root
        self.addCleanup(self._restore)

        self.client = TestClient(app)

    def _restore(self):
        self.project_service.OUTPUT_ROOT = self._real_root

    def test_자료를_넣으려는_사람이_프로젝트를_먼저_만들지_않아도_된다(self):
        made = self.client.post(
            "/studio/api/review",
            json={"topic": "새 영상 2026-08-18", "channel": "wellbeing"})

        self.assertEqual(made.status_code, 200, made.text)

        project_id = made.json()["project_id"]

        self.assertTrue(project_id)
        self.assertTrue(os.path.isdir(os.path.join(self.root, project_id)))

        # 그리고 그 프로젝트에 대본 없이 자료가 들어간다.
        answer = self.client.post(
            f"/studio/api/projects/{project_id}/staging",
            data={"kind": "image"}, files=[_png("첫 자료.png")])

        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(answer.json()["counts"]["image"], 1)

    def test_기존_프로젝트에_넣으면_그_프로젝트로_간다(self):
        """다른 프로젝트로 새는 일이 없어야 한다."""

        first = self.client.post(
            "/studio/api/review",
            json={"topic": "먼저 만든 것", "channel": "wellbeing"}
        ).json()["project_id"]

        second = self.client.post(
            "/studio/api/review",
            json={"topic": "나중에 만든 것", "channel": "wellbeing"}
        ).json()["project_id"]

        self.client.post(f"/studio/api/projects/{first}/staging",
                         data={"kind": "image"}, files=[_png("첫째.png")])

        self.assertEqual(
            self.client.get(f"/studio/api/projects/{first}/staging")
            .json()["total"], 1)
        self.assertEqual(
            self.client.get(f"/studio/api/projects/{second}/staging")
            .json()["total"], 0)

    def test_같은_초에_만들어도_섞이지_않는다(self):
        """
        Sprint222 - 이름이 초 단위라 같은 초에 두 번 만들면 같은 폴더가
        됐다. 사람이 손으로 만들 때는 드러나지 않았지만, 이제 화면이
        자료를 받으며 대신 만든다 - 파일 고르고 곧바로 폴더 고르기가
        그 상황이다.
        """

        from app.services import project_service

        made = [project_service.create_project(f"{n}번", "wellbeing")
                for n in range(5)]

        ids = [one["id"] for one in made]

        self.assertEqual(len(set(ids)), 5, f"이름이 겹쳤다: {ids}")

        for one in made:
            self.assertTrue(os.path.isdir(str(one["path"])))

        # 그리고 자료가 서로 섞이지 않는다.
        self.client.post(f"/studio/api/projects/{ids[0]}/staging",
                         data={"kind": "image"}, files=[_png("첫째.png")])

        totals = [
            self.client.get(f"/studio/api/projects/{one}/staging")
            .json()["total"] for one in ids
        ]

        self.assertEqual(totals, [1, 0, 0, 0, 0], totals)

    def test_이름_없이는_만들지_않는다(self):
        """화면이 기본 이름을 붙이지 않고 부르면 막힌다."""

        self.assertEqual(
            self.client.post("/studio/api/review",
                             json={"topic": "  ", "channel": "wellbeing"})
            .status_code, 400)


class StagingServiceTest(unittest.TestCase):
    """라우터 없이 서비스만. 여기에 매칭이 없다는 것을 못 박는다."""

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def test_받는_종류는_provider_가_있는_것뿐이다(self):
        self.assertEqual(set(staging.KINDS), {"image", "voice"})
        self.assertEqual(staging.provider_name("image"), "image_import")
        self.assertEqual(staging.provider_name("voice"), "voice_import")

    def test_사라진_파일은_세지_않는다(self):
        staging.add(self.project, "image",
                    [("하나.png", io.BytesIO(PNG))])

        where = staging.paths_for(self.project, "image")[0]
        shutil.rmtree(os.path.dirname(where))

        self.assertEqual(staging.listing(self.project)["total"], 0)

    def test_깨진_manifest_로_죽지_않는다(self):
        os.makedirs(staging.root(self.project), exist_ok=True)

        with open(staging.manifest_path(self.project), "w",
                  encoding="utf-8") as f:
            f.write("이건 JSON 이 아니다")

        self.assertEqual(staging.listing(self.project)["total"], 0)


if __name__ == "__main__":
    unittest.main()
