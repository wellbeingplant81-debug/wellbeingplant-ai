"""
Sprint151 - 내 PC 음성을 등록소에 올린다 (Epic 57, Phase 2).

엔진은 app/providers/local_voice_provider.py에 있고 tts_provider가
이미 그것을 부른다. 여기서 만드는 것은 엔진이 아니라 자리다 -
등록소가 알게 하고, 화면이 그것을 고를 수 있게 한다.

Sprint125의 ElevenLabs 자리와 같은 모양이다. 부르는 방식도 같다:
환경변수를 바꿔 쓰지 않고 tts_provider.generate_voice에 어느
Provider인지 인자로 넘긴다 - studio_jobs가 파이프라인을 스레드로
돌리므로 전역을 건드리면 두 작업이 겹칠 때 서로의 설정을 덮어쓴다.

쓸 수 있는가
------------
키가 없다. 그래서 환경변수로 판정할 수 없고, 조건은 "그 프로젝트가
폴더를 훑어 두었는가"다. 그것은 프로젝트마다 다르므로 등록소가
답하지 못한다 - 여기서는 늘 쓸 수 있다고 하고, 실제로 자료가 없으면
generate()가 몇 번 scene이 없는지 말하며 멈춘다.

돈이 얼마나 드는가
------------------
0이다. 파일을 복사할 뿐이다. estimated_cost는 "0.0은 무료임을 안다는
뜻이고 None은 아직 모른다는 뜻"이라고 이미 정해져 있으므로, 여기가
0.0을 적을 수 있는 몇 안 되는 자리다.
"""

import os

from app.production import source_modes, stages
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    StageProvider,
)
from app.services import audio_policy

LOCAL_VOICE = "local_voice"

AUDIO_DIRNAME = "audio"
SCENES_DIRNAME = "scenes"

# 파일을 복사할 뿐이다. 모르는 것이 아니라 0인 것이다.
FREE = 0.0


class LocalVoiceProvider(StageProvider):
    """내 PC에 녹음해 둔 목소리로 scene 음성을 채운다."""

    def __init__(self):
        self.capabilities = ProviderCapabilities(
            name=LOCAL_VOICE,
            stage=stages.VOICE,
            # 재 본 적이 없다. 등급을 매길 근거가 생기면 그때 바꾼다.
            quality_tier=STANDARD,
            supported_source_modes=(source_modes.GENERATE,),
            # 키가 없다. 인증도 없다. 둘 다 비어 있으면 정말로 필요
            # 없는 것이다(ProviderCapabilities.authentication 참고).
            required_settings=(),
            authentication="",
            description=(
                "내 PC voice 폴더에서 scene 번호에 맞는 녹음을 골라 "
                "씁니다. TTS를 호출하지 않으므로 돈이 들지 않고, 그 "
                "번호의 파일이 없으면 만들지 않고 그대로 멈춥니다."
            ),
            display_name="내 PC 음성",
            vendor="직접 준비",
            estimated_cost=FREE,
            supports_streaming=False,
        )

    # ---- 쓸 수 있는가 -------------------------------------------------

    def availability(self):
        """
        (쓸 수 있는가, 왜 못 쓰는가).

        여기서 판정할 것이 없다 - 조건은 프로젝트마다 다른 "훑어 둔
        폴더"이고, 등록소는 어느 프로젝트인지 모른다.
        """

        return True, ""

    def is_configured(self) -> bool:
        return True

    # ---- 만든다 -------------------------------------------------------

    def generate(self, request):
        self._require(source_modes.GENERATE)

        if request is None:
            raise ValueError(
                "이 단계에 필요한 값이 없습니다: ['project_path', 'scenes']"
            )

        request.require("project_path", "scenes")

        # 늦게 부른다 - 등록소에 올리는 것만으로 ffmpeg 계층을 끌고
        # 오지 않는다.
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
                scene.get("narration") or "", target, provider=LOCAL_VOICE,
            )
            paths.append(target)

        # voice.wav는 엔진의 것을 그대로 쓴다. 새로 만들지 않는다.
        voice_path = os.path.join(
            project_path, AUDIO_DIRNAME, audio_policy.VOICE_FILENAME,
        )
        audio_service.concat_scene_audio(paths, voice_path)

        return {"scenes": paths, "voice_path": voice_path}
