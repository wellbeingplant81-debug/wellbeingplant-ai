"""
Sprint121 - 승인 기반 제작 (Epic 55, Phase 1).

한 번에 만들지 않는다. AI가 한 단계를 만들고, 사람이 보고 고치고
승인하면 다음 단계로 간다.

이것이 가능한 이유는 Resolver가 이미 그 모양이기 때문이다
(Sprint106·111·113). 산출물이 디스크에 있으면 그 단계는 건너뛴다.
그래서 "승인"이란 곧 산출물을 남기는 일이고, 마지막 Render는
run_pipeline을 그대로 부르면 01·02·03이 저절로 건너뛰어진다.

    STEP1 승인   script.json 확정      step01 Resolver가 IMPORT로 읽는다
    STEP2 승인   images/ 확정          step02 Resolver가 IMPORT로 읽는다
    STEP3 승인   audio/scenes/ 확정    step03 Resolver가 조립만 한다
    STEP4        run_pipeline          04~07만 실제로 돈다

그래서 새 상태 파일을 만들지 않는다. 어디까지 왔는지는 디스크가
말한다 - Sprint84가 "사람이 내린 결정만 저장하고 나머지는 산출물에서
읽는다"로 정한 것과 같은 원칙이다.

여기에 새 엔진은 없다. 부르는 것은 전부 이미 있는 것들이다.

    대본       step01_script.run
    대본 검증  step01_script_resolve.validate
    이미지     step02_assets.collect_assets
    음성       scene_tts_service.create_scene_tts
    음성 한 개 tts_provider.generate_voice
    최종       studio_jobs.start  (생성 버튼이 쓰는 그 경로)

Scene 하나만 다시 만드는 두 자리가 서로 다른 함수를 쓰는 이유가 있다.
collect_assets는 파일명을 scene["scene"]으로 정해서 한 개만 넘겨도
그 scene을 고친다. 반면 create_scene_tts는 목록의 순서로 파일명을
정하므로(enumerate start=1) 한 개만 넘기면 scene1.wav를 덮어쓴다 -
그래서 음성은 그 아래의 generate_voice를 직접 부른다.

전부 다시 만드는 버튼은 두지 않는다. 사람이 승인한 것을 우리가 지우는
일이 없어야 한다.
"""

import json
import os

from app.providers.tts_provider import generate_voice
from app.services import audio_policy
from app.steps import step01_script_resolve

SCRIPT = "script"
IMAGE = "image"
VOICE = "voice"
VIDEO = "video"
DONE = "done"

STEPS = (SCRIPT, IMAGE, VOICE, VIDEO)

LABELS = {
    SCRIPT: "대본",
    IMAGE: "이미지",
    VOICE: "음성",
    VIDEO: "영상",
}

SCRIPT_FILENAME = "script.json"
IMAGES_DIRNAME = "images"
AUDIO_DIRNAME = "audio"
SCENES_DIRNAME = "scenes"
FINAL_VIDEO = os.path.join("video", "final_short.mp4")


class ReviewError(ValueError):
    """이 단계로 갈 수 없다.

    무엇이 왜 안 되는지 적는다 - 사람이 고쳐서 다시 할 수 있어야
    한다."""


def _script_path(project_path):
    return os.path.join(project_path, SCRIPT_FILENAME)


def _image_path(project_path, number):
    return os.path.join(project_path, IMAGES_DIRNAME, f"scene{number}.png")


def _voice_path(project_path, number):
    return os.path.join(
        project_path, AUDIO_DIRNAME, SCENES_DIRNAME,
        audio_policy.scene_audio_filename(number),
    )


def _load_script(project_path):
    path = _script_path(project_path)

    if not os.path.exists(path):
        raise ReviewError(
            "아직 대본이 없습니다. 대본을 먼저 만들거나 넣어 주십시오."
        )

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        raise ReviewError(f"대본을 읽을 수 없습니다: {exc}") from exc


def _scene_numbers(data):
    return [
        scene.get("scene", index + 1)
        for index, scene in enumerate(data.get("scenes") or [])
    ]


def state(project_path):
    """
    어디까지 왔는가. 순수 읽기다 - 아무것도 쓰지 않는다.

    한 단계가 끝났다는 것은 그 단계의 산출물이 전부 있다는 뜻이다.
    일부만 있으면 아직 그 단계다.
    """

    has_script = os.path.exists(_script_path(project_path))
    scenes = []
    numbers = []
    data = {}

    if has_script:
        try:
            data = _load_script(project_path)
        except ReviewError:
            has_script = False
            data = {}
        numbers = _scene_numbers(data)
        scenes = [
            {
                "scene": number,
                "narration": (data["scenes"][index].get("narration") or ""),
                "image_prompt": (
                    data["scenes"][index].get("image_prompt") or ""
                ),
                "has_image": os.path.exists(_image_path(project_path, number)),
                "has_voice": os.path.exists(_voice_path(project_path, number)),
            }
            for index, number in enumerate(numbers)
        ]

    done = {
        SCRIPT: has_script,
        IMAGE: bool(scenes) and all(s["has_image"] for s in scenes),
        VOICE: bool(scenes) and all(s["has_voice"] for s in scenes),
        VIDEO: os.path.exists(os.path.join(project_path, FINAL_VIDEO)),
    }

    step = DONE
    for name in STEPS:
        if not done[name]:
            step = name
            break

    return {
        "step": step,
        "label": LABELS.get(step, "완료"),
        # 화면이 대본을 저장할 때 제목을 그대로 돌려보내야 한다 -
        # 안 주면 사람이 쓴 제목이 저장에서 사라진다.
        "title": data.get("title") or "",
        "index": (STEPS.index(step) + 1) if step in STEPS else len(STEPS),
        "total": len(STEPS),
        "done": done,
        "scenes": scenes,
    }


def generate_script(topic, project_path):
    """STEP1. 기존 Writer를 그대로 부른다 - script.json도 그것이 쓴다."""

    # 늦게 부른다. 검토 화면을 여는 것만으로 Writer 쪽 무거운 것들을
    # 들이지 않는다.
    from app.steps import step01_script

    return step01_script.run(topic, project_path)


def save_script(project_path, data):
    """
    사람이 고친 대본을 저장한다. 우리가 다시 만들지 않는다.

    검증은 Sprint106 Resolver의 것을 그대로 쓴다 - 뒤 단계가 실제로
    꺼내는 값만 본다. 여기서 새 규칙을 만들면 화면이 통과시킨 대본이
    파이프라인에서 걸리는 날이 온다.
    """

    try:
        validated = step01_script_resolve.validate(data)
    except step01_script_resolve.ScriptResolveError as exc:
        raise ReviewError(str(exc)) from exc

    with open(_script_path(project_path), "w", encoding="utf-8") as f:
        json.dump(validated, f, ensure_ascii=False, indent=4)

    return validated


def _scene_for(project_path, scene_number):
    data = _load_script(project_path)

    for index, number in enumerate(_scene_numbers(data)):
        if number == scene_number:
            return data["scenes"][index]

    raise ReviewError(
        f"그런 Scene이 없습니다: {scene_number}. "
        f"대본에 있는 것은 {_scene_numbers(data)}입니다."
    )


def generate_images(project_path, channel):
    """STEP2. 확정된 대본으로 엔진을 부른다."""

    from app.steps import step02_assets

    data = _load_script(project_path)

    return step02_assets.collect_assets(
        data["scenes"], project_path, channel,
    )


def regenerate_image(project_path, channel, scene_number):
    """
    Scene 하나만 다시 만든다.

    collect_assets는 파일명을 scene["scene"]으로 정하므로 한 개만
    넘기면 그 scene만 바뀐다. 나머지 파일은 손대지 않는다.
    """

    from app.steps import step02_assets

    scene = _scene_for(project_path, scene_number)

    return step02_assets.collect_assets([scene], project_path, channel)


def generate_voices(project_path):
    """STEP3. 확정된 대본으로 scene별 나레이션을 만든다."""

    from app.services import scene_tts_service

    data = _load_script(project_path)

    return scene_tts_service.create_scene_tts(data["scenes"], project_path)


def regenerate_voice(project_path, scene_number):
    """
    Scene 하나만 다시 만든다.

    create_scene_tts를 쓰지 않는 이유가 있다 - 그것은 목록의 순서로
    파일명을 정해서(enumerate start=1) 한 개만 넘기면 scene1.wav를
    덮어쓴다. 그 아래의 generate_voice를 직접 불러 제 자리에 쓴다.
    """

    scene = _scene_for(project_path, scene_number)
    target = _voice_path(project_path, scene_number)

    os.makedirs(os.path.dirname(target), exist_ok=True)
    generate_voice(scene.get("narration") or "", target)

    return target


def render(topic, project_id, channel):
    """
    STEP4. 생성 버튼이 쓰는 그 경로를 그대로 쓴다.

    새 Render를 만들지 않는다. run_pipeline이 돌면 Resolver들이 이미
    확정된 대본·이미지·음성을 보고 01·02·03을 건너뛰고, 04~07만
    실제로 돈다.
    """

    from app.services import studio_jobs

    return studio_jobs.start(topic, channel, project_id)
