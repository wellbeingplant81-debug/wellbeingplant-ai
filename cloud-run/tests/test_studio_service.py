"""
Sprint80 - AI Video Studio UI의 읽기 계층.

엔진은 한 줄도 건드리지 않는다. 이 계층이 하는 일은 파이프라인이 이미
디스크에 남긴 것을 읽어 화면이 쓸 모양으로 바꾸는 것뿐이다.

진행 상황을 로그 파싱이 아니라 **산출물**로 판정하는 이유가 있다.
로그 문구는 아무 때나 바뀌고, 파이프라인에 진행 신호를 넣으려면
파이프라인을 고쳐야 한다. script.json이 있으면 대본이 끝난 것이고,
video/final_short.mp4가 있으면 영상이 끝난 것이다 - 이 판정은
파이프라인이 무엇을 출력하든 성립한다.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import studio_service


class _Project:
    """산출물이 놓인 프로젝트 디렉터리 하나."""

    def __init__(self, root, name, stages=()):
        self.path = os.path.join(root, name)
        os.makedirs(self.path)

        self._write("project.json", {
            "project_id": name, "topic": "혈관 건강", "channel": "wellbeing",
        })

        if "script" in stages:
            self._write("script.json", {
                "title": "제목", "hook": "훅",
                "scenes": [
                    {"scene": 1, "narration": "나레이션1",
                     "subject": "a man", "camera": "close-up",
                     "image_prompt": "a man, close-up",
                     "provider": "ai_image", "asset_type": "image",
                     "character_scene": True},
                    {"scene": 2, "narration": "나레이션2",
                     "subject": "a bowl", "camera": "top-down view",
                     "image_prompt": "a bowl, top-down",
                     "provider": "pexels_image", "asset_type": "image"},
                ],
            })

        if "images" in stages:
            os.makedirs(os.path.join(self.path, "images"))
            for number in (1, 2):
                self._touch(f"images/scene{number}.png")

        if "audio" in stages:
            os.makedirs(os.path.join(self.path, "audio"))
            self._touch("audio/final_audio.wav")

        if "subtitle" in stages:
            os.makedirs(os.path.join(self.path, "subtitle"))
            self._touch("subtitle/subtitle.srt")

        if "video" in stages:
            os.makedirs(os.path.join(self.path, "video"))
            self._touch("video/final_short.mp4")

        if "thumbnail" in stages:
            self._touch("thumbnail.png")

        if "quality" in stages:
            self._write("quality_report.json", {
                "ai_quality_evaluation": {
                    "scores": {
                        "overall_quality": 85, "image_realism": 90,
                        "composition": 80, "character_consistency": 95,
                        "hook_strength": 75, "thumbnail_quality": 70,
                        "scene1_quality": 88,
                    },
                    "scenes": [
                        {"scene": 1, "realism_score": 95,
                         "composition_score": 90, "regenerate": False,
                         "reason": None},
                        {"scene": 2, "realism_score": 40,
                         "composition_score": 50, "regenerate": True,
                         "reason": "프롬프트와 다릅니다"},
                    ],
                    "thumbnail": {"consistency_with_scene1": 90,
                                  "ctr_score": 70, "regenerate": False,
                                  "reason": None},
                },
            })

        if "observatory" in stages:
            self._write("asset_observatory.json", {
                "schema_version": "sprint77",
                "cache": {"hits": 1, "misses": 3},
                "scenes": [{
                    "scene": 2,
                    "searches": [{"query": "bowl", "provider": "pexels_image",
                                  "cache_hit": False, "result_count": 3}],
                    "candidates": [
                        {"provider": "pexels_image", "alt": "a bowl of soup",
                         "slug": "", "source_url": "https://p/1/",
                         "download_url": "https://i/1.jpg",
                         "width": 1080, "height": 1920, "duration": None,
                         "relevance": 0.2, "human_penalty": 0.0,
                         "composition": 0.15, "motion": 0.0,
                         "ranking_score": 1.2, "selected": True},
                        {"provider": "pexels_image", "alt": "a bowl of oatmeal",
                         "slug": "", "source_url": "https://p/2/",
                         "download_url": "https://i/2.jpg",
                         "width": 1080, "height": 1920, "duration": None,
                         "relevance": 0.4, "human_penalty": 0.0,
                         "composition": 0.15, "motion": 0.0,
                         "ranking_score": 1.1, "selected": False},
                    ],
                    "scene_terms": ["bowl", "oatmeal"],
                    "selection_reason": "후보 2개 중 0번",
                    "final_provider": "pexels_image",
                    "final_asset": "/p/images/scene2.png",
                }],
            })

    def _write(self, name, payload):
        with open(os.path.join(self.path, name), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def _touch(self, relative):
        with open(os.path.join(self.path, relative), "wb") as f:
            f.write(b"x")


class TestStageProgress(unittest.TestCase):
    """진행 상황은 산출물로 판정한다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def test_a_fresh_project_has_only_planning_done(self):
        project = _Project(self.root, "p1")

        stages = studio_service.stage_progress(project.path)
        done = {s["key"]: s["done"] for s in stages}

        self.assertTrue(done["plan"])
        self.assertFalse(done["script"])
        self.assertFalse(done["video"])

    def test_each_artifact_marks_its_stage(self):
        project = _Project(self.root, "p2", stages=(
            "script", "images", "audio", "subtitle", "video",
            "thumbnail", "quality",
        ))

        done = {s["key"]: s["done"]
                for s in studio_service.stage_progress(project.path)}

        for key in ("plan", "script", "image", "voice", "subtitle",
                    "video", "thumbnail", "quality"):
            with self.subTest(key=key):
                self.assertTrue(done[key], key)

    def test_upload_is_never_done(self):
        """업로드 경로가 아직 없다. youtube_provider.py는 0바이트다.

        화면에 '연결 안 됨'으로 보여야지, 끝난 것처럼 보이면 안 된다.
        """

        project = _Project(self.root, "p3", stages=("script", "video"))

        upload = [s for s in studio_service.stage_progress(project.path)
                  if s["key"] == "upload"][0]

        self.assertFalse(upload["done"])
        self.assertTrue(upload.get("unavailable"))

    def test_the_stage_order_is_stable(self):
        project = _Project(self.root, "p4")

        keys = [s["key"] for s in studio_service.stage_progress(project.path)]

        self.assertEqual(keys, [
            "plan", "script", "image", "voice", "subtitle",
            "video", "thumbnail", "quality", "upload",
        ])

    def test_a_missing_project_does_not_raise(self):
        stages = studio_service.stage_progress(
            os.path.join(self.root, "nope"),
        )

        self.assertTrue(all(not s["done"] for s in stages))


class TestProjectListing(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        _Project(self.root, "20260101_000001", stages=("script", "video"))
        _Project(self.root, "20260101_000002", stages=("script",))

    def test_projects_are_listed_newest_first(self):
        projects = studio_service.list_projects(self.root)

        self.assertEqual(
            [p["project_id"] for p in projects],
            ["20260101_000002", "20260101_000001"],
        )

    def test_a_listing_says_whether_a_video_exists(self):
        by_id = {p["project_id"]: p
                 for p in studio_service.list_projects(self.root)}

        self.assertTrue(by_id["20260101_000001"]["has_video"])
        self.assertFalse(by_id["20260101_000002"]["has_video"])

    def test_the_title_comes_from_the_script(self):
        by_id = {p["project_id"]: p
                 for p in studio_service.list_projects(self.root)}

        self.assertEqual(by_id["20260101_000001"]["title"], "제목")

    def test_a_directory_without_a_project_file_is_ignored(self):
        os.makedirs(os.path.join(self.root, "images"))

        self.assertEqual(len(studio_service.list_projects(self.root)), 2)

    def test_a_missing_root_lists_nothing(self):
        self.assertEqual(
            studio_service.list_projects(os.path.join(self.root, "nope")), [],
        )


class TestProjectDetail(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.project = _Project(self.root, "p1", stages=(
            "script", "images", "video", "thumbnail", "quality",
            "observatory",
        ))

    def test_scenes_carry_what_the_explorer_shows(self):
        detail = studio_service.project_detail(self.project.path)
        scene = detail["scenes"][0]

        for field in ("scene", "narration", "image_prompt", "provider",
                      "asset_type", "character_scene", "realism",
                      "composition", "regenerate"):
            with self.subTest(field=field):
                self.assertIn(field, scene)

    def test_the_quality_panel_gets_every_score(self):
        detail = studio_service.project_detail(self.project.path)

        for key in ("overall_quality", "image_realism", "composition",
                    "character_consistency", "hook_strength",
                    "thumbnail_quality"):
            with self.subTest(key=key):
                self.assertIn(key, detail["quality"])

    def test_the_observatory_is_attached_per_scene(self):
        detail = studio_service.project_detail(self.project.path)
        by_scene = {s["scene"]: s for s in detail["scenes"]}

        self.assertIsNone(by_scene[1].get("observatory"))
        self.assertEqual(len(by_scene[2]["observatory"]["candidates"]), 2)

    def test_a_project_without_an_evaluation_still_returns_scenes(self):
        bare = _Project(self.root, "p2", stages=("script",))

        detail = studio_service.project_detail(bare.path)

        self.assertEqual(len(detail["scenes"]), 2)
        self.assertEqual(detail["quality"], {})

    def test_media_availability_is_reported(self):
        detail = studio_service.project_detail(self.project.path)

        self.assertTrue(detail["media"]["video"])
        self.assertTrue(detail["media"]["thumbnail"])


class TestMediaPathSafety(unittest.TestCase):
    """UI가 파일을 서빙하므로 경로를 그대로 믿으면 안 된다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.project = _Project(self.root, "p1", stages=("images", "video"))

    def test_a_known_kind_resolves(self):
        path = studio_service.media_path(self.project.path, "video")

        self.assertTrue(path.endswith("final_short.mp4"))

    def test_a_scene_image_resolves_by_number(self):
        path = studio_service.media_path(self.project.path, "scene", 2)

        self.assertTrue(path.endswith("scene2.png"))

    def test_an_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            studio_service.media_path(self.project.path, "../../etc/passwd")

    def test_a_non_numeric_scene_is_rejected(self):
        with self.assertRaises(ValueError):
            studio_service.media_path(self.project.path, "scene", "../secret")

    def test_a_missing_file_raises_not_found(self):
        with self.assertRaises(FileNotFoundError):
            studio_service.media_path(self.project.path, "thumbnail")


if __name__ == "__main__":
    unittest.main()
