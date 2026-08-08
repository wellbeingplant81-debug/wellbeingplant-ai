"""
Sprint166 - 무엇으로 만들어졌는지 말한다 (Epic 57, Phase 17).

만들고 나면 사람은 묻는다. "이 영상, 뭘로 만든 거지?" 대본은 어디서
왔고, 그림은 어느 파일이며, 돈은 나갔는가.

전부 이미 어딘가에 적혀 있다
----------------------------
    project.json     production_source · *_provider
    output_check     영상 길이 · 검사 결과
    free_workspace   Scene마다 무엇이 쓰였는가
    asset_override   사람이 정한 것

새로 적지 않는다. 적어 두면 그것이 또 하나의 진실이 되고, 실제 파일과
갈리는 날이 온다 - 이 저장소가 여러 번 겪은 모양이다.

지어내지 않는다
---------------
품질 점수도, 예상 비용도, 추천도 없다.

"무료"·"저렴"·"가성비"라고 쓰지 않는다. 그것은 값어치에 대한 판단이고
우리는 값을 모른다. 아는 것은 "이 Provider가 API를 부르는가"뿐이고,
그것도 우리가 판정하지 않는다 - 등록소가 말하는 estimated_cost와
required_settings에서 읽는다.
"""

import os


def _script_source(metadata: dict) -> str:
    """
    대본이 어디서 왔는가.

    붙여넣기/직접 작성으로 만든 프로젝트에는 imported_project가
    적어 둔다. 없으면 엔진이 만든 것이다.
    """

    from app.steps import step01_script_resolve

    found = metadata.get(step01_script_resolve.SOURCE_FIELD)

    return found if found in step01_script_resolve.SOURCES \
        else step01_script_resolve.AUTO


def _calls_api(stage: str, provider: str, source: str) -> dict:
    """
    이 단계가 모델을 부르는가.

    우리가 판정하지 않는다. provider_selection이 말한다 - 등록소의
    ProviderCapabilities도 같은 사실을 들고 있고(estimated_cost 0.0),
    두 층이 갈리지 않는 것은 테스트가 잠근다.

    서비스 층에서 등록소를 부를 수는 없다. 파이프라인과 엔진은
    Provider 계층을 모르는 채로 둔다는 경계가 있고,
    test_production_architecture가 그것을 지킨다.

    대본은 Provider가 아니라 출처가 정한다 - 붙여넣기와 직접 작성은
    모델을 부르지 않는다(chat_import).
    """

    from app.services import provider_selection
    from app.steps import step01_script_resolve

    if stage == "script":
        calls = source == step01_script_resolve.AUTO

        return {"provider": provider, "source": source, "calls_api": calls}

    return {
        "provider": provider,
        "source": None,
        "calls_api": provider_selection.calls_api(stage, provider),
    }


def _scene_rows(prepared: dict) -> list:
    """Scene마다 무엇이 쓰였는가. 준비 상태가 낸 것을 그대로 옮긴다."""

    rows = []

    for row in prepared["scenes"]:
        image = row["image"]

        rows.append({
            "scene": row["scene"],
            "image": image.get("name"),
            # override / generated / matched. 화면이 그대로 읽는다.
            "image_source": image.get("asset_source"),
            "voice": row["voice"].get("name"),
            "voice_source": row["voice"].get("from"),
        })

    return rows


def build(project_path: str, scenes: list) -> dict:
    """
    무엇으로 만들어졌는가. 읽고 옮기기만 한다.

    돌려주는 것:

        title · topic     프로젝트가 들고 있던 것
        script            대본이 어디서 왔는가
        image · voice     어느 Provider를 골랐는가
        video             몇 초인가
        output            검사 결과 그대로
        cost              API를 부르는 단계가 있는가
        scene_rows        Scene마다 무엇이 쓰였는가
    """

    import json

    from app.services import (
        free_workspace, output_check, provider_selection, studio_review,
    )

    try:
        with open(os.path.join(project_path, "project.json"),
                  encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception:
        metadata = {}

    if not isinstance(metadata, dict):
        metadata = {}

    chosen = provider_selection.all_selected(project_path)
    source = _script_source(metadata)

    stages = {
        stage: _calls_api(stage, chosen.get(stage), source)
        for stage in ("script", "image", "voice")
    }

    result = output_check.build(project_path, scenes)
    prepared = free_workspace.preparation(project_path, scenes)

    return {
        "topic": metadata.get("topic"),
        "title": studio_review.state(project_path).get("title"),
        "script": {"source": source, "provider": chosen.get("script")},
        "image": {"provider": chosen.get("image")},
        "voice": {"provider": chosen.get("voice")},
        "video": {
            "exists": result["video"]["exists"],
            "seconds": result["video"]["seconds"],
        },
        "output": {
            "state": result["state"],
            "issues": result["issues"],
            "scenes": result["scenes"],
            "voices": result["voices"],
            "subtitle": result["subtitle"],
        },
        "cost": {
            # 값이 아니라 사실이다 - 부르는 단계가 하나도 없는가.
            "no_api_call": not any(x["calls_api"] for x in stages.values()),
            "stages": stages,
        },
        "scene_rows": _scene_rows(prepared),
    }
