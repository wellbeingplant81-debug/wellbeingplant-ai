"""
EPIC Instagram Connector (Production) (RED->GREEN) -
desktop/application/assets/asset_reference.py.

AssetReference는 "이 자산을 어떻게 참조할 수 있는가"를 플랫폼 공통
모양으로 담는다 - Instagram처럼 API가 요구하는 아 File(local_path)/
공개 URL(public_url) 어느 쪽도 될 수 있다. 이 Epic 때문에 만든 것이
아니라 앞으로 TikTok/Facebook/Threads 등도 재사용할 공통 인프라다 -
필드는 특정 플랫폼 파라미터명을 흉내내지 않고 순수 데이터만 담는다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.storage.asset_reference import AssetReference


class TestAssetReferenceDefaults(unittest.TestCase):

    def test_all_fields_have_safe_empty_defaults(self):
        ref = AssetReference()

        self.assertEqual(ref.local_path, "")
        self.assertEqual(ref.public_url, "")
        self.assertEqual(ref.mime_type, "")
        self.assertIsNone(ref.width)
        self.assertIsNone(ref.height)
        self.assertIsNone(ref.duration)
        self.assertIsNone(ref.file_size)

    def test_can_be_constructed_with_only_local_path(self):
        # "YouTube는 local_path를 사용하면 된다" - 최소 구성.
        ref = AssetReference(local_path="output/proj/video/final_short.mp4")

        self.assertEqual(ref.local_path, "output/proj/video/final_short.mp4")
        self.assertEqual(ref.public_url, "")

    def test_can_be_constructed_with_only_public_url(self):
        # "Instagram은 public_url을 사용하면 된다" - 최소 구성.
        ref = AssetReference(public_url="https://cdn.example.com/v1.mp4")

        self.assertEqual(ref.public_url, "https://cdn.example.com/v1.mp4")
        self.assertEqual(ref.local_path, "")

    def test_can_carry_full_metadata(self):
        ref = AssetReference(
            local_path="a.mp4", public_url="https://x/a.mp4", mime_type="video/mp4",
            width=1080, height=1920, duration=12.5, file_size=2048,
        )

        self.assertEqual(ref.mime_type, "video/mp4")
        self.assertEqual(ref.width, 1080)
        self.assertEqual(ref.height, 1920)
        self.assertEqual(ref.duration, 12.5)
        self.assertEqual(ref.file_size, 2048)


if __name__ == "__main__":
    unittest.main()
