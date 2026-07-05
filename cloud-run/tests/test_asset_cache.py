import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.utils import asset_cache


class TestAssetCache(unittest.TestCase):

    def test_cache_key_is_deterministic(self):
        key1 = asset_cache.cache_key("pexels_video", "video", "tired woman")
        key2 = asset_cache.cache_key("pexels_video", "video", "tired woman")
        self.assertEqual(key1, key2)

    def test_cache_key_differs_by_query(self):
        key1 = asset_cache.cache_key("pexels_video", "video", "tired woman")
        key2 = asset_cache.cache_key("pexels_video", "video", "happy man")
        self.assertNotEqual(key1, key2)

    def test_cache_key_differs_by_provider(self):
        key1 = asset_cache.cache_key("pexels_video", "video", "tired woman")
        key2 = asset_cache.cache_key("pixabay_video", "video", "tired woman")
        self.assertNotEqual(key1, key2)

    def test_get_cached_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            key = asset_cache.cache_key("pexels_video", "video", "nothing here")
            result = asset_cache.get_cached(key, cache_root=tmp_dir)
            self.assertIsNone(result)

    def test_save_and_get_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            key = asset_cache.cache_key("pexels_image", "image", "tired woman")

            saved_path = asset_cache.save_to_cache(
                key,
                content=b"fake image bytes",
                filename="asset.jpg",
                meta={"source": "pexels_image", "query": "tired woman"},
                cache_root=tmp_dir,
            )

            self.assertTrue(os.path.exists(saved_path))

            cached = asset_cache.get_cached(key, cache_root=tmp_dir)
            self.assertIsNotNone(cached)

            cached_path, meta = cached
            self.assertEqual(cached_path, saved_path)
            self.assertEqual(meta["source"], "pexels_image")
            self.assertEqual(meta["filename"], "asset.jpg")

            with open(cached_path, "rb") as f:
                self.assertEqual(f.read(), b"fake image bytes")

    def test_get_cached_none_if_asset_file_missing_but_meta_present(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            key = asset_cache.cache_key("pexels_image", "image", "orphan meta")

            directory = asset_cache.cache_dir(key, cache_root=tmp_dir)
            os.makedirs(directory, exist_ok=True)

            from app.utils.atomic_write import atomic_write_json
            atomic_write_json(
                os.path.join(directory, "meta.json"),
                {"filename": "missing.jpg"},
            )

            result = asset_cache.get_cached(key, cache_root=tmp_dir)
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
