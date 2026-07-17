"""
Sprint122 (GREEN) - Longform Production Profile Foundation, Pipeline
Interface.

render_profile_name은 production_profile_name과 동일한 "명시적 opt-in"
관례를 따른다: render_profile_name을 명시적으로 주면(무엇이든, "shorts"
포함) 그 요청에 한해 RenderProfile.get()으로 해석된 dict가 결과 dict
(data["render_profile"])와 4개 Compose 단계(step02_assets/step04_
subtitle/step05_video/step06_thumbnail) 호출 kwarg에 노출된다.
render_profile_name을 아예 안 주면(기본값 None) 그 kwarg 자체가 어느
호출에도 추가되지 않는다 - 각 Compose 단계/서비스 함수 자체의 기본값
(render_profile=None -> 기존 VIDEO_WIDTH/9:16/FontSize=18/MarginV=115)이
적용되므로 실제 운영 동작은 100% 동일하다.

(GREEN 단계에서 확정: 초기 RED 초안은 "항상 resolve된 dict를 무조건
전달"이었으나, 그러면 수십 개의 기존 pipeline 테스트가 쓰는 정확한
call-args/exact-dict 비교(assert_called_once_with, assertEqual)가
전부 깨진다 - Regression Zero가 최우선이라는 명시적 지시에 따라
production_profile_name과 동일한 조건부 노출 방식으로 조정했다.)
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.pipeline import pipeline
from app.services.render_profile import RenderProfile

from tests.test_pipeline_production_profile import patched_pipeline, _wire_defaults


class TestPipelineRenderProfileThreading(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def _run_pipeline(self, **kwargs):
        return pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
            **kwargs,
        )

    def test_default_call_omits_render_profile_from_result(self):
        # Regression Zero - render_profile_name을 안 넘기면 결과 dict에
        # render_profile 키 자체가 없다(기존 pipeline 출력과 100% 동일).
        with patched_pipeline() as m:
            _wire_defaults(m)

            result = self._run_pipeline()

            self.assertNotIn("render_profile", result)

    def test_default_call_omits_render_profile_kwarg_from_every_compose_step(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline()

            self.assertNotIn(
                "render_profile", m["step02_assets"].collect_assets.call_args[1],
            )
            self.assertNotIn("render_profile", m["step04"].run.call_args[1])
            self.assertNotIn("render_profile", m["step05"].run.call_args[1])
            self.assertNotIn("render_profile", m["step06"].run.call_args[1])

    def test_explicit_longform_name_exposes_longform_profile_in_result(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            result = self._run_pipeline(render_profile_name="longform")

            self.assertEqual(result["render_profile"], RenderProfile.get("longform"))

    def test_explicit_shorts_name_exposes_shorts_profile_in_result(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            result = self._run_pipeline(render_profile_name="shorts")

            self.assertEqual(result["render_profile"], RenderProfile.get("shorts"))

    def test_step02_assets_receives_resolved_render_profile_when_opted_in(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline(render_profile_name="longform")

            _, kwargs = m["step02_assets"].collect_assets.call_args
            self.assertEqual(kwargs["render_profile"], RenderProfile.get("longform"))

    def test_step04_subtitle_receives_resolved_render_profile_when_opted_in(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline(render_profile_name="longform")

            _, kwargs = m["step04"].run.call_args
            self.assertEqual(kwargs["render_profile"], RenderProfile.get("longform"))

    def test_step05_video_receives_resolved_render_profile_when_opted_in(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline(render_profile_name="longform")

            _, kwargs = m["step05"].run.call_args
            self.assertEqual(kwargs["render_profile"], RenderProfile.get("longform"))

    def test_step06_thumbnail_receives_resolved_render_profile_when_opted_in(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline(render_profile_name="longform")

            _, kwargs = m["step06"].run.call_args
            self.assertEqual(kwargs["render_profile"], RenderProfile.get("longform"))

    def test_unknown_render_profile_name_falls_back_to_shorts(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            result = self._run_pipeline(render_profile_name="does_not_exist")

            self.assertEqual(result["render_profile"]["profile"], "shorts")


if __name__ == "__main__":
    unittest.main()
