import json
import os
import time

from app import config
from app.services import ai_director_service
from app.services import character_consistency_engine
from app.steps import step01_script
from app.services import scene_prompt_service
from app.steps import step02_assets
from app.steps import step03_tts
from app.steps import step04_subtitle
from app.steps import step05_video
from app.steps import step06_thumbnail
from app.steps import step07_quality
from app.services import prompt_effectiveness_service
from app.services import prompt_enrichment_service
from app.services import prompt_learning_service
from app.services import prompt_optimization_service
from app.services import regeneration_service
from app.services import scene_planner_service
from app.services import visual_consistency_engine


# Sprint66 (Stage 1) - Observability와 Production의 분리.
#
# 측정 엔진(Sprint47 Effectiveness, Sprint49 Learning)은 파이프라인이
# 무엇을 만들지에 전혀 관여하지 않는다. 그런데 결과를 project_data에
# 담아 두면 _save_script()가 그것까지 script.json에 써 버려서, 플래그를
# 켜는 것만으로 생성 산출물의 바이트가 달라진다(실측 +1,277자).
#
# script.json은 "무엇을 만들었는가"만 담는다. "그게 얼마나 좋았는가"는
# MEASUREMENT_FILENAME으로 나간다. 아래 키들은 project_data 안에서만
# 살아 있고(다음 스테이지의 Optimization이 메모리로 소비한다) 디스크의
# script.json에는 절대 실리지 않는다.
#
# Sprint67 (Stage 2) - AI Director의 결정도 같은 성격이다. Director는
# scene을 바꾸지 않고 accept/review/regenerate 권고만 계산하므로,
# 그 결과 역시 생성 산출물이 아니라 관측 산출물이다(실측: 켜는 것만으로
# script.json에 755자가 붙었다).
MEASUREMENT_ONLY_KEYS = ("prompt_metrics", "director_decision")

# 이제 프롬프트 점수만 담는 파일이 아니므로 이름도 그에 맞춘다. 모든
# 참조가 이 상수를 거치므로 파급은 없다.
MEASUREMENT_FILENAME = "measurements.json"


def _save_script(project_path, data):

    script_path = os.path.join(
        project_path,
        "script.json",
    )

    payload = {
        key: value
        for key, value in data.items()
        if key not in MEASUREMENT_ONLY_KEYS
    }

    with open(
        script_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=4,
        )


def _write_measurements(project_path, measurements, learning_summary):
    """
    측정 결과를 script.json이 아닌 별도 파일로 남긴다. 순수한 관측
    산출물이므로 파이프라인의 어떤 단계도 이 파일을 읽지 않는다.

    measurements는 MEASUREMENT_ONLY_KEYS 중 이번 실행에서 실제로 채워진
    것들만 담는다 - 꺼져 있는 엔진의 키를 null로 남겨 두면 "돌았는데
    결과가 없다"와 "아예 안 돌았다"를 구분할 수 없기 때문이다.

    Sprint49 Learning은 인메모리 카운터만 갱신하고 아무것도 남기지
    않으므로, 여기서 그 스냅샷을 함께 기록해 실제로 무엇을 배웠는지
    볼 수 있게 한다. 영속화(다음 실행이 이어받는 것)는 Optimization이
    학습 결과를 실제로 소비하는 시점의 과제다 - 여기서는 관측만 한다.
    """

    path = os.path.join(project_path, MEASUREMENT_FILENAME)

    payload = dict(measurements)

    if learning_summary is not None:
        payload["learning_summary"] = learning_summary

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=4,
        )

    return path


def run_pipeline(
    topic: str,
    project_path: str,
    channel: str,
    project_creation_time: float = 0.0,
    pipeline_start: float = None,
):

    if pipeline_start is None:
        pipeline_start = time.perf_counter()

    timings = {
        "project_creation": project_creation_time,
    }

    t0 = time.perf_counter()
    data = step01_script.run(
        topic,
        project_path,
    )
    timings["script_generation"] = time.perf_counter() - t0

    if config.ENABLE_SCENE_PLANNER:
        try:
            data["scene_plan"] = scene_planner_service.plan_scenes(data)
        except Exception as exc:
            print(f"Scene planner step failed: {exc}")

    data["scenes"] = visual_consistency_engine.apply_visual_consistency(
        data["scenes"],
        channel,
    )

    pre_enrichment_scenes = data["scenes"]

    if config.ENABLE_PROMPT_ENRICHMENT and data.get("scene_plan"):
        try:
            data["scenes"] = prompt_enrichment_service.apply_prompt_enrichment(
                data["scenes"], data["scene_plan"],
            )
        except Exception as exc:
            print(f"Prompt enrichment step failed: {exc}")

    if config.ENABLE_PROMPT_EFFECTIVENESS:
        try:
            data["prompt_metrics"] = prompt_effectiveness_service.evaluate_scenes(
                pre_enrichment_scenes, data["scenes"], data.get("scene_plan"),
            )
        except Exception as exc:
            print(f"Prompt effectiveness step failed: {exc}")

    pre_optimization_scenes = data["scenes"]
    optimized_scene_ids = set()

    if config.ENABLE_PROMPT_OPTIMIZATION and data.get("prompt_metrics"):
        try:
            data["scenes"] = prompt_optimization_service.optimize_scenes(
                pre_enrichment_scenes,
                data["scenes"],
                data["prompt_metrics"],
                data.get("scene_plan"),
            )
            before_prompt_by_scene = {
                scene.get("scene"): scene.get("image_prompt")
                for scene in pre_optimization_scenes
            }
            optimized_scene_ids = {
                scene.get("scene")
                for scene in data["scenes"]
                if before_prompt_by_scene.get(scene.get("scene")) != scene.get("image_prompt")
            }
        except Exception as exc:
            print(f"Prompt optimization step failed: {exc}")

    if config.ENABLE_PROMPT_LEARNING and data.get("prompt_metrics"):
        try:
            prompt_learning_service.learn_from_scenes(
                data["scenes"], data.get("scene_plan"), data["prompt_metrics"],
            )
        except Exception as exc:
            print(f"Prompt learning step failed: {exc}")

    if config.ENABLE_AI_DIRECTOR:
        try:
            best_pattern = (
                prompt_learning_service.get_best_pattern()
                if config.ENABLE_PROMPT_LEARNING else None
            )
            data["director_decision"] = ai_director_service.evaluate_scenes(
                data["scenes"],
                data.get("scene_plan"),
                data.get("prompt_metrics"),
                data.get("asset_quality_results"),
                best_pattern,
                optimized_scene_ids,
            )
        except Exception as exc:
            print(f"AI director step failed: {exc}")

    # Sprint66 (Stage 1) / Sprint67 (Stage 2) - 관측 산출물을 남긴다.
    #
    # 반드시 관측 엔진들이 전부 끝난 뒤여야 한다. Stage 1에서는 이
    # 블록이 Director보다 앞에 있어서, Director를 켜면 결정이 파일에는
    # 안 남고 script.json에만 실렸다.
    #
    # 이 블록은 Observability Layer이며 Production Pipeline과 분리되어
    # 있다 - 여기서 무슨 예외가 나든(디스크 오류 포함) 영상 생성은
    # 그대로 계속되어야 한다.
    measurements = {
        key: data[key]
        for key in MEASUREMENT_ONLY_KEYS
        if data.get(key)
    }

    if measurements:
        try:
            _write_measurements(
                project_path,
                measurements,
                (
                    prompt_learning_service.get_learning_summary()
                    if config.ENABLE_PROMPT_LEARNING else None
                ),
            )
        except Exception as exc:
            print(f"Measurement recording failed: {exc}")

    # Sprint60 - Smart Visual Selection v1: 최종 image_prompt(enrichment/
    # optimization까지 다 반영된 뒤)를 기준으로 scene마다 real/ai를
    # 정한다. scene_plan(ENABLE_SCENE_PLANNER) 오버레이와 달리 항상
    # 실행된다 - asset 선택에 직접 쓰이는 필수 분기이기 때문이다.
    data["scenes"] = scene_planner_service.apply_visual_type(
        data["scenes"],
    )

    # Sprint71 - Character Consistency v1. Writer가 한 인물만 쓰도록
    # 이미 지시받았더라도, 그 인물이 나오는 scene이 Pexels로 가면
    # 매번 다른 실제 사람이 나온다. 인물 scene만 Imagen 쪽으로 돌린다 -
    # image_prompt는 건드리지 않는다(대본이 적어 둔 인물 묘사와
    # 어긋나면 안 된다).
    if config.ENABLE_CHARACTER_CONSISTENCY:
        try:
            data["scenes"] = character_consistency_engine.apply_character_routing(
                data["scenes"],
            )
        except Exception as exc:
            print(f"Character consistency step failed: {exc}")

    # Sprint75 - 인물 앵커를 인물 scene에 싣는다. character_scene 표시가
    # 붙은 뒤여야 하므로 라우팅 다음이다.
    #
    # 앵커는 대본 최상위 character 한 곳에서 온다. Scene마다 외형을
    # 다시 쓰게 하면 Writer가 조금씩 다르게 쓰고, 그때부터 얼굴이
    # 갈라진다 - 실측에서 character_consistency가 40까지 떨어졌다.
    data["scenes"] = scene_prompt_service.attach_character_reference(
        data["scenes"], data.get("character"),
    )

    t0 = time.perf_counter()
    data["scenes"] = step02_assets.collect_assets(
        data["scenes"],
        project_path,
        channel,
    )
    _save_script(project_path, data)
    timings["image_generation"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    step03_tts.run(
        data["scenes"],
        project_path,
    )
    timings["tts_generation"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    step04_subtitle.run(
        project_path,
    )
    timings["subtitle_generation"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    step05_video.run(
        project_path,
    )
    timings["video_rendering"] = time.perf_counter() - t0

    scene1 = data["scenes"][0]

    t0 = time.perf_counter()
    step06_thumbnail.run(
        data["title"],
        topic,
        project_path,
        channel,
        scene1["narration"],
        scene1["image_prompt"],
        # Sprint75 - 썸네일도 같은 인물이어야 한다. scene 1의 subject는
        # 이제 짧아서("the same man") 외형 묘사가 들어 있지 않다.
        character_reference=scene1.get(
            scene_prompt_service.CHARACTER_REFERENCE_FIELD, "",
        ),
    )
    timings["thumbnail_generation"] = time.perf_counter() - t0

    try:
        step07_quality.run(
            project_path,
            data,
            timings,
            pipeline_start,
        )
    except Exception as exc:
        print(f"Quality evaluation step failed: {exc}")
    else:
        try:
            regeneration_service.run(project_path)
        except Exception as exc:
            print(f"Regeneration step failed: {exc}")

    return data
