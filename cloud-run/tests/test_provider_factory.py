import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.provider_factory import build_provider_chain


class TestProviderFactory(unittest.TestCase):

    def test_default_chain_matches_original_priority_order(self):
        chain = build_provider_chain()
        sources = [source for source, _ in chain]
        self.assertEqual(
            sources,
            ["pexels_video", "pexels_image", "pixabay_video", "pixabay_image"],
        )

    def test_allow_video_true_is_explicit_equivalent_of_default(self):
        self.assertEqual(
            [s for s, _ in build_provider_chain(allow_video=True)],
            [s for s, _ in build_provider_chain()],
        )

    def test_allow_video_false_excludes_video_providers(self):
        chain = build_provider_chain(allow_video=False)
        sources = [source for source, _ in chain]
        self.assertEqual(sources, ["pexels_image", "pixabay_image"])

    @patch("app.providers.pexels_provider.search_videos")
    def test_chain_entry_calls_through_to_underlying_provider(self, mock_search_videos):
        mock_search_videos.return_value = [{"source": "pexels_video"}]

        chain = build_provider_chain()
        _, search_fn = chain[0]

        result = search_fn("tired woman")

        mock_search_videos.assert_called_once_with("tired woman")
        self.assertEqual(result, [{"source": "pexels_video"}])


if __name__ == "__main__":
    unittest.main()
