"""
Sprint146 - 진짜 MP4로 확인한다 (Epic 56, Phase 23).

Sprint145는 렌더가 쓰는 네 자리가 같은 차례를 내는지까지 봤다. 이번에는
실제로 영상을 만들어 눈으로 본다 - 그 차이가 결함 하나를 잡았다.

찾은 것
-------
subtitle_service가 자막 글과 시각을 이렇게 짝지었다.

    zip(sorted(scenes, key=...번호...), timeline)

timeline은 이미 렌더 차례인데 글만 번호순으로 정렬해 index로 붙였다.
그래서 파랑(3번) 구간에 1번 문장이 나왔다. video_builder에 있던 것과
같은 부류이고, 두 순서가 늘 같던 시절에는 드러나지 않았다.

어떻게 확인하는가
-----------------
AI는 한 번도 부르지 않는다. 준비된 산출물로 조립·자막·영상만 돌린다.

    그림   scene마다 다른 단색을 넣고 프레임을 뽑아 색을 본다
    소리   scene마다 다른 음량을 넣고 구간 평균 음량을 잰다
    자막   SRT 첫 자막이 누구의 문장인지 본다
"""

import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import scene_order

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)

# scene마다 색·길이·음량을 다르게 준다. 뒤섞여도 누가 어디 있는지
# 알아볼 수 있어야 한다.
SPEC = {
    1: {"color": (220, 30, 30), "name": "빨강", "secs": 1.2, "amp": 0.10},
    2: {"color": (30, 200, 30), "name": "초록", "secs": 1.6, "amp": 0.35},
    3: {"color": (30, 60, 230), "name": "파랑", "secs": 2.0, "amp": 0.90},
}

ORDER = [3, 1, 2]


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _script():
    page = _page()
    return page[page.index("<script>"):]


def _function(name):
    script = _script()
    block = script[script.index(f"function {name}("):]
    end = block.find("\nfunction ", 1)

    return block if end < 0 else block[:end]


def _have_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True)
        return True
    except Exception:
        return False


def _build_project():
    from PIL import Image

    path = tempfile.mkdtemp(prefix="sprint146_")
    os.makedirs(os.path.join(path, "images"))
    os.makedirs(os.path.join(path, "audio", "scenes"))

    scenes = []

    for number, spec in SPEC.items():
        Image.new("RGB", (1080, 1920), spec["color"]).save(
            os.path.join(path, "images", f"scene{number}.png"))

        wav = wave.open(
            os.path.join(path, "audio", "scenes", f"scene{number}.wav"), "wb")
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"".join(
            struct.pack("<h", int(spec["amp"] * 20000 * math.sin(
                2 * math.pi * 300 * i / 24000)))
            for i in range(int(24000 * spec["secs"]))))
        wav.close()

        scenes.append({
            "scene": number,
            "narration": f"{spec['name']} 장면입니다.",
            "image_prompt": f"a {spec['name']} frame",
        })

    with open(os.path.join(path, "script.json"), "w", encoding="utf-8") as f:
        json.dump({"title": "차례 시험", "scenes": scenes}, f,
                  ensure_ascii=False)

    return path, scenes


def _render(path, scenes):
    from app.steps import step03_voice_resolve, step04_subtitle, step05_video

    ordered = scene_order.for_render(path, scenes)

    step03_voice_resolve.run(ordered, path)
    step04_subtitle.run(path)
    step05_video.run(path)

    return os.path.join(path, "video", "final_short.mp4")


def _frame_scene(video, at):
    from PIL import Image

    shot = os.path.join(tempfile.mkdtemp(), "f.png")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", video,
         "-frames:v", "1", shot], capture_output=True)

    image = Image.open(shot).convert("RGB")
    rgb = image.getpixel((image.size[0] // 2, image.size[1] // 2))

    return min(SPEC, key=lambda n: sum(
        (a - b) ** 2 for a, b in zip(rgb, SPEC[n]["color"])))


def _mean_db(audio, start, length):
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", str(start), "-t", str(length),
         "-i", audio, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True)

    found = re.search(r"mean_volume:\s*(-?\d+\.?\d*) dB", out.stderr)

    return float(found.group(1)) if found else None


def _bounds(order):
    out, cursor = [], 0.0

    for number in order:
        out.append((number, cursor, cursor + SPEC[number]["secs"]))
        cursor += SPEC[number]["secs"]

    return out


@unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
class TestRealRenderFollowsTimelineOrder(unittest.TestCase):
    """실제로 영상을 만들어 본다. AI는 부르지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.path, cls.scenes = _build_project()
        scene_order.save(cls.path, order=ORDER)
        cls.video = _render(cls.path, cls.scenes)

    def test_real_render_follows_timeline_order(self):
        self.assertTrue(os.path.exists(self.video))

        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", self.video],
            capture_output=True, text=True)

        expected = sum(s["secs"] for s in SPEC.values())

        self.assertAlmostEqual(float(out.stdout.strip()), expected, delta=0.3)

    def test_mp4_scene_order_matches_timeline(self):
        """[3,1,2] -> 첫 장면이 파랑, 다음이 빨강, 마지막이 초록."""

        seen = [
            _frame_scene(self.video, (start + end) / 2)
            for _, start, end in _bounds(ORDER)
        ]

        self.assertEqual(seen, ORDER)

    def test_audio_image_subtitle_point_at_the_same_scene(self):
        # 소리 - 구간 평균 음량의 순위가 원래 진폭 순위와 같아야 한다
        audio = os.path.join(self.path, "audio", "final_audio.wav")

        measured = [
            (number, _mean_db(audio, start + 0.2, (end - start) - 0.4))
            for number, start, end in _bounds(ORDER)
        ]

        by_volume = [n for n, _ in sorted(measured, key=lambda x: x[1])]
        by_amp = sorted(SPEC, key=lambda n: SPEC[n]["amp"])

        self.assertEqual(by_volume, by_amp)

        # 자막 - 첫 자막이 첫 장면의 문장이어야 한다
        srt = os.path.join(self.path, "subtitle", "subtitle.srt")

        with open(srt, encoding="utf-8") as f:
            first = f.read().strip().split("\n\n")[0]

        self.assertIn(SPEC[ORDER[0]]["name"], first)

    def test_the_subtitle_no_longer_sorts_behind_our_back(self):
        """실제 MP4가 잡은 결함이다."""

        from app.services import subtitle_service

        with open(subtitle_service.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn('sorted(scenes, key=lambda item: item["scene"])',
                         source)
        self.assertIn("zip(scenes, timeline)", source)


class TestRenderErrorShowsMissingScene(unittest.TestCase):

    def _project(self):
        path = tempfile.mkdtemp()
        os.makedirs(os.path.join(path, "images"))
        os.makedirs(os.path.join(path, "audio", "scenes"))

        scenes = [{"scene": n, "narration": f"{n}번", "image_prompt": "p"}
                  for n in (1, 2)]

        with open(os.path.join(path, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": scenes}, f, ensure_ascii=False)

        return path, scenes

    def test_render_error_shows_missing_scene(self):
        path, scenes = self._project()

        problems = scene_order.render_problems(path, scenes)

        self.assertIn("Scene 1 이미지가 없습니다", problems)
        self.assertIn("Scene 2 음성이 없습니다", problems)

    def test_the_endpoint_says_it_and_starts_nothing(self):
        from fastapi.testclient import TestClient

        import app.routers.studio as studio_router
        from app.main import app

        path, _ = self._project()

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            with patch("app.services.studio_review.render") as render:
                response = TestClient(app).post(
                    "/studio/api/review/p1/render")

        self.assertEqual(response.status_code, 400)
        self.assertIn("이미지가 없습니다", response.json()["detail"])
        render.assert_not_called()

    def test_the_screen_shows_them_instead_of_going_on(self):
        script = _script()

        self.assertIn("renderProblems", script)
        self.assertIn("renderProblems", _function("reviewApprove"))
        self.assertIn("onRefused", _function("reviewCall"))

    def test_the_screen_does_not_guess_them_in_advance(self):
        """눌러 본 뒤에만 말한다 - 미리 짐작하지 않는다."""

        block = _function("sceneTimeline")

        self.assertIn("renderProblems.length", block)


class TestTimelineDirtyState(unittest.TestCase):

    def test_timeline_dirty_state(self):
        script = _script()

        self.assertIn("function timelineSaveState(", script)

        block = _function("timelineSaveState")

        self.assertIn("저장하지 않은 변경", block)
        self.assertIn("저장 완료", block)
        self.assertIn("저장됨", block)

    def test_it_asks_the_one_function_that_knows(self):
        block = _function("timelineSaveState")

        self.assertIn("timelineDirty()", block)
        self.assertIn("timelineJustSaved", block)

    def test_saving_says_it_is_done(self):
        block = _function("reviewSaveScript")

        self.assertIn("timelineJustSaved = true", block)

    def test_touching_it_again_clears_that(self):
        for name in ("noteEdit", "moveScene", "addScene", "hideScene"):
            with self.subTest(name=name):
                self.assertIn("timelineJustSaved = false", _function(name))

    def test_the_current_order_is_shown(self):
        block = _function("sceneTimeline")

        self.assertIn("visibleScenes(state)", block)
        self.assertIn("순서", block)


class TestDeletedSceneCanRestore(unittest.TestCase):

    def test_deleted_scene_can_restore(self):
        path = tempfile.mkdtemp()
        scenes = [{"scene": n, "narration": f"{n}번", "image_prompt": "p"}
                  for n in (1, 2, 3)]

        scene_order.save(path, deleted=[2])
        self.assertEqual(
            [s["scene"] for s in scene_order.for_render(path, scenes)],
            [1, 3])

        scene_order.save(path, deleted=[])
        self.assertEqual(
            [s["scene"] for s in scene_order.for_render(path, scenes)],
            [1, 2, 3])

    def test_the_screen_calls_it_hiding_not_deleting(self):
        script = _script()

        self.assertIn("function hideScene(", script)
        self.assertIn("function restoreScene(", script)
        self.assertNotIn("function deleteScene(", script)

    def test_a_hidden_scene_stays_on_the_timeline(self):
        """목록에서 빼 버리면 복구할 자리가 없다."""

        block = _function("timelineScenes")

        # 숨긴 것을 걸러 내던 자리가 없어야 한다.
        self.assertNotIn("gone.has", block)
        self.assertNotIn("filter(s => !", block)

        # 대신 카드가 흐리게 그린다.
        self.assertIn("hidden", _function("sceneCard"))

    def test_the_card_offers_the_way_back(self):
        block = _function("sceneCard")

        self.assertIn("restoreScene(", block)
        self.assertIn("hideScene(", block)

    def test_hiding_removes_no_file(self):
        block = _function("hideScene")

        self.assertIn("sceneDeleted", block)
        self.assertNotIn("fetch(", block)

    def test_the_words_stay_in_the_script(self):
        """숨김은 지움이 아니다 - 대본은 전부 저장된다."""

        block = _function("reviewSaveScript")

        self.assertIn("data: {title:", block)
        self.assertIn("scenes: scenes}", block)
        self.assertIn("order: shown.map", block)


class TestNothingForbiddenMoved(unittest.TestCase):

    def _constants(self, module):
        import ast

        with open(module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        return {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_the_steps_did_not_change(self):
        from app.steps import (
            step01_script, step02_asset_resolve, step03_voice_resolve,
        )

        for module in (step01_script, step02_asset_resolve,
                       step03_voice_resolve):
            with self.subTest(module=module.__name__):
                self.assertNotIn("scene_order", self._constants(module))
                self.assertNotIn("timeline.json", self._constants(module))

    def test_the_providers_did_not_change(self):
        from app.services import provider_selection

        self.assertNotIn("scene_order", self._constants(provider_selection))

    def test_the_engines_did_not_change(self):
        from app.services import image_service, script_service

        for module in (script_service, image_service):
            with self.subTest(module=module.__name__):
                self.assertNotIn("scene_order", self._constants(module))


if __name__ == "__main__":
    unittest.main()
