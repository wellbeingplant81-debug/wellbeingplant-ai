"""
Sprint123 (GREEN) - Production Policy: Longform 산출물은 Shorts 명칭을
재사용하지 않는다. render_profile이 없거나 "longform"이 아니면(기본값)
오늘의 하드코딩된 파일명과 100% 동일하다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.render_profile import (
    RenderProfile,
    final_video_filename,
    silent_video_filename,
    thumbnail_filename,
)


SHORTS = RenderProfile.get("shorts")
LONGFORM = RenderProfile.get("longform")


class TestRenderProfileFilenames(unittest.TestCase):

    def test_no_render_profile_matches_existing_shorts_filenames(self):
        self.assertEqual(silent_video_filename(None), "short.mp4")
        self.assertEqual(final_video_filename(None), "final_short.mp4")
        self.assertEqual(thumbnail_filename(None), "thumbnail.png")

    def test_shorts_render_profile_matches_existing_filenames(self):
        self.assertEqual(silent_video_filename(SHORTS), "short.mp4")
        self.assertEqual(final_video_filename(SHORTS), "final_short.mp4")
        self.assertEqual(thumbnail_filename(SHORTS), "thumbnail.png")

    def test_longform_render_profile_uses_distinct_filenames(self):
        self.assertEqual(silent_video_filename(LONGFORM), "longform.mp4")
        self.assertEqual(final_video_filename(LONGFORM), "final_longform.mp4")
        self.assertEqual(thumbnail_filename(LONGFORM), "thumbnail_longform.png")

    def test_shorts_and_longform_never_collide(self):
        self.assertNotEqual(silent_video_filename(SHORTS), silent_video_filename(LONGFORM))
        self.assertNotEqual(final_video_filename(SHORTS), final_video_filename(LONGFORM))
        self.assertNotEqual(thumbnail_filename(SHORTS), thumbnail_filename(LONGFORM))


if __name__ == "__main__":
    unittest.main()
