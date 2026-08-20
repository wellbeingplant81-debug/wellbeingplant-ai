"""
Sprint246 - 무료 경로가 혼자서 끝까지 간다.

무엇을 증명하려는가
-------------------
내 자료 + 무료 스톡 + 내 PC 음성 + 로컬 BGM 만으로 영상 한 편이
완성된다. 도중에 돈이 드는 문을 하나도 열지 않는다.

Sprint241~245 가 문마다 관문을 세웠다. 이 파일은 그 관문들이 **함께**
서 있을 때 길이 막히지 않는지를 본다 - 관문 하나하나가 옳아도, 다
막아 놓고 보니 갈 길이 없으면 제품이 아니다.

여기서 재지 않는 것
-------------------
실제 EXE 렌더는 여기서 하지 않는다. 그것은 사람이 지켜보는 검증이고,
이 파일은 계약만 붙잡는다.

무료 Provider(Pexels)도 부르지 않는다. 망을 타는 것은 시험이 할 일이
아니다 - 여기서 세는 것은 **유료 문이 몇 번 열렸는가** 하나다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers import (
    elevenlabs_provider, google_tts_provider, local_voice_provider,
    tts_provider,
)
from app.services import (
    image_service, local_library, media_policy, provider_selection,
    voice_policy,
)

WAV_HEADER = b"RIFF"


class _PaidDoor:
    """돈이 나가는 문. 열리면 세고, 실제로 내보내지는 않는다."""

    def __init__(self, name, book):
        self.name = name
        self.book = book

    def __call__(self, *a, **k):
        self.book[self.name] = self.book.get(self.name, 0) + 1

        raise AssertionError(f"{self.name} 이(가) 실제로 불렸습니다.")


class _Case(unittest.TestCase):

    def setUp(self):
        self.book = {}

        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.project = os.path.join(self.root, "p")
        os.makedirs(os.path.join(self.project, "audio", "scenes"),
                    exist_ok=True)

        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"topic": "무릎"}, f)

        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        for module, attr in ((voice_policy, "default_store_path"),
                             (media_policy, "default_store_path")):
            p = patch.object(
                module, attr,
                lambda m=module: os.path.join(self.home, m.STORE_FILENAME))
            p.start()
            self.addCleanup(p.stop)

        self.watch_every_paid_door()

    def watch_every_paid_door(self):
        """유료 문 다섯을 전부 감시자로 바꾼다."""

        g = patch.object(google_tts_provider, "texttospeech")
        gm = g.start()
        self.addCleanup(g.stop)
        gm.TextToSpeechClient = _PaidDoor("google_tts", self.book)

        e = patch.object(elevenlabs_provider, "requests")
        em = e.start()
        self.addCleanup(e.stop)
        em.post = _PaidDoor("elevenlabs", self.book)

        i = patch.object(image_service, "client")
        im = i.start()
        self.addCleanup(i.stop)
        im.models.generate_images = _PaidDoor("imagen", self.book)

        for name in ("flux_provider", "gpt_image_provider"):
            try:
                module = __import__(f"app.providers.{name}",
                                    fromlist=[name])
            except Exception:
                continue

            if not hasattr(module, "generate_image"):
                continue

            p = patch.object(module, "generate_image",
                             _PaidDoor(name, self.book))
            p.start()
            self.addCleanup(p.stop)

    def paid_calls(self):
        return sum(self.book.values())

    def place_voices(self, count):
        """번호가 붙은 음성을 내 자료 폴더에 놓고 색인한다."""

        library = os.path.join(self.root, "내자료")
        voice = os.path.join(library, "voice")
        os.makedirs(voice, exist_ok=True)

        for n in range(1, count + 1):
            with open(os.path.join(voice, f"scene{n}.wav"), "wb") as f:
                f.write(WAV_HEADER + bytes(200))

        local_library.save(self.project, local_library.scan(library))

        return library

    def out(self, n):
        return os.path.join(self.project, "audio", "scenes", f"scene{n}.wav")


# -- 1. 음성이 없을 때 ----------------------------------------------
class NoRecordingNeverBecomesABillTest(_Case):

    def test_음성이_없으면_유료로_넘어가지_않는다(self):
        provider_selection.save(self.project, {"voice": "local_voice"})

        with self.assertRaises(local_voice_provider.LocalVoiceUnavailable):
            tts_provider.generate_voice("안녕하세요", self.out(1),
                                        provider="local_voice")

        self.assertEqual(self.paid_calls(), 0)

    def test_몇_번이_없는지_말해_준다(self):
        provider_selection.save(self.project, {"voice": "local_voice"})
        self.place_voices(3)

        try:
            tts_provider.generate_voice("안녕하세요", self.out(5),
                                        provider="local_voice")
        except local_voice_provider.LocalVoiceUnavailable as exc:
            said = str(exc)
        else:
            self.fail("없는데 만들었다")

        self.assertIn("5", said)
        self.assertEqual(self.paid_calls(), 0)

    def test_없는_파일을_지어내지_않는다(self):
        provider_selection.save(self.project, {"voice": "local_voice"})

        with self.assertRaises(Exception):
            tts_provider.generate_voice("안녕하세요", self.out(1),
                                        provider="local_voice")

        self.assertFalse(os.path.exists(self.out(1)))


# -- 2·3. 음성이 있을 때 --------------------------------------------
class ThePreparedVoicesAreUsedTest(_Case):

    def test_번호가_정확히_대응한다(self):
        self.place_voices(6)

        for n in range(1, 7):
            with self.subTest(scene=n):
                found = local_voice_provider.find(self.project, n)

                self.assertIsNotNone(found)
                self.assertEqual(os.path.basename(found["path"]),
                                 f"scene{n}.wav")

    def test_없는_번호는_없다고_한다(self):
        self.place_voices(6)

        self.assertIsNone(local_voice_provider.find(self.project, 7))

    def test_다른_번호로_대신하지_않는다(self):
        """3번이 없다고 2번을 주면 자막과 소리가 어긋난다."""

        library = os.path.join(self.root, "내자료")
        voice = os.path.join(library, "voice")
        os.makedirs(voice, exist_ok=True)

        for n in (1, 2, 4):
            with open(os.path.join(voice, f"scene{n}.wav"), "wb") as f:
                f.write(WAV_HEADER + bytes(200))

        local_library.save(self.project, local_library.scan(library))

        self.assertIsNone(local_voice_provider.find(self.project, 3))


# -- 5·6. 그림은 스톡으로 --------------------------------------------
class ThePictureNeverFallsBackToAiTest(_Case):

    def test_AI_금지에서_유료_그림_문이_열리지_않는다(self):
        media_policy.choose(self.project, media_policy.MODE_MINE_THEN_STOCK)

        with self.assertRaises(media_policy.AiNotAllowed):
            image_service.generate_image(
                "무릎", os.path.join(self.project, "images", "scene1.png"))

        self.assertEqual(self.paid_calls(), 0)

    def test_썸네일도_유료로_새지_않는다(self):
        media_policy.choose(self.project, media_policy.MODE_MINE_THEN_STOCK)

        images = os.path.join(self.project, "images")
        os.makedirs(images, exist_ok=True)

        with open(os.path.join(images, "scene1.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + bytes(100))

        from app.services import thumbnail_service

        thumbnail_service.create_thumbnail(
            "제목", "무릎", self.project, "wellbeing", "내레이션", "knee")

        self.assertTrue(
            os.path.isfile(os.path.join(self.project, "thumbnail.png")))
        self.assertEqual(self.paid_calls(), 0)


# -- 9. 결제 잠금이 500 이 되지 않는다 -------------------------------
class TheFreeJourneyIsNotAnErrorTest(_Case):

    def test_무료_경로_전체에서_유료_문이_한_번도_안_열린다(self):
        media_policy.choose(self.project, media_policy.MODE_MINE_THEN_STOCK)
        provider_selection.save(self.project, {"voice": "local_voice"})
        self.place_voices(6)

        # 음성 여섯 - 실제 변환은 ffmpeg 이 한다. 여기서는 고르기까지만
        # 본다(가짜 wav 라 변환은 못 한다).
        for n in range(1, 7):
            self.assertIsNotNone(local_voice_provider.find(self.project, n))

        self.assertEqual(voice_policy.mode_for(self.project),
                         voice_policy.MODE_FREE_ONLY)
        self.assertFalse(media_policy.ai_allowed(
            media_policy.mode_for(self.project)))
        self.assertEqual(self.paid_calls(), 0)

    def test_환경변수가_선택을_덮지_못한다(self):
        provider_selection.save(self.project, {"voice": "local_voice"})
        self.place_voices(1)

        for name in ("google", "elevenlabs"):
            with self.subTest(name=name):
                with patch.dict(os.environ, {"TTS_PROVIDER": name}):
                    chosen = provider_selection.selected(self.project, "voice")

                self.assertEqual(chosen, "local_voice")

        self.assertEqual(self.paid_calls(), 0)


# -- 10. 묶은 프로그램에 열쇠를 넣지 않는다 --------------------------
class TheBundleCarriesNoKeysTest(unittest.TestCase):

    def test_묶는_목록에_열쇠_파일이_없다(self):
        """
        글자로 찾으면 제 설명에 걸린다.

        이 spec 은 독스트링에 "무엇을 넣지 않는가" 를 적어 두었고
        (.env API 키), os.environ 에도 ".env" 가 들어 있다. 둘 다
        열쇠를 묶는다는 뜻이 아니다.

        그래서 실제 **문자열 리터럴**만 본다. 파일을 묶으려면 그
        이름이 어딘가 글자로 적혀야 하고, 적히지 않은 것은 묶이지
        않는다.
        """

        import ast

        here = os.path.dirname(os.path.abspath(__file__))
        spec = os.path.join(os.path.dirname(here), "packaging",
                            "AI영상제작소.spec")

        with open(spec, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        # 독스트링은 설명이지 값이 아니다.
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        }

        literals = [
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value not in docstrings
        ]

        for secret in (".env", "credentials", "API_KEY", "token.json"):
            with self.subTest(secret=secret):
                guilty = [t for t in literals if secret in t]

                self.assertEqual(guilty, [], f"열쇠를 묶고 있다: {guilty}")


if __name__ == "__main__":
    unittest.main()
