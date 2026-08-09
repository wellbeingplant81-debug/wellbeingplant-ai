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
from app.services import project_service, studio_jobs


PROJECT_ID = "20260805_120000"

# Sprint150 - 실제로 있는 폴더가 필요한 자리에 쓴다.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Sprint158 - 실제로 있는 파일이 필요한 자리에 쓴다.
REAL_FILE = os.path.join(REPO_ROOT, "app", "static", "studio.html")


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

    # Sprint80 - Studio UI. 엔진을 부르지 않고 산출물을 읽기만 하므로
    # 패치할 서비스가 없다. 생성만 factory_service를 그대로 탄다.
    ("GET", "/studio", None, []),
    ("GET", "/studio/", None, []),
    ("GET", "/studio/api/projects", None, []),
    ("GET", "/studio/api/projects/{project_id}", None, [],
     f"/studio/api/projects/{PROJECT_ID}"),
    ("GET", "/studio/api/projects/{project_id}/media/{kind}", None, [],
     f"/studio/api/projects/{PROJECT_ID}/media/thumbnail"),
    ("GET", "/studio/api/dataset", None, []),
    ("POST", "/studio/api/jobs", {"topic": "t"},
     ["app.routers.studio.studio_jobs.start"]),
    ("GET", "/studio/api/jobs/{job_id}", None, [],
     "/studio/api/jobs/contract_job"),

    # Sprint81 - 재생성. 엔진을 그대로 부르므로 실제 호출을 막기 위해
    # orchestration 진입점만 패치한다.
    ("GET", "/studio/api/projects/{project_id}/regeneration", None, [],
     f"/studio/api/projects/{PROJECT_ID}/regeneration"),
    ("POST", "/studio/api/projects/{project_id}/regenerate", {"scenes": [2]},
     ["app.routers.studio.studio_jobs.start_regeneration"],
     f"/studio/api/projects/{PROJECT_ID}/regenerate"),

    # Sprint82 - Replay Viewer. 순수 읽기라 패치할 서비스가 없다.
    ("GET", "/studio/replay", None, []),
    ("GET", "/studio/api/replay", None, []),
    ("GET", "/studio/api/projects/{project_id}/replay", None, [],
     f"/studio/api/projects/{PROJECT_ID}/replay"),

    # Sprint90 - OAuth. status는 로컬 파일만 읽으므로 패치 없이 부른다.
    # POST는 백그라운드 작업을 띄우므로 진입점만 패치한다 - 패치하지
    # 않으면 실제 브라우저 로그인이 시작된다.
    ("GET", "/studio/api/oauth/status", None, []),
    ("POST", "/studio/api/oauth/{action}", None,
     ["app.routers.studio.studio_jobs.start_oauth"],
     "/studio/api/oauth/login"),

    # Sprint84 - Production Queue. 승인은 workflow 상태만 바꾸므로
    # 엔진을 부르지 않는다.
    ("GET", "/studio/queue", None, []),
    ("GET", "/studio/api/queue", None, []),
    ("POST", "/studio/api/projects/{project_id}/approve", None,
     ["app.routers.studio.studio_workflow.approve"],
     f"/studio/api/projects/{PROJECT_ID}/approve"),
    ("GET", "/studio/api/production/modes", None, []),
    # Sprint107 - 프로젝트를 실제로 만드는 엔드포인트다. create_project를
    # 패치해 디스크에 남기지 않는다 - 계약만 확인한다.
    # Sprint109 - 단계별 선택. 계획만 만들고 실행하지 않는다.
    ("GET", "/studio/api/production/stages", None, []),
    # Sprint110 - 이미지 업로드.
    ("POST", "/studio/api/production/images", None, []),
    # Sprint112 - 음성 업로드.
    ("POST", "/studio/api/production/voice", None, []),

    # Sprint121 - 승인 기반 제작. 한 단계씩 만들고 사람이 승인한다.
    # 엔진을 부르는 것들은 studio_review 쪽을 패치해 실제 호출을 막는다.
    ("POST", "/studio/api/review", {"topic": "주제"},
     ["app.routers.studio.project_service.create_project"]),
    ("GET", "/studio/api/review/{project_id}", None, [],
     f"/studio/api/review/{PROJECT_ID}"),
    ("POST", "/studio/api/review/{project_id}/script", None,
     ["app.services.studio_review.generate_script"],
     f"/studio/api/review/{PROJECT_ID}/script"),
    ("PUT", "/studio/api/review/{project_id}/providers",
     {"providers": {"voice": "current"}},
     ["app.services.provider_selection.save"],
     f"/studio/api/review/{PROJECT_ID}/providers"),
    ("PUT", "/studio/api/review/{project_id}/script",
     {"data": {"title": "t", "scenes": [
         {"scene": 1, "narration": "n", "image_prompt": "p"}]}},
     ["app.services.studio_review.save_script"],
     f"/studio/api/review/{PROJECT_ID}/script"),
    # Sprint147 - 사람이 고친 제목·설명·태그를 확정한다.
    ("PUT", "/studio/api/review/{project_id}/metadata",
     {"metadata": {"title": "t"}},
     ["app.services.publish_gate.save_edits"],
     f"/studio/api/review/{PROJECT_ID}/metadata"),
    # Sprint152 - 정해 둔 내 자료 폴더. 읽기와 정하기 둘 다 파일을
    # 건드리지 않는다 - 경로를 적어 둘 뿐이다.
    ("GET", "/studio/api/workspace", None,
     ["app.services.free_workspace.status"],
     "/studio/api/workspace",
     {"app.services.free_workspace.status": {"root": None}}),
    ("PUT", "/studio/api/workspace", {"root": REPO_ROOT},
     ["app.services.free_workspace.remember",
      "app.services.free_workspace.status"],
     "/studio/api/workspace",
     {"app.services.free_workspace.remember": {"root": REPO_ROOT},
      "app.services.free_workspace.status": {"root": REPO_ROOT}}),
    # Sprint154 - 붙여넣을 요청문을 만든다. 글자만 만든다 - 모델을
    # 부르지 않으므로 패치할 것이 없다.
    ("POST", "/studio/api/script-prompt", {"topic": "40대 허리 건강 운동"}, []),
    # Sprint174 - 지금 무엇을 쓰고 있는가. 화면의 [정보 복사]가 읽는다.
    #
    # 읽기만 한다 - 판번호와 자리와 도구를 그대로 돌려줄 뿐이라
    # 패치할 것이 없다.
    ("GET", "/studio/api/about", None, []),
    # Sprint177 - 보내 주실 것 한 덩이. 적혀 있는 것을 옮기기만 하므로
    # 패치할 것이 없다.
    ("GET", "/studio/api/beta-feedback", None, []),
    # Sprint179 - 붙여넣기 전에 읽어 본다. 읽고 말할 뿐이라 패치할
    # 것이 없다.
    ("POST", "/studio/api/script-check", {"raw": ""}, []),
    # Sprint158 - 미리보기와 직접 고르기.
    #
    # 셋 다 훑어 둔 목록을 먼저 본다. 목록에 없는 경로는 내주지도
    # 받지도 않으므로, 계약만 보려면 그 판정을 패치한다.
    ("GET", "/studio/api/review/{project_id}/asset", None,
     ["app.routers.studio._library_item"],
     f"/studio/api/review/{PROJECT_ID}/asset?path=x",
     # 실제로 있는 파일을 가리켜야 200이 온다 - 없으면 404이고,
     # 그것은 계약이 아니라 파일 유무를 보는 것이 된다.
     {"app.routers.studio._library_item":
          {"path": REAL_FILE, "name": "studio.html", "kind": "images"}}),
    ("GET", "/studio/api/review/{project_id}/scenes/{scene}/alternatives",
     None,
     ["app.services.studio_review.state",
      "app.services.local_library.load",
      "app.providers.local_stock_provider.match"],
     f"/studio/api/review/{PROJECT_ID}/scenes/1/alternatives",
     {"app.services.studio_review.state":
          {"scenes": [{"scene": 1, "image_prompt": "무릎"}]},
      "app.services.local_library.load": {"items": []},
      "app.providers.local_stock_provider.match": None}),
    ("PUT", "/studio/api/review/{project_id}/scenes/{scene}/asset",
     {"path": "x"},
     ["app.routers.studio._library_item",
      "app.services.asset_override.save"],
     f"/studio/api/review/{PROJECT_ID}/scenes/1/asset",
     {"app.routers.studio._library_item":
          {"path": "x", "name": "x.png", "kind": "images"}}),
    ("DELETE", "/studio/api/review/{project_id}/scenes/{scene}/asset", None,
     ["app.services.asset_override.clear"],
     f"/studio/api/review/{PROJECT_ID}/scenes/1/asset"),
    # Sprint166 - 무엇으로 만들어졌는가. 순수 읽기다.
    ("GET", "/studio/api/review/{project_id}/completion", None,
     ["app.services.studio_review.state",
      "app.services.completion_report.build"],
     f"/studio/api/review/{PROJECT_ID}/completion",
     {"app.services.studio_review.state": {"scenes": []},
      "app.services.completion_report.build": {"cost": {}}}),
    # Sprint163 - 만든 뒤 결과 확인. 순수 읽기다.
    ("GET", "/studio/api/review/{project_id}/output-check", None,
     ["app.services.studio_review.state",
      "app.services.output_check.build"],
     f"/studio/api/review/{PROJECT_ID}/output-check",
     {"app.services.studio_review.state": {"scenes": []},
      "app.services.output_check.build": {"state": "failed"}}),
    # Sprint162 - 누르기 전 최종 확인. 순수 읽기다.
    ("GET", "/studio/api/review/{project_id}/final-check", None,
     ["app.services.studio_review.state",
      "app.services.final_check.build"],
     f"/studio/api/review/{PROJECT_ID}/final-check",
     {"app.services.studio_review.state": {"scenes": []},
      "app.services.final_check.build": {"state": "blocked"}}),
    # Sprint161 - 봤고 괜찮다. 판정은 준비 상태에서 그대로 읽으므로
    # 그 한 줄만 흉내 내면 계약을 볼 수 있다.
    ("POST", "/studio/api/review/{project_id}/scenes/{scene}/confirm", None,
     ["app.routers.studio._scene_row",
      "app.services.review_confirm.save"],
     f"/studio/api/review/{PROJECT_ID}/scenes/1/confirm",
     {"app.routers.studio._scene_row":
          {"scene": 1, "state": "review", "reasons": ["weak"],
           "image": {"path": "x"}}}),
    ("DELETE", "/studio/api/review/{project_id}/scenes/{scene}/confirm", None,
     ["app.services.review_confirm.clear"],
     f"/studio/api/review/{PROJECT_ID}/scenes/1/confirm"),
    # Sprint153 - 무엇이 필요하고 어디에 두면 되는가. 순수 읽기다 -
    # 만드는 함수는 하나도 부르지 않는다.
    ("GET", "/studio/api/review/{project_id}/requirements", None,
     ["app.services.free_workspace.requirements"],
     f"/studio/api/review/{PROJECT_ID}/requirements",
     {"app.services.free_workspace.requirements": {"requirements": []}}),
    # Sprint152 - Scene마다 무엇이 준비됐는가. 순수 읽기다.
    ("GET", "/studio/api/review/{project_id}/preparation", None,
     ["app.services.free_workspace.preparation"],
     f"/studio/api/review/{PROJECT_ID}/preparation",
     {"app.services.free_workspace.preparation": {"scenes": []}}),
    # Sprint150 - 내 PC 폴더를 훑는다. 없는 폴더는 400이므로 root는
    # 실제로 있는 곳을 준다(이 저장소 자신). 훑기와 적기는 패치한다 -
    # 여기는 계약을 보는 자리이지 파일 시스템을 보는 자리가 아니다.
    ("POST", "/studio/api/review/{project_id}/library",
     {"root": REPO_ROOT},
     ["app.services.local_library.scan", "app.services.local_library.save",
      "app.services.local_library.counts"],
     f"/studio/api/review/{PROJECT_ID}/library",
     {"app.services.local_library.scan": {"items": []},
      "app.services.local_library.counts": {}}),
    ("POST", "/studio/api/review/{project_id}/images", None,
     ["app.services.studio_review.generate_images"],
     f"/studio/api/review/{PROJECT_ID}/images"),
    ("POST", "/studio/api/review/{project_id}/images/{scene}", None,
     ["app.services.studio_review.regenerate_image"],
     f"/studio/api/review/{PROJECT_ID}/images/1"),
    ("POST", "/studio/api/review/{project_id}/voices", None,
     ["app.services.studio_review.generate_voices"],
     f"/studio/api/review/{PROJECT_ID}/voices"),
    ("POST", "/studio/api/review/{project_id}/voices/{scene}", None,
     ["app.services.studio_review.regenerate_voice"],
     f"/studio/api/review/{PROJECT_ID}/voices/1"),
    # Sprint145 - 렌더 앞에 검사가 생겼다. 빈 임시 프로젝트는 당연히
    # 걸리므로, 계약을 보려면 "걸릴 것이 없는" 상태를 흉내 내야 한다.
    ("POST", "/studio/api/review/{project_id}/render", None,
     ["app.services.studio_review.render",
      "app.services.scene_order.render_problems"],
     f"/studio/api/review/{PROJECT_ID}/render",
     {"app.services.scene_order.render_problems": []}),
    ("POST", "/studio/api/production/plan",
     {"selections": {"script": "generate"}}, []),
    ("POST", "/studio/api/production/project",
     {"raw": "{\"title\":\"t\",\"scenes\":[{\"narration\":\"n\"}]}"},
     ["app.production.imported_project.create_from_script"]),
    ("POST", "/studio/api/production/import",
     {"raw": "{\"title\":\"t\",\"scenes\":[{\"narration\":\"n\"}]}"},
     []),
        # Sprint149 - 올리기 전 검사가 생겼다. 계약을 보려면 "걸릴 것이
    # 없는" 상태를 흉내 내야 한다.
    ("POST", "/studio/api/projects/{project_id}/upload", None,
     ["app.services.studio_jobs.start_upload",
      "app.services.studio_upload.is_approved",
      "app.services.publish_gate.problems"],
     f"/studio/api/projects/{PROJECT_ID}/upload",
     {"app.services.studio_upload.is_approved": True,
      "app.services.publish_gate.problems": []}),
    # Sprint148 - 올리겠다는 요청과 거절. 둘 다 사람의 결정이다.
    ("POST", "/studio/api/projects/{project_id}/request-upload", None,
     ["app.services.studio_workflow.request_upload",
      "app.services.publish_gate.problems"],
     f"/studio/api/projects/{PROJECT_ID}/request-upload",
     {"app.services.publish_gate.problems": []}),
    # Sprint149 - 다시 시도. 새 승인을 만들지 않는다.
    ("POST", "/studio/api/projects/{project_id}/retry-upload", None,
     ["app.services.studio_workflow.retry_upload"],
     f"/studio/api/projects/{PROJECT_ID}/retry-upload"),
    ("POST", "/studio/api/projects/{project_id}/reject",
     {"reason": "다시 보십시오"},
     ["app.services.studio_workflow.reject"],
     f"/studio/api/projects/{PROJECT_ID}/reject"),
    ("POST", "/studio/api/projects/{project_id}/unapprove", None,
     ["app.routers.studio.studio_workflow.unapprove"],
     f"/studio/api/projects/{PROJECT_ID}/unapprove"),
]


class RouterContractTestCase(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.tmp_dir = tempfile.mkdtemp()
        project_dir = os.path.join(self.tmp_dir, PROJECT_ID)
        os.makedirs(project_dir)

        # Sprint80 - Studio 엔드포인트가 읽을 최소 산출물. 다른 계약
        # 테스트는 이 파일들을 보지 않는다.
        with open(os.path.join(project_dir, "project.json"),
                  "w", encoding="utf-8") as f:
            f.write('{"topic": "t", "channel": "wellbeing"}')
        with open(os.path.join(project_dir, "thumbnail.png"), "wb") as f:
            f.write(b"png")

        # Studio 작업 하나를 미리 넣어 둔다. start()를 부르면 실제
        # 파이프라인 스레드가 뜬다.
        studio_jobs.reset()
        studio_jobs._jobs["contract_job"] = {
            "job_id": "contract_job", "topic": "t", "channel": "wellbeing",
            "state": "done", "project_id": None, "project_path": None,
            "title": None,
            "error": None, "console": [],
        }
        self.addCleanup(studio_jobs.reset)

        patcher = patch.object(project_service, "OUTPUT_ROOT", self.tmp_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp_dir, True)

    def call(self, method, path, payload, services, returns=None):
        """서비스를 autospec으로 패치한 채 엔드포인트를 호출한다.

        Sprint145 - 돌려줄 값을 정해야 하는 서비스가 생겼다. 검사
        함수는 "문제 목록"을 돌려주는데, MagicMock은 그 자체로 참이라
        아무 문제가 없는 프로젝트도 걸린 것처럼 보인다."""

        returns = returns or {}
        patchers = [patch(target, autospec=True) for target in services]
        mocks = [p.start() for p in patchers]

        for target, mock in zip(services, mocks):
            if target in returns:
                mock.return_value = returns[target]

        # Sprint149 - 요청이 끝나면 바로 푼다.
        #
        # addCleanup은 시험이 끝날 때 돈다. 그런데 이 시험은 subTest로
        # 엔드포인트를 줄줄이 부르므로, 같은 함수를 두 항목이 함께
        # 쓰면 두 번째가 이미 Mock이 된 것을 다시 autospec하려다 죽는다.
        #
        # 호출 기록은 stop 뒤에도 남으므로 뒤에서 확인하는 데 지장이 없다.

        # Sprint121 - PUT이 생겼다. 메서드를 그대로 보내지 않으면 405가
        # 나고, 서비스가 안 불린 것을 계약 위반으로 잘못 읽는다.
        # Sprint158 - DELETE도 생겼다. 빠뜨리면 POST로 보내게 되고,
        # 그러면 405가 나 서비스가 안 불린 것을 계약 위반으로 잘못
        # 읽는다(PUT 때와 같은 모양이다).
        if method == "GET":
            response = self.client.get(path)
        elif method == "PUT":
            response = self.client.put(path, json=payload)
        elif method == "DELETE":
            response = self.client.delete(path)
        else:
            response = self.client.post(path, json=payload)

        for p in patchers:
            p.stop()

        return response, mocks


class TestEveryEndpointIsCovered(RouterContractTestCase):

    def test_table_covers_all_registered_endpoints(self):
        registered = {
            (method.upper(), path)
            for path, operations in app.openapi()["paths"].items()
            for method in operations
        }

        covered = {(entry[0], entry[1]) for entry in ENDPOINTS}

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


# multipart/form-data를 받는 엔드포인트. 이 파일의 호출 루프는 JSON만
# 보내므로 여기서 부르면 형식이 맞지 않는다 - 등록 여부는 위 표가
# 덮고, 실제 호출은 tests/test_image_import_provider.py와 전용
# smoke 검증이 한다.
MULTIPART_ENDPOINTS = {
    ("POST", "/studio/api/production/images"),
    ("POST", "/studio/api/production/voice"),
}


class TestValidRequestsNeverRaiseTypeError(RouterContractTestCase):
    """라우터가 서비스를 부를 때 인자 개수/이름이 맞는지 확인한다.
    autospec 덕분에 불일치는 곧바로 TypeError로 드러난다."""

    def test_all_endpoints_accept_a_valid_request(self):
        for entry in ENDPOINTS:
            method, path, payload, services = entry[:4]

            if (method, path) in MULTIPART_ENDPOINTS:
                continue

            # 경로 파라미터가 있는 엔드포인트는 구체 경로로 호출한다.
            call_path = entry[4] if len(entry) > 4 else path
            returns = entry[5] if len(entry) > 5 else None

            with self.subTest(endpoint=f"{method} {path}"):
                response, mocks = self.call(
                    method, call_path, payload, services, returns,
                )

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
