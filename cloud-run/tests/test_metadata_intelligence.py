"""
Sprint93 - Metadata Intelligence Foundation (Epic 47).

Script만 보고 업로드 메타데이터를 만든다. Gemini도 Imagen도 부르지
않는다 - 해시태그는 대본 텍스트의 빈도 추출, 설명은 고정 템플릿 조립,
카테고리/언어/공개상태는 정책 표, Playlist는 주제의 규칙 기반 분류다.

가장 중요한 계약이 둘이다.

하나. 제목은 새로 만들지 않는다. script.json의 제목이 곧 업로드
제목이다 - 영상과 썸네일이 그 제목을 기준으로 만들어졌기 때문에,
여기서 또 만들면 한 영상에 제목이 둘이 된다.

둘. publish_package.json이 없어도 업로드가 동작해야 한다. Sprint91부터
있던 script.json 폴백이 그것이고, PV-02에서 실제로 검증된 길이다.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.services import (
    description_generator,
    hashtag_generator,
    metadata_service,
    metadata_strategy_service,
    playlist_recommendation_service,
)


def _script(title="혈압을 낮추는 아침 습관", script="혈압 관리가 중요합니다. 아침에 물을 마시세요."):
    return {
        "title": title,
        "hook": "훅",
        "script": script,
        "scenes": [
            {"scene": 1, "narration": "첫 장면", "image_prompt": "p1"},
            {"scene": 2, "narration": "둘째 장면", "image_prompt": "p2"},
        ],
    }


class TestTheTitleIsNotInvented(unittest.TestCase):
    """영상과 썸네일이 script.json의 제목을 기준으로 만들어졌다.
    여기서 또 만들면 썸네일 문구와 업로드 제목이 다른 영상이 나온다."""

    def test_the_script_title_becomes_the_upload_title(self):
        data = _script(title="정확히 이 제목")

        self.assertEqual(metadata_service.build_metadata(data).title, "정확히 이 제목")

    def test_the_thumbnail_text_is_the_same_title(self):
        meta = metadata_service.build_metadata(_script(title="한 제목"))

        self.assertEqual(meta.thumbnail_text, meta.title)

    def test_no_title_generator_is_imported(self):
        """원본(OneDrive)은 title_generator로 Gemini를 한 번 더 부른다."""

        import ast

        tree = ast.parse(
            open(metadata_service.__file__, encoding="utf-8").read(),
        )
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)

        self.assertNotIn("title_generator", names)


class TestNoAIIsCalled(unittest.TestCase):
    """이 계층은 Gemini도 Imagen도 부르지 않는다."""

    def test_the_metadata_modules_import_no_ai_provider(self):
        import ast

        for module in (metadata_service, hashtag_generator,
                       description_generator, playlist_recommendation_service,
                       metadata_strategy_service):
            tree = ast.parse(open(module.__file__, encoding="utf-8").read())
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    names.add(node.module or "")
                elif isinstance(node, ast.Import):
                    names.update(a.name for a in node.names)

            for forbidden in ("ai_provider_manager", "google.generativeai",
                              "image_service", "vertexai"):
                with self.subTest(module=module.__name__, forbidden=forbidden):
                    self.assertFalse(
                        any(forbidden in n for n in names), forbidden,
                    )

    def test_building_a_package_makes_no_network_call(self):
        import urllib.request

        with patch.object(urllib.request, "urlopen") as opener:
            metadata_service.build_package(_script(), "혈압")

        opener.assert_not_called()


class TestTheSevenRequiredFields(unittest.TestCase):
    """Acceptance 3 - title/description/hashtags/playlist/privacy/
    language/category_id가 자동으로 채워진다."""

    def setUp(self):
        self.package = metadata_service.build_package(
            _script(), "고혈압에 좋은 아침 습관", duration=44.2,
        )

    def test_every_required_field_is_present_and_filled(self):
        for field in ("title", "description", "hashtags", "playlist_title",
                      "category_id", "privacy_status", "language"):
            with self.subTest(field=field):
                self.assertIn(field, self.package)
                self.assertTrue(self.package[field], field)

    def test_privacy_defaults_to_private(self):
        """Acceptance 4. 실수로 공개되지 않는다."""

        self.assertEqual(self.package["privacy_status"], "private")

    def test_language_and_category_are_the_youtube_shaped_values(self):
        self.assertEqual(self.package["language"], "ko")
        self.assertEqual(self.package["category_id"], "26")

    def test_the_measured_duration_is_carried(self):
        self.assertEqual(self.package["duration"], 44.2)

    def test_the_description_carries_the_medical_disclaimer(self):
        """건강 정보 콘텐츠다. 면책 문구가 빠지면 안 된다."""

        self.assertIn("의학적 진단이나 치료를", self.package["description"])

    def test_the_description_starts_with_the_script_body(self):
        self.assertTrue(
            self.package["description"].startswith("혈압 관리가 중요합니다"),
        )


class TestPlaylistComesFromRuleBasedClassification(unittest.TestCase):

    def test_a_blood_pressure_topic_maps_to_the_vascular_playlist(self):
        rec = playlist_recommendation_service.recommend_playlist("고혈압 관리법")

        self.assertEqual(rec.playlist_title, "혈압·혈관 건강")

    def test_a_diabetes_topic_maps_to_the_metabolism_playlist(self):
        rec = playlist_recommendation_service.recommend_playlist("당뇨 예방")

        self.assertEqual(rec.playlist_title, "당뇨·대사 관리")

    def test_an_unmatched_topic_falls_back_to_general(self):
        rec = playlist_recommendation_service.recommend_playlist("커피 마시는 법")

        self.assertEqual(rec.playlist_title, "건강 정보")

    def test_a_reason_is_always_given(self):
        """근거 없는 권장은 만들지 않는다."""

        rec = playlist_recommendation_service.recommend_playlist("당뇨")

        self.assertIn("medical_domain", rec.reason)


class TestTheFileIsWritten(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name

    def _write(self, name, payload):
        with open(os.path.join(self.project, name), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def test_a_package_is_written_next_to_the_project(self):
        self._write("script.json", _script())
        self._write("project.json", {"topic": "고혈압"})

        metadata_service.generate_publish_package(self.project)

        path = os.path.join(self.project, metadata_service.PACKAGE_FILENAME)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["playlist_title"], "혈압·혈관 건강")

    def test_the_real_rendered_duration_is_used(self):
        """원본은 이 단계가 렌더보다 앞이라 추정치를 썼다. 여기서는
        파이프라인 끝에서 도니 측정값이 있다."""

        self._write("script.json", _script())
        self._write("project.json", {"topic": "고혈압"})
        self._write("quality_report.json", {"technical_validation": {"checks": {
            "video_duration": {"duration_seconds": 43.5}}}})

        package = metadata_service.generate_publish_package(self.project)

        self.assertEqual(package["duration"], 43.5)

    def test_no_script_means_no_package(self):
        """만들 재료가 없는데 빈 껍데기를 남기면 업로드가 그것을
        진짜 메타데이터로 읽는다."""

        result = metadata_service.generate_publish_package(self.project)

        self.assertIsNone(result)
        self.assertFalse(os.path.exists(
            os.path.join(self.project, metadata_service.PACKAGE_FILENAME)))

    def test_a_corrupt_script_does_not_crash(self):
        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            f.write("{ broken")

        self.assertIsNone(
            metadata_service.generate_publish_package(self.project),
        )

    def test_production_artifacts_are_not_touched(self):
        self._write("script.json", _script())
        self._write("project.json", {"topic": "고혈압"})
        before = json.load(
            open(os.path.join(self.project, "script.json"), encoding="utf-8"),
        )

        metadata_service.generate_publish_package(self.project)

        after = json.load(
            open(os.path.join(self.project, "script.json"), encoding="utf-8"),
        )
        self.assertEqual(before, after)


class TestUploadPrefersThePackageButStillWorksWithout(unittest.TestCase):
    """Acceptance 2 와 5. 우선 사용하되, 없으면 기존 경로로 돈다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name

    def _build(self, package=None):
        from app.services import youtube_upload_step_service as step

        if package is not None:
            with open(os.path.join(self.project, "publish_package.json"),
                      "w", encoding="utf-8") as f:
                json.dump(package, f, ensure_ascii=False)

        return step._build_metadata(
            "주제", {"title": "대본 제목", "script": "대본 본문"}, self.project,
        )

    def test_the_package_wins_when_present(self):
        metadata = self._build({
            "title": "패키지 제목", "description": "패키지 설명",
            "tags": ["#a"], "playlist_title": "재생목록",
            "category_id": "26", "language": "ko", "privacy_status": "private",
        })

        self.assertEqual(metadata["title"], "패키지 제목")
        self.assertEqual(metadata["playlist_title"], "재생목록")
        self.assertEqual(metadata["category_id"], "26")
        self.assertEqual(metadata["privacy_status"], "private")

    def test_without_a_package_the_old_path_still_works(self):
        """PV-02에서 실제로 업로드된 길이다. 그대로 남아 있어야 한다."""

        metadata = self._build()

        self.assertEqual(metadata["title"], "대본 제목")
        self.assertEqual(metadata["description"], "대본 본문")
        self.assertNotIn("playlist_title", metadata)

    def test_a_generated_package_flows_end_to_end_into_upload_metadata(self):
        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump(_script(), f, ensure_ascii=False)
        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"topic": "고혈압"}, f, ensure_ascii=False)

        metadata_service.generate_publish_package(self.project)
        metadata = self._build()

        self.assertEqual(metadata["playlist_title"], "혈압·혈관 건강")
        self.assertEqual(metadata["privacy_status"], "private")
        self.assertEqual(metadata["category_id"], "26")
        self.assertIn("의학적 진단이나 치료를", metadata["description"])


class TestThePipelineWiring(unittest.TestCase):

    def test_metadata_runs_before_upload(self):
        """업로드가 읽을 파일이므로 반드시 앞이어야 한다."""

        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        self.assertLess(
            source.index("generate_publish_package"),
            source.index("run_upload_quietly"),
        )

    def test_the_flag_is_on(self):
        self.assertTrue(config.ENABLE_METADATA_INTELLIGENCE)

    def test_the_engine_stays_light(self):
        """메타데이터 계층이 Upload Core를 파이프라인에 끌고 오면 안 된다."""

        import subprocess

        result = subprocess.run(
            [sys.executable, "-c",
             "import sys\nimport app.pipeline.pipeline\n"
             "print(len([m for m in sys.modules if 'providers.upload' in m "
             "or m.startswith('googleapiclient')]))"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertEqual(result.stdout.strip(), "0")


class TestKnownLimitOfKeywordExtraction(unittest.TestCase):
    """이식한 추출기는 조사가 붙은 형태를 그대로 토큰으로 남긴다 -
    원본이 문서화해 둔 한계다. 여기에 못을 박아 두는 이유는, 이것이
    고쳐졌는지 아닌지를 나중에 분명히 알 수 있게 하기 위해서다.

    지금은 '않는'/'특히' 같은 부사와 조사 부착형이 해시태그로 나온다.
    품질 개선은 별도 과제이며, 이 테스트는 개선되면 실패해서 그
    사실을 알려 준다."""

    def test_particles_and_adverbs_still_leak_into_hashtags(self):
        data = _script(script="특히 혈압이 높으면 정말 위험합니다. 혈압을 낮추세요.")

        tags = hashtag_generator.generate_hashtags(data)

        leaked = [t for t in tags if t in ("#특히", "#정말")]
        self.assertTrue(
            leaked,
            "부사가 더 이상 새지 않는다면 추출기가 개선된 것이다 - "
            "이 테스트와 Sprint93 보고서의 '알려진 한계'를 갱신하십시오.",
        )


if __name__ == "__main__":
    unittest.main()
