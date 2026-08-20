"""
Sprint244 - 고르지 않은 유료 목소리는 부르지 않는다.

무엇이 실제로 있었나
--------------------
새 EXE 로 영상을 만들 때 나레이션이 Google 로 나갔다. 아무도 화면에서
Google 을 고른 적이 없다. .env 의 TTS_PROVIDER=google 한 줄이 그것을
정하고 있었다.

    scene_tts_service   프로젝트의 선택을 읽는다 -> 안 골랐으면 None
    tts_provider        provider or os.getenv("TTS_PROVIDER", "google")
    google_tts_provider 유료 호출

이미지에서 Sprint241~243 이 막은 것과 같은 모양이다. 다른 점은 이미지
쪽 관문이 **잘못된 자리**에 있었다는 것이고, 음성 쪽에는 아예 없었다는
것이다.

관문을 어디에 두는가
--------------------
tts_provider.generate_voice 에 두지 않는다. 무료인 local_voice 도 그
함수를 지난다 - Sprint241 이 _ai_result 에 관문을 두어 85 개를 깨뜨린
것과 똑같은 실수가 된다.

유료 Provider 자신의 문 앞에 둔다.

    google_tts_provider.generate_voice
    elevenlabs_provider.generate_voice

여기서 재는 것
--------------
실제 API 는 한 번도 부르지 않는다. 두 Provider 가 바깥으로 나가는
지점(TextToSpeechClient / requests.post)을 감시자로 바꿔 두고, 그것이
**몇 번 불렸는가**만 센다. 0 이어야 한다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers import elevenlabs_provider, google_tts_provider, tts_provider
from app.services import provider_selection, voice_policy


class _Watch:
    """바깥으로 나가려는 시도를 센다. 실제로 내보내지는 않는다."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1

        raise AssertionError(
            "유료 음성 API 가 실제로 불렸습니다. 이 시험은 절대 "
            "바깥으로 나가면 안 됩니다."
        )


class _Case(unittest.TestCase):

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        self.write_project({"topic": "무릎"})

        self.audio = os.path.join(self.project, "audio", "scenes")
        os.makedirs(self.audio, exist_ok=True)

        self.out = os.path.join(self.audio, "scene1.wav")

        # 전역 기본값을 시험이 건드리지 않도록 딴 곳을 보게 한다.
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        patcher = patch.object(
            voice_policy, "default_store_path",
            lambda: os.path.join(self.home, voice_policy.STORE_FILENAME),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_project(self, data):
        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump(data, f)

    def watch_google(self):
        watch = _Watch()

        p = patch.object(google_tts_provider, "texttospeech")
        mock = p.start()
        self.addCleanup(p.stop)
        mock.TextToSpeechClient = watch

        return watch

    def watch_elevenlabs(self):
        watch = _Watch()

        p = patch.object(elevenlabs_provider, "requests")
        mock = p.start()
        self.addCleanup(p.stop)
        mock.post = watch

        return watch

    def choose_voice(self, name):
        provider_selection.save(self.project, {"voice": name})


# -- 전역 기본값 ----------------------------------------------------
class TheDefaultIsFreeTest(_Case):

    def test_전역_기본값은_유료_금지다(self):
        self.assertEqual(voice_policy.current_mode(),
                         voice_policy.MODE_FREE_ONLY)

    def test_정책_파일이_없어도_유료가_열리지_않는다(self):
        self.assertFalse(os.path.exists(voice_policy.default_store_path()))
        self.assertFalse(
            voice_policy.paid_allowed(voice_policy.current_mode()))

    def test_프로젝트가_고르지_않았으면_기본값을_따른다(self):
        self.assertEqual(voice_policy.mode_for(self.project),
                         voice_policy.MODE_FREE_ONLY)

    def test_상태_어휘를_새로_만들지_않는다(self):
        from app.services import media_policy

        for name in ("AVAILABLE", "NOT_CONFIGURED", "NOT_IMPLEMENTED",
                     "DISABLED"):
            with self.subTest(name=name):
                self.assertIs(getattr(voice_policy, name),
                              getattr(media_policy, name))


# -- 고르지 않았을 때 -----------------------------------------------
class NobodyChoseSoNobodyPaysTest(_Case):

    def test_고르지_않으면_Google_이_불리지_않는다(self):
        watch = self.watch_google()

        with self.assertRaises(voice_policy.PaidVoiceNotAllowed):
            google_tts_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 0)

    def test_고르지_않으면_ElevenLabs_가_불리지_않는다(self):
        watch = self.watch_elevenlabs()

        with self.assertRaises(voice_policy.PaidVoiceNotAllowed):
            elevenlabs_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 0)

    def test_환경변수_google_이_있어도_자동으로_불리지_않는다(self):
        watch = self.watch_google()

        with patch.dict(os.environ, {"TTS_PROVIDER": "google"}):
            with self.assertRaises(Exception):
                tts_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 0)

    def test_환경변수_elevenlabs_가_있어도_자동으로_불리지_않는다(self):
        watch = self.watch_elevenlabs()

        with patch.dict(os.environ, {"TTS_PROVIDER": "elevenlabs",
                                     "ELEVENLABS_API_KEY": "x",
                                     "ELEVENLABS_VOICE_ID": "y"}):
            with self.assertRaises(Exception):
                tts_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 0)

    def test_환경변수는_유료를_고를_수_없다(self):
        """사람이 고르는 자리는 화면이다. .env 한 줄이 아니다."""

        for name in ("google", "elevenlabs"):
            with self.subTest(name=name):
                with patch.dict(os.environ, {"TTS_PROVIDER": name}):
                    self.assertNotEqual(voice_policy.default_provider(), name)


# -- 금지 모드 ------------------------------------------------------
class TheForbiddenModeHoldsTest(_Case):

    def setUp(self):
        super().setUp()
        voice_policy.choose(self.project, voice_policy.MODE_FREE_ONLY)

    def test_금지_모드에서_Google_이_막힌다(self):
        watch = self.watch_google()
        self.choose_voice("google")

        with self.assertRaises(voice_policy.PaidVoiceNotAllowed):
            google_tts_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 0)

    def test_금지_모드에서_ElevenLabs_가_막힌다(self):
        watch = self.watch_elevenlabs()
        self.choose_voice("elevenlabs")

        with self.assertRaises(voice_policy.PaidVoiceNotAllowed):
            elevenlabs_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 0)

    def test_거절_문장이_사람_말이다(self):
        try:
            google_tts_provider.generate_voice("안녕하세요", self.out)
        except voice_policy.PaidVoiceNotAllowed as exc:
            said = str(exc)
        else:
            self.fail("막지 않았다")

        self.assertTrue(said.strip())
        self.assertNotIn("Traceback", said)

        # 무엇을 하면 되는지 적혀 있어야 한다.
        self.assertTrue(any(w in said for w in ("고르", "선택")), said)


# -- 허용 모드 ------------------------------------------------------
class OnlyTheChosenOneIsCalledTest(_Case):

    def setUp(self):
        super().setUp()
        voice_policy.choose(self.project, voice_policy.MODE_PAID_OK)

    def test_고른_것은_지나간다(self):
        self.choose_voice("google")

        # 관문을 지났는지만 본다. 그 뒤 실제 호출은 감시자가 막는다.
        watch = self.watch_google()

        with self.assertRaises(AssertionError):
            google_tts_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 1)

    def test_고르지_않은_다른_유료로_새지_않는다(self):
        """Google 을 골랐다고 ElevenLabs 가 열리지는 않는다."""

        self.choose_voice("google")
        watch = self.watch_elevenlabs()

        with self.assertRaises(voice_policy.PaidVoiceNotAllowed):
            elevenlabs_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 0)

    def test_허용해도_고르지_않았으면_부르지_않는다(self):
        watch = self.watch_google()

        with self.assertRaises(voice_policy.PaidVoiceNotAllowed):
            google_tts_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 0)


# -- 무료 경로 ------------------------------------------------------
class TheFreePathIsNotBlockedTest(_Case):

    def test_local_voice_는_정책에_막히지_않는다(self):
        self.choose_voice(provider_selection.LOCAL_VOICE)

        seen = {}

        def fake(text, output_file):
            seen["called"] = True

            return output_file

        with patch("app.providers.local_voice_provider.generate_voice", fake):
            tts_provider.generate_voice("안녕하세요", self.out,
                                        provider="local_voice")

        self.assertTrue(seen.get("called"), "무료 경로가 막혔다")

    def test_고르지_않았으면_무료_쪽으로_간다(self):
        self.assertEqual(voice_policy.default_provider(),
                         provider_selection.LOCAL_VOICE)


# -- 무료 자료가 없을 때 --------------------------------------------
class NoRecordingIsNotAnExcuseToPayTest(_Case):

    def test_녹음이_없으면_유료로_넘어가지_않는다(self):
        self.choose_voice(provider_selection.LOCAL_VOICE)

        google = self.watch_google()
        eleven = self.watch_elevenlabs()

        from app.providers import local_voice_provider

        with patch.object(
                local_voice_provider, "generate_voice",
                side_effect=local_voice_provider.LocalVoiceUnavailable(
                    "scene 1 의 녹음이 없습니다.")):
            with self.assertRaises(local_voice_provider.LocalVoiceUnavailable):
                tts_provider.generate_voice("안녕하세요", self.out,
                                            provider="local_voice")

        self.assertEqual(google.calls, 0)
        self.assertEqual(eleven.calls, 0)

    def test_조용히_성공으로_처리하지_않는다(self):
        from app.providers import local_voice_provider

        self.assertTrue(
            issubclass(local_voice_provider.LocalVoiceUnavailable, Exception))


# -- 정책 오류가 돈으로 바뀌지 않는다 -------------------------------
class APolicyErrorNeverBecomesACallTest(_Case):

    def test_알_수_없는_모드가_유료를_열지_않는다(self):
        watch = self.watch_google()

        self.write_project({"voice_policy": "이상한값"})

        with self.assertRaises(voice_policy.PaidVoiceNotAllowed):
            google_tts_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 0)

    def test_프로젝트를_못_찾아도_유료가_열리지_않는다(self):
        watch = self.watch_google()

        lonely = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, lonely, ignore_errors=True)

        with self.assertRaises(voice_policy.PaidVoiceNotAllowed):
            google_tts_provider.generate_voice(
                "안녕하세요", os.path.join(lonely, "scene1.wav"))

        self.assertEqual(watch.calls, 0)

    def test_읽을_수_없는_project_json_도_유료를_열지_않는다(self):
        watch = self.watch_google()

        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            f.write("{ 망가진")

        with self.assertRaises(voice_policy.PaidVoiceNotAllowed):
            google_tts_provider.generate_voice("안녕하세요", self.out)

        self.assertEqual(watch.calls, 0)


if __name__ == "__main__":
    unittest.main()
