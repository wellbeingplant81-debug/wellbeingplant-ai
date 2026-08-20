"""
Sprint244 - 화면을 거치지 않는 문도 같은 정책을 지킨다.

POST /generate-tts 는 프로젝트의 선택을 아예 보지 않는다.

    routers/tts.generate
      -> tts_service.create_tts(script, project_path)
          -> generate_voice(script, output)      <- provider 인자가 없다
              -> TTS_PROVIDER -> google          <- 유료

Sprint243 에서 배운 것이 그대로 되풀이된다. 파이프라인만 막으면
옆문이 남는다 - 썸네일이 그랬다.

관문이 유료 Provider 자신에게 있으므로 이 문도 자동으로 지난다. 그
사실을 시험으로 붙잡는다 - 나중에 누가 관문을 위로 올리면 여기가
먼저 운다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers import google_tts_provider
from app.services import tts_service, voice_policy


class _Case(unittest.TestCase):

    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"topic": "무릎"}, f)

        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        patcher = patch.object(
            voice_policy, "default_store_path",
            lambda: os.path.join(self.home, voice_policy.STORE_FILENAME),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.watch = _Watch()
        p = patch.object(google_tts_provider, "texttospeech")
        mock = p.start()
        self.addCleanup(p.stop)
        mock.TextToSpeechClient = self.watch


class _Watch:

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1

        raise AssertionError("유료 음성 API 가 실제로 불렸습니다.")


class TheSideDoorIsGuardedTest(_Case):

    def test_고르지_않은_채로_부르면_유료로_가지_않는다(self):
        """
        고르지 않았으면 무료 쪽으로 간다. 녹음이 없으면 거기서 멈춘다 -
        유료로 넘어가지 않는다. 어느 쪽이든 조용히 성공하지 않는다.
        """

        with self.assertRaises(Exception):
            tts_service.create_tts("안녕하세요", self.project)

        self.assertEqual(self.watch.calls, 0)

    def test_환경변수가_있어도_막힌다(self):
        with patch.dict(os.environ, {"TTS_PROVIDER": "google"}):
            with self.assertRaises(Exception):
                tts_service.create_tts("안녕하세요", self.project)

        self.assertEqual(self.watch.calls, 0)

    def test_금지_모드에서_막힌다(self):
        voice_policy.choose(self.project, voice_policy.MODE_FREE_ONLY)

        from app.services import provider_selection

        provider_selection.save(self.project, {"voice": "google"})

        with self.assertRaises(voice_policy.PaidVoiceNotAllowed):
            tts_service.create_tts("안녕하세요", self.project)

        self.assertEqual(self.watch.calls, 0)


class TheEndpointReportsItHonestlyTest(_Case):
    """
    막혔다는 사실이 사람에게 닿아야 한다. 500 으로 뭉개면 사용자는
    무엇을 고르면 되는지 알 수 없다.
    """

    def choose_paid(self):
        """유료를 고른 채 금지 모드에 둔다 - 관문이 거절하는 그 상황."""

        from app.services import provider_selection

        voice_policy.choose(self.project, voice_policy.MODE_FREE_ONLY)
        provider_selection.save(self.project, {"voice": "google"})

    def test_라우터가_정책_거절을_400_으로_돌려준다(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.choose_paid()
        client = TestClient(app)

        with patch("app.routers.tts.project_path_or_404",
                   return_value=self.project):
            response = client.post("/generate-tts", json={
                "script": "안녕하세요", "project_id": "x"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.watch.calls, 0)

    def test_거절_문장에_무엇을_하면_되는지_적힌다(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.choose_paid()
        client = TestClient(app)

        with patch("app.routers.tts.project_path_or_404",
                   return_value=self.project):
            response = client.post("/generate-tts", json={
                "script": "안녕하세요", "project_id": "x"})

        said = json.dumps(response.json(), ensure_ascii=False)

        self.assertTrue(any(w in said for w in ("고르", "선택")), said)


    def test_녹음이_없을_때도_500_이_아니다(self):
        """
        고르지 않아 무료로 갔는데 녹음이 없다. 그것은 고장이 아니라
        사람이 채워 넣으면 되는 일이다 - 무엇이 없는지 말해야 한다.
        """

        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        with patch("app.routers.tts.project_path_or_404",
                   return_value=self.project):
            response = client.post("/generate-tts", json={
                "script": "안녕하세요", "project_id": "x"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.watch.calls, 0)


if __name__ == "__main__":
    unittest.main()
