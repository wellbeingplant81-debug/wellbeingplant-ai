"""
Sprint121 - Scene Stability & Stock Video Priority.

scene_stability_policy.max_assets_for_duration()의 순수 함수 계약을
검증한다. Scene 길이 구간(0~5초/5~8초/8초 이상)별 최대 asset 개수
규칙과, 그 결과가 항상 Minimum Asset Duration(2.5초) 이상을 보장하는지
확인한다. 파일 I/O/렌더링/파이프라인 연결 없음 - 순수 계산 로직만
테스트한다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.scene_stability_policy import (
    MIN_ASSET_DURATION_SECONDS,
    max_assets_for_duration,
)


class TestMaxAssetsForDurationBuckets(unittest.TestCase):

    def test_zero_to_five_seconds_allows_one_asset(self):
        self.assertEqual(max_assets_for_duration(0.0), 1)
        self.assertEqual(max_assets_for_duration(2.5), 1)
        self.assertEqual(max_assets_for_duration(4.99), 1)

    def test_five_to_eight_seconds_allows_two_assets(self):
        self.assertEqual(max_assets_for_duration(5.0), 2)
        self.assertEqual(max_assets_for_duration(6.5), 2)
        self.assertEqual(max_assets_for_duration(7.99), 2)

    def test_eight_seconds_and_above_allows_three_assets(self):
        self.assertEqual(max_assets_for_duration(8.0), 3)
        self.assertEqual(max_assets_for_duration(15.0), 3)
        self.assertEqual(max_assets_for_duration(60.0), 3)


class TestMaxAssetsForDurationMinimumAssetDurationInvariant(unittest.TestCase):

    def test_min_asset_duration_constant_is_two_point_five(self):
        self.assertEqual(MIN_ASSET_DURATION_SECONDS, 2.5)

    def test_per_asset_duration_never_falls_below_minimum_when_split(self):
        # count > 1인 모든 구간에서 duration/count가 2.5초 미만으로
        # 떨어지면 안 된다(불필요한 빠른 컷 편집 방지의 핵심 불변식).
        sample_durations = [5.0, 5.5, 6.0, 7.0, 7.99, 8.0, 8.5, 10.0, 20.0, 45.0]

        for duration in sample_durations:
            count = max_assets_for_duration(duration)
            if count > 1:
                per_asset = duration / count
                self.assertGreaterEqual(
                    per_asset, MIN_ASSET_DURATION_SECONDS,
                    msg=f"duration={duration}, count={count}, per_asset={per_asset}",
                )


if __name__ == "__main__":
    unittest.main()
