"""
Sprint125 - ElevenLabs를 Provider 자리에 올린다 (Epic 56, Phase 2).

엔진은 이미 있다. app/providers/elevenlabs_provider.py가 실제 API를
부르고, voice 이름을 조회하고(못 찾으면 다른 voice로 대체하지 않고
에러), 받은 오디오를 정책 포맷(24kHz mono PCM)으로 바꿔 놓는다.
app/providers/tts_provider.py가 이미 그것을 부르므로 TTS_PROVIDER=
elevenlabs면 파이프라인 전체가 오늘도 ElevenLabs로 돈다.

그래서 여기서 만드는 것은 엔진이 아니라 자리다 - app.production의
StageProvider로 감싸서 등록소가 알게 하고, 설정이 됐는지 판정하고,
화면이 그것을 말할 수 있게 한다.

출력은 step03과 같아야 한다
---------------------------
scene wav가 반드시 있어야 한다. subtitle_service가 scene 오디오
개수와 scene 개수가 다르면 예외를 던지고(subtitle_service:521),
scene_timeline과 technical_validation도 같은 파일을 센다. voice.wav
하나만 만들면 자막이 죽는다.

파일 이름은 audio_policy가 정하고, 번호는 create_scene_tts와 같은
방식(목록 순서, 1부터)으로 매긴다. 다르게 매기면 같은 대본에서
step03과 다른 파일이 나온다.

voice.wav는 새로 만들지 않는다 - 엔진의 concat_scene_audio를 그대로
부른다. 나중에 파이프라인이 돌 때 Resolver가 같은 scene 파일로 다시
이어 붙이는데, 같은 입력이라 결과도 같다.

환경변수를 바꿔 쓰지 않는다
---------------------------
TTS_PROVIDER를 잠깐 elevenlabs로 바꾸는 방법도 있지만 쓰지 않는다.
studio_jobs는 파이프라인을 스레드로 돌리므로 두 작업이 겹치면 서로의
설정을 덮어쓴다. 대신 tts_provider.generate_voice에 어느 Provider를
쓸지 인자로 넘긴다.
"""

import os

from app.production import source_modes, stages
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    ProviderUnavailable,
    StageProvider,
)
from app.services import audio_policy

ELEVENLABS = "elevenlabs"

# 엔진이 실제로 읽는 이름들. 여기서 새로 정하지 않는다 -
# app/providers/elevenlabs_provider.py가 이 이름으로 읽는다.
API_KEY_SETTING = "ELEVENLABS_API_KEY"
VOICE_ID_SETTING = "ELEVENLABS_VOICE_ID"
VOICE_NAME_SETTING = "ELEVENLABS_VOICE_NAME"
MODEL_SETTING = "ELEVENLABS_MODEL"

AUDIO_DIRNAME = "audio"
SCENES_DIRNAME = "scenes"


class ElevenLabsVoiceProvider(StageProvider):
    """ElevenLabs로 scene별 나레이션을 만든다."""

    def __init__(self):
        self.capabilities = ProviderCapabilities(
            name=ELEVENLABS,
            stage=stages.VOICE,
            # 재 본 적이 없다. 등급을 매길 근거가 생기면 그때 바꾼다.
            quality_tier=STANDARD,
            supported_source_modes=(source_modes.GENERATE,),
            required_settings=(API_KEY_SETTING, VOICE_ID_SETTING),
            description=(
                "ElevenLabs로 나레이션을 만듭니다. 파이프라인이 이것을 "
                "쓰게 하려면 TTS_PROVIDER=elevenlabs가 필요합니다."
            ),
            display_name="ElevenLabs",
            vendor="ElevenLabs",
            # 실측 금액 계산은 아직이다. 모르는 것은 비워 둔다.
            estimated_cost=None,
            supports_streaming=False,
        )

    # ---- 쓸 수 있는가 -------------------------------------------------

    def _missing(self):
        """없는 설정. 엔진이 읽는 그 이름으로 돌려준다."""

        if not os.getenv(API_KEY_SETTING):
            return API_KEY_SETTING

        if not (os.getenv(VOICE_ID_SETTING) or os.getenv(VOICE_NAME_SETTING)):
            return VOICE_ID_SETTING

        return None

    def is_configured(self) -> bool:
        return self._missing() is None

    def availability(self):
        """(쓸 수 있는가, 왜 못 쓰는가). 화면이 그대로 보여 준다."""

        missing = self._missing()

        if missing is None:
            return True, ""

        if missing == VOICE_ID_SETTING:
            return False, (
                f"{VOICE_ID_SETTING} 또는 {VOICE_NAME_SETTING}이(가) "
                "설정되지 않았습니다."
            )

        return False, f"{missing}가 설정되지 않았습니다."

    # ---- 만든다 -------------------------------------------------------

    def generate(self, request):
        self._require(source_modes.GENERATE)

        available, reason = self.availability()

        if not available:
            raise ProviderUnavailable(reason)

        if request is None:
            raise ValueError("이 단계에 필요한 값이 없습니다: ['project_path', 'scenes']")

        request.require("project_path", "scenes")

        # 늦게 부른다 - 등록소에 올리는 것만으로 requests와 ffmpeg
        # 계층을 끌고 오지 않는다.
        from app.providers import tts_provider
        from app.services import audio_service

        project_path = request.project_path
        scenes = request.scenes

        scenes_dir = os.path.join(project_path, AUDIO_DIRNAME, SCENES_DIRNAME)
        os.makedirs(scenes_dir, exist_ok=True)

        paths = []

        # create_scene_tts와 같은 방식으로 번호를 매긴다 - 목록 순서,
        # 1부터. 다르게 매기면 step03과 다른 파일이 나온다.
        for index, scene in enumerate(scenes, start=1):
            target = os.path.join(
                scenes_dir, audio_policy.scene_audio_filename(index),
            )
            tts_provider.generate_voice(
                scene.get("narration") or "", target, provider=ELEVENLABS,
            )
            paths.append(target)

        # voice.wav는 엔진의 것을 그대로 쓴다. 새로 만들지 않는다.
        voice_path = os.path.join(
            project_path, AUDIO_DIRNAME, audio_policy.VOICE_FILENAME,
        )
        audio_service.concat_scene_audio(paths, voice_path)

        return {"scenes": paths, "voice_path": voice_path}
