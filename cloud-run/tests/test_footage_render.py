"""
Sprint223 - 진짜 MP4로 확인한다 (Epic 65).

단위 시험은 계산이 맞는지만 안다. "영상이 실제로 움직이는가"는 만들어
놓고 프레임을 뽑아 봐야 안다 - Sprint146이 같은 이유로 이 방식을
택했고 그때 결함 하나를 잡았다.

무엇을 만들어 보는가
--------------------
AI는 한 번도 부르지 않는다. 준비된 산출물로 조립·자막·영상만 돌린다.

    scene 1   스톡 영상    빨강 -> 초록 (받아 온 것 6초, 쓸 자리 1.35초
                           - 잘라 쓴다)
    scene 2   정지 이미지  파랑
    scene 3   스톡 영상    자홍 -> 노랑 (받아 온 것 1.5초, 쓸 자리 2.4초
                           - 되풀이한다)

왜 색이 바뀌는 영상인가
-----------------------
정지 그림에 Ken Burns를 걸어도 화면은 움직인다. 그래서 "프레임이
달라졌다"로는 아무것도 증명하지 못한다 - 단색 그림을 밀고 당겨서는
빨강이 초록이 될 수 없다는 것이 요점이다.

되풀이도 같은 방법으로 본다. scene 3의 뒷자리에서 자홍이 다시 나오면
그것은 처음으로 돌아갔다는 뜻이다.

어디를 재는가
-------------
경계마다 0.35초씩 겹쳐 섞이고(CROSSFADE_DURATION) 첫 scene은 검정에서
밝아지며 마지막 scene은 검정으로 어두워진다. 그래서 섞이지 않는
한가운데만 잰다 - 아래 시각들은 그렇게 고른 것이다.

소리
----
받아 온 영상에 일부러 소리를 넣어 둔다. 중간본(short.mp4)에 소리
갈래가 하나라도 있으면 그것은 스톡의 소리다 - 이 단계는 소리를 넣지
않는다.
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

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import media_tools


RED = (220, 30, 30)
GREEN = (30, 200, 30)
BLUE = (30, 60, 230)
MAGENTA = (200, 40, 200)
YELLOW = (240, 200, 40)

KNOWN = (RED, GREEN, BLUE, MAGENTA, YELLOW)

# scene 마다 나레이션 길이. 이것이 곧 scene 의 길이다(scene_timeline).
SECONDS = {1: 1.0, 2: 1.4, 3: 2.4}

# 받아 온 영상. 색이 언제 바뀌는가.
FOOTAGE = {
    1: {"length": 6.0, "first": RED, "second": GREEN, "switch": 0.5},
    3: {"length": 1.5, "first": MAGENTA, "second": YELLOW, "switch": 0.75},
}

STILL = {2: BLUE}


def _have(tool):
    try:
        subprocess.run([media_tools.resolve(tool), "-version"],
                       capture_output=True)
        return True
    except Exception:
        return False


def _hex(color):
    return "0x%02x%02x%02x" % color


def _make_footage(path, spec):
    """
    두 색이 이어 붙은 영상 하나. 소리도 함께 넣는다.

    lavfi 로 만든다 - 저장소에 이진 파일을 두지 않는다.
    """

    subprocess.run(
        [media_tools.resolve(media_tools.FFMPEG), "-v", "error", "-y",
         "-f", "lavfi", "-i",
         "color=c=%s:s=1920x1080:r=30:d=%s" % (
             _hex(spec["first"]), spec["switch"]),
         "-f", "lavfi", "-i",
         "color=c=%s:s=1920x1080:r=30:d=%s" % (
             _hex(spec["second"]), spec["length"] - spec["switch"]),
         "-f", "lavfi", "-i",
         "sine=frequency=880:duration=%s" % spec["length"],
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
         "-map", "[v]", "-map", "2:a",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         path],
        capture_output=True)


def _build_project():
    from PIL import Image

    path = tempfile.mkdtemp(prefix="sprint223_")
    os.makedirs(os.path.join(path, "images"))
    os.makedirs(os.path.join(path, "videos"))
    os.makedirs(os.path.join(path, "audio", "scenes"))

    scenes = []

    for number in sorted(SECONDS):
        # 첫 프레임은 언제나 함께 남는다 - 그것이 이 회차가 지킨
        # 계약이다. 영상 scene 의 그림은 그 영상의 첫 색으로 둔다.
        color = STILL.get(number) or FOOTAGE[number]["first"]

        Image.new("RGB", (1080, 1920), color).save(
            os.path.join(path, "images", "scene%d.png" % number))

        wav = wave.open(
            os.path.join(path, "audio", "scenes", "scene%d.wav" % number),
            "wb")
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"".join(
            struct.pack("<h", int(0.3 * 20000 * math.sin(
                2 * math.pi * 300 * i / 24000)))
            for i in range(int(24000 * SECONDS[number]))))
        wav.close()

        scene = {
            "scene": number,
            "narration": "%d번 장면입니다." % number,
            "image_prompt": "a frame",
            "asset_path": os.path.join(
                path, "images", "scene%d.png" % number),
        }

        if number in FOOTAGE:
            where = os.path.join(path, "videos", "scene%d.mp4" % number)
            _make_footage(where, FOOTAGE[number])

            scene["asset_type"] = "video"
            scene["provider"] = "pexels_video"
            scene["footage_path"] = where

        scenes.append(scene)

    with open(os.path.join(path, "script.json"), "w", encoding="utf-8") as f:
        json.dump({"title": "영상 시험", "scenes": scenes}, f,
                  ensure_ascii=False)

    return path, scenes


def _colour_at(video, at):
    """그 시각의 화면 가운데 색. 아는 색 중 가장 가까운 것."""

    from PIL import Image

    shot = os.path.join(tempfile.mkdtemp(), "f.png")

    subprocess.run(
        [media_tools.resolve(media_tools.FFMPEG), "-v", "error", "-y",
         "-ss", str(at), "-i", video, "-frames:v", "1", shot],
        capture_output=True)

    image = Image.open(shot).convert("RGB")
    rgb = image.getpixel((image.size[0] // 2, image.size[1] // 2))

    return min(KNOWN, key=lambda known: sum(
        (a - b) ** 2 for a, b in zip(rgb, known)))


def _probe(video, what):
    out = subprocess.run(
        [media_tools.resolve(media_tools.FFPROBE), "-v", "error",
         "-show_entries", what, "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace")

    return out.stdout.strip()


def _streams(video, kind):
    out = subprocess.run(
        [media_tools.resolve(media_tools.FFPROBE), "-v", "error",
         "-select_streams", kind, "-show_entries", "stream=index",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace")

    return [line for line in out.stdout.split() if line.strip()]


@unittest.skipUnless(_have(media_tools.FFMPEG) and _have(media_tools.FFPROBE),
                     "ffmpeg/ffprobe가 없습니다")
class TheMixedTimelineActuallyMovesTest(unittest.TestCase):
    """영상과 그림이 한 타임라인에 섞인다. 실제로 만들어 본다."""

    @classmethod
    def setUpClass(cls):
        from app.services import final_video_service, video_builder
        from app.steps import step03_voice_resolve, step04_subtitle

        cls.path, cls.scenes = _build_project()

        step03_voice_resolve.run(cls.scenes, cls.path)
        step04_subtitle.run(cls.path)

        cls.short = video_builder.build_video(cls.path)

        final_video_service.merge_video_audio(cls.path)

        cls.final = os.path.join(cls.path, "video", "final_short.mp4")

    # --- 만들어졌는가 ---

    def test_the_intermediate_video_exists(self):
        self.assertTrue(os.path.exists(self.short))
        self.assertGreater(os.path.getsize(self.short), 0)

    def test_the_final_video_exists(self):
        self.assertTrue(os.path.exists(self.final))
        self.assertGreater(os.path.getsize(self.final), 0)

    def test_the_screen_is_still_nine_by_sixteen(self):
        self.assertEqual(_probe(self.short, "stream=width"), "1080")
        self.assertEqual(_probe(self.short, "stream=height"), "1920")

    def test_it_is_still_thirty_frames_a_second(self):
        self.assertEqual(_probe(self.short, "stream=r_frame_rate"), "30/1")

    def test_the_length_is_the_narration_total(self):
        """영상이 섞였다고 길이가 달라지면 안 된다. 기준은 나레이션이다."""

        self.assertAlmostEqual(
            float(_probe(self.short, "format=duration")),
            sum(SECONDS.values()), delta=0.15,
        )

    # --- 실제로 움직이는가 ---

    def test_the_first_scene_changes_colour_inside_itself(self):
        """
        단색 그림을 밀고 당겨서는 빨강이 초록이 될 수 없다. 색이
        바뀌었다면 받아 온 영상이 재생된 것이다.
        """

        self.assertEqual(_colour_at(self.short, 0.30), RED)
        self.assertEqual(_colour_at(self.short, 0.85), GREEN)

    def test_the_third_scene_changes_colour_inside_itself(self):
        self.assertEqual(_colour_at(self.short, 2.75), MAGENTA)
        self.assertEqual(_colour_at(self.short, 3.30), YELLOW)

    def test_a_short_video_comes_back_to_its_start(self):
        """받아 온 것이 1.5초인데 쓸 자리가 2.4초다 - 되풀이한다."""

        self.assertEqual(_colour_at(self.short, 4.10), MAGENTA)

    def test_the_still_scene_is_still_the_still(self):
        """영상이 끼어들었다고 그림 scene 이 밀리면 안 된다."""

        self.assertEqual(_colour_at(self.short, 1.80), BLUE)

    # --- 소리 ---

    def test_no_stock_audio_reaches_the_intermediate(self):
        """
        받아 온 영상에는 880Hz 소리가 들어 있다. 이 단계는 소리를 넣지
        않으므로, 소리 갈래가 하나라도 있으면 그것은 스톡의 것이다.
        """

        self.assertEqual(_streams(self.short, "a"), [])

    def test_the_narration_still_reaches_the_final(self):
        self.assertEqual(len(_streams(self.final, "a")), 1)

    def test_the_final_keeps_the_narration_length(self):
        self.assertAlmostEqual(
            float(_probe(self.final, "format=duration")),
            sum(SECONDS.values()), delta=0.30,
        )

    # --- 자막 ---

    def test_the_subtitles_still_end_where_the_narration_ends(self):
        """
        자막의 시각은 같은 타임라인에서 나온다. 영상이 섞였다고 그
        끝이 밀리면 화면과 글이 어긋난다.
        """

        srt = os.path.join(self.path, "subtitle", "subtitle.srt")

        self.assertTrue(os.path.exists(srt))

        with open(srt, encoding="utf-8") as f:
            said = f.read()

        last = re.findall(
            r"--> (\d\d):(\d\d):(\d\d),(\d\d\d)", said)[-1]

        ends = (int(last[0]) * 3600 + int(last[1]) * 60
                + int(last[2]) + int(last[3]) / 1000)

        self.assertAlmostEqual(ends, sum(SECONDS.values()), delta=0.30)


if __name__ == "__main__":
    unittest.main()
