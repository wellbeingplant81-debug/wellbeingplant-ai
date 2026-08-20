"""
Sprint245 - 사장님이 화면에서 목소리를 고른다.

Sprint244 가 관문을 세웠다. 고르지 않은 유료는 부르지 않는다. 그런데
**고르는 자리**가 없었다 - 관문만 있고 문고리가 없는 셈이다.

그림 쪽은 Sprint242 에서 같은 일을 했다. 그때 만든 모양을 그대로
따른다. 화면이 두 벌의 규칙을 배우게 하지 않는다.

    /studio/api/review/{id}/media-policy   그림
    /studio/api/review/{id}/voice-policy   목소리   <- 이번

무엇을 고르는가
---------------
Provider 하나다. 모드는 거기서 따라 나온다.

    내 PC 음성   -> FREE_ONLY
    Google TTS   -> PAID_OK
    ElevenLabs   -> PAID_OK

모드와 Provider 를 각각 고르게 하면 "유료 허용인데 내 PC 음성" 같은
말이 만들어진다. 사람이 정하는 것은 "누가 읽어 주는가" 하나다.

여기서 재는 것
--------------
실제 API 는 한 번도 부르지 않는다. 화면과 저장까지다.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app
from app.services import provider_selection, voice_policy


def _page():
    here = os.path.dirname(os.path.abspath(__file__))

    with open(os.path.join(os.path.dirname(here), "app", "static",
                           "studio.html"), encoding="utf-8") as f:
        return f.read()


class _Case(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.project = os.path.join(self.root, "p1")
        os.makedirs(self.project, exist_ok=True)

        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"topic": "무릎 통증", "channel": "wellbeing"}, f)

        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        p = patch.object(
            voice_policy, "default_store_path",
            lambda: os.path.join(self.home, voice_policy.STORE_FILENAME))
        p.start()
        self.addCleanup(p.stop)

        p2 = patch("app.routers.studio._project_path",
                   lambda project_id: os.path.join(self.root, project_id))
        p2.start()
        self.addCleanup(p2.stop)

        self.client = TestClient(app)

    def get(self, scenes=0):
        return self.client.get(
            f"/studio/api/review/p1/voice-policy?scene_count={scenes}")

    def put(self, body):
        return self.client.put("/studio/api/review/p1/voice-policy", json=body)


# -- 서버가 무엇을 말해 주는가 --------------------------------------
class TheScreenIsToldWhatItCanChooseTest(_Case):

    def test_읽을_수_있다(self):
        self.assertEqual(self.get().status_code, 200)

    def test_고를_수_있는_것이_셋이다(self):
        now = self.get().json()

        self.assertEqual(set(now["providers"]),
                         {"local_voice", "google", "elevenlabs"})

    def test_유료인지_아닌지_말해_준다(self):
        rows = self.get().json()["providers"]

        self.assertFalse(rows["local_voice"]["paid"])
        self.assertTrue(rows["google"]["paid"])
        self.assertTrue(rows["elevenlabs"]["paid"])

    def test_상태_어휘는_그림_쪽_것이다(self):
        from app.services import media_policy

        rows = self.get().json()["providers"]

        for name, row in rows.items():
            with self.subTest(name=name):
                self.assertIn(row["state"], media_policy.STATES)

    def test_열쇠가_없는_것은_고를_수_없다(self):
        """
        고를 수 있는가는 **지금 허용되는가**가 아니라 **고르면 실제로
        돌아가는가**다.

        실제 창에서 드러났다. 무료 모드라 유료 두 줄이 꺼져 있었는데,
        그것을 켜는 길이 바로 그 줄을 고르는 것이었다 - 사장님이 유료
        음성을 영영 켤 수 없었다.
        """

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ELEVENLABS_API_KEY", None)

            rows = self.get().json()["providers"]

        # 열쇠가 없다 - 골라도 못 만든다.
        self.assertFalse(rows["elevenlabs"]["choosable"])

    def test_유료가_꺼져_있어도_고를_수는_있다(self):
        """그것을 고르는 것이 켜는 방법이기 때문이다."""

        rows = self.get().json()["providers"]

        self.assertEqual(rows["google"]["state"], "DISABLED")
        self.assertTrue(rows["google"]["choosable"])

    def test_사람이_읽을_이름이_있다(self):
        rows = self.get().json()["providers"]

        self.assertEqual(rows["local_voice"]["label"], "내 PC 음성")
        self.assertEqual(rows["google"]["label"], "Google TTS")
        self.assertEqual(rows["elevenlabs"]["label"], "ElevenLabs")


# -- 안전한 기본값 --------------------------------------------------
class TheFirstAnswerIsNeverPaidTest(_Case):

    def test_첫_진입_기본값이_유료가_아니다(self):
        now = self.get().json()

        self.assertFalse(now["paid_allowed"])
        self.assertEqual(now["mode"], voice_policy.MODE_FREE_ONLY)

    def test_첫_진입_Provider_가_유료가_아니다(self):
        now = self.get().json()

        self.assertFalse(now["providers"][now["provider"]]["paid"])

    def test_금지_상태에서는_유료가_꺼져_보인다(self):
        rows = self.get().json()["providers"]

        self.assertEqual(rows["google"]["state"], "DISABLED")
        self.assertEqual(rows["elevenlabs"]["state"], "DISABLED")
        self.assertEqual(rows["local_voice"]["state"], "AVAILABLE")

    def test_환경변수가_화면_기본값을_바꾸지_못한다(self):
        for name in ("google", "elevenlabs"):
            with self.subTest(name=name):
                with patch.dict(os.environ, {"TTS_PROVIDER": name}):
                    now = self.get().json()

                self.assertEqual(now["mode"], voice_policy.MODE_FREE_ONLY)
                self.assertFalse(now["providers"][now["provider"]]["paid"])


# -- 고른 것이 남는가 -----------------------------------------------
class WhatWasChosenStaysChosenTest(_Case):

    def test_고르면_저장된다(self):
        self.put({"provider": "google"})

        self.assertEqual(
            provider_selection.selected(self.project, "voice"), "google")

    def test_유료를_고르면_그때만_허용된다(self):
        self.put({"provider": "google"})

        self.assertEqual(voice_policy.mode_for(self.project),
                         voice_policy.MODE_PAID_OK)

    def test_무료를_고르면_다시_금지로_돌아간다(self):
        self.put({"provider": "google"})
        self.put({"provider": "local_voice"})

        self.assertEqual(voice_policy.mode_for(self.project),
                         voice_policy.MODE_FREE_ONLY)

    def test_새로고침해도_남는다(self):
        self.put({"provider": "elevenlabs"})

        now = self.get().json()

        self.assertEqual(now["provider"], "elevenlabs")
        self.assertTrue(now["paid_allowed"])

    def test_프로젝트의_다른_칸을_지우지_않는다(self):
        self.put({"provider": "google"})

        with open(os.path.join(self.project, "project.json"),
                  encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["topic"], "무릎 통증")
        self.assertEqual(data["channel"], "wellbeing")

    def test_다른_프로젝트와_섞이지_않는다(self):
        other = os.path.join(self.root, "p2")
        os.makedirs(other, exist_ok=True)

        with open(os.path.join(other, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"topic": "허리"}, f)

        self.put({"provider": "google"})

        self.assertEqual(voice_policy.mode_for(other),
                         voice_policy.MODE_FREE_ONLY)
        self.assertIsNone(provider_selection.selected(other, "voice"))

    def test_모르는_이름은_거절한다(self):
        r = self.put({"provider": "지어낸것"})

        self.assertEqual(r.status_code, 400)


# -- 제작 전에 보여 줄 것 -------------------------------------------
class ThePlanIsHonestTest(_Case):

    def test_장면_셋이면_최대_세_번이다(self):
        self.put({"provider": "google", "scene_count": 3})

        plan = self.get(scenes=3).json()["plan"]

        self.assertEqual(plan["voice_calls"], 3)
        self.assertEqual(plan["paid_calls"], 3)

    def test_금지_상태에서는_유료가_최대_0회다(self):
        plan = self.get(scenes=3).json()["plan"]

        self.assertEqual(plan["paid_calls"], 0)

    def test_금액을_지어내지_않는다(self):
        plan = self.get(scenes=3).json()["plan"]

        self.assertIsNone(plan["estimated_cost"])
        self.assertTrue(plan["cost_unknown"])

    def test_고른_것의_이름을_적는다(self):
        self.put({"provider": "elevenlabs"})

        plan = self.get(scenes=2).json()["plan"]

        self.assertEqual(plan["provider_label"], "ElevenLabs")
        self.assertTrue(plan["paid"])

    def test_화면이_계획을_다시_계산하지_않는다(self):
        """
        파이프라인이 부를 횟수와 화면이 적은 횟수가 갈리면, 사람이
        본 것과 청구서가 달라진다. 서버가 한 번만 센다.
        """

        page = _page()

        self.assertNotIn("voice_calls =", page)
        self.assertNotIn("paid_calls =", page)


# -- 화면 --------------------------------------------------------
class TheCardIsOnThePageTest(_Case):

    def test_음성_카드가_있다(self):
        self.assertIn('id="voicePolicy"', _page())

    def test_서버에서_읽어_온다(self):
        self.assertIn("voice-policy", _page())

    def test_고른_것을_서버로_보낸다(self):
        page = _page()

        self.assertIn("chooseVoiceProvider", page)

    def test_Provider_이름을_화면에_적어_두지_않는다(self):
        """
        무엇을 고를 수 있는지는 서버가 정한다. 화면에 이름을 적어 두면
        하나가 붙거나 빠질 때 두 곳을 고쳐야 하고, 언젠가 한 곳만
        고친다.
        """

        page = _page()

        body = re.sub(r"/\*[\s\S]*?\*/", "", page)
        body = "\n".join(
            line for line in body.splitlines()
            if not line.strip().startswith("//"))

        at = body.index('id="voicePolicy"')
        near = body[at:at + 6000]

        for name in ("elevenlabs", "ElevenLabs", "google_tts"):
            with self.subTest(name=name):
                self.assertNotIn(name, near)

    def test_상태_낱말을_사람_말로_바꾼다(self):
        page = _page()

        self.assertIn("STATE_WORDS", page)

    def test_비용을_모르면_확인_불가라고_적는다(self):
        page = _page()

        at = page.index("voicePolicy")

        self.assertIn("확인 불가", page[at - 4000:at + 6000])


if __name__ == "__main__":
    unittest.main()
