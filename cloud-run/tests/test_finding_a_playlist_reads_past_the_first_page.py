"""
Sprint253 - 재생목록을 찾을 때 첫 장에서 멈추지 않는다.

무엇이 문제인가
---------------
find_playlist_by_title 은 playlists.list 를 한 번 부르고 끝난다. 그
한 번이 주는 것은 최대 50 개다.

재생목록이 50 개를 넘으면, 51 번째에 있는 이름은 "없다" 로 읽힌다.
그리고 그 답을 받은 get_or_create_playlist 는 같은 이름을 하나 더
만든다. 찾지 못해서 만드는 것이지, 없어서 만드는 것이 아니다.

Sprint252 가 playlistItems 쪽에 같은 걸음을 놓았다. 여기도 같은 결함이
같은 모양으로 남아 있었다 - 한쪽만 고치면 다른 쪽이 언젠가 같은 일을
되풀이한다.

무엇을 바꾸지 않는가
--------------------
돌려주는 것은 그대로다. 찾으면 그 id, 못 찾으면 None. 같은 이름이
여럿이면 처음 만난 것 - 페이지가 늘어도 차례는 그대로다.

여기서 재는 것
--------------
실제 YouTube 는 부르지 않는다. 클라이언트를 가짜로 바꿔 두고
**list 가 몇 번, 어떤 표를 들고 불렸는가**를 센다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _credential():
    class _C:
        access_token = "token"
        refresh_token = "refresh"
        account_id = "default"

    return _C()


class _Youtube:
    """playlists().list(...).execute() 만 흉내 낸다."""

    def __init__(self, pages, error=None, last_token=None):
        # pages: [[(id, title), ...], ...]
        self.pages = list(pages)
        self.error = error

        # 마지막 장이 돌려줄 nextPageToken. 기본은 아예 없음.
        self.last_token = last_token

        self.list_calls = []
        self.insert_calls = []

    def playlists(self):
        return self

    def list(self, **kwargs):
        self.list_calls.append(kwargs)

        return _Execute(self._page(kwargs), self.error)

    def insert(self, **kwargs):
        self.insert_calls.append(kwargs)

        return _Execute({"id": "PL_new"})

    def _page(self, kwargs):
        index = 0

        if kwargs.get("pageToken"):
            index = int(str(kwargs["pageToken"]).split("-")[-1])

        rows = self.pages[index] if index < len(self.pages) else []

        body = {"items": [
            {"id": pid, "snippet": {"title": name}} for pid, name in rows
        ]}

        if index + 1 < len(self.pages):
            body["nextPageToken"] = f"page-{index + 1}"
        elif self.last_token is not None:
            # 마지막 장인데 무언가를 더 준 경우. 따라가면 안 된다.
            body["nextPageToken"] = self.last_token

        return body


class _Execute:

    def __init__(self, payload, error=None):
        self.payload = payload
        self.error = error

    def execute(self):
        if self.error is not None:
            raise self.error

        return self.payload


class _Case(unittest.TestCase):

    def find(self, youtube, title="건강 정보"):
        from app.providers.upload.youtube_playlist_service import (
            YouTubePlaylistService,
        )

        with patch(
            "app.providers.upload.youtube_playlist_service.build",
            return_value=youtube,
        ):
            service = YouTubePlaylistService(credential=_credential())

            return service.find_playlist_by_title(title)


# -- 1. 첫 장에 있으면 거기서 끝 --------------------------------------
class TheFirstPageIsEnoughWhenItIsThereTest(_Case):

    def test_첫_장에_있으면_찾는다(self):
        youtube = _Youtube(pages=[[("PL_a", "다른 것"), ("PL_t", "건강 정보")]])

        self.assertEqual(self.find(youtube), "PL_t")

    def test_찾았으면_더_묻지_않는다(self):
        """다음 장이 있어도 부를 이유가 없다."""

        youtube = _Youtube(pages=[[("PL_t", "건강 정보")], [("PL_z", "뒤")]])

        self.find(youtube)

        self.assertEqual(len(youtube.list_calls), 1)

    def test_묻는_모양이_예전_그대로다(self):
        youtube = _Youtube(pages=[[("PL_t", "건강 정보")]])

        self.find(youtube)

        asked = youtube.list_calls[0]

        self.assertEqual(asked["part"], "snippet")
        self.assertTrue(asked["mine"])
        self.assertEqual(asked["maxResults"], 50)
        self.assertIsNone(asked.get("pageToken"))


# -- 2·3·4. 뒤 장까지 따라간다 ----------------------------------------
class TheSearchFollowsThePagesTest(_Case):

    def test_둘째_장에_있으면_찾는다(self):
        youtube = _Youtube(pages=[
            [("PL_a", "하나"), ("PL_b", "둘")],
            [("PL_t", "건강 정보")],
        ])

        self.assertEqual(self.find(youtube), "PL_t")
        self.assertEqual(len(youtube.list_calls), 2)

    def test_셋째_장에_있어도_찾는다(self):
        youtube = _Youtube(pages=[
            [("PL_a", "하나")],
            [("PL_b", "둘")],
            [("PL_t", "건강 정보")],
        ])

        self.assertEqual(self.find(youtube), "PL_t")
        self.assertEqual(len(youtube.list_calls), 3)

    def test_페이지_표를_그대로_들고_간다(self):
        youtube = _Youtube(pages=[[("PL_a", "하나")], [("PL_b", "둘")],
                                  [("PL_c", "셋")]])

        self.find(youtube, title="없는 이름")

        self.assertIsNone(youtube.list_calls[0].get("pageToken"))
        self.assertEqual(youtube.list_calls[1]["pageToken"], "page-1")
        self.assertEqual(youtube.list_calls[2]["pageToken"], "page-2")

    def test_오십을_넘겨도_찾는다(self):
        """이 결함이 실제로 드러나는 크기다."""

        first = [(f"PL_{i}", f"목록 {i}") for i in range(50)]
        youtube = _Youtube(pages=[first, [("PL_t", "건강 정보")]])

        self.assertEqual(self.find(youtube), "PL_t")


# -- 5. 끝까지 없으면 예전 답 그대로 ----------------------------------
class NothingFoundStaysNoneTest(_Case):

    def test_끝까지_없으면_None(self):
        youtube = _Youtube(pages=[[("PL_a", "하나")], [("PL_b", "둘")]])

        self.assertIsNone(self.find(youtube, title="없는 이름"))

    def test_빈_목록이면_None(self):
        youtube = _Youtube(pages=[[]])

        self.assertIsNone(self.find(youtube, title="없는 이름"))

    def test_찾는_동안_아무것도_만들지_않는다(self):
        youtube = _Youtube(pages=[[("PL_a", "하나")], [("PL_b", "둘")]])

        self.find(youtube, title="없는 이름")

        self.assertEqual(youtube.insert_calls, [], "찾다가 만들었다")


# -- 6·7. 이상한 표는 따라가지 않는다 ---------------------------------
class AStrangeTokenDoesNotLoopForeverTest(_Case):

    def test_빈_문자열이면_멈춘다(self):
        youtube = _Youtube(pages=[[("PL_a", "하나")]], last_token="")

        self.assertIsNone(self.find(youtube, title="없는 이름"))
        self.assertEqual(len(youtube.list_calls), 1)

    def test_None_이면_멈춘다(self):
        youtube = _Youtube(pages=[[("PL_a", "하나")]], last_token=None)

        self.assertIsNone(self.find(youtube, title="없는 이름"))
        self.assertEqual(len(youtube.list_calls), 1)

    def test_글자가_아니면_멈춘다(self):
        """
        가짜 객체가 무엇이든 돌려줄 때 여기서 영원히 돌면 안 된다.
        진짜 API 는 글자를 주거나 아무것도 주지 않는다.
        """

        for odd in (123, True, {}, [], object()):
            with self.subTest(token=type(odd).__name__):
                youtube = _Youtube(pages=[[("PL_a", "하나")]], last_token=odd)

                self.assertIsNone(self.find(youtube, title="없는 이름"))
                self.assertEqual(len(youtube.list_calls), 1)

    def test_MagicMock_이어도_멈춘다(self):
        """예전 시험들이 통째로 MagicMock 을 준다."""

        from unittest.mock import MagicMock

        fake = MagicMock()
        fake.playlists.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "PL_t", "snippet": {"title": "건강 정보"}}],
        }

        from app.providers.upload.youtube_playlist_service import (
            YouTubePlaylistService,
        )

        with patch(
            "app.providers.upload.youtube_playlist_service.build",
            return_value=fake,
        ):
            service = YouTubePlaylistService(credential=_credential())
            got = service.find_playlist_by_title("건강 정보")

        self.assertEqual(got, "PL_t")


# -- 같은 이름이 여럿일 때 --------------------------------------------
class TheFirstMatchWinsTest(_Case):

    def test_같은_이름이_둘이면_먼저_만난_것(self):
        youtube = _Youtube(pages=[[("PL_first", "건강 정보"),
                                   ("PL_second", "건강 정보")]])

        self.assertEqual(self.find(youtube), "PL_first")

    def test_앞_장의_것이_뒤_장의_것보다_먼저다(self):
        youtube = _Youtube(pages=[[("PL_first", "건강 정보")],
                                  [("PL_second", "건강 정보")]])

        self.assertEqual(self.find(youtube), "PL_first")


# -- 8. 다른 플랫폼 ---------------------------------------------------
class TheOtherPlatformsAreUntouchedTest(unittest.TestCase):

    def test_이_파일은_YouTube_만_안다(self):
        import re

        from app.providers.upload import youtube_playlist_service

        with open(youtube_playlist_service.__file__, encoding="utf-8") as f:
            text = re.sub(r'"""[\s\S]*?"""', "", f.read())

        for name in ("instagram", "tiktok"):
            with self.subTest(name=name):
                self.assertNotIn(name, text.lower())

    def test_두_찾기가_같은_방식을_쓴다(self):
        """
        Sprint252 가 playlistItems 쪽에 놓은 걸음과 같은 모양이어야
        한다. 한쪽만 고치면 다른 쪽이 언젠가 같은 결함으로 돌아간다.
        """

        import inspect

        from app.providers.upload.youtube_playlist_service import (
            YouTubePlaylistService,
        )

        for name in ("find_playlist_by_title", "already_in_playlist"):
            source = inspect.getsource(getattr(YouTubePlaylistService, name))

            with self.subTest(method=name):
                self.assertIn("nextPageToken", source)
                self.assertIn("isinstance(token, str)", source)


if __name__ == "__main__":
    unittest.main()
