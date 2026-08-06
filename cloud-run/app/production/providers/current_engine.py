"""
Sprint103 - 지금 엔진을 Provider로 감싼다 (Epic 54, Phase 2).

새 AI 연결도 새 API도 없다. 지금 파이프라인이 부르는 바로 그 함수를
Provider 계약 뒤에 두는 것이 전부다.

  CurrentScriptProvider    -> step01_script.run()
  CurrentImageProvider     -> step02_assets.collect_assets()
  CurrentVoiceProvider     -> step03_tts.run()
  CurrentMetadataProvider  -> metadata_service.generate_publish_package()

파이프라인이 실제로 부르는 진입점을 감쌌다. 한 겹 아래(script_service.
generate_script 같은 것)를 감싸면 그 사이에 있는 것들 - Duration
Gate와 Topic Fidelity(Sprint95), scene별 병렬 처리, 오디오 병합 - 이
빠져서 결과가 달라진다. 같은 것을 부르므로 결과도 같다.

엔진 import는 전부 메서드 안에서 한다. script_service는 모듈을 읽는
것만으로 genai.Client를 만들고, 그것만으로 265개 모듈이 딸려 온다
(실측). Provider를 등록하는 것이 그 비용을 내는 일이 되면 안 된다.

지금은 GENERATE만 지원한다. 이 클래스들은 "지금 엔진을 감싼 것"이고,
지금 엔진에는 붙여넣기를 읽는 파서도 업로드 파일을 받는 경로도 없다.
그것들은 Wrapper가 아니라 새 기능이라 이번 범위 밖이다 - 없는 능력을
선언하지 않는다. 사용자가 Assisted/Manual에서 IMPORT/MANUAL을 고르면
Plan은 만들어지지만 그 단계를 맡을 Provider가 아직 없고, 등록소는
그 사실을 그대로 답한다.

품질 등급은 전부 STANDARD다. 지금 엔진 하나뿐이라 등급을 매길 상대가
없다 - Premium이라고 적어 두면 나중에 진짜 Premium Provider가 들어올
때 "무엇이 더 나은가"를 판단할 기준이 사라진다.
"""

from app.production import source_modes, stages
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    StageProvider,
)

# 지금 엔진을 가리키는 이름. 나중에 Provider가 늘어나도 이 이름이
# "현재 파이프라인이 쓰던 것"을 뜻한다.
CURRENT = "current"


class _CurrentEngineProvider(StageProvider):
    """지금 엔진을 감싸는 것들의 공통 부분.

    셋 다 GENERATE 하나만 지원하고, 등급은 STANDARD이고, 실제 호출은
    메서드 안에서 엔진 모듈을 들여 수행한다."""

    stage_name = ""
    description = ""

    def __init__(self):
        self.capabilities = ProviderCapabilities(
            name=CURRENT,
            stage=self.stage_name,
            quality_tier=STANDARD,
            supported_source_modes=(source_modes.GENERATE,),
            description=self.description,
        )


class CurrentScriptProvider(_CurrentEngineProvider):

    stage_name = stages.SCRIPT
    description = (
        "지금 쓰는 대본 엔진. Duration Gate와 Topic Fidelity를 거쳐 "
        "script.json까지 남긴다."
    )

    def generate(self, request):
        self._require(source_modes.GENERATE)
        request.require("topic", "project_path")

        from app.steps import step01_script

        return step01_script.run(request.topic, request.project_path)


class CurrentImageProvider(_CurrentEngineProvider):

    stage_name = stages.IMAGE
    description = (
        "지금 쓰는 이미지 엔진. scene마다 스톡 검색과 Imagen 생성을 "
        "골라 붙인다."
    )

    def generate(self, request):
        self._require(source_modes.GENERATE)
        request.require("scenes", "project_path")

        from app.steps import step02_assets

        return step02_assets.collect_assets(
            request.scenes, request.project_path, request.channel,
        )


class CurrentVoiceProvider(_CurrentEngineProvider):

    stage_name = stages.VOICE
    description = (
        "지금 쓰는 음성 엔진. TTS_PROVIDER 환경변수가 Google과 "
        "ElevenLabs 중 하나를 고른다."
    )

    def generate(self, request):
        self._require(source_modes.GENERATE)
        request.require("scenes", "project_path")

        from app.steps import step03_tts

        return step03_tts.run(request.scenes, request.project_path)


class CurrentMetadataProvider(_CurrentEngineProvider):

    stage_name = stages.METADATA
    description = (
        "지금 쓰는 메타데이터 엔진. 대본만 보고 publish_package.json을 "
        "만든다. AI를 부르지 않는다."
    )

    def generate(self, request):
        self._require(source_modes.GENERATE)
        request.require("project_path")

        from app.services import metadata_service

        return metadata_service.generate_publish_package(request.project_path)

    def estimate_cost(self, request, source_mode):
        """이 단계만 단가를 안다 - 0이다.

        메타데이터 엔진은 Gemini도 Imagen도 부르지 않는다(Sprint93).
        해시태그는 대본 텍스트에서 뽑고, 설명은 템플릿 조립이고,
        카테고리와 Playlist는 규칙 표에서 온다. 추측이 아니라 그
        코드가 그렇다."""

        from app.production.cost import CostEstimate

        return CostEstimate(
            stage=self.stage, provider=self.name, source_mode=source_mode,
            amount=0.0, note="규칙 기반이라 API를 호출하지 않습니다.",
        )


# 등록 순서는 파이프라인이 도는 순서와 같게 둔다 - 목록을 읽는 사람이
# 제작 흐름을 그대로 보게 된다.
CURRENT_PROVIDER_CLASSES = (
    CurrentScriptProvider,
    CurrentImageProvider,
    CurrentVoiceProvider,
    CurrentMetadataProvider,
)
