"""
Sprint65 - 라우터 계약 정합성.

라우터가 서비스 함수의 필수 인자를 빠뜨리면 그 엔드포인트는 "존재하지만
호출하는 순간 TypeError"가 된다. 서비스 시그니처는 스프린트마다 바뀌는데
라우터는 아무도 부르지 않아 조용히 남아 있었다 - 실제로 4개가 그랬다
(merge_video_audio / generate_image / create_tts / build_video).

이 파일은 그 부류를 통째로 막는 장치다.

  - ENDPOINTS 표가 등록된 모든 엔드포인트를 덮는지 먼저 확인한다.
    라우터를 새로 붙이면 표에 넣기 전까지 테스트가 실패한다.
  - 각 엔드포인트를 실제로 호출하되, 서비스는 autospec=True로 패치한다.
    autospec은 원본 시그니처를 그대로 강제하므로, 라우터가 인자를
    빠뜨리면 mock 단계에서 바로 TypeError가 난다 - 실제 서비스(Gemini/
    ffmpeg)를 부르지 않고도 계약 불일치를 잡는다.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from fastapi.testclient import TestClient

from app.main import app
from app.services import project_service


PROJECT_ID = "20260805_120000"


# (method, path, 유효 payload, autospec으로 패치할 서비스 경로들)
ENDPOINTS = [
    ("GET", "/", None, []),
    ("GET", "/health", None, []),
    ("GET", "/test-ai", None, ["app.routers.video.test_connection"]),
    ("POST", "/generate-video", {"prompt": "p"},
     ["app.routers.video.generate_video"]),
    ("POST", "/generate-script", {"topic": "t"},
     ["app.routers.script.generate_script"]),
    ("POST", "/generate-scenes", {"script": "s"},
     ["app.routers.scene.generate_scenes"]),
    ("POST", "/generate-topics", {"category": "c", "count": 3},
     ["app.routers.topic.generate_topics"]),
    ("POST", "/generate-short-video", {"topic": "t"},
     ["app.routers.factory.generate_short_video"]),
    ("POST", "/generate-batch", {"topics": ["t1", "t2"]},
     ["app.routers.batch.generate_short_video"]),
    ("POST", "/generate-image", {"prompt": "p", "project_id": PROJECT_ID},
     ["app.routers.image.generate_image"]),
    ("POST", "/generate-tts", {"script": "s", "project_id": PROJECT_ID},
     ["app.routers.tts.create_tts"]),
    ("POST", "/build-video", {"project_id": PROJECT_ID},
     ["app.routers.video_builder.build_video"]),
    ("POST", "/merge-video", {"project_id": PROJECT_ID},
     ["app.routers.final_video.merge_video_audio"]),
]


class RouterContractTestCase(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.tmp_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp_dir, PROJECT_ID))

        patcher = patch.object(project_service, "OUTPUT_ROOT", self.tmp_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp_dir, True)

    def call(self, method, path, payload, services):
        """서비스를 autospec으로 패치한 채 엔드포인트를 호출한다."""

        patchers = [patch(target, autospec=True) for target in services]
        mocks = [p.start() for p in patchers]

        for p in patchers:
            self.addCleanup(p.stop)

        if method == "GET":
            response = self.client.get(path)
        else:
            response = self.client.post(path, json=payload)

        return response, mocks


class TestEveryEndpointIsCovered(RouterContractTestCase):

    def test_table_covers_all_registered_endpoints(self):
        registered = {
            (method.upper(), path)
            for path, operations in app.openapi()["paths"].items()
            for method in operations
        }

        covered = {(method, path) for method, path, _, _ in ENDPOINTS}

        self.assertEqual(
            registered - covered,
            set(),
            "계약 테스트가 없는 엔드포인트가 있습니다",
        )

        self.assertEqual(
            covered - registered,
            set(),
            "등록되지 않은 엔드포인트가 표에 남아 있습니다",
        )


class TestValidRequestsNeverRaiseTypeError(RouterContractTestCase):
    """라우터가 서비스를 부를 때 인자 개수/이름이 맞는지 확인한다.
    autospec 덕분에 불일치는 곧바로 TypeError로 드러난다."""

    def test_all_endpoints_accept_a_valid_request(self):
        for method, path, payload, services in ENDPOINTS:
            with self.subTest(endpoint=f"{method} {path}"):
                response, mocks = self.call(method, path, payload, services)

                self.assertEqual(
                    response.status_code, 200,
                    f"{method} {path} -> {response.status_code} "
                    f"{response.text[:200]}",
                )

                for mock in mocks:
                    self.assertTrue(
                        mock.called,
                        f"{method} {path}가 서비스를 호출하지 않았습니다",
                    )


class TestProjectScopedEndpointsValidateInput(RouterContractTestCase):
    """project_id를 받는 엔드포인트의 오류 응답 계약."""

    PROJECT_SCOPED = [
        ("/merge-video", {}),
        ("/build-video", {}),
        ("/generate-tts", {"script": "s"}),
        ("/generate-image", {"prompt": "p"}),
    ]

    SERVICES = {
        "/merge-video": "app.routers.final_video.merge_video_audio",
        "/build-video": "app.routers.video_builder.build_video",
        "/generate-tts": "app.routers.tts.create_tts",
        "/generate-image": "app.routers.image.generate_image",
    }

    def test_missing_project_id_returns_422(self):
        for path, base in self.PROJECT_SCOPED:
            with self.subTest(path=path):
                response = self.client.post(path, json=base)
                self.assertEqual(response.status_code, 422)

    def test_unknown_project_id_returns_404(self):
        for path, base in self.PROJECT_SCOPED:
            with self.subTest(path=path):
                with patch(self.SERVICES[path], autospec=True):
                    response = self.client.post(
                        path, json={**base, "project_id": "20990101_000000"},
                    )
                self.assertEqual(response.status_code, 404)

    def test_path_traversal_project_id_returns_400(self):
        for path, base in self.PROJECT_SCOPED:
            for bad_id in ("../etc", "a/b", "..", "", "C:\\Windows"):
                with self.subTest(path=path, project_id=bad_id):
                    with patch(self.SERVICES[path], autospec=True):
                        response = self.client.post(
                            path, json={**base, "project_id": bad_id},
                        )
                    self.assertIn(response.status_code, (400, 422))

    def test_service_never_runs_for_a_rejected_project_id(self):
        for path, base in self.PROJECT_SCOPED:
            with self.subTest(path=path):
                with patch(self.SERVICES[path], autospec=True) as service:
                    self.client.post(
                        path, json={**base, "project_id": "../escape"},
                    )
                    self.assertFalse(service.called)


class TestResolveProjectPath(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, True)
        os.makedirs(os.path.join(self.tmp_dir, PROJECT_ID))

        patcher = patch.object(project_service, "OUTPUT_ROOT", self.tmp_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_resolves_an_existing_project(self):
        path = project_service.resolve_project_path(PROJECT_ID)
        self.assertTrue(os.path.isdir(path))
        self.assertTrue(os.path.abspath(path).startswith(
            os.path.abspath(self.tmp_dir)
        ))

    def test_rejects_separators_and_parent_references(self):
        for bad in ("../etc", "a/b", "a\\b", "..", "", "   ", "C:\\Windows"):
            with self.subTest(project_id=bad):
                with self.assertRaises(ValueError):
                    project_service.resolve_project_path(bad)

    def test_missing_project_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            project_service.resolve_project_path("20990101_000000")


if __name__ == "__main__":
    unittest.main()
