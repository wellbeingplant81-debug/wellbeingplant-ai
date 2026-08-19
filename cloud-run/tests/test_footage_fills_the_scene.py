"""
Sprint227 - 고른 영상이 그 장면을 채운다 (Epic 68).

Sprint223·224가 스톡 영상과 내 자료 영상을 실제로 재생시켰다. 그런데
고르는 쪽은 그 사실을 모르고 있었다.

    motion_score   Pexels 길이가 3~30초면 일률적으로 +0.10
                   scene이 12초든 2초든 같은 점수
    Pixabay        응답에 있던 duration을 버리고 있었다 -> 늘 0점
    내 자료         길이를 아는 곳이 아예 없었다

그래서 scene보다 많이 짧은 영상이 뽑히면 footage.plan이 마지막 프레임을
붙잡고(hold), 그 scene은 사실상 예전의 정지 사진으로 되돌아간다. 그 일이
얼마나 자주 일어나는지도 아무 데도 남지 않았다.

이 회차가 하는 일은 셋뿐이다
----------------------------
    1. 길이를 알게 한다        Pixabay · 내 자료
    2. 그 길이를 scene 길이와 견준다
    3. 실제로 어떻게 채웠는지 남긴다   trim · loop · hold

더 좋은 영상을 고르는 규칙을 새로 짜지 않는다. 순위의 다른 항목은 한
줄도 건드리지 않았다.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import asset_relevance, footage, media_tools
from app.services.duration_estimator import estimate_duration


# 예상 길이가 넉넉히 나오는 나레이션 하나. 숫자를 지어내지 않고
# 시험 안에서 같은 함수로 다시 잰다.
NARRATION = (
    "무릎이 아플 때는 앉아서 다리를 천천히 펴고 십 초를 세어 봅니다. "
    "그다음 반대쪽도 같은 방법으로 해 주십시오."
)

SCENE = {"scene": 1, "narration": NARRATION, "image_prompt": "무릎 스트레칭"}


def _video(duration, source="pexels_video"):
    return {"source": source, "duration": duration,
            "source_url": "u", "download_url": "d", "query": "q"}


class TheScoreAsksWhetherItFillsTheSceneTest(unittest.TestCase):
    """
    "이 영상이 이 scene을 채울 수 있는가"가 판정이다.
    """

    def setUp(self):
        self.needed = estimate_duration(NARRATION)

        self.assertGreater(self.needed, 2.0, "시험용 나레이션이 너무 짧다")

    def test_a_video_that_covers_the_scene_gets_the_full_mark(self):
        self.assertEqual(
            asset_relevance.motion_score(_video(self.needed + 1), SCENE),
            asset_relevance.MOTION_BONUS,
        )

    def test_exactly_long_enough_still_covers(self):
        self.assertEqual(
            asset_relevance.motion_score(_video(self.needed), SCENE),
            asset_relevance.MOTION_BONUS,
        )

    def test_a_video_that_must_loop_gets_less(self):
        """되풀이해야 덮는다. 덮기는 하므로 0은 아니다."""

        said = asset_relevance.motion_score(
            _video(self.needed / 2.0), SCENE)

        self.assertEqual(said, asset_relevance.MOTION_LOOP_BONUS)
        self.assertGreater(said, 0.0)
        self.assertLess(said, asset_relevance.MOTION_BONUS)

    def test_a_video_that_would_only_freeze_gets_nothing(self):
        """
        마지막 프레임을 붙잡으면 그 scene은 정지 사진으로 되돌아간다 -
        영상을 골랐다는 사실이 화면에서 사라진다.
        """

        self.assertEqual(
            asset_relevance.motion_score(
                _video(footage.LOOP_MIN_SOURCE_SECONDS / 2.0), SCENE),
            0.0,
        )

    def test_longer_is_not_better(self):
        """
        6초와 60초가 5초 scene을 채우는 데는 아무 차이가 없다 - 둘 다
        앞에서 잘라 쓰고 남는 것은 버린다. 길이에 점수를 주면 쓰지도
        않을 시간을 이유로 더 맞는 영상을 밀어낸다.
        """

        just_enough = asset_relevance.motion_score(
            _video(self.needed), SCENE)
        far_more = asset_relevance.motion_score(
            _video(self.needed * 10), SCENE)

        self.assertEqual(just_enough, far_more)

    def test_the_boundary_is_the_one_the_render_uses(self):
        """
        점수와 실제 결과가 서로 다른 말을 하면 안 된다. 판정을 여기서
        새로 짜지 않고 footage.plan에게 묻는다.
        """

        for source_seconds in (self.needed * 2, self.needed / 2.0, 0.4):
            with self.subTest(source=source_seconds):
                mode = footage.plan(source_seconds, self.needed)["mode"]
                said = asset_relevance.motion_score(
                    _video(source_seconds), SCENE)

                expected = {
                    footage.TRIM: asset_relevance.MOTION_BONUS,
                    footage.LOOP: asset_relevance.MOTION_LOOP_BONUS,
                    footage.HOLD: 0.0,
                }[mode]

                self.assertEqual(said, expected)

    # --- 모르는 것은 모른다고 한다 ---

    def test_a_photo_is_not_scored_for_motion(self):
        self.assertEqual(
            asset_relevance.motion_score(
                {"source": "pexels_image"}, SCENE), 0.0)

    def test_a_video_without_a_length_scores_nothing(self):
        self.assertEqual(
            asset_relevance.motion_score(_video(None), SCENE), 0.0)

    def test_without_a_scene_it_behaves_as_before(self):
        """
        기존 호출부는 인자 하나로 부른다. 그 길은 예전 그대로 넓은
        창으로 본다.
        """

        low, high = asset_relevance.USABLE_DURATION_SECONDS

        self.assertEqual(
            asset_relevance.motion_score(_video((low + high) / 2)),
            asset_relevance.MOTION_BONUS)
        self.assertEqual(
            asset_relevance.motion_score(_video(high + 10)), 0.0)

    def test_a_scene_without_narration_falls_back_to_the_window(self):
        """대본이 없으면 몇 초짜리 scene인지 알 방법이 없다."""

        empty = {"scene": 1, "narration": "", "image_prompt": "p"}

        self.assertIsNone(asset_relevance.needed_seconds(empty))
        self.assertEqual(
            asset_relevance.motion_score(_video(100), empty), 0.0)


class ThePixabayVideoNowCarriesItsLengthTest(unittest.TestCase):
    """
    응답에 이미 있던 값이다. 버리고 있었기 때문에 Pixabay 영상은 길이가
    무엇이든 늘 같은 점수를 받았다.
    """

    def _answer(self, hits):
        class _Response:
            status_code = 200

            def json(self):
                return {"hits": hits}

        return _Response()

    def _search(self, hits):
        from app.providers import pixabay_provider

        with patch.dict(os.environ, {"PIXABAY_API_KEY": "k"}), \
                patch.object(pixabay_provider.requests, "get",
                             return_value=self._answer(hits)):
            return pixabay_provider.search_videos("무릎")

    def test_the_length_comes_through(self):
        found = self._search([{
            "pageURL": "u", "duration": 12,
            "videos": {"large": {"url": "v", "width": 1080, "height": 1920}},
        }])

        self.assertEqual(found[0]["duration"], 12)

    def test_a_hit_without_a_length_says_none(self):
        """없는 것을 지어내지 않는다."""

        found = self._search([{
            "pageURL": "u",
            "videos": {"large": {"url": "v", "width": 1080, "height": 1920}},
        }])

        self.assertIsNone(found[0]["duration"])

    def test_the_rest_of_the_candidate_is_unchanged(self):
        found = self._search([{
            "pageURL": "u", "duration": 12,
            "videos": {"large": {"url": "v", "width": 1080, "height": 1920}},
        }])[0]

        self.assertEqual(found["source"], "pixabay_video")
        self.assertEqual(found["source_url"], "u")
        self.assertEqual(found["download_url"], "v")
        self.assertEqual(found["width"], 1080)
        self.assertEqual(found["height"], 1920)
        self.assertEqual(found["query"], "무릎")

    def test_it_can_now_be_judged_against_a_scene(self):
        """
        길이를 알기 전에는 이 후보가 scene을 채우는지 알 수 없었다.
        """

        found = self._search([{
            "pageURL": "u", "duration": 60,
            "videos": {"large": {"url": "v", "width": 1080, "height": 1920}},
        }])[0]

        self.assertEqual(asset_relevance.motion_score(found, SCENE),
                         asset_relevance.MOTION_BONUS)


def _have_ffmpeg():
    try:
        for tool in (media_tools.FFMPEG, media_tools.FFPROBE):
            subprocess.run([media_tools.resolve(tool), "-version"],
                           capture_output=True)
        return True
    except Exception:
        return False


def _clip(path, seconds, colour="0x1e3ce6"):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        [media_tools.resolve(media_tools.FFMPEG), "-v", "error", "-y",
         "-f", "lavfi", "-i",
         "color=c=%s:s=640x360:r=30:d=%s" % (colour, seconds),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
        capture_output=True)

    return path


@unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
class MyOwnVideoTellsItsLengthTest(unittest.TestCase):
    """
    스톡은 검색 응답이 길이를 알려 준다. 내 자료는 알려 줄 사람이 없어
    고른 뒤에 한 번 잰다.
    """

    def setUp(self):
        from app.services import local_library

        self.root = tempfile.mkdtemp(prefix="sprint227_")
        self.project = tempfile.mkdtemp(prefix="sprint227_p_")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.library = local_library

    def _scan(self):
        self.library.save(self.project, self.library.scan(self.root))

    def test_a_video_reports_how_long_it_is(self):
        from app.providers import local_stock_provider

        _clip(os.path.join(self.root, "videos", "무릎.mp4"), 2.0)
        self._scan()

        said = local_stock_provider.place(
            "무릎 스트레칭",
            os.path.join(self.project, "images", "scene1.png"))

        self.assertIsNotNone(said["duration"])
        self.assertAlmostEqual(said["duration"], 2.0, delta=0.3)

    def test_a_picture_reports_no_length(self):
        """그림에는 길이가 없다. 0이 아니라 없는 것이다."""

        from PIL import Image

        from app.providers import local_stock_provider

        os.makedirs(os.path.join(self.root, "images"), exist_ok=True)
        Image.new("RGB", (1080, 1920), (30, 60, 230)).save(
            os.path.join(self.root, "images", "무릎.png"))
        self._scan()

        said = local_stock_provider.place(
            "무릎 스트레칭",
            os.path.join(self.project, "images", "scene1.png"))

        self.assertIsNone(said["duration"])

    def test_the_rest_of_the_contract_is_unchanged(self):
        from app.providers import local_stock_provider

        source = _clip(os.path.join(self.root, "videos", "무릎.mp4"), 2.0)
        self._scan()

        where = os.path.join(self.project, "images", "scene1.png")
        said = local_stock_provider.place("무릎 스트레칭", where)

        self.assertEqual(said["path"], where)
        self.assertEqual(said["kind"], self.library.VIDEOS)
        self.assertEqual(said["footage_source"], source)

    def test_something_that_is_not_a_video_measures_to_nothing(self):
        from app.providers import local_stock_provider

        broken = os.path.join(self.root, "videos", "깨진.mp4")
        os.makedirs(os.path.dirname(broken), exist_ok=True)

        with open(broken, "wb") as f:
            f.write(b"not a video")

        self.assertIsNone(local_stock_provider.seconds_of(broken))


@unittest.skipUnless(_have_ffmpeg(), "ffmpeg이 없습니다")
class HowItActuallyFilledTheSceneIsRecordedTest(unittest.TestCase):
    """
    실제 영상으로 세 갈래를 모두 지나 본다. hold가 얼마나 자주
    일어나는지 알고 싶다는 것이 이 기록의 목적이다.
    """

    def setUp(self):
        from app.services import asset_observatory

        self.observatory = asset_observatory

        self.where = tempfile.mkdtemp(prefix="sprint227_f_")
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)

        asset_observatory.start()
        self.addCleanup(asset_observatory.abandon)

    def _mode_for(self, scene_number, source_seconds, scene_seconds):
        clip = _clip(
            os.path.join(self.where, "s%d.mp4" % scene_number),
            source_seconds)

        made = footage.build_footage_clip(
            clip, scene_seconds, scene_number=scene_number)
        made.close()

        return self.observatory.snapshot()[scene_number]["footage"]

    def test_a_long_video_is_recorded_as_trimmed(self):
        said = self._mode_for(1, 3.0, 1.0)

        self.assertEqual(said["mode"], footage.TRIM)
        self.assertAlmostEqual(said["source_seconds"], 3.0, delta=0.3)
        self.assertAlmostEqual(said["scene_seconds"], 1.0, delta=0.01)

    def test_a_short_video_is_recorded_as_looped(self):
        said = self._mode_for(2, 1.5, 3.0)

        self.assertEqual(said["mode"], footage.LOOP)

    def test_a_very_short_video_is_recorded_as_held(self):
        """이것이 알고 싶은 것이다 - 사실상 정지 사진으로 되돌아간 scene."""

        said = self._mode_for(3, 0.5, 3.0)

        self.assertEqual(said["mode"], footage.HOLD)

    def test_all_three_can_be_counted_together(self):
        self._mode_for(1, 3.0, 1.0)
        self._mode_for(2, 1.5, 3.0)
        self._mode_for(3, 0.5, 3.0)

        modes = [entry["footage"]["mode"]
                 for entry in self.observatory.snapshot().values()
                 if entry.get("footage")]

        self.assertEqual(sorted(modes),
                         sorted([footage.TRIM, footage.LOOP, footage.HOLD]))

    def test_without_a_scene_number_nothing_is_recorded(self):
        """예전 호출부는 번호를 주지 않는다."""

        clip = _clip(os.path.join(self.where, "quiet.mp4"), 2.0)

        made = footage.build_footage_clip(clip, 1.0)
        made.close()

        self.assertEqual(self.observatory.snapshot(), {})

    def test_a_scene_that_used_a_picture_has_no_footage_record(self):
        """
        영상이 아니었던 scene에는 끝까지 없다 - "기록이 없다"와 "그림을
        썼다"가 구별되어야 한다.
        """

        self.observatory.record_outcome(9, "ai_image", "images/scene9.png")

        self.assertIsNone(self.observatory.snapshot()[9]["footage"])


if __name__ == "__main__":
    unittest.main()
