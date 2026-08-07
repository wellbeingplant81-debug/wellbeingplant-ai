"""
Sprint110 - 사용자가 만든 이미지를 쓴다 (Epic 54, Phase 9).

AI 이미지를 생성하지 않는다. 사용자가 준 파일을 엔진이 쓰는 자리에
그대로 놓는다.

받는 모양은 넷이다 - 폴더, 파일 여러 개, ZIP, 그리고 그것들이 섞인
목록. 화면에서 어떻게 고르든(폴더 선택/드래그/ZIP 업로드) 결국
경로이거나 경로의 목록이라서, 여기서는 그 둘만 알면 된다.

출력은 step02가 만드는 것과 같은 모양이다.

    파일        {project}/images/scene{N}.png
    scene 키    asset_path / asset_type / provider / confidence

같게 만드는 이유가 있다. 다르면 뒤 단계가 "이건 어디서 온 이미지지"를
알아야 하고, 그 순간 이미지가 오는 길이 둘이 된다. 이 저장소에서
한 슬롯을 두 곳에서 쓰는 구조는 이미 여러 번 사고를 냈다.

확장자는 png/jpg/jpeg/webp를 받되 놓을 때는 전부 scene{N}.png 이름을
쓴다 - 엔진이 그 이름만 찾기 때문이다. 파일 내용은 바꾸지 않는다.
변환하지 않고 복사만 한다.

scene 수와 이미지 수가 맞지 않으면 경고한다. 고쳐 주지 않는다 -
없는 이미지를 지어낼 수 없고, 남는 이미지를 조용히 버리면 사용자가
준 것이 사라진다.
"""

import os
import shutil
import zipfile

from app.production import source_modes, stages
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    StageProvider,
)

IMAGE_IMPORT = "image_import"

# 받아 주는 확장자. 엔진이 실제로 읽을 수 있는 것들이다.
SUPPORTED_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

# 엔진이 찾는 이름. asset_integration_service가 scene{N}.png로 만든다.
IMAGES_DIRNAME = "images"
SCENE_FILENAME = "scene{number}.png"

# step02가 스톡/AI에 매기는 값과 같은 자리다. 사용자가 직접 고른
# 이미지는 그 scene을 위해 뽑힌 것이므로 AI Image와 같은 1.0으로 둔다 -
# 스톡의 0.8은 "검색으로 찾은 것"이라는 뜻이라 여기에 맞지 않는다.
CONFIDENCE = 1.0


class ImageImportError(ValueError):
    """준 이미지를 쓸 수 없다.

    무엇이 왜 안 되는지 적는다 - 사람이 고쳐서 다시 넣을 수 있어야
    한다."""


def _is_supported(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in SUPPORTED_SUFFIXES


def _sort_key(path: str):
    """번호 순서로 세운다.

    파일 이름이 순서다 - 사람이 0001, 0002로 적었으면 그 순서고,
    2와 10이 섞여 있으면 2가 먼저다(문자열로 세면 10이 앞선다)."""

    stem = os.path.splitext(os.path.basename(path))[0]
    digits = "".join(ch for ch in stem if ch.isdigit())

    return (0, int(digits)) if digits else (1, stem.lower())


def _from_directory(path: str) -> list:
    found = [
        os.path.join(path, name)
        for name in os.listdir(path)
        if _is_supported(name)
    ]

    return sorted(found, key=_sort_key)


def _from_zip(path: str, workspace: str) -> list:
    extracted = []

    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or not _is_supported(info.filename):
                continue
            # 압축 안의 경로는 버리고 이름만 쓴다 - 압축 파일이
            # 바깥 경로를 가리키는 것을 막는다.
            name = os.path.basename(info.filename)
            target = os.path.join(workspace, name)
            with archive.open(info) as source, open(target, "wb") as out:
                shutil.copyfileobj(source, out)
            extracted.append(target)

    return sorted(extracted, key=_sort_key)


def _collect(payload, workspace: str) -> list:
    """준 것을 파일 목록으로 편다. 목록의 순서는 지킨다."""

    if payload is None:
        raise ImageImportError("이미지를 받지 못했습니다.")

    entries = payload if isinstance(payload, (list, tuple)) else [payload]
    collected = []

    for entry in entries:
        path = str(entry)

        if not os.path.exists(path):
            raise ImageImportError(f"찾을 수 없는 경로입니다: {path}")

        if os.path.isdir(path):
            collected.extend(_from_directory(path))
        elif zipfile.is_zipfile(path):
            collected.extend(_from_zip(path, workspace))
        elif _is_supported(path):
            collected.append(path)
        else:
            suffix = os.path.splitext(path)[1] or "(확장자 없음)"
            raise ImageImportError(
                f"지원하지 않는 형식입니다: {suffix}. "
                f"{', '.join(SUPPORTED_SUFFIXES)}만 받습니다."
            )

    if not collected:
        raise ImageImportError(
            "이미지를 하나도 찾지 못했습니다. "
            f"{', '.join(SUPPORTED_SUFFIXES)} 파일이 있어야 합니다."
        )

    return collected


def _warnings(scene_count: int, image_count: int) -> list:
    if scene_count == image_count:
        return []

    if image_count < scene_count:
        missing = list(range(image_count + 1, scene_count + 1))
        return [
            f"Scene {scene_count}개, 이미지 {image_count}개 - "
            f"Scene {', '.join(str(n) for n in missing)}의 이미지가 없습니다."
        ]

    return [
        f"Scene {scene_count}개, 이미지 {image_count}개 - "
        f"뒤쪽 {image_count - scene_count}장은 쓰이지 않습니다."
    ]


class ImageImportProvider(StageProvider):
    """사용자가 준 이미지를 받는다. 만들지 않는다."""

    def __init__(self):
        self.capabilities = ProviderCapabilities(
            name=IMAGE_IMPORT,
            stage=stages.IMAGE,
            quality_tier=STANDARD,
            # GENERATE가 없다. AI 이미지를 만들지 않는다.
            supported_source_modes=(source_modes.IMPORT, source_modes.MANUAL),
            description=(
                "직접 만든 이미지를 씁니다. 폴더·여러 파일·ZIP을 받고 "
                "API를 호출하지 않습니다."
            ),
        )

    def import_content(self, raw, request=None):
        self._require(source_modes.IMPORT)

        return self._place(raw, request)

    def accept_manual(self, payload, request=None):
        self._require(source_modes.MANUAL)

        return self._place(payload, request)

    def _place(self, payload, request) -> dict:
        """
        준 이미지를 엔진이 쓰는 자리에 놓는다.

        원본은 손대지 않는다 - 복사만 하고 변환하지 않는다.
        """

        if request is None:
            raise ValueError("이 단계에 필요한 값이 없습니다: ['project_path', 'scenes']")

        request.require("project_path", "scenes")

        project_path = request.project_path
        scenes = request.scenes

        images_dir = os.path.join(project_path, IMAGES_DIRNAME)

        # 압축을 푸는 자리. 실패하면 아무것도 남기지 않으려고 먼저
        # 전부 모은 뒤에 옮긴다.
        workspace = os.path.join(images_dir, "_import")
        os.makedirs(workspace, exist_ok=True)

        try:
            collected = _collect(payload, workspace)

            placed = []
            for index, scene in enumerate(scenes):
                if index >= len(collected):
                    break

                number = scene.get("scene", index + 1)
                target = os.path.join(
                    images_dir, SCENE_FILENAME.format(number=number),
                )
                shutil.copyfile(collected[index], target)

                enriched = dict(scene)
                enriched["provider"] = IMAGE_IMPORT
                enriched["asset_type"] = "image"
                enriched["asset_path"] = target
                enriched["confidence"] = CONFIDENCE
                enriched["source"] = collected[index]
                placed.append(enriched)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

        return {
            "scenes": placed,
            "scene_count": len(scenes),
            "image_count": len(collected),
            "warnings": _warnings(len(scenes), len(collected)),
        }
