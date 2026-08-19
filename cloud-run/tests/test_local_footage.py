"""
Sprint224 - 내 자료 영상도 움직인다 (Epic 65, Phase 2).

Sprint223이 스톡 영상을 재생시키고 나서 비대칭 하나가 남았다.

    Pexels·Pixabay에서 받은 영상   재생된다
    사람이 제 폴더에 넣은 영상     여전히 첫 프레임 한 장

받는 사람에게 이것은 설명할 수 없는 차이다 - 돈이 드는 쪽만 움직이고,
공짜인 제 자료는 정지 사진이다. 게다가 release.py가 나눠 주는 예시
폴더 틀에는 videos/가 들어 있다. 영상을 넣으라고 안내해 놓고 그 영상을
정지 사진으로 쓰고 있었다.

새 영상 처리 코드를 만들지 않는다
---------------------------------
재생은 Sprint223의 footage.py가 그대로 한다. 이번에 하는 일은 그
길까지 사실 하나를 나르는 것뿐이다 - "이 그림은 영상에서 뽑았고, 그
영상은 저기 있다".

사람의 파일은 읽기만 한다
-------------------------
받아 온 영상은 우리가 방금 임시 자리에 내려놓은 것이라 옮겨도 잃을
것이 없다. 이것은 다르다 - 사람이 모아 둔 자료이고 다음 영상에도 쓴다.
여기서 가장 중요하게 지키는 것이 그것이다.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.providers import local_stock_provider
from app.services import asset_integration_service, local_library, media_tools


def _have_ffmpeg():
    try:
        subprocess.run([media_tools.resolve(media_tools.FFMPEG), "-version"],
                       capture_output=True)
        return True
    except Exception:
        return False


def _png(path, colour=(200, 30, 30)):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (1080, 1920), colour).save(path)

    return path


def _clip(path, seconds=2.0, colour="0x1e3ce6"):
    """색 하나짜리 짧은 영상. 저장소에 이진 파일을 두지 않는다."""

    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        [media_tools.resolve(media_tools.FFMPEG), "-v", "error", "-y",
         "-f", "lavfi", "-i",
         "color=c=%s:s=640x360:r=30:d=%s" % (colour, seconds),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
        capture_output=True)

    return path


class TheProviderSaysWhatItPlacedTest(unittest.TestCase):
    """
    place()는 놓은 것과 함께 그것이 무엇이었는지 말한다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def _library(self):
        local_library.save(self.project, local_library.scan(self.root))

    def test_a_picture_reports_no_footage(self):
        _png(os.path.join(self.root, "images", "무릎.png"))
        self._library()

        where = os.path.join(self.project, "images", "scene1.png")
        said = local_stock_provider.place("무릎 스트레칭", where)

        self.assertEqual(said["kind"], local_library.IMAGES)
        self.assertIsNone(said["footage_source"])
        self.assertEqual(said["path"], where)
        self.assertTrue(os.path.exists(where))

    @unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
    def test_a_video_reports_where_the_video_is(self):
        source = _clip(os.path.join(self.root, "videos", "무릎.mp4"))
        self._library()

        where = os.path.join(self.project, "images", "scene1.png")
        said = local_stock_provider.place("무릎 스트레칭", where)

        self.assertEqual(said["kind"], local_library.VIDEOS)
        self.assertEqual(said["footage_source"], source)

    @unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
    def test_the_first_frame_is_still_placed(self):
        """예전에 하던 일을 그만두지 않았다."""

        _clip(os.path.join(self.root, "videos", "무릎.mp4"))
        self._library()

        where = os.path.join(self.project, "images", "scene1.png")
        local_stock_provider.place("무릎 스트레칭", where)

        self.assertTrue(os.path.exists(where))
        self.assertGreater(os.path.getsize(where), 0)

    def test_the_old_name_still_returns_the_place(self):
        """
        generate_image로 부르는 자리가 아직 있다(등록소). 돌려주는
        것도 놓이는 파일도 예전과 같아야 한다.
        """

        _png(os.path.join(self.root, "images", "무릎.png"))
        self._library()

        where = os.path.join(self.project, "images", "scene2.png")
        given = local_stock_provider.generate_image("무릎 스트레칭", where)

        self.assertEqual(given, where)
        self.assertTrue(os.path.exists(where))

    def test_the_old_name_still_refuses_the_same_way(self):
        self._library()

        with self.assertRaises(local_stock_provider.LocalStockUnavailable):
            local_stock_provider.generate_image(
                "우주선 착륙",
                os.path.join(self.project, "images", "scene1.png"))


class TheBridgeCarriesItTest(unittest.TestCase):
    """
    다리가 그 사실을 받아 프로젝트에 영상을 놓는다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        os.makedirs(os.path.join(self.project, "images"), exist_ok=True)

        # 기록은 공유 파일에 쌓이므로 막는다(다른 시험들과 같다).
        patcher = patch.object(
            asset_integration_service.asset_feedback_service, "record")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _pick_local_stock(self):
        return patch.object(
            asset_integration_service.provider_selection, "selected",
            lambda project_path, stage: "local_stock")

    def _integrate(self, number=1):
        local_library.save(self.project, local_library.scan(self.root))

        # visual_type을 적어 둔다. 파이프라인이 scene마다 채우는 값이고
        # (visual_type_classifier.apply_visual_type), 프로젝트가 고른
        # Provider가 다리까지 실려 가는 길이 그 두 갈래다. 값이 없는
        # 옛 경로는 Sprint127 때부터 고른 Provider를 보지 않는다 -
        # 이번 회차가 만든 일이 아니고 여기서 고치지도 않는다.
        scene = {"scene": number, "narration": "무릎",
                 "image_prompt": "무릎 스트레칭", "visual_type": "ai"}

        with self._pick_local_stock():
            return asset_integration_service.integrate_asset(
                scene, self.project)

    @unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
    def test_the_video_lands_in_the_project(self):
        _clip(os.path.join(self.root, "videos", "무릎.mp4"))

        result = self._integrate()

        self.assertEqual(
            result["footage_path"],
            os.path.join(self.project, "videos", "scene1.mp4"))
        self.assertTrue(os.path.exists(result["footage_path"]))

    @unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
    def test_the_persons_own_file_is_left_alone(self):
        """
        여기가 이 회차에서 가장 중요한 자리다. 옮기면 사람의 폴더에서
        사라지고, 사람은 우리가 지웠다는 사실조차 모른다.
        """

        source = _clip(os.path.join(self.root, "videos", "무릎.mp4"))
        before = os.path.getsize(source)

        self._integrate()

        self.assertTrue(os.path.exists(source))
        self.assertEqual(os.path.getsize(source), before)

    @unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
    def test_it_is_a_copy_not_a_link(self):
        source = _clip(os.path.join(self.root, "videos", "무릎.mp4"))

        result = self._integrate()

        self.assertNotEqual(result["footage_path"], source)
        self.assertEqual(os.path.getsize(result["footage_path"]),
                         os.path.getsize(source))

    @unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
    def test_the_first_frame_stays_too(self):
        _clip(os.path.join(self.root, "videos", "무릎.mp4"))

        self._integrate()

        self.assertTrue(os.path.exists(
            os.path.join(self.project, "images", "scene1.png")))

    @unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
    def test_the_scene_says_it_is_a_video(self):
        _clip(os.path.join(self.root, "videos", "무릎.mp4"))

        result = self._integrate()

        self.assertEqual(result["asset_type"], "video")
        self.assertEqual(result["provider"], "local_stock")

    @unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
    def test_the_extension_is_not_rewritten(self):
        """
        .mkv를 받아 scene1.mp4로 적으면 이름이 거짓말을 한다.
        """

        _clip(os.path.join(self.root, "videos", "무릎.mkv"))

        result = self._integrate()

        self.assertTrue(result["footage_path"].endswith(".mkv"))

    @unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
    def test_whatever_lands_there_is_understood_as_footage(self):
        """
        렌더가 그것을 영상으로 알아보지 못하면 그림으로 읽혀 깨진다.
        """

        from app.services import footage

        _clip(os.path.join(self.root, "videos", "무릎.mkv"))

        result = self._integrate()

        self.assertTrue(footage.is_footage(result["footage_path"]))


class TheImagePathIsUntouchedTest(unittest.TestCase):
    """
    내 자료 **그림** 경로는 한 글자도 달라지지 않아야 한다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        os.makedirs(os.path.join(self.project, "images"), exist_ok=True)

        patcher = patch.object(
            asset_integration_service.asset_feedback_service, "record")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _integrate(self):
        local_library.save(self.project, local_library.scan(self.root))

        with patch.object(
            asset_integration_service.provider_selection, "selected",
            lambda project_path, stage: "local_stock",
        ):
            return asset_integration_service.integrate_asset(
                {"scene": 1, "narration": "무릎",
                 "image_prompt": "무릎 스트레칭", "visual_type": "ai"},
                self.project)

    def test_a_picture_gains_no_footage(self):
        _png(os.path.join(self.root, "images", "무릎.png"))

        result = self._integrate()

        self.assertNotIn("footage_path", result)
        self.assertEqual(result["asset_type"], "image")

    def test_a_picture_makes_no_videos_folder(self):
        _png(os.path.join(self.root, "images", "무릎.png"))

        self._integrate()

        self.assertFalse(os.path.exists(
            os.path.join(self.project, "videos")))

    def test_the_picture_is_still_placed_where_it_was(self):
        _png(os.path.join(self.root, "images", "무릎.png"))

        result = self._integrate()

        self.assertEqual(
            result["asset_path"],
            os.path.join(self.project, "images", "scene1.png"))
        self.assertTrue(os.path.exists(result["asset_path"]))

    def test_the_persons_picture_is_left_alone(self):
        source = _png(os.path.join(self.root, "images", "무릎.png"))

        self._integrate()

        self.assertTrue(os.path.exists(source))


def _two_colour_clip(path, first, second, switch, length):
    """색이 한 번 바뀌는 영상. 그 변화가 재생의 증거가 된다."""

    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        [media_tools.resolve(media_tools.FFMPEG), "-v", "error", "-y",
         "-f", "lavfi", "-i",
         "color=c=%s:s=1920x1080:r=30:d=%s" % (first, switch),
         "-f", "lavfi", "-i",
         "color=c=%s:s=1920x1080:r=30:d=%s" % (second, length - switch),
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
         "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
        capture_output=True)

    return path


def _tone(path, seconds):
    import math
    import struct
    import wave

    os.makedirs(os.path.dirname(path), exist_ok=True)

    wav = wave.open(path, "wb")
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(24000)
    wav.writeframes(b"".join(
        struct.pack("<h", int(0.3 * 20000 * math.sin(
            2 * math.pi * 300 * i / 24000)))
        for i in range(int(24000 * seconds))))
    wav.close()

    return path


def _colour_at(video, at, known):
    from PIL import Image

    shot = os.path.join(tempfile.mkdtemp(), "f.png")

    subprocess.run(
        [media_tools.resolve(media_tools.FFMPEG), "-v", "error", "-y",
         "-ss", str(at), "-i", video, "-frames:v", "1", shot],
        capture_output=True)

    image = Image.open(shot).convert("RGB")
    rgb = image.getpixel((image.size[0] // 2, image.size[1] // 2))

    return min(known, key=lambda one: sum(
        (a - b) ** 2 for a, b in zip(rgb, one)))


MAGENTA = (200, 40, 200)
YELLOW = (240, 200, 40)
BLUE = (30, 60, 230)


@unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
class MyOwnVideoActuallyMovesTest(unittest.TestCase):
    """
    사람의 폴더에 있는 영상 하나로 끝까지 만들어 본다.

    scene 1  내 자료 영상   자홍 -> 노랑 (받아 온 6초에서 잘라 쓴다)
    scene 2  내 자료 그림   파랑

    Ken Burns를 걸어도 단색 그림은 자홍에서 노랑이 되지 않는다. 한
    scene 안에서 색이 바뀌면 그것은 그 영상이 재생된 것이다.
    """

    @classmethod
    def setUpClass(cls):
        from app.services import video_builder

        cls.root = tempfile.mkdtemp(prefix="sprint224_root_")
        cls.project = tempfile.mkdtemp(prefix="sprint224_proj_")

        cls.source_video = _two_colour_clip(
            os.path.join(cls.root, "videos", "무릎.mp4"),
            "0xc828c8", "0xf0c828", 0.5, 6.0)
        cls.source_image = _png(
            os.path.join(cls.root, "images", "어깨.png"), BLUE)

        os.makedirs(os.path.join(cls.project, "images"), exist_ok=True)
        local_library.save(cls.project, local_library.scan(cls.root))

        seconds = {1: 1.0, 2: 1.4}
        cls.total = sum(seconds.values())

        scenes = []

        with patch.object(
            asset_integration_service.asset_feedback_service, "record",
        ), patch.object(
            asset_integration_service.provider_selection, "selected",
            lambda project_path, stage: "local_stock",
        ):
            for number, prompt in ((1, "무릎 스트레칭"), (2, "어깨 돌리기")):
                _tone(
                    os.path.join(cls.project, "audio", "scenes",
                                 "scene%d.wav" % number),
                    seconds[number])

                scenes.append(asset_integration_service.integrate_asset(
                    {"scene": number, "narration": "%d번" % number,
                     "image_prompt": prompt, "visual_type": "ai"},
                    cls.project))

        cls.scenes = scenes

        import json

        with open(os.path.join(cls.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "내 자료 시험", "scenes": scenes}, f,
                      ensure_ascii=False)

        cls.short = video_builder.build_video(cls.project)

    def test_the_video_scene_actually_moves(self):
        self.assertEqual(
            _colour_at(self.short, 0.30, (MAGENTA, YELLOW, BLUE)), MAGENTA)
        self.assertEqual(
            _colour_at(self.short, 0.85, (MAGENTA, YELLOW, BLUE)), YELLOW)

    def test_the_picture_scene_is_still_the_picture(self):
        self.assertEqual(
            _colour_at(self.short, 1.70, (MAGENTA, YELLOW, BLUE)), BLUE)

    def test_the_length_is_still_the_narration_total(self):
        out = subprocess.run(
            [media_tools.resolve(media_tools.FFPROBE), "-v", "error",
             "-show_entries", "format=duration", "-of",
             "default=nw=1:nk=1", self.short],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace")

        self.assertAlmostEqual(
            float(out.stdout.strip()), self.total, delta=0.15)

    def test_the_persons_files_are_all_still_there(self):
        for where in (self.source_video, self.source_image):
            with self.subTest(where=os.path.basename(where)):
                self.assertTrue(os.path.exists(where))

    def test_the_render_read_the_copy_not_the_original(self):
        """
        사람의 폴더를 렌더가 직접 열지 않는다. 프로젝트 안의 복사본을
        읽는다 - 만드는 도중에 사람이 그 폴더를 건드려도 흔들리지
        않아야 한다.
        """

        self.assertTrue(
            self.scenes[0]["footage_path"].startswith(self.project))

    def test_the_picture_scene_never_got_a_footage(self):
        self.assertNotIn("footage_path", self.scenes[1])


class TheOtherProvidersAreUntouchedTest(unittest.TestCase):
    """
    말할 수 있는 Provider만 새 부름말로 부른다. 나머지 둘에게 새 계약을
    강요하지 않는다.
    """

    def test_only_the_one_that_can_speak_has_the_new_name(self):
        import importlib

        from app.services.asset_integration_service import (
            SINGLE_IMAGE_PROVIDERS,
        )

        speaks = {
            name for name, where in SINGLE_IMAGE_PROVIDERS.items()
            if hasattr(importlib.import_module(where), "place")
        }

        self.assertEqual(speaks, {"local_stock"})

    def test_the_others_still_only_need_generate_image(self):
        import importlib

        from app.services.asset_integration_service import (
            SINGLE_IMAGE_PROVIDERS,
        )

        for name, where in SINGLE_IMAGE_PROVIDERS.items():
            with self.subTest(name=name):
                self.assertTrue(
                    hasattr(importlib.import_module(where), "generate_image"))


if __name__ == "__main__":
    unittest.main()
