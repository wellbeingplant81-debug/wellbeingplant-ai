"""
Sprint252 - 같은 영상을 같은 재생목록에 두 번 넣지 않는다.

무엇이 문제였나
---------------
add_video_to_playlist 는 확인 없이 곧장 insert 했다. YouTube 는 같은
영상이 한 재생목록에 여러 번 들어가는 것을 막지 않으므로, 그대로
항목이 하나 더 생긴다.

업로드 걸음은 다시 눌릴 수 있는 자리다(재시도 · 줄 다시 세우기).
그때마다 재생목록이 조금씩 지저분해진다.

Sprint251 의 실제 검증에서 playlistItems.list 로 미리 보면 피할 수
있다는 것을 확인했다. 그 확인을 사람이 손으로 하는 대신 코드가 한다.

무엇이 중복인가
---------------
    같은 재생목록  +  같은 영상    <- 이 둘이 동시에 맞을 때만

다른 재생목록에 같은 영상이 있는 것은 중복이 아니다. 한 영상이 여러
재생목록에 드는 것은 정상이다.

뒤 페이지까지 본다
------------------
playlistItems.list 는 한 번에 최대 50 개만 준다. 51 번째부터는
nextPageToken 을 따라가야 보인다. 첫 페이지만 보고 "없다" 고 하면
큰 재생목록에서는 매번 중복이 쌓인다.

여기서 재는 것
--------------
실제 YouTube 는 부르지 않는다. 클라이언트를 가짜로 바꿔 두고
**insert 가 몇 번 불렸는가**를 센다.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _credential():
    class _C:
        access_token = "token"
        refresh_token = "refresh"
        account_id = "default"

    return _C()


class _Youtube:
    """
    playlistItems().list(...).execute() 와 insert(...).execute() 만
    흉내 낸다. 페이지는 준 대로 차례로 돌려준다.
    """

    def __init__(self, pages=None, list_error=None, insert_error=None):
        self.pages = list(pages if pages is not None else [[]])
        self.list_error = list_error
        self.insert_error = insert_error

        self.list_calls = []
        self.insert_calls = []

    # -- googleapiclient 모양 ---------------------------------------
    def playlistItems(self):
        return self

    def list(self, **kwargs):
        self.list_calls.append(kwargs)

        return _Execute(self._listed(kwargs), self.list_error)

    def insert(self, **kwargs):
        self.insert_calls.append(kwargs)

        return _Execute({"id": "item-1"}, self.insert_error)

    # -- 페이지 ------------------------------------------------------
    def _listed(self, kwargs):
        index = 0

        if kwargs.get("pageToken"):
            index = int(str(kwargs["pageToken"]).split("-")[-1])

        page = self.pages[index] if index < len(self.pages) else []

        body = {"items": [
            {"snippet": {"resourceId": {"kind": "youtube#video",
                                        "videoId": v}}}
            for v in page
        ]}

        if index + 1 < len(self.pages):
            body["nextPageToken"] = f"page-{index + 1}"

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

    def run_with(self, youtube, playlist="PL_target", video="vid_123"):
        from app.providers.upload.youtube_playlist_service import (
            YouTubePlaylistService,
        )

        with patch(
            "app.providers.upload.youtube_playlist_service.build",
            return_value=youtube,
        ):
            service = YouTubePlaylistService(credential=_credential())

            return service.add_video_to_playlist(playlist, video)


# -- 1·4. 없으면 넣는다 ----------------------------------------------
class AnAbsentVideoIsAddedTest(_Case):

    def test_빈_재생목록이면_넣는다(self):
        youtube = _Youtube(pages=[[]])

        self.run_with(youtube)

        self.assertEqual(len(youtube.insert_calls), 1)

    def test_다른_영상만_있으면_넣는다(self):
        youtube = _Youtube(pages=[["other-1", "other-2"]])

        self.run_with(youtube)

        self.assertEqual(len(youtube.insert_calls), 1)

    def test_넣는_모양이_예전_그대로다(self):
        youtube = _Youtube(pages=[[]])

        self.run_with(youtube)

        body = youtube.insert_calls[0]["body"]

        self.assertEqual(body["snippet"]["playlistId"], "PL_target")
        self.assertEqual(body["snippet"]["resourceId"]["videoId"], "vid_123")
        self.assertEqual(body["snippet"]["resourceId"]["kind"], "youtube#video")
        self.assertEqual(youtube.insert_calls[0]["part"], "snippet")


# -- 2. 있으면 넣지 않는다 --------------------------------------------
class APresentVideoIsNotAddedAgainTest(_Case):

    def test_이미_있으면_넣지_않는다(self):
        youtube = _Youtube(pages=[["vid_123"]])

        self.run_with(youtube)

        self.assertEqual(youtube.insert_calls, [])

    def test_여럿_중_하나로_있어도_넣지_않는다(self):
        youtube = _Youtube(pages=[["a", "vid_123", "b"]])

        self.run_with(youtube)

        self.assertEqual(youtube.insert_calls, [])

    def test_던지지_않는다(self):
        """이미 있는 것은 고장이 아니다 - 부르는 쪽이 실패로 읽으면 안 된다."""

        youtube = _Youtube(pages=[["vid_123"]])

        self.run_with(youtube)   # 예외가 나면 여기서 끝난다

    def test_그_재생목록을_물어본다(self):
        youtube = _Youtube(pages=[["vid_123"]])

        self.run_with(youtube)

        self.assertEqual(youtube.list_calls[0]["playlistId"], "PL_target")


# -- 3. 뒤 페이지까지 본다 --------------------------------------------
class TheSearchFollowsThePagesTest(_Case):

    def test_둘째_페이지에_있어도_찾는다(self):
        youtube = _Youtube(pages=[["a"] * 50, ["b", "vid_123"]])

        self.run_with(youtube)

        self.assertEqual(youtube.insert_calls, [], "뒤 페이지를 안 봤다")
        self.assertEqual(len(youtube.list_calls), 2)

    def test_셋째_페이지까지_따라간다(self):
        youtube = _Youtube(pages=[["a"], ["b"], ["c", "vid_123"]])

        self.run_with(youtube)

        self.assertEqual(youtube.insert_calls, [])
        self.assertEqual(len(youtube.list_calls), 3)

    def test_페이지_표를_그대로_들고_간다(self):
        youtube = _Youtube(pages=[["a"], ["b"], ["c"]])

        self.run_with(youtube)

        self.assertIsNone(youtube.list_calls[0].get("pageToken"))
        self.assertEqual(youtube.list_calls[1]["pageToken"], "page-1")
        self.assertEqual(youtube.list_calls[2]["pageToken"], "page-2")

    def test_끝까지_없으면_넣는다(self):
        youtube = _Youtube(pages=[["a"], ["b"], ["c"]])

        self.run_with(youtube)

        self.assertEqual(len(youtube.insert_calls), 1)


# -- 7. 다른 재생목록은 상관없다 --------------------------------------
class AnotherPlaylistIsNotADuplicateTest(_Case):

    def test_다른_재생목록에_있는_것은_중복이_아니다(self):
        """
        이 재생목록에는 없다. 저쪽에 있든 말든 여기에는 넣어야 한다.
        """

        youtube = _Youtube(pages=[["other-video"]])

        self.run_with(youtube, playlist="PL_here", video="vid_123")

        self.assertEqual(len(youtube.insert_calls), 1)
        self.assertEqual(youtube.list_calls[0]["playlistId"], "PL_here")


# -- 5·6. 오류 -------------------------------------------------------
class AnErrorIsNotASilentInsertTest(_Case):

    def test_list_가_실패하면_넣지_않는다(self):
        youtube = _Youtube(pages=[[]], list_error=RuntimeError("403"))

        with self.assertRaises(Exception):
            self.run_with(youtube)

        self.assertEqual(youtube.insert_calls, [])

    def test_list_실패를_삼키지_않는다(self):
        """
        모르는 채로 넣으면 중복이 생긴다. 모른다는 사실이 위로
        올라가야 한다 - 부르는 쪽이 그것을 오류 문자열로 적는다.
        """

        youtube = _Youtube(pages=[[]], list_error=RuntimeError("망가짐"))

        with self.assertRaises(RuntimeError):
            self.run_with(youtube)

    def test_insert_오류는_예전처럼_올라간다(self):
        youtube = _Youtube(pages=[[]], insert_error=RuntimeError("insert 실패"))

        with self.assertRaises(RuntimeError):
            self.run_with(youtube)


# -- 8. 다른 플랫폼은 상관없다 ----------------------------------------
class TheOtherPlatformsAreUntouchedTest(unittest.TestCase):

    def test_재생목록은_YouTube_만의_것이다(self):
        import re

        from app.providers.upload import youtube_playlist_service

        with open(youtube_playlist_service.__file__, encoding="utf-8") as f:
            text = re.sub(r'"""[\s\S]*?"""', "", f.read())

        for name in ("instagram", "tiktok"):
            with self.subTest(name=name):
                self.assertNotIn(name, text.lower())

    def test_부르는_자리가_하나뿐이다(self):
        """
        업로드 provider 만 이것을 쓴다. 늘어나면 중복 규칙도 흩어진다.
        """

        import pathlib

        root = pathlib.Path(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")

        callers = []

        for path in root.rglob("*.py"):
            if "__pycache__" in str(path):
                continue

            with open(path, encoding="utf-8") as f:
                if "add_video_to_playlist(" in f.read():
                    callers.append(path.name)

        self.assertEqual(sorted(callers),
                         ["youtube_playlist_service.py",
                          "youtube_upload_provider.py"])


if __name__ == "__main__":
    unittest.main()
