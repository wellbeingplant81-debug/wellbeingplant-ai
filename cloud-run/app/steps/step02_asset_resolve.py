"""
Sprint111 - 이미지를 어디서 가져올지 정한다 (Epic 54, Phase 10).

Sprint106의 Script Resolver와 같은 자리, 같은 원칙이다. step02 앞에
서서 고르기만 하고, AUTO면 손대지 않은 step02를 그대로 부른다.

step02_assets.py는 수정하지 않는다. 그 파일은 "AI가 이미지를 구해
온다"는 한 가지 일만 한다. 사용자가 이미 놓아 둔 이미지를 쓸지 말지는
그 파일이 판단할 문제가 아니고, 거기에 if를 넣는 순간 이미지가 오는
길이 그 안에서 둘로 갈라진다.

Resolver가 하는 일은 셋뿐이다.

    존재 판단   images/scene{N}.png가 있는가
    검증        scene 수만큼 다 있는가
    선택        있으면 그것을 쓰고, 없으면 step02를 부른다

만들지 않는다. 고치지 않는다. 변환하지 않는다. 이미지를 놓는 일은
Sprint110의 ImageImportProvider가 이미 끝냈고, 여기는 그것이 남긴
결과를 확인만 한다.

장수가 모자라면 거절한다. 경고만 하고 넘기면 그 scene은 렌더에서
파일을 못 찾아 죽는데, 그때는 이미 TTS까지 다 돌린 뒤다. 여기서
멈추는 편이 사용자에게 훨씬 싸다. 반대로 남는 장수는 경고만 한다 -
쓰이지 않을 뿐 잘못된 것은 없다.

파일 이름 규칙은 엔진의 것을 그대로 쓴다. app.production을 import하지
않는다 - 파이프라인과 엔진은 Provider 계층을 모르는 채로 둔다(그
경계는 test_production_architecture가 지킨다). Sprint110 Provider가
같은 규칙을 갖고 있지만 그쪽이 엔진을 따라간 쪽이고, 따라가는 쪽을
가져다 쓰면 의존 방향이 거꾸로 선다. 두 값이 갈라지지 않는 것은
테스트로 잠근다.
"""

import json
import os

# 엔진이 이미지를 놓고 찾는 자리. asset_integration_service가 여기에
# scene{N}.png로 만들고, video_builder가 같은 이름으로 읽는다.
IMAGES_DIRNAME = "images"
SCENE_FILENAME = "scene{number}.png"

# 붙일 값도 step02가 쓰는 것과 같은 자리다. Sprint110 Provider가 놓고
# 간 이미지이므로 그쪽 이름을 그대로 적는다.
IMAGE_IMPORT = "image_import"

# 사용자가 그 scene을 위해 직접 고른 이미지다. step02가 AI Image에
# 주는 값과 같은 1.0으로 둔다 - 스톡의 0.8은 "검색으로 찾은 것"이라는
# 뜻이라 여기에 맞지 않는다.
CONFIDENCE = 1.0

AUTO = "auto"
IMPORT = "import"
MANUAL = "manual"

SOURCES = (AUTO, IMPORT, MANUAL)

# 사용자가 직접 놓은 이미지를 쓰는 두 가지. 화면에서 폴더를 고르든
# 파일을 끌어다 놓든 결과는 같은 자리의 같은 파일이라, 여기서
# 갈라야 할 이유가 없다.
PREPARED_SOURCES = (IMPORT, MANUAL)

# project.json에 사람이 고른 것을 적어 둔다. Sprint107이 대본에
# production_source를 쓰는 것과 같은 방식이고, 단계마다 출처가
# 다를 수 있으므로(Sprint109) 이미지는 이미지의 칸을 쓴다.
SOURCE_FIELD = "image_source"

PROJECT_FILENAME = "project.json"


class AssetResolveError(ValueError):
    """준비된 이미지를 쓸 수 없다.

    무엇이 왜 안 되는지 적는다 - 사람이 고쳐서 다시 넣을 수 있어야
    한다."""


def _images_dir(project_path):
    return os.path.join(project_path, IMAGES_DIRNAME)


def _scene_path(project_path, number):
    return os.path.join(
        _images_dir(project_path), SCENE_FILENAME.format(number=number),
    )


def _placed_numbers(project_path):
    """놓여 있는 scene 번호들. 파일이 실제로 있는 것만 센다."""

    images_dir = _images_dir(project_path)

    if not os.path.isdir(images_dir):
        return []

    stem, suffix = SCENE_FILENAME.format(number="\0").split("\0")
    found = []

    for name in os.listdir(images_dir):
        if not (name.startswith(stem) and name.endswith(suffix)):
            continue

        digits = name[len(stem):len(name) - len(suffix)]
        if digits.isdigit():
            found.append(int(digits))

    return sorted(found)


def source_from_metadata(project_path):
    """사람이 고른 것이 적혀 있으면 그것. 없으면 None."""

    path = os.path.join(project_path, PROJECT_FILENAME)

    if not os.path.exists(path):
        return None

    try:
        with open(path, encoding="utf-8") as f:
            recorded = json.load(f).get(SOURCE_FIELD)
    except (OSError, ValueError):
        # 읽을 수 없는 project.json 때문에 제작이 멈추지는 않는다.
        # 적혀 있지 않은 것과 같게 다룬다.
        return None

    return recorded if recorded in SOURCES else None


def detect_source(project_path):
    """
    적힌 것 > 디스크 > AUTO.

    디스크를 보는 이유는 create_project()가 images/를 비운 채로
    만들기 때문이다. 비어 있으면 아직 아무도 놓지 않았다는 뜻이고,
    scene{N}.png가 있으면 Provider가 이미 놓고 간 것이다.
    """

    recorded = source_from_metadata(project_path)

    if recorded:
        return recorded

    return IMPORT if _placed_numbers(project_path) else AUTO


def validate(scenes, project_path):
    """
    준비된 이미지가 scene을 다 덮는지 본다. 고쳐 주지 않는다.

    모자라면 거절하고, 남으면 경고만 돌려준다.
    """

    expected = [
        scene.get("scene", index + 1) for index, scene in enumerate(scenes)
    ]
    missing = [
        number for number in expected
        if not os.path.exists(_scene_path(project_path, number))
    ]

    if missing:
        raise AssetResolveError(
            f"Scene {len(expected)}개인데 이미지는 "
            f"{len(expected) - len(missing)}개입니다 - "
            f"Scene {', '.join(str(n) for n in missing)}의 이미지가 없습니다. "
            "이미지를 채운 뒤 다시 실행하거나, 이미지 생성을 자동으로 "
            "바꾸십시오."
        )

    extra = [n for n in _placed_numbers(project_path) if n not in expected]

    if extra:
        return [
            f"Scene {len(expected)}개, 이미지 {len(expected) + len(extra)}개 - "
            f"scene {', '.join(str(n) for n in extra)}.png는 쓰이지 않습니다."
        ]

    return []


def load_prepared(scenes, project_path, source):
    """
    놓여 있는 이미지를 scene에 붙인다. 파일은 건드리지 않는다.

    붙이는 키는 step02가 쓰는 것과 같다. 다르면 뒤 단계가 출처를
    알아야 하고, 그 순간 이미지가 오는 길이 둘이 된다.
    """

    warnings = validate(scenes, project_path)

    for warning in warnings:
        print("STEP02 RESOLVE WARN - " + warning)

    resolved = []

    for index, scene in enumerate(scenes):
        number = scene.get("scene", index + 1)

        enriched = dict(scene)
        enriched["provider"] = IMAGE_IMPORT
        enriched["asset_type"] = "image"
        enriched["asset_path"] = _scene_path(project_path, number)
        enriched["confidence"] = CONFIDENCE
        resolved.append(enriched)

    return resolved


def run(scenes, project_path, channel, source=None):
    """
    이미지 단계 입구.

    준비된 이미지가 있으면 그것을 쓰고, 없으면 step02를 그대로
    부른다. AUTO 경로는 예전과 완전히 같아야 한다 - 인자도, 횟수도.

    명시된 source가 detect보다 우선한다(Sprint107과 같다). 화면에서
    "자동"을 고른 사람은 폴더에 뭐가 있든 자동을 기대한다.
    """

    resolved = source or detect_source(project_path)

    if resolved not in SOURCES:
        raise AssetResolveError(
            f"알 수 없는 이미지 출처입니다: {resolved}. "
            f"{', '.join(SOURCES)} 중 하나여야 합니다."
        )

    if resolved in PREPARED_SOURCES:
        print("STEP02 RESOLVE - " + resolved)

        return load_prepared(scenes, project_path, resolved)

    # AUTO. step02는 수정되지 않았고, 여기서만 불린다.
    #
    # 늦게 부르는 이유는 step02가 읽히는 것만으로 이미지 엔진 쪽
    # 모듈을 대량으로 끌고 오기 때문이다. 준비된 이미지를 쓰는
    # 경로에서는 그것들이 필요 없다.
    from app.steps import step02_assets

    return step02_assets.collect_assets(scenes, project_path, channel)
