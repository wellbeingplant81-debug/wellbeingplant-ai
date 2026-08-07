"""
Sprint106 - Script Resolver (Epic 54, Phase 5).

파이프라인이 대본을 어디서 얻을지 정하는 자리다. step01 앞에 선다.

step01_script.py는 손대지 않았다. 그 파일은 "AI가 대본을 쓴다"는 한
가지 일만 하고, 붙여넣은 대본을 쓸지 말지는 그 파일이 알 바가 아니다.
if문을 거기에 넣으면 Writer가 Writer가 아니게 된다.

Resolver는 만들지 않는다. 어디서 가져올지만 정하고, AI 생성이
필요하면 기존 step01_script.run()을 인자 그대로 부른다.

출처를 어떻게 아는가.

    project_service.create_project()는 매번 타임스탬프로 새 디렉터리를
    만들고 그 안에 script.json을 넣지 않는다. 그러니 파이프라인이
    시작될 때 script.json이 이미 있다면, 그것은 누군가 일부러 놓아
    둔 것이다. 추측이 아니라 그 코드가 그렇다(테스트로 묶어 두었다).

명시적으로 알려 줄 수도 있다. source를 주면 그것을 따르고, 주지
않으면 위 사실로 판단한다.

IMPORT와 MANUAL은 디스크에서 구분되지 않는다 - 둘 다 미리 놓인
script.json 하나다. 다른 것은 그 파일이 어디서 왔는가(붙여넣기냐
사람이 쓴 것이냐)이고, 그것은 파이프라인이 알 필요가 없다. 그래서
읽는 방법은 하나다.
"""

import json
import os

from app.steps import resolve_common

# 대본을 어디서 얻는가. Sprint114 - 세 Resolver가 같은 말을 쓰도록
# 어휘는 resolve_common이 소유한다. 값도 객체도 같다.
AUTO = resolve_common.AUTO
IMPORT = resolve_common.IMPORT
MANUAL = resolve_common.MANUAL

SOURCES = resolve_common.SOURCES

# 미리 놓인 대본을 쓰는 출처들. 둘 다 step01을 부르지 않는다.
PREPARED_SOURCES = resolve_common.PREPARED_SOURCES

SCRIPT_FILENAME = "script.json"

# 뒤 단계가 대괄호로 꺼내는 것들. 없으면 KeyError로 터진다 -
# 여기서 먼저 잡는 편이 훨씬 싸다.
#
#   scene["narration"]     scene_tts_service / duration_estimator / quality_service
#   scene["image_prompt"]  asset_integration_service
#   scene["scene"]         step02_assets
REQUIRED_SCENE_FIELDS = ("scene", "narration", "image_prompt")


class ScriptResolveError(ValueError):
    """미리 놓인 대본을 쓸 수 없다.

    고쳐서 다시 넣을 수 있게 무엇이 왜 안 되는지 적는다. 여기서
    대신 만들어 주지 않는다 - 사용자가 준 대본을 우리가 고치면
    그것은 더 이상 사용자가 준 대본이 아니다."""


def script_path(project_path: str) -> str:
    return os.path.join(project_path, SCRIPT_FILENAME)


# Sprint107 - 프로젝트를 만들 때 적어 두는 출처. project.json에 산다.
SOURCE_FIELD = "production_source"


def source_from_metadata(project_path: str):
    """project.json에 적힌 출처. 없으면 None.

    적혀 있으면 그것이 가장 확실한 근거다 - 프로젝트를 만든 쪽이
    직접 남긴 것이므로 디스크 상태를 보고 추측할 필요가 없다."""

    return resolve_common.source_from_metadata(project_path, SOURCE_FIELD)


def detect_source(project_path: str) -> str:
    """무엇으로 볼 것인가. 순수 읽기입니다.

    적혀 있으면 그것을 쓰고, 없으면 디스크 상태로 판단한다.

    "놓였다"의 뜻은 여기서 정한다 - 대본은 파일 하나이므로 그것이
    있느냐가 전부다.
    """

    return resolve_common.resolve_source(
        project_path,
        SOURCE_FIELD,
        lambda: os.path.exists(script_path(project_path)),
    )


def _load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ScriptResolveError(
            f"script.json을 읽을 수 없습니다({path}): {exc}"
        ) from exc
    except OSError as exc:
        raise ScriptResolveError(
            f"script.json을 열 수 없습니다({path}): {exc}"
        ) from exc


def validate(data) -> dict:
    """
    쓸 수 있는 대본인지 본다. 내용은 다시 만들지 않는다.

    확인하는 것은 뒤 단계가 실제로 꺼내는 것뿐이다 - 여기서 품질을
    판단하지 않는다. 그것은 step07이 할 일이다.
    """

    if not isinstance(data, dict):
        raise ScriptResolveError(
            "script.json의 최상위가 객체가 아닙니다. "
            '{"title": ..., "scenes": [...]} 모양이어야 합니다.'
        )

    if not data.get("title"):
        raise ScriptResolveError("script.json에 title이 없습니다.")

    scenes = data.get("scenes")

    if not isinstance(scenes, list) or not scenes:
        raise ScriptResolveError("script.json에 scene이 하나도 없습니다.")

    problems = []

    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            problems.append(f"{index}번째 scene이 객체가 아닙니다")
            continue

        missing = [
            field for field in REQUIRED_SCENE_FIELDS if not scene.get(field)
        ]

        if missing:
            problems.append(f"scene {index}: {', '.join(missing)} 없음")

    if problems:
        raise ScriptResolveError(
            "script.json의 scene이 뒤 단계가 요구하는 값을 갖추지 "
            f"못했습니다 - {'; '.join(problems)}"
        )

    return data


def load_prepared(project_path: str) -> dict:
    """미리 놓인 대본을 읽는다. 없으면 실패한다."""

    path = script_path(project_path)

    if not os.path.exists(path):
        raise ScriptResolveError(
            f"쓰기로 한 script.json이 없습니다: {path}. "
            "붙여넣기나 직접 작성으로 대본을 먼저 넣어 주십시오."
        )

    return validate(_load(path))


def run(topic: str, project_path: str, source: str = None) -> dict:
    """
    대본을 확보한다.

    AUTO면 기존 step01_script.run()을 인자 그대로 부른다 - 호출 형태도
    횟수도 산출물도 예전과 같다.

    IMPORT/MANUAL이면 step01을 부르지 않는다. Writer도 Gemini도
    건드리지 않는다.
    """

    resolved = source or detect_source(project_path)

    if resolved not in SOURCES:
        raise ScriptResolveError(
            f"알 수 없는 대본 출처입니다: {resolved!r}. "
            f"사용 가능한 값: {list(SOURCES)}"
        )

    if resolved in PREPARED_SOURCES:
        data = load_prepared(project_path)

        print("\n" + "=" * 80)
        print(f"STEP01 RESOLVE - {resolved}")
        print("=" * 80)
        print(f"미리 놓인 script.json을 씁니다 · scene {len(data['scenes'])}개")
        print(f"제목: {data.get('title')}")
        print("=" * 80)

        return data

    # AI 생성이 필요한 경우에만 무거운 것을 들인다.
    from app.steps import step01_script

    return step01_script.run(topic, project_path)
