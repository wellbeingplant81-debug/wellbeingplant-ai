"""
Sprint241 - 무엇으로 만들지 사람이 정한다 (Media Source Policy).

무엇이 있었나
-------------
2026-08-01~18 사이 Gemini 이미지 생성으로 약 20만원이 나갔고 결과도
만족스럽지 않았다. 지금 결제는 잠겨 있다.

그리고 잠긴 상태에서 배포된 EXE 가 이렇게 죽었다(실측).

    step02_assets -> asset_integration_service -> best_of_n_service
      -> image_service.generate_image -> imagen-4.0-generate-001
      -> ClientError: 404 NOT_FOUND -> HTTP 500

"AI 이미지 안 씀" 이 예외 경로였기 때문이다. 스톡이 한 장 실패하면
곧바로 유료 모델로 넘어갔고, 그 모델에 닿지 못하자 제작 전체가 멈췄다.

이 파일이 못 박는 것
--------------------
**AI 를 쓰지 않는 것이 정상 경로다.** 결제가 잠겨 있어도 내 자료와
무료 스톡만으로 영상이 끝까지 만들어져야 한다.

목이 하나인 것이 다행이다
-------------------------
asset_integration_service._ai_result 가 유료 모델로 가는 유일한
지점이다 - 그 함수의 주석이 "Imagen을 부르는 유일한 지점" 이라고
적어 두었고, 실제로 세 갈래가 전부 그리로 모인다.

    visual_type 없음   스톡 실패/품질 미달 -> _ai_result
    visual_type real   스톡 실패           -> _ai_result
    visual_type ai     처음부터            -> _ai_result

그래서 관문을 그 하나에 세운다. 새 계층을 만들지 않는다.

몰래 바꾸지 않는다
------------------
AI 를 쓰지 않겠다고 한 사람에게는 스톡으로 이어 주는 것이 맞다. 그런데
**AI 로 만들겠다고 고른 사람**에게 조용히 스톡을 내주면 그것은 다른
영상이다. 그때는 사람이 읽을 수 있는 말로 멈춘다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import media_policy


class TheDefaultIsNoAiTest(unittest.TestCase):
    """
    결제가 잠겨 있다. 아무것도 고르지 않은 사람이 유료 모델을 부르는
    일이 일어나면 안 된다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        patched = patch.object(media_policy, "default_store_path",
                               return_value=os.path.join(self.root, "s.json"))
        patched.start()
        self.addCleanup(patched.stop)

    def test_기본은_AI_를_쓰지_않는다(self):
        self.assertFalse(media_policy.ai_allowed(media_policy.current_mode()))

    def test_기본_모드가_무엇인지_밝힌다(self):
        self.assertIn(media_policy.current_mode(), media_policy.MODES)
        self.assertEqual(media_policy.current_mode(), media_policy.DEFAULT_MODE)

    def test_기본값을_바꿔_적을_수_있다(self):
        media_policy.remember_default(media_policy.MODE_MINE_STOCK_AI)

        self.assertEqual(media_policy.current_mode(),
                         media_policy.MODE_MINE_STOCK_AI)

    def test_모르는_모드는_받지_않는다(self):
        with self.assertRaises(ValueError):
            media_policy.remember_default("아무거나")

    def test_망가진_설정은_기본값으로_읽는다(self):
        with open(media_policy.default_store_path(), "w", encoding="utf-8") as f:
            f.write("{망가진")

        self.assertEqual(media_policy.current_mode(), media_policy.DEFAULT_MODE)

    def test_새_DB_를_만들지_않는다(self):
        with open(media_policy.__file__, encoding="utf-8") as f:
            body = f.read()

        for forbidden in ("sqlite3", "CREATE TABLE"):
            self.assertNotIn(forbidden, body, forbidden)


class TheFiveModesTest(unittest.TestCase):

    def test_다섯이다(self):
        self.assertEqual(
            media_policy.MODES,
            (media_policy.MODE_MINE_ONLY,
             media_policy.MODE_STOCK,
             media_policy.MODE_MINE_THEN_STOCK,
             media_policy.MODE_MINE_STOCK_AI,
             media_policy.MODE_AI_FIRST))

    def test_AI_를_허용하는_것은_둘뿐이다(self):
        allowed = [m for m in media_policy.MODES if media_policy.ai_allowed(m)]

        self.assertEqual(allowed, [media_policy.MODE_MINE_STOCK_AI,
                                   media_policy.MODE_AI_FIRST])

    def test_스톡을_허용하는_것을_밝힌다(self):
        self.assertFalse(media_policy.stock_allowed(media_policy.MODE_MINE_ONLY))

        for mode in (media_policy.MODE_STOCK,
                     media_policy.MODE_MINE_THEN_STOCK,
                     media_policy.MODE_MINE_STOCK_AI,
                     media_policy.MODE_AI_FIRST):
            with self.subTest(mode=mode):
                self.assertTrue(media_policy.stock_allowed(mode))

    def test_내_자료를_허용하는_것을_밝힌다(self):
        self.assertFalse(media_policy.mine_allowed(media_policy.MODE_STOCK))

        for mode in (media_policy.MODE_MINE_ONLY,
                     media_policy.MODE_MINE_THEN_STOCK,
                     media_policy.MODE_MINE_STOCK_AI):
            with self.subTest(mode=mode):
                self.assertTrue(media_policy.mine_allowed(mode))

    def test_AI_를_고른_사람인지_구별한다(self):
        """
        몰래 바꾸지 않기 위해서다. AI 로 만들겠다고 고른 사람에게
        조용히 스톡을 내주면 그것은 다른 영상이다.
        """

        self.assertTrue(media_policy.ai_is_the_point(media_policy.MODE_AI_FIRST))

        self.assertFalse(
            media_policy.ai_is_the_point(media_policy.MODE_MINE_STOCK_AI))

    def test_같은_모드는_같은_답을_준다(self):
        for mode in media_policy.MODES:
            with self.subTest(mode=mode):
                self.assertEqual(media_policy.ai_allowed(mode),
                                 media_policy.ai_allowed(mode))


class ThePolicyLivesWhereTheChoiceLivesTest(unittest.TestCase):
    """
    프로젝트가 고른 것은 프로젝트에 적는다 - provider_selection 이
    이미 그렇게 산다. 새 저장소를 만들지 않는다.
    """

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        patched = patch.object(media_policy, "default_store_path",
                               return_value=os.path.join(self.root, "s.json"))
        patched.start()
        self.addCleanup(patched.stop)

    def test_안_골랐으면_전역_기본값을_따른다(self):
        self.assertEqual(media_policy.mode_for(self.project),
                         media_policy.DEFAULT_MODE)

    def test_고르면_그_프로젝트에만_적용된다(self):
        media_policy.choose(self.project, media_policy.MODE_STOCK)

        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)

        self.assertEqual(media_policy.mode_for(self.project),
                         media_policy.MODE_STOCK)
        self.assertEqual(media_policy.mode_for(other),
                         media_policy.DEFAULT_MODE)

    def test_project_json_에_적힌다(self):
        """provider_selection 이 쓰는 그 파일이다."""

        media_policy.choose(self.project, media_policy.MODE_MINE_ONLY)

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            found = json.load(f)

        self.assertEqual(found[media_policy.PROJECT_FIELD],
                         media_policy.MODE_MINE_ONLY)

    def test_다른_칸을_건드리지_않는다(self):
        with open(os.path.join(self.project, "project.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"topic": "무릎", "channel": "wellbeing"}, f)

        media_policy.choose(self.project, media_policy.MODE_STOCK)

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            found = json.load(f)

        self.assertEqual(found["topic"], "무릎")
        self.assertEqual(found["channel"], "wellbeing")

    def test_모르는_모드는_적지_않는다(self):
        with self.assertRaises(ValueError):
            media_policy.choose(self.project, "아무거나")

    def test_모든_모드가_적히고_읽힌다(self):
        for mode in media_policy.MODES:
            with self.subTest(mode=mode):
                media_policy.choose(self.project, mode)

                self.assertEqual(media_policy.mode_for(self.project), mode)


class TheProviderStatesAreHonestTest(unittest.TestCase):
    """
    없는 것을 있다고 하지 않는다. 화면이 그것을 그대로 보여 준다.
    """

    def test_네_가지로_가른다(self):
        self.assertEqual(
            sorted(media_policy.STATES),
            sorted(("AVAILABLE", "NOT_CONFIGURED", "NOT_IMPLEMENTED",
                    "DISABLED")))

    def test_열쇠가_없으면_NOT_CONFIGURED(self):
        with patch.dict(os.environ, {"FLUX_API_KEY": ""}):
            found = media_policy.provider_states(
                media_policy.MODE_MINE_STOCK_AI)

        self.assertEqual(found["flux"]["state"], "NOT_CONFIGURED")

    def test_안_붙은_것은_NOT_IMPLEMENTED(self):
        found = media_policy.provider_states(media_policy.MODE_MINE_STOCK_AI)

        for name in ("imagen", "ideogram"):
            with self.subTest(name=name):
                self.assertEqual(found[name]["state"], "NOT_IMPLEMENTED")

    def test_AI_금지_모드에서는_모두_DISABLED(self):
        """
        고를 수 있는 것처럼 보이면 사람은 눌러 보고, 왜 안 되는지
        모른 채 시간을 버린다.
        """

        found = media_policy.provider_states(media_policy.MODE_MINE_ONLY)

        for name, row in found.items():
            with self.subTest(name=name):
                self.assertEqual(row["state"], "DISABLED")

    def test_금액을_지어내지_않는다(self):
        """
        Provider 가 단가를 말해 주지 않는다. 모르면 모른다고 한다.
        """

        found = media_policy.provider_states(media_policy.MODE_MINE_STOCK_AI)

        for name, row in found.items():
            with self.subTest(name=name):
                self.assertIn("cost", row)
                self.assertIn(row["cost"], (None, 0, 0.0),
                              f"{name} 이 금액을 지어냈다: {row['cost']}")


class TheCostSheetCountsButDoesNotGuessTest(unittest.TestCase):

    def _plan(self, mode, scenes=6):
        return media_policy.plan_for(mode, scene_count=scenes)

    def test_장수를_센다(self):
        found = self._plan(media_policy.MODE_MINE_STOCK_AI, scenes=6)

        self.assertEqual(found["scenes"], 6)
        self.assertIn("ai_max_images", found)
        self.assertIn("ai_max_calls", found)

    def test_AI_금지_모드는_0장_0회다(self):
        for mode in (media_policy.MODE_MINE_ONLY, media_policy.MODE_STOCK,
                     media_policy.MODE_MINE_THEN_STOCK):
            with self.subTest(mode=mode):
                found = self._plan(mode)

                self.assertEqual(found["ai_max_images"], 0)
                self.assertEqual(found["ai_max_calls"], 0)

    def test_AI_허용_모드도_상한이_있다(self):
        """
        재시도 때문에 무제한으로 불리면 안 된다.
        """

        found = self._plan(media_policy.MODE_AI_FIRST, scenes=100)

        self.assertLessEqual(found["ai_max_images"],
                             media_policy.AI_IMAGE_HARD_LIMIT)
        self.assertLessEqual(found["ai_max_calls"],
                             media_policy.AI_CALL_HARD_LIMIT)

    def test_비용은_확인_불가라고_적는다(self):
        found = self._plan(media_policy.MODE_AI_FIRST)

        self.assertIsNone(found["estimated_cost"])
        self.assertTrue(found["cost_unknown"])

    def test_같은_입력은_같은_답을_준다(self):
        first = self._plan(media_policy.MODE_MINE_STOCK_AI, scenes=8)
        second = self._plan(media_policy.MODE_MINE_STOCK_AI, scenes=8)

        self.assertEqual(first, second)


class TheGateRefusesTest(unittest.TestCase):
    """
    관문 자체. 부르는 쪽이 없어도 이것만은 참이어야 한다.
    """

    def test_금지_모드에서_막는다(self):
        for mode in (media_policy.MODE_MINE_ONLY, media_policy.MODE_STOCK,
                     media_policy.MODE_MINE_THEN_STOCK):
            with self.subTest(mode=mode):
                with self.assertRaises(media_policy.AiNotAllowed):
                    media_policy.require_ai_allowed(mode)

    def test_허용_모드는_지나간다(self):
        for mode in (media_policy.MODE_MINE_STOCK_AI,
                     media_policy.MODE_AI_FIRST):
            with self.subTest(mode=mode):
                self.assertIsNone(media_policy.require_ai_allowed(mode))

    def test_거절_문장이_사람_말이다(self):
        try:
            media_policy.require_ai_allowed(media_policy.MODE_MINE_ONLY)
        except media_policy.AiNotAllowed as refused:
            said = str(refused)

        self.assertIn("AI", said)
        self.assertTrue(len(said) > 15, said)


if __name__ == "__main__":
    unittest.main()
