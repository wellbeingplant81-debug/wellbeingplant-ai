import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.search_query_extractor import (
    extract_search_query,
    generate_semantic_primary_query,
)
from app.services.style_boilerplate_stripper import strip_style_boilerplate


class TestSearchQueryExtractor(unittest.TestCase):

    def test_empty_prompt_returns_empty(self):
        self.assertEqual(extract_search_query(""), "")

    def test_filler_phrases_removed(self):
        prompt = "Ultra realistic, cinematic photography, tired woman in office."
        result = extract_search_query(prompt)
        self.assertNotIn("ultra", result)
        self.assertNotIn("realistic", result)
        self.assertNotIn("cinematic", result)

    def test_core_subject_words_survive(self):
        prompt = "Ultra realistic, cinematic photography of a tired woman sitting at a messy office desk."
        result = extract_search_query(prompt)
        self.assertIn("tired", result)
        self.assertIn("woman", result)
        self.assertIn("office", result)

    def test_max_words_truncation(self):
        prompt = "one two three four five six seven eight nine ten"
        result = extract_search_query(prompt, max_words=3)
        self.assertEqual(result, "one two three")

    def test_punctuation_stripped(self):
        prompt = "Scene 1: Korean woman, shocked expression!"
        result = extract_search_query(prompt)
        self.assertNotIn(":", result)
        self.assertNotIn(",", result)
        self.assertNotIn("!", result)

    def test_original_prompt_not_mutated(self):
        prompt = "Ultra realistic photo of a tired woman."
        snapshot = prompt
        extract_search_query(prompt)
        self.assertEqual(prompt, snapshot)


# Sprint103 - Semantic Preservation Score corpus. Sprint102 Root Cause
# 분석에서 쓴 6개 대표 샘플 그대로 고정한다(카메라 앵글 선행 구조 +
# 실제 Production QA에서 확인된 카테고리 분포: 음식/의료/도보/운동/
# 식사/의학 다이어그램). 실제 프로덕션 image_prompt corpus가 리포에
# 저장돼 있지 않아(Sprint103 SPEC §8) 이 6개를 KPI 측정 기준으로
# 승인받았다.
SEMANTIC_PRESERVATION_CORPUS = [
    (
        "food_salad",
        "A high-angle shot showing a person's hands pushing away an "
        "empty plate of processed snacks to reach for a vibrant bowl "
        "of fresh salad with spinach and sliced bananas, bright "
        "kitchen lighting, hopeful mood.",
    ),
    (
        "hospital",
        "High angle shot, dimly lit hospital room capturing a somber "
        "mood as an elderly Korean patient lies in bed while a doctor "
        "reviews medical charts nearby.",
    ),
    (
        "walking",
        "Wide shot, showing a fit Korean man in his 50s walking "
        "briskly through a sunlit park path, surrounded by autumn "
        "trees, energetic morning atmosphere.",
    ),
    (
        "exercise",
        "Medium shot, showing a middle-aged Korean woman stretching "
        "her arms and legs on a yoga mat in a bright home living "
        "room, calm focused expression, soft daylight.",
    ),
    (
        "meal",
        "Close-up, framing tightly on a family gathered around a "
        "wooden dinner table sharing a home-cooked meal of grilled "
        "vegetables and rice, warm evening lighting, joyful "
        "atmosphere.",
    ),
    (
        "medical_diagram",
        "Cross section illustration style shot showing an artery "
        "gradually narrowing due to plaque buildup, cinematic "
        "lighting, dramatic scientific mood, cool blue tones.",
    ),
]


def _semantic_preservation_score(image_prompt):
    """Sprint103 SPEC 6 정의: (최종 Query 단어 수) / (Semantic Filter 통과 직후 단어 수)."""

    from app.services.search_query_extractor import _clean_words

    filtered_word_count = len(_clean_words(strip_style_boilerplate(image_prompt)))
    query_word_count = len(generate_semantic_primary_query(image_prompt).split())
    return query_word_count / filtered_word_count


class TestGenerateSemanticPrimaryQuery(unittest.TestCase):

    def test_empty_prompt_returns_empty(self):
        self.assertEqual(generate_semantic_primary_query(""), "")

    def test_camera_meta_words_never_appear_in_output(self):
        prompt = (
            "high angle shot showing a person's hands pushing away a "
            "plate of salad"
        )
        result = generate_semantic_primary_query(prompt)
        for camera_word in ["high", "angle", "shot", "showing"]:
            self.assertNotIn(camera_word, result.split())

    def test_late_position_noun_survives_unlike_positional_truncation(self):
        # Sprint102 실측 회귀 방지: extract_search_query()는 카메라
        # 어휘가 앞 8단어를 차지해 뒷부분 명사를 잃었다. Semantic
        # Compression은 카메라 어휘를 먼저 제거하므로 문장 내 위치와
        # 무관하게 의미어를 보존해야 한다.
        prompt = (
            "A high-angle shot showing a vibrant bowl of fresh salad "
            "with spinach and sliced bananas on a kitchen counter."
        )
        result = generate_semantic_primary_query(prompt)
        for content_word in ["salad", "spinach", "bananas"]:
            self.assertIn(content_word, result)

    def test_very_long_prompt_may_still_lose_late_content_to_safety_cap(self):
        # Sprint103 SPEC에서 승인된 안전장치(max_words=12)의 정직한
        # 한계: 카메라 어휘를 다 제거해도 필터 후 의미어 자체가 12개를
        # 넘으면(예: "무엇을 밀어내고 무엇으로 향하는지"를 모두 묘사하는
        # 장문) 뒷부분 명사가 잘릴 수 있다. 이 경우는 corpus 평균/
        # 상대비교(TestSemanticPreservationScoreCorpus)로 다룬다 -
        # 이 테스트는 그 트레이드오프가 의도된 것임을 고정할 뿐이다.
        prompt = (
            "A high-angle shot showing a person's hands pushing away an "
            "empty plate of processed snacks to reach for a vibrant bowl "
            "of fresh salad with spinach and sliced bananas."
        )
        result = generate_semantic_primary_query(prompt)
        self.assertLessEqual(len(result.split()), 12)
        self.assertIn("snacks", result)
        self.assertNotIn("bananas", result.split())

    def test_noun_phrase_adjacency_preserved(self):
        prompt = (
            "an artery narrowing due to plaque buildup and sliced "
            "bananas on a plate"
        )
        result = generate_semantic_primary_query(prompt)
        self.assertIn("plaque buildup", result)
        self.assertIn("sliced bananas", result)

    def test_safety_cap_applies_to_very_long_prompts(self):
        long_prompt = "artery " + " ".join(f"content{i}" for i in range(30))
        result = generate_semantic_primary_query(long_prompt)
        self.assertLessEqual(len(result.split()), 12)

    def test_original_prompt_not_mutated(self):
        prompt = "high angle shot of a person walking in a park"
        snapshot = prompt
        generate_semantic_primary_query(prompt)
        self.assertEqual(prompt, snapshot)


class TestSemanticPreservationScoreCorpus(unittest.TestCase):
    """
    Sprint103 SPEC 6/8 - KPI 목표(Semantic Preservation Score >= 70%)를
    Sprint102 Root Cause 분석에 쓴 6개 대표 샘플(고정 corpus)로 검증한다.
    개별 샘플이 아니라 corpus 평균으로 판정한다 - 승인된 안전장치
    (max_words=12)가 유독 긴 샘플 하나(food_salad, 필터 후 20단어)에서는
    개별 70%를 밑돌 수 있음이 실측으로 확인됐기 때문이다(그래도 기존
    extract_search_query()보다는 모든 샘플에서 훨씬 낫다 - 아래
    test_outperforms_positional_truncation_on_every_sample 참고).
    """

    def test_average_preservation_score_meets_kpi_target(self):
        scores = [
            _semantic_preservation_score(prompt)
            for _name, prompt in SEMANTIC_PRESERVATION_CORPUS
        ]
        average = sum(scores) / len(scores)
        self.assertGreaterEqual(average, 0.70)

    def test_outperforms_positional_truncation_on_every_sample(self):
        from app.services.search_query_extractor import _clean_words

        for name, prompt in SEMANTIC_PRESERVATION_CORPUS:
            with self.subTest(sample=name):
                old_words = set(extract_search_query(prompt).split())
                new_words = set(generate_semantic_primary_query(prompt).split())
                total_content_words = set(_clean_words(strip_style_boilerplate(prompt)))

                old_retained = len(old_words & total_content_words)
                new_retained = len(new_words & total_content_words)

                self.assertGreater(new_retained, old_retained)


if __name__ == "__main__":
    unittest.main()
