import os

from PIL import (
    Image,
    ImageEnhance,
    ImageFilter,
)

from google import genai
from google.genai import types

from app.prompts import prompt_elements
from app.prompts import style_profiles
from app.services import prompt_composer

# Sprint71 - 이미지 스타일. provider 라우팅(visual_type: "real"/"ai")과는
# 완전히 다른 축이다.
#
# 예전에는 generate_image()가 visual_type을 읽어 스타일을 정했다. 두
# 개념이 같은 값을 공유하고 있었던 셈인데, Sprint60 시점에는 "ai"가
# 곧 "혈관/세포 주제"였으므로 우연히 맞아떨어졌다. Character
# Consistency가 인물 scene을 Imagen으로 보내면서 그 우연이 깨졌다.
IMAGE_STYLE_DEFAULT = "default"
IMAGE_STYLE_MEDICAL = "medical_illustration"
IMAGE_STYLE_CHARACTER = "character"
IMAGE_STYLE_THUMBNAIL = "thumbnail"

IMAGE_STYLES = frozenset({
    IMAGE_STYLE_DEFAULT,
    IMAGE_STYLE_MEDICAL,
    IMAGE_STYLE_CHARACTER,
    IMAGE_STYLE_THUMBNAIL,
})


client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def enhance_image(path: str):

    image = Image.open(path)

    if image.mode != "RGB":
        image = image.convert("RGB")

    image = ImageEnhance.Contrast(
        image
    ).enhance(1.10)

    image = ImageEnhance.Color(
        image
    ).enhance(1.08)

    image = ImageEnhance.Sharpness(
        image
    ).enhance(1.25)

    image = ImageEnhance.Brightness(
        image
    ).enhance(1.02)

    image = image.filter(
        ImageFilter.DETAIL
    )

    image.save(
        path,
        format="PNG",
        optimize=True,
    )


def _build_prompt(prompt: str, image_style: str, channel: str,
                  is_hook_scene: bool, elements: dict = None):
    """
    Sprint75 - 최종 프롬프트를 슬롯에서 조립한다.

    예전에는 채널 스타일 블록 하나를 scene 문장 앞에 통째로 이어붙였다.
    그 블록 안에 스타일, 인물 품질, 조명, 카메라, 구도, 부정어가 전부
    섞여 있었고 그것이 모든 scene에 붙었다 - 오트밀 그릇을 그리는
    프롬프트가 "Korean people, Natural facial expression, Realistic
    eyes"로 시작하고 "85mm portrait photography"가 뒤따랐다.

    이제 프로필은 scene이 비워 둔 슬롯만 채운다. 카메라처럼 scene이
    정한 슬롯은 프로필이 건드리지 않는다.

    elements가 없는 scene(구버전 대본)은 문장 전체를 subject 슬롯에
    넣는다. 구조는 없지만 최소한 프로필이 인물을 요구하지는 않는다.
    """

    profile = style_profiles.resolve(image_style, channel, is_hook_scene)

    scene = dict(elements or {})

    if not scene.get(prompt_elements.SUBJECT):
        scene[prompt_elements.SUBJECT] = prompt

    composed = prompt_composer.compose(
        prompt_composer.merge(profile, scene),
    )

    return composed.positive, composed.negative


def _write_generated(generated, output_file: str) -> str:
    """생성된 이미지 한 장을 파일로 쓴다."""

    if generated.image is None:
        raise Exception(
            "Image 객체가 없습니다."
        )

    if generated.image.image_bytes is None:
        raise Exception(
            "image_bytes가 없습니다."
        )

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "wb") as f:
        f.write(generated.image.image_bytes)

    enhance_image(output_file)

    print(f"Saved : {output_file}")

    return output_file


def generate_image_candidates(
    prompt: str,
    output_files: list,
    channel: str = "wellbeing",
    is_hook_scene: bool = False,
    image_style: str = IMAGE_STYLE_DEFAULT,
    elements: dict = None,
):
    """
    Sprint74 - 같은 프롬프트로 후보를 여러 장 받는다.

    Imagen은 한 요청에 여러 장을 돌려준다. generate_image를 N번 부르면
    왕복도 N번이지만, 이쪽은 한 번이다.

    요청한 것보다 적게 돌아올 수 있다(안전 필터 등). 그것은 오류가
    아니라 후보가 줄어든 것이므로, 받은 만큼만 쓰고 그만큼의 경로를
    돌려준다. 한 장도 못 받은 경우만 예외다.
    """

    final_prompt, negative_prompt = _build_prompt(
        prompt, image_style, channel, is_hook_scene, elements,
    )

    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=final_prompt,
        config=types.GenerateImagesConfig(
            aspect_ratio="9:16",
            negative_prompt=negative_prompt,
            add_watermark=False,
            number_of_images=len(output_files),
        ),
    )

    if not response.generated_images:
        raise Exception(
            "Imagen이 이미지를 생성하지 않았습니다."
        )

    return [
        _write_generated(generated, output_file)
        for generated, output_file in zip(
            response.generated_images, output_files,
        )
    ]


def generate_image(
    prompt: str,
    output_file: str,
    channel: str = "wellbeing",
    is_hook_scene: bool = False,
    image_style: str = IMAGE_STYLE_DEFAULT,
    elements: dict = None,
):

    final_prompt, negative_prompt = _build_prompt(
        prompt, image_style, channel, is_hook_scene, elements,
    )

    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=final_prompt,
        config=types.GenerateImagesConfig(
            aspect_ratio="9:16",
            negative_prompt=negative_prompt,
            add_watermark=False,
            # Sprint74 - 이 줄이 없던 동안 Vertex는 자기 기본값인 4장을
            # 만들었고, 아래에서 [0]만 저장했다. 나머지 세 장은 요금이
            # 청구된 뒤 그대로 버려졌다.
            #
            # 여러 장이 필요하면 generate_image_candidates를 쓴다.
            # 이 함수는 한 장을 쓰므로 한 장만 요청한다.
            number_of_images=1,
        ),
    )

    if not response.generated_images:
        raise Exception(
            "Imagen이 이미지를 생성하지 않았습니다."
        )

    generated = response.generated_images[0]

    if generated.image is None:
        raise Exception(
            "Image 객체가 없습니다."
        )

    if generated.image.image_bytes is None:
        raise Exception(
            "image_bytes가 없습니다."
        )

    os.makedirs(
        os.path.dirname(output_file),
        exist_ok=True,
    )

    with open(
        output_file,
        "wb",
    ) as f:

        f.write(
            generated.image.image_bytes
        )

    enhance_image(
        output_file
    )

    print(
        f"Saved : {output_file}"
    )

    return output_file