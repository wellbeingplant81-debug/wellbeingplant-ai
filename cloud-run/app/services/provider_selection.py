"""
Sprint126 - 고른 Provider를 프로젝트에 적는다 (Epic 56, Phase 3).

Sprint125에서 ElevenLabs는 실제로 부를 수 있게 됐지만, 화면에서 고른
것이 파이프라인까지 가지는 못했다. 파이프라인은 TTS_PROVIDER 환경변수만
보고 있었다.

환경변수는 쓰지 않는다. studio_jobs가 파이프라인을 스레드로 돌리므로
전역 설정을 잠깐 바꾸는 방법은 두 작업이 겹치는 순간 서로의 설정을
덮어쓴다. 대신 고른 것을 프로젝트에 적는다 - project.json은 Resolver들이
이미 voice_source를 읽는 그 파일이고, "사람이 내린 결정만 저장하고
나머지는 산출물에서 읽는다"는 Sprint84의 원칙과도 같다.

칸 이름은 Resolver가 쓰는 것과 겹치지 않게 나눈다.

    voice_source    어디서 가져오는가(auto / import / manual)
    voice_provider  누가 만드는가(current / google / elevenlabs)

둘은 다른 질문이다. 섞으면 "직접 업로드한 음성을 ElevenLabs로 만든다"
같은 말이 되어 버린다.

"current"는 고르지 않은 것과 같다
---------------------------------
기존 동작을 100% 지키려면 "아무것도 고르지 않았다"가 확실히 예전
경로여야 한다. 그래서 current는 None으로 접히고, None이면 부르는 쪽이
예전처럼 환경변수를 읽는다.

이번 스프린트에서 실제로 읽히는 것은 voice 하나다. 나머지 셋은 같은
방식으로 적히기만 하고 아직 아무도 읽지 않는다 - 읽는 척하지 않는다.
"""

import json
import os

PROJECT_FILENAME = "project.json"

# 단계마다 누가 만드는가. Resolver가 읽는 *_source와 다른 칸이다.
FIELDS = {
    "script": "script_provider",
    "image": "image_provider",
    "voice": "voice_provider",
    "metadata": "metadata_provider",
}

# 고르지 않은 것과 같은 값. 현재 엔진이 정한 대로 간다는 뜻이다.
CURRENT = "current"

# 사람이 직접 쓴다. 엔진이 만들지 않는다는 뜻이다.
MANUAL = "manual"

# Sprint130 - 실제로 붙은 이미지 Provider.
FLUX = "flux"


class ProviderNotWired(RuntimeError):
    """고른 Provider가 아직 연결되지 않았다.

    app.production의 ProviderUnavailable과 같은 뜻이지만 층이 다르다 -
    그쪽은 StageProvider를 부를 때고, 이쪽은 엔진이 만들려는 순간이다.
    엔진 서비스가 app.production을 import하지 않게 하려고 나눠 둔다."""


def _wired_for(stage):
    """
    그 단계가 실제로 아는 Provider 이름들.

    voice는 tts_provider가 안다 - 여기 다시 적으면 한쪽만 바뀌는 날이
    온다. 나머지 셋은 아직 하나도 붙지 않았다(Sprint124의 자리들은
    부르면 거절한다).
    """

    if stage == "voice":
        from app.providers import tts_provider

        return tuple(tts_provider.PROVIDERS)

    # Sprint129 - 메타데이터의 manual은 앞의 것들과 다르다. "아직 안
    # 붙은 자리"가 아니라 이미 뜻이 정해져 있다 - 사람이 직접 쓴다는
    # 것이고, 그러면 엔진이 만들지 않는 것이 맞다. 없는 엔진을 새로
    # 만들 필요가 없으므로 처음부터 연결된 것으로 둔다.
    if stage == "metadata":
        return (MANUAL,)

    # Sprint130 - FLUX가 실제로 붙었다. 나머지 이미지 자리들
    # (imagen·gpt_image·ideogram)은 여전히 비어 있다.
    if stage == "image":
        return (FLUX,)

    return ()


class _Wired(dict):
    """WIRED["image"] 처럼 읽히되, 값은 물어볼 때 계산한다."""

    def __missing__(self, stage):
        require_stage(stage)
        return _wired_for(stage)


# 실제로 연결된 것. 여기 없는 이름을 고르면 만들 때 정직하게 거절한다.
WIRED = _Wired()


def require_wired(stage, provider):
    """
    고른 Provider로 실제로 만들 수 있는가.

    None(=고르지 않음/current)은 언제나 통과한다 - 기존 경로다.
    """

    require_stage(stage)

    if not provider or provider == CURRENT:
        return None

    if provider not in _wired_for(stage):
        raise ProviderNotWired(
            f"{provider}은(는) {stage} 단계에 아직 연결되지 않았습니다. "
            "현재 엔진으로 만들려면 current를 고르십시오."
        )

    return provider


def _path(project_path):
    return os.path.join(project_path, PROJECT_FILENAME)


def _load(project_path):
    try:
        with open(_path(project_path), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        # 읽을 수 없는 project.json 때문에 제작이 멈추지는 않는다.
        return {}

    return data if isinstance(data, dict) else {}


def require_stage(stage):
    if stage not in FIELDS:
        raise ValueError(
            f"알 수 없는 단계입니다: {stage!r}. "
            f"사용 가능한 값: {sorted(FIELDS)}"
        )

    return stage


def selected(project_path, stage):
    """
    이 프로젝트가 그 단계에 쓰기로 한 Provider. 안 골랐으면 None.

    순수 읽기다. current도 None으로 돌려준다 - 고르지 않은 것과 같은
    뜻이고, 부르는 쪽이 예전 경로로 가야 하기 때문이다.
    """

    require_stage(stage)

    value = _load(project_path).get(FIELDS[stage])

    if not value or value == CURRENT:
        return None

    return value


def all_selected(project_path):
    """화면이 보여 줄 현재 선택. 안 고른 것은 current로 적는다."""

    data = _load(project_path)

    return {
        stage: (data.get(field) or CURRENT)
        for stage, field in FIELDS.items()
    }


def save(project_path, providers):
    """
    사람이 고른 것을 프로젝트에 적는다. 나머지 값은 건드리지 않는다.

    project.json은 topic·channel·*_source가 사는 곳이라 통째로 덮어쓰면
    안 된다 - 읽어서 그 칸만 바꾸고 다시 쓴다.
    """

    data = _load(project_path)

    for stage, provider in (providers or {}).items():
        require_stage(stage)
        data[FIELDS[stage]] = provider or CURRENT

    with open(_path(project_path), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return all_selected(project_path)
