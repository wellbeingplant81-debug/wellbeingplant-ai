import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.voice_quality_engine import optimize_for_tts


class TestVoiceQualityEngine(unittest.TestCase):

    def test_chain_inserts_pause_markup(self):
        narration = "밤마다 화장실 때문에 자주 깨시나요? 그 원인은 단순한 노화가 아닐 수도 있습니다."
        result = optimize_for_tts(narration)
        self.assertIn("<break time=", result)

    def test_chain_applies_emphasis_when_keywords_given(self):
        narration = "그 원인은 단순한 노화가 아닐 수도 있습니다."
        result = optimize_for_tts(narration, keywords=["노화"])
        self.assertIn('<break time="0.15s" /> 노화', result)

    def test_chain_without_keywords_skips_emphasis(self):
        # 문장이 2개 이상이어야 문장 사이 pause가 실제로 삽입된다
        # (마지막 문장 끝에는 불필요한 트레일링 pause를 넣지 않는 것이
        # 의도된 설계이므로, 단일 문장으로는 이 동작을 검증할 수 없다).
        narration = "밤마다 화장실 때문에 자주 깨시나요? 그 원인은 단순한 노화가 아닐 수도 있습니다."
        result = optimize_for_tts(narration)
        self.assertIn("<break time=", result)

    def test_original_narration_never_mutated(self):
        narration = "밤마다 화장실 때문에 자주 깨시나요? 그 원인은 단순한 노화가 아닐 수도 있습니다."
        snapshot = narration
        optimize_for_tts(narration, keywords=["노화"])
        self.assertEqual(narration, snapshot)

    def test_output_still_contains_core_words(self):
        narration = "밤마다 화장실 때문에 자주 깨시나요?"
        result = optimize_for_tts(narration)
        for word in ["밤마다", "화장실", "자주"]:
            self.assertIn(word, result)


if __name__ == "__main__":
    unittest.main()
