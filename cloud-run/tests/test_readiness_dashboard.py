"""
Sprint160 - 지금 만들 수 있는가를 한 자리에서 본다 (Epic 57, Phase 11).

Sprint152~159가 Scene마다의 사실을 하나씩 쌓았다. 모자란 것, 약하게
걸린 것, 여럿이 같은 파일을 쓰는 것, 사람이 정한 것. 그런데 "그래서
지금 만들 수 있는가"는 표를 끝까지 읽어야 알 수 있었다.

세 가지로 줄인다
----------------
    READY    다 있고 볼 것도 없다
    REVIEW   다 있으나 사람이 봐야 할 것이 있다
    BLOCKED  없는 것이 있다

BLOCKED만 막는다. REVIEW는 막지 않는다 - 같은 그림을 여러 Scene에
쓰는 것도, 낱말 하나로 걸린 것도 사람이 일부러 그랬을 수 있다.

무엇을 지키는가
---------------
    1. 다 있으면 준비 완료      test_ready_when_all_assets_exist
    2. 약하게 걸리면 검토 필요  test_review_when_match_is_weak
    3. 없으면 막힌다            test_blocked_when_asset_missing
    4. 센 수가 맞는다           test_dashboard_counts_match
    5. 렌더 규칙은 그대로다     test_render_rule_unchanged

넷째가 이 Sprint의 값어치다. 화면에 뜬 숫자가 Scene별 판정과 다르면
사람은 어느 쪽을 믿어야 할지 모른다.
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

from app.services import free_workspace, local_library, scene_order

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
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def images(self, *names):
        for name in names:
            _png(os.path.join(self.root, "images", name))

    def voices(self, *numbers):
        for number in numbers:
            _tone(os.path.join(self.root, "voices", f"scene{number}.wav"))

    def scan(self):
        local_library.save(self.project, local_library.scan(self.root))

    def scenes(self, prompts):
        return [
            {"scene": n, "narration": f"{n}번 문장", "image_prompt": prompt}
            for n, prompt in enumerate(prompts, start=1)
        ]

    def report(self, prompts):
        return free_workspace.preparation(self.project, self.scenes(prompts))


class ReadyTest(Base):
    """1. 다 있고 볼 것도 없으면 준비 완료."""

    def test_ready_when_all_assets_exist(self):
        self.images("무릎 스트레칭.png", "허리 세우기.png")
        self.voices(1, 2)
        self.scan()

        report = self.report(["무릎 스트레칭 거실", "허리 세우기 침실"])

        self.assertEqual(report["state"], free_workspace.READY)
        self.assertEqual(report["counts"],
                         {"ready": 2, "review": 0, "blocked": 0})

        for row in report["scenes"]:
            with self.subTest(scene=row["scene"]):
                self.assertEqual(row["state"], free_workspace.READY)
                self.assertEqual(row["reasons"], [])


class ReviewTest(Base):
    """2. 다 있으나 볼 것이 있으면 검토 필요."""

    def test_review_when_match_is_weak(self):
        """낱말 하나로만 걸렸다 - 걸리긴 했으나 근거가 약하다."""

        self.images("자연광.png", "허리 세우기.png")
        self.voices(1, 2)
        self.scan()

        report = self.report([
            "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광",
            "허리 세우기 침실",
        ])

        self.assertEqual(report["state"], free_workspace.REVIEW)
        self.assertEqual(report["counts"],
                         {"ready": 1, "review": 1, "blocked": 0})

        rows = {row["scene"]: row for row in report["scenes"]}

        self.assertEqual(rows[1]["state"], free_workspace.REVIEW)
        self.assertEqual(rows[2]["state"], free_workspace.READY)

        # 왜 검토가 필요한지 그 줄이 말한다 - 표를 끝까지 읽지 않아도
        # 되게 하려는 것이 이 Sprint다.
        self.assertIn("weak", rows[1]["reasons"])

    def test_review_when_the_same_file_is_used_twice(self):
        self.images("운동.png")
        self.voices(1, 2)
        self.scan()

        report = self.report(["무릎 운동", "허리 운동"])

        self.assertEqual(report["state"], free_workspace.REVIEW)
        self.assertEqual(report["counts"]["review"], 2)

        for row in report["scenes"]:
            with self.subTest(scene=row["scene"]):
                self.assertIn("shared", row["reasons"])

    def test_an_override_alone_is_not_a_reason_to_review(self):
        """
        사람이 정한 것은 이미 사람이 본 것이다.

        그것을 검토 필요로 세면 자기가 정한 것을 다시 보라는 말이 된다.
        """

        from app.services import asset_override

        self.images("자연광.png", "허리 세우기.png")
        self.voices(1, 2)
        self.scan()

        asset_override.save(
            self.project, 1, os.path.join(self.root, "images", "자연광.png"))

        report = self.report(["무릎 스트레칭 거실", "허리 세우기 침실"])

        rows = {row["scene"]: row for row in report["scenes"]}

        self.assertEqual(rows[1]["image"]["asset_source"], "override")
        self.assertEqual(rows[1]["state"], free_workspace.READY)
        self.assertEqual(report["state"], free_workspace.READY)


class BlockedTest(Base):
    """3. 없는 것이 있으면 막힌다."""

    def test_blocked_when_asset_missing(self):
        self.images("무릎 스트레칭.png")
        self.voices(1)
        self.scan()

        report = self.report(["무릎 스트레칭 거실", "우주선 착륙"])

        self.assertEqual(report["state"], free_workspace.BLOCKED)
        self.assertEqual(report["counts"],
                         {"ready": 1, "review": 0, "blocked": 1})

        rows = {row["scene"]: row for row in report["scenes"]}

        self.assertEqual(rows[2]["state"], free_workspace.BLOCKED)
        self.assertIn("image", rows[2]["reasons"])
        self.assertIn("voice", rows[2]["reasons"])

    def test_a_missing_voice_alone_blocks(self):
        self.images("무릎 스트레칭.png")
        self.scan()

        report = self.report(["무릎 스트레칭 거실"])

        self.assertEqual(report["state"], free_workspace.BLOCKED)
        self.assertEqual(report["scenes"][0]["reasons"], ["voice"])

    def test_a_missing_script_blocks_too(self):
        self.images("무릎 스트레칭.png")
        self.voices(1)
        self.scan()

        scenes = [{"scene": 1, "narration": "  ",
                   "image_prompt": "무릎 스트레칭 거실"}]

        report = free_workspace.preparation(self.project, scenes)

        self.assertEqual(report["state"], free_workspace.BLOCKED)
        self.assertIn("script", report["scenes"][0]["reasons"])

    def test_blocked_wins_over_review(self):
        """
        하나라도 없으면 막힌다.

        나머지가 검토 필요라고 해서 "만들 수 있다"고 하면 안 된다.
        """

        self.images("자연광.png")
        self.voices(1)
        self.scan()

        report = self.report([
            "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광",
            "우주선 착륙",
        ])

        self.assertEqual(report["state"], free_workspace.BLOCKED)
        self.assertEqual(report["counts"],
                         {"ready": 0, "review": 1, "blocked": 1})

    def test_nothing_scanned_is_blocked(self):
        report = self.report(["무릎"])

        self.assertEqual(report["state"], free_workspace.BLOCKED)
        self.assertFalse(report["scanned"])

    def test_no_scenes_is_blocked_not_ready(self):
        """
        Scene이 없으면 만들 것이 없다.

        빈 것을 "준비 완료"라고 하면 제작 버튼이 열리고, 눌러도
        아무 일도 일어나지 않는다.
        """

        report = free_workspace.preparation(self.project, [])

        self.assertEqual(report["state"], free_workspace.BLOCKED)
        self.assertEqual(report["counts"],
                         {"ready": 0, "review": 0, "blocked": 0})
        self.assertEqual(report["total"], 0)


class DashboardCountsTest(Base):
    """4. 센 수가 Scene별 판정과 맞는다."""

    def test_dashboard_counts_match(self):
        """
        화면에 뜬 숫자가 표와 다르면 사람은 어느 쪽을 믿어야 할지
        모른다. 같은 판정에서 나와야 한다.
        """

        self.images("무릎 스트레칭.png", "허리 세우기.png", "자연광.png")
        self.voices(1, 2, 3)
        self.scan()

        report = self.report([
            "무릎 스트레칭 거실",                                  # ready
            "허리 세우기 침실",                                    # ready
            "40대 남성, 어깨 돌리기, 주방, 미디엄, 중앙, 자연광",   # weak
            "우주선 착륙",                                        # blocked
        ])

        counted = {"ready": 0, "review": 0, "blocked": 0}

        for row in report["scenes"]:
            counted[row["state"]] += 1

        self.assertEqual(report["counts"], counted)
        self.assertEqual(sum(report["counts"].values()), report["total"])

        self.assertEqual(counted, {"ready": 2, "review": 1, "blocked": 1})

    def test_the_counts_ride_along_with_the_requirements(self):
        """두 화면이 같은 말을 한다."""

        self.images("무릎 스트레칭.png")
        self.voices(1)
        self.scan()

        scenes = self.scenes(["무릎 스트레칭 거실", "우주선"])

        prepared = free_workspace.preparation(self.project, scenes)
        required = free_workspace.requirements(self.project, scenes)

        self.assertEqual(required["state"], prepared["state"])
        self.assertEqual(required["counts"], prepared["counts"])

    def test_the_screen_reads_the_counts_instead_of_counting(self):
        source = _script_source()

        for name in ("counts", "blocked"):
            with self.subTest(name=name):
                self.assertIn(name, source)

    def test_the_screen_can_jump_to_a_scene(self):
        """
        누르면 그 Scene으로 간다.

        Timeline이 이미 가진 자리를 쓴다 - 새 이동 방식을 만들지
        않는다.
        """

        source = _script_source()

        self.assertIn("function dashboardRow", source)
        self.assertIn("pickScene", source)


class RenderRuleUnchangedTest(Base):
    """5. 렌더 규칙은 그대로다."""

    def test_render_rule_unchanged(self):
        """
        검토 필요는 막지 않는다. 없는 것만 막는다.

        그리고 그 판정을 렌더 검사에 심지 않았다 - 심으면 화면을
        위한 결정이 파이프라인으로 새어 든다.
        """

        from app.services import asset_integration_service, scene_tts_service

        self.images("자연광.png")
        self.voices(1, 2)
        self.scan()

        scenes = self.scenes([
            "40대 남성, 무릎 스트레칭, 거실, 미디엄, 중앙, 자연광",
            "40대 여성, 허리 세우기, 침실, 미디엄, 중앙, 자연광",
        ])

        self.assertEqual(
            free_workspace.preparation(self.project, scenes)["state"],
            free_workspace.REVIEW)

        for scene in scenes:
            target = os.path.join(
                self.project, "images", f"scene{scene['scene']}.png")

            asset_integration_service._select_ai_first(
                scene["image_prompt"], target, "wellbeing", False,
                scene=scene, provider="local_stock")

        scene_tts_service.create_scene_tts(
            scenes, self.project, provider="local_voice")

        self.assertEqual(
            scene_order.render_problems(self.project, scenes), [])

    def test_scene_order_knows_nothing_about_the_dashboard(self):
        with open(scene_order.__file__, encoding="utf-8") as f:
            source = f.read()

        for word in ("READY", "REVIEW", "BLOCKED", "counts", "reasons"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)

    def test_nothing_external_is_called(self):
        import requests

        from app.providers import local_stock_provider, local_voice_provider
        from app.services import asset_integration_service

        self.images("자연광.png")
        self.scan()

        with patch.object(
            local_stock_provider, "generate_image") as make_image, \
                patch.object(
                    local_voice_provider, "generate_voice") as make_voice, \
                patch.object(
                    asset_integration_service, "get_candidates") as stock, \
                patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post:

            report = self.report(["무릎 스트레칭", "우주선"])

            for name, mock in (("local_stock", make_image),
                               ("local_voice", make_voice),
                               ("스톡 검색", stock),
                               ("requests.get", get),
                               ("requests.post", post)):
                with self.subTest(name=name):
                    mock.assert_not_called()

        self.assertEqual(report["state"], free_workspace.BLOCKED)

    def test_no_file_is_written(self):
        self.images("무릎 스트레칭.png")
        self.scan()

        before = sorted(os.listdir(self.project))

        self.report(["무릎 스트레칭"])

        self.assertEqual(sorted(os.listdir(self.project)), before)


if __name__ == "__main__":
    unittest.main()
