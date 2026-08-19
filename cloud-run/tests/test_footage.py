"""
Sprint223 - 영상 clip 만들기 (Epic 65).

여기서 보는 것은 순수 계산이다 - 어떤 크기를 어떻게 자르고, 모자란
길이를 어떻게 채우는가. 파일을 열지 않으므로 영상이 없어도 돈다.

실제 영상으로 도는 확인은 test_footage_render.py 에 있다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import footage
from app.services.kenburns import VIDEO_HEIGHT, VIDEO_WIDTH


class TheKindOfAssetTest(unittest.TestCase):
    """사진과 영상이 갈리는 자리는 여기 하나뿐이다."""

    def test_it_knows_the_video_containers_we_place(self):
        for name in ("videos/scene1.mp4", "videos/scene2.MOV",
                     "a.m4v", "b.webm"):
            with self.subTest(name=name):
                self.assertTrue(footage.is_footage(name))

    def test_an_image_is_not_footage(self):
        for name in ("images/scene1.png", "a.jpg", "b.JPEG", "c.webp"):
            with self.subTest(name=name):
                self.assertFalse(footage.is_footage(name))

    def test_nothing_is_not_footage(self):
        for name in ("", None):
            with self.subTest(name=name):
                self.assertFalse(footage.is_footage(name))

    def test_it_covers_everything_the_library_calls_a_video(self):
        """
        Sprint224 - 사람이 제 폴더에 넣어 둔 영상이 확장자 그대로
        복사되어 온다. 이 목록이 그것을 덮지 못하면 덮이지 않은
        확장자가 사진으로 읽혀 ImageClip 에 넘어가고, 그 순간 렌더가
        깨진다. 두 목록을 여기서 잠근다.
        """

        from app.services import local_library

        for extension in local_library.EXTENSIONS[local_library.VIDEOS]:
            with self.subTest(extension=extension):
                self.assertTrue(footage.is_footage("내 자료" + extension))


class FillingTheScreenTest(unittest.TestCase):
    """
    9:16 을 덮을 때까지 키우고 넘치는 쪽을 가운데로 자른다.

    여백을 두면 검은 띠가 남고 늘이면 사람이 홀쭉해진다 - 둘 다 하지
    않는다는 것이 이 계산의 전부다.
    """

    def test_a_wide_video_is_scaled_by_its_height(self):
        """가로 영상은 세로가 모자라다. 세로를 기준으로 키운다."""

        wide, tall = footage.scaled_size(1920, 1080)

        self.assertGreaterEqual(tall, VIDEO_HEIGHT)
        self.assertGreater(wide, VIDEO_WIDTH)

    def test_a_tall_video_is_scaled_by_its_width(self):
        wide, tall = footage.scaled_size(720, 1600)

        self.assertGreaterEqual(wide, VIDEO_WIDTH)
        self.assertGreater(tall, VIDEO_HEIGHT)

    def test_an_already_vertical_video_still_covers(self):
        wide, tall = footage.scaled_size(1080, 1920)

        self.assertGreaterEqual(wide, VIDEO_WIDTH)
        self.assertGreaterEqual(tall, VIDEO_HEIGHT)

    def test_the_crop_is_exactly_the_screen(self):
        for source in ((1920, 1080), (720, 1600), (1080, 1920), (640, 480)):
            with self.subTest(source=source):
                x1, y1, x2, y2 = footage.crop_box(*source)

                self.assertEqual(x2 - x1, VIDEO_WIDTH)
                self.assertEqual(y2 - y1, VIDEO_HEIGHT)

    def test_the_crop_never_starts_outside_the_picture(self):
        for source in ((1920, 1080), (720, 1600), (1080, 1920)):
            with self.subTest(source=source):
                x1, y1, _, _ = footage.crop_box(*source)

                self.assertGreaterEqual(x1, 0)
                self.assertGreaterEqual(y1, 0)

    def test_the_crop_stays_inside_the_scaled_picture(self):
        for source in ((1920, 1080), (720, 1600), (1080, 1920), (3840, 2160)):
            with self.subTest(source=source):
                wide, tall = footage.scaled_size(*source)
                _, _, x2, y2 = footage.crop_box(*source)

                self.assertLessEqual(x2, wide)
                self.assertLessEqual(y2, tall)

    def test_what_is_kept_is_the_middle(self):
        """
        어느 쪽을 남길지 고를 근거가 없다. 근거 없이 치우치면 그것은
        구도를 정한 것이 아니라 던진 것이다.

        남는 폭이 홀수면 한쪽이 1px 더 넓다 - 픽셀은 반으로 못 쪼갠다.
        그 1px 말고는 어긋나지 않는다는 것이 여기서 보는 것이다.
        """

        for source in ((1920, 1080), (720, 1600), (640, 480), (3840, 2160)):
            with self.subTest(source=source):
                wide, tall = footage.scaled_size(*source)
                x1, y1, x2, y2 = footage.crop_box(*source)

                self.assertLessEqual(abs(x1 - (wide - x2)), 1)
                self.assertLessEqual(abs(y1 - (tall - y2)), 1)

    def test_a_size_we_cannot_read_is_refused(self):
        for source in ((0, 1080), (1920, 0), (-1, -1)):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    footage.cover_scale(*source)


class MakingTheLengthFitTest(unittest.TestCase):
    """
    scene 의 길이는 나레이션이 정한다. 받아 온 영상이 그 길이에 맞을
    이유가 없다.
    """

    def test_a_longer_video_is_trimmed(self):
        how = footage.plan(20.0, 4.5)

        self.assertEqual(how["mode"], footage.TRIM)
        self.assertEqual(how["take"], 4.5)

    def test_exactly_the_same_length_is_not_looped(self):
        """되풀이할 것이 없다. 한 번 그대로 쓴다."""

        how = footage.plan(4.5, 4.5)

        self.assertEqual(how["mode"], footage.TRIM)

    def test_a_shorter_video_is_looped(self):
        how = footage.plan(3.0, 7.0)

        self.assertEqual(how["mode"], footage.LOOP)
        self.assertEqual(how["take"], 7.0)

    def test_it_loops_enough_times_to_cover_the_scene(self):
        how = footage.plan(3.0, 7.0)

        self.assertGreaterEqual(how["times"] * 3.0, 7.0)

    def test_it_does_not_loop_more_than_it_must(self):
        how = footage.plan(3.0, 7.0)

        self.assertLess((how["times"] - 1) * 3.0, 7.0)

    def test_a_very_short_video_holds_its_last_frame_instead(self):
        """
        0.4초짜리를 열 번 잇는 것은 움직임이 아니라 딸꾹질이다.
        """

        how = footage.plan(0.4, 5.0)

        self.assertEqual(how["mode"], footage.HOLD)
        self.assertEqual(how["play"], 0.4)
        self.assertAlmostEqual(how["freeze"], 4.6)

    def test_the_boundary_between_looping_and_holding_is_one_value(self):
        self.assertEqual(
            footage.plan(footage.LOOP_MIN_SOURCE_SECONDS, 5.0)["mode"],
            footage.LOOP,
        )
        self.assertEqual(
            footage.plan(
                footage.LOOP_MIN_SOURCE_SECONDS - 0.01, 5.0)["mode"],
            footage.HOLD,
        )

    def test_every_plan_fills_exactly_the_scene(self):
        for source in (0.4, 1.0, 3.0, 20.0):
            with self.subTest(source=source):
                self.assertEqual(footage.plan(source, 6.0)["take"], 6.0)

    def test_a_length_we_cannot_use_is_refused(self):
        for source, want in ((20.0, 0), (20.0, -1), (0, 5.0), (-1, 5.0)):
            with self.subTest(source=source, want=want):
                with self.assertRaises(ValueError):
                    footage.plan(source, want)


class TheSameShapeAsKenBurnsTest(unittest.TestCase):
    """
    두 clip 이 같은 타임라인에 이어 붙는다. 크기가 두 곳에 적혀 있으면
    어느 날 한쪽만 바뀌고, 그날 영상의 절반이 다른 크기가 된다.
    """

    def test_the_screen_size_comes_from_kenburns(self):
        from app.services import kenburns

        self.assertIs(footage.VIDEO_WIDTH, kenburns.VIDEO_WIDTH)
        self.assertIs(footage.VIDEO_HEIGHT, kenburns.VIDEO_HEIGHT)
        self.assertIs(footage.SAFETY_SCALE, kenburns.SAFETY_SCALE)

    def test_it_declares_the_same_fps_the_render_writes(self):
        self.assertEqual(footage.FPS, 30)

    def test_a_missing_file_says_so(self):
        with self.assertRaises(Exception) as caught:
            footage.build_footage_clip("없는영상.mp4", 3.0)

        self.assertIn("없는영상.mp4", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
