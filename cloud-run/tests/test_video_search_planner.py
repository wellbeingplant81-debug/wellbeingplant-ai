"""
Sprint102 - Video Coverage Intelligence. video_search_planner.
plan_video_search_queries()가 narration/image_prompt로부터 우선순위
순서의 검색어 리스트(Primary -> Action -> Fallback... -> Broad)를
생성하는지 확인한다.

순수 함수다(Gemini/네트워크 호출 없음) - image_prompt(영어)에서
매칭된 카테고리에 따라 결정적으로 쿼리 목록을 만든다. VideoIntent
판단(motion_contract.py)도, Asset 채점/선택(asset_selector.py)도
하지 않는다 - 검색어 문자열 리스트만 반환한다.

Sprint102-1 - 카테고리 매칭 신호를 narration(한국어)에서 image_prompt
(영어)로 바꿨다. 2026-07-14 Production QA 실측: narration에 병원/
의사/환자 같은 한국어 키워드가 전혀 없는데도 image_prompt가 "hospital
room"을 명시한 scene에서 카테고리를 하나도 못 찾은 사례가 확인됐다 -
TestCategoryMatchingUsesImagePromptNotNarration이 그 재발을 막는다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import video_search_planner
from app.services.search_query_extractor import generate_semantic_primary_query


class TestPlanVideoSearchQueriesBasics(unittest.TestCase):

    def test_returns_a_list(self):
        result = video_search_planner.plan_video_search_queries(
            "매일 30분씩 가벼운 산책을 해보세요", "a person walking in a park",
        )
        self.assertIsInstance(result, list)

    def test_first_query_is_primary_extracted_from_image_prompt(self):
        image_prompt = "medium shot fit korean man 50s walking briskly in a park"
        result = video_search_planner.plan_video_search_queries(
            "매일 30분씩 가벼운 산책을 해보세요", image_prompt,
        )
        self.assertEqual(result[0], generate_semantic_primary_query(image_prompt))

    def test_at_least_one_query_always_returned(self):
        result = video_search_planner.plan_video_search_queries(
            "오늘의 주제를 시작하겠습니다", "a neutral scene",
        )
        self.assertGreaterEqual(len(result), 1)

    def test_no_matching_category_returns_only_primary(self):
        image_prompt = "an abstract conceptual diagram"
        result = video_search_planner.plan_video_search_queries(
            "오늘의 주제를 시작하겠습니다", image_prompt,
        )
        self.assertEqual(result, [generate_semantic_primary_query(image_prompt)])

    def test_does_not_mutate_inputs(self):
        narration = "매일 30분씩 가벼운 산책을 해보세요"
        image_prompt = "a person walking in a park"
        video_search_planner.plan_video_search_queries(narration, image_prompt)
        self.assertEqual(narration, "매일 30분씩 가벼운 산책을 해보세요")
        self.assertEqual(image_prompt, "a person walking in a park")

    def test_empty_inputs_do_not_crash(self):
        result = video_search_planner.plan_video_search_queries("", "")
        self.assertIsInstance(result, list)

    def test_queries_have_no_duplicates(self):
        result = video_search_planner.plan_video_search_queries(
            "매일 30분씩 가벼운 산책을 해보세요", "walking",
        )
        self.assertEqual(len(result), len(set(result)))


class TestWalkingCategoryQueries(unittest.TestCase):
    """
    사용자가 SPEC에서 직접 예시로 든 walking 카테고리 - 순서와 내용을
    그대로 고정한다(Primary 다음에 이어짐).
    """

    def setUp(self):
        self.narration = "매일 30분씩 가벼운 산책을 해보세요"
        self.image_prompt = "walking park medium shot fit korean man 50s"
        self.result = video_search_planner.plan_video_search_queries(
            self.narration, self.image_prompt,
        )

    def test_includes_action_query(self):
        self.assertIn("person walking", self.result)

    def test_includes_all_fallback_queries_in_order(self):
        expected_fallbacks = [
            "healthy walking",
            "senior walking",
            "person walking outside",
            "walking exercise",
        ]
        for query in expected_fallbacks:
            self.assertIn(query, self.result)

        fallback_indices = [self.result.index(q) for q in expected_fallbacks]
        self.assertEqual(fallback_indices, sorted(fallback_indices))

    def test_primary_comes_before_fallbacks(self):
        primary = generate_semantic_primary_query(self.image_prompt)
        self.assertEqual(self.result[0], primary)
        self.assertLess(self.result.index(primary), self.result.index("healthy walking"))


class TestExerciseCategoryQueries(unittest.TestCase):

    def test_exercise_keyword_produces_exercise_queries(self):
        result = video_search_planner.plan_video_search_queries(
            "매일 운동을 하면 도움이 됩니다", "a person exercising",
        )
        self.assertIn("person exercising", result)
        self.assertIn("home workout", result)


class TestMealCategoryQueries(unittest.TestCase):

    def test_meal_keyword_produces_food_queries(self):
        result = video_search_planner.plan_video_search_queries(
            "오늘 식사는 채소 위주로 챙겨보세요", "a healthy meal",
        )
        self.assertIn("eating healthy food", result)
        self.assertIn("healthy meal", result)


class TestHospitalCategoryQueries(unittest.TestCase):

    def test_hospital_keyword_produces_medical_lifestyle_queries(self):
        result = video_search_planner.plan_video_search_queries(
            "병원에서 정기 검진을 받아보세요", "a doctor consultation",
        )
        self.assertIn("doctor patient consultation", result)
        self.assertIn("hospital checkup", result)


class TestCategoryMatchingUsesImagePromptNotNarration(unittest.TestCase):
    """
    Sprint102-1 - 2026-07-14 Production QA 실측 회귀 방지: narration에
    카테고리 키워드가 전혀 없어도 image_prompt에 있으면 매칭돼야 하고,
    반대로 narration에 키워드가 있어도 image_prompt에 없으면 더 이상
    매칭되면 안 된다(신호 출처가 완전히 바뀌었음을 확인).
    """

    def test_narration_without_keywords_but_image_prompt_with_hospital_matches(self):
        # 실측 사례 그대로: narration은 "초기 증상이 거의 없다"는
        # 내용일 뿐 병원/의사/환자라는 단어가 전혀 없다.
        narration = "문제는 초기 증상이 거의 없다는 겁니다. 방치하면 간경화로 이어질 수 있는 무서운 질병이죠."
        image_prompt = "high angle shot dimly lit hospital room capturing a somber mood"

        result = video_search_planner.plan_video_search_queries(narration, image_prompt)

        self.assertIn("doctor patient consultation", result)
        self.assertIn("hospital checkup", result)

    def test_narration_with_korean_keyword_but_image_prompt_without_match_does_not_match(self):
        # narration에는 "산책"이 있지만 image_prompt는 무관한 내용 -
        # Sprint102-0(narration 기반)이었다면 매칭됐겠지만, 이제는
        # image_prompt 기준이므로 매칭되면 안 된다.
        narration = "매일 산책을 하면 좋습니다"
        image_prompt = "an abstract conceptual diagram of insulin resistance"

        result = video_search_planner.plan_video_search_queries(narration, image_prompt)

        self.assertEqual(result, [generate_semantic_primary_query(image_prompt)])


class TestStyleBoilerplateDoesNotFalselyMatchLifestyle(unittest.TestCase):
    """
    Sprint102-2 - 2026-07-14 Production QA 실측 회귀 방지: 모든
    image_prompt 끝에 붙는 공통 스타일 접미사("warm, soft, clean
    wellness aesthetic, natural morning lighting, minimal composition,
    cinematic feel.")의 morning/wellness가 lifestyle 카테고리와
    우연히 매칭되어, 과일주스/간 대사 같은 무관한 scene에서도 매번
    "daily lifestyle routine" Fallback을 시도하던 문제가 실측됐다.
    """

    def test_unrelated_scene_with_standard_style_suffix_does_not_match_lifestyle(self):
        image_prompt = (
            "A top-down view of a dark wooden table featuring a pitcher "
            "of fruit juice, a glass jar of Korean fruit syrup, and a "
            "bowl of assorted dried fruits, all arranged beautifully "
            "under dramatic studio lighting. warm, soft, clean wellness "
            "aesthetic, natural morning lighting, minimal composition, "
            "cinematic feel."
        )

        result = video_search_planner.plan_video_search_queries("", image_prompt)

        self.assertNotIn("daily lifestyle routine", result)
        self.assertNotIn("healthy lifestyle", result)
        self.assertEqual(result, [generate_semantic_primary_query(image_prompt)])

    def test_genuinely_lifestyle_scene_still_matches_despite_style_suffix(self):
        image_prompt = (
            "A person following their daily lifestyle routine in the "
            "morning. warm, soft, clean wellness aesthetic, natural "
            "morning lighting, minimal composition, cinematic feel."
        )

        result = video_search_planner.plan_video_search_queries("", image_prompt)

        self.assertIn("healthy lifestyle", result)

    def test_word_boundary_avoids_false_positive_substring_match(self):
        # "walk"가 "walkway"라는 단어 중간에 우연히 끼어 있어도(부분
        # 문자열) 단어 단위 매칭이므로 walking 카테고리가 매칭되면
        # 안 된다. 다른 카테고리 키워드가 섞이지 않도록 image_prompt를
        # 구성한다.
        image_prompt = "a wooden walkway through a historic town square structure"
        result = video_search_planner.plan_video_search_queries("", image_prompt)
        self.assertEqual(result, [generate_semantic_primary_query(image_prompt)])


if __name__ == "__main__":
    unittest.main()
