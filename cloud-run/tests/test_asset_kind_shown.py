"""
Sprint223 - 이 그림이 어디서 왔는지 화면이 말한다 (Epic 65).

스톡 영상이 실제로 재생되기 시작하면, 사람은 어떤 scene이 움직이고
어떤 scene이 정지 사진인지 알아볼 수 있어야 한다. 지금까지는 전부
정지 사진이라 물을 일이 없었다.

새로 분류하지 않는다
--------------------
script.json에는 이미 provider와 asset_type이 적혀 있다. 화면이 다시
판정하면 그 순간 같은 사실을 두 곳에서 관리하게 되고, 어느 날 화면과
산출물이 서로 다른 말을 한다.
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

from app.services import asset_kind, studio_review

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


class TheNameWeShowTest(unittest.TestCase):
    """provider 이름을 사람의 말로 옮긴다."""

    def test_stock_video_says_it_is_video(self):
        for name in ("pexels_video", "pixabay_video"):
            with self.subTest(name=name):
                self.assertEqual(
                    asset_kind.label(name, "video"), "스톡 영상")

    def test_stock_photo_says_it_is_a_photo(self):
        for name in ("pexels_image", "pixabay_image"):
            with self.subTest(name=name):
                self.assertEqual(
                    asset_kind.label(name, "image"), "스톡 사진")

    def test_what_the_model_drew_says_ai(self):
        for name in ("ai_image", "flux", "gpt_image"):
            with self.subTest(name=name):
                self.assertEqual(
                    asset_kind.label(name, "image"), "AI 이미지")

    def test_my_own_material_is_not_called_ai(self):
        """
        local_stock은 AI_SOURCES에 들어 있지만(confidence 때문이다)
        사람에게는 제 폴더에서 고른 제 자료다. AI가 만들었다고 적으면
        거짓말이다.
        """

        self.assertEqual(
            asset_kind.label("local_stock", "image"), "내 자료")

    def test_my_own_video_says_it_is_a_video(self):
        """
        Sprint224 - 내 자료도 이제 재생된다. "내 자료"라고만 적으면
        사람은 그 scene이 움직이는지 알 수 없다 - 스톡과 달리 이름이
        local_stock 하나뿐이라 asset_type이 갈라 준다.
        """

        self.assertEqual(
            asset_kind.label("local_stock", "video"), "내 자료 영상")
        self.assertTrue(asset_kind.moves("video"))

    def test_what_the_person_put_in_says_so(self):
        self.assertEqual(
            asset_kind.label("image_import", "image"),
            "내가 넣은 그림")

    def test_an_unknown_provider_says_nothing(self):
        """지어내지 않는다. 빈 글자면 화면은 아무것도 그리지 않는다."""

        for name in ("", None, "무언가새로운것"):
            with self.subTest(name=name):
                self.assertEqual(asset_kind.label(name, "image"), "")

    def test_an_unknown_provider_that_gave_video_is_still_video(self):
        """이름은 몰라도 영상이었다는 것은 안다 - 영상은 스톡뿐이다."""

        self.assertEqual(
            asset_kind.label("무언가새로운것", "video"), "스톡 영상")


class TheReviewStateCarriesItTest(unittest.TestCase):
    """화면이 읽는 자리까지 값이 온다."""

    def _project(self, scenes):
        path = tempfile.mkdtemp(prefix="sprint223_ui_")

        with open(os.path.join(path, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": scenes}, f, ensure_ascii=False)

        return path

    def test_it_hands_over_what_script_json_already_said(self):
        path = self._project([
            {"scene": 1, "narration": "가", "image_prompt": "p",
             "provider": "pexels_video", "asset_type": "video"},
            {"scene": 2, "narration": "나", "image_prompt": "p",
             "provider": "ai_image", "asset_type": "image"},
        ])

        scenes = studio_review.state(path)["scenes"]

        self.assertEqual(scenes[0]["asset_label"], "스톡 영상")
        self.assertEqual(scenes[0]["asset_type"], "video")
        self.assertEqual(scenes[0]["asset_source"], "pexels_video")
        self.assertEqual(scenes[1]["asset_label"], "AI 이미지")

    def test_an_older_project_says_nothing_instead_of_guessing(self):
        """
        provider를 적기 전에 만든 프로젝트가 있다. 그때는 빈 글자다 -
        화면이 그 자리에 아무것도 그리지 않는다.
        """

        path = self._project([
            {"scene": 1, "narration": "가", "image_prompt": "p"},
        ])

        scene = studio_review.state(path)["scenes"][0]

        self.assertEqual(scene["asset_label"], "")
        self.assertEqual(scene["asset_type"], "")
        self.assertEqual(scene["asset_source"], "")


class TheCardShowsItTest(unittest.TestCase):
    """검수 화면의 scene 카드가 그 말을 그린다."""

    def test_the_card_asks_for_the_badge(self):
        page = _page()

        self.assertIn("assetBadge(s)", page)

    def test_the_badge_reads_the_server_word(self):
        page = _page()

        self.assertIn("s.asset_label", page)

    def test_the_badge_draws_nothing_when_there_is_nothing_to_say(self):
        page = _page()
        block = page[page.index("function assetBadge("):]
        block = block[:block.index("\nfunction ", 1)]

        self.assertIn('if(!label) return "";', block)

    def test_the_moving_one_is_marked_apart(self):
        """
        스톡 영상은 이 프로그램이 정지 사진으로만 쓰던 것이다. 사람이
        그 차이를 알아볼 수 있어야 한다.
        """

        page = _page()
        block = page[page.index("function assetBadge("):]
        block = block[:block.index("\nfunction ", 1)]

        self.assertIn('s.asset_type === "video"', block)

    def test_the_badge_has_a_style_of_its_own(self):
        page = _page()

        self.assertIn(".tl .card .src{", page)

    def test_the_badge_paints_with_tokens_only(self):
        """
        Sprint218이 본문 CSS에서 박힌 색을 전부 걷어냈다. 새 규칙이
        그것을 되살리면 라이트 테마에서 안 보이는 자리가 생긴다.
        """

        page = _page()
        start = page.index(".tl .card .src{")
        block = page[start:page.index("\n.tl .card .foot{", start)]

        self.assertNotIn("#", block)


class TheNamesLiveInOnePlaceTest(unittest.TestCase):
    """
    이 표를 처음에는 studio_review 안에 두었다가 가드가 울었다 - 검수
    흐름에 Provider 이름이 새어 드는 것을 막는 가드이고, 그 가드가
    옳았다. 다시 그쪽으로 새지 않게 여기서도 붙잡는다.
    """

    def test_the_review_flow_does_not_name_providers(self):
        source = open(studio_review.__file__, encoding="utf-8").read()

        for name in ("pexels", "pixabay", "ai_image", "local_stock",
                     "image_import"):
            with self.subTest(name=name):
                self.assertNotIn(name, source.lower())

    def test_the_ai_list_comes_from_the_registry(self):
        """
        새 그림 Provider가 붙는 날 이름을 여기 다시 적어야 한다면,
        그것을 잊는 날 화면이 아무 말도 못 한다.
        """

        from app.services import provider_selection

        self.assertIn(provider_selection.FLUX, asset_kind.AI_PROVIDERS)
        self.assertIn(provider_selection.GPT_IMAGE, asset_kind.AI_PROVIDERS)
        self.assertNotIn(
            provider_selection.LOCAL_STOCK, asset_kind.AI_PROVIDERS)

    def test_a_third_stock_vendor_would_be_understood(self):
        """
        pexels·pixabay를 나열하지 않는다. 이름의 생김새로 가른다 -
        provider_factory가 <업체>_<종류>로 짓는다.
        """

        self.assertEqual(asset_kind.label("새업체_video", "video"), "스톡 영상")
        self.assertEqual(asset_kind.label("새업체_image", "image"), "스톡 사진")

    def test_it_says_which_scenes_move(self):
        self.assertTrue(asset_kind.moves("video"))
        self.assertFalse(asset_kind.moves("image"))
        self.assertFalse(asset_kind.moves(""))


if __name__ == "__main__":
    unittest.main()
