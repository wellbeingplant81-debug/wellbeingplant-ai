"""
Sprint80 - Studio 라우터 계약.

가장 중요한 것은 "엔진을 건드리지 않는다"이다. 이 라우터는 화면을
내려 주고 디스크의 산출물을 읽을 뿐이며, 생성은 기존
factory_service를 그대로 부른다.

경로 안전은 새로 만들지 않고 Sprint65의 resolve_project_path를 쓴다 -
요청 하나로 output 밖을 가리키는 것을 막는 지점이 두 곳이 되면 한쪽만
고쳐지는 날이 온다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from fastapi.testclient import TestClient

from app.main import app
from app.services import studio_jobs


client = TestClient(app)


class TestStudioPage(unittest.TestCase):

    def test_the_page_is_served(self):
        response = client.get("/studio")

        self.assertEqual(response.status_code, 200)
        self.assertIn("AI 영상제작소", response.text)

    def test_the_page_declares_the_panels_the_epic_asked_for(self):
        text = client.get("/studio").text

        for panel in ("Pipeline Progress", "Scene Explorer", "Console",
                      "Quality", "Thumbnail", "Video Preview",
                      "Asset Inspector", "Upload", "Analytics"):
            with self.subTest(panel=panel):
                self.assertIn(panel, text)

    def test_upload_runtime_is_shown_as_not_connected(self):
        """Sprint80에는 "youtube_provider.py가 0바이트"라고 적혀 있었다.
        Sprint89에서 OneDrive의 검증된 Upload Core를 이식했으므로 그
        문구는 더 이상 사실이 아니다.

        지켜야 할 계약은 그대로다 - 없는 능력을 있는 것처럼 보이지
        않는다. 지금 사실은 "인증은 되지만 Upload Runtime은 아직
        연결되지 않았다"이고, 화면이 그렇게 말해야 한다.
        """

        text = client.get("/studio").text

        self.assertIn("Upload Runtime은 아직 연결되지 않았습니다", text)
        self.assertIn("실제 업로드는 일어나지 않습니다", text)

    def test_the_oauth_panel_is_present(self):
        text = client.get("/studio").text

        self.assertIn("YouTube 연결", text)
        self.assertIn("Google 로그인", text)


class TestProjectApi(unittest.TestCase):

    def test_listing_projects_returns_a_list(self):
        response = client.get("/studio/api/projects")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json()["projects"], list)

    def test_a_path_traversal_project_id_is_rejected(self):
        response = client.get("/studio/api/projects/..%2F..%2Fetc")

        self.assertIn(response.status_code, (400, 404))

    def test_an_unknown_project_is_404(self):
        response = client.get("/studio/api/projects/no_such_project_xyz")

        self.assertEqual(response.status_code, 404)

    def test_an_unknown_media_kind_is_rejected(self):
        response = client.get(
            "/studio/api/projects/no_such_project_xyz/media/passwd",
        )

        self.assertIn(response.status_code, (400, 404))


class TestJobApi(unittest.TestCase):

    def setUp(self):
        studio_jobs.reset()
        self.addCleanup(studio_jobs.reset)

    def test_an_empty_topic_is_rejected(self):
        response = client.post("/studio/api/jobs", json={"topic": "   "})

        self.assertEqual(response.status_code, 400)

    def test_starting_a_job_returns_an_id(self):
        with patch.object(studio_jobs, "start", return_value="abc123"):
            response = client.post(
                "/studio/api/jobs", json={"topic": "혈관 건강"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "abc123")

    def test_an_unknown_job_is_404(self):
        response = client.get("/studio/api/jobs/nope")

        self.assertEqual(response.status_code, 404)

    def test_a_job_reports_console_and_state(self):
        with patch.object(studio_jobs, "status", return_value={
            "found": True, "job_id": "j1", "state": "running",
            "topic": "t", "channel": "wellbeing", "project_id": None,
            "title": None, "error": None,
            "console": ["line one"], "console_next": 1,
        }):
            data = client.get("/studio/api/jobs/j1").json()

        self.assertEqual(data["state"], "running")
        self.assertEqual(data["console"], ["line one"])


class TestDatasetApi(unittest.TestCase):

    def test_the_dataset_widget_reports_readiness(self):
        data = client.get("/studio/api/dataset").json()

        self.assertIn("rows", data)
        self.assertIn("readiness", data)
        self.assertIn("ready", data["readiness"])


class TestTheEngineIsNotTouched(unittest.TestCase):
    """이 Epic의 절대 원칙."""

    def test_generation_goes_through_the_existing_factory_service(self):
        from app.services import studio_jobs as jobs

        source = open(jobs.__file__, encoding="utf-8").read()

        self.assertIn("generate_short_video", source)
        # 파이프라인을 직접 부르거나 재구현하지 않는다.
        self.assertNotIn("run_pipeline", source)
