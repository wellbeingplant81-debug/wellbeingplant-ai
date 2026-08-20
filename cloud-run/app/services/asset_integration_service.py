import importlib
import os
import shutil
import subprocess

from app.services import asset_feedback_service
from app.services import media_tools
from app.services import asset_observatory
from app.services import best_of_n_service
from app.services import provider_selection
from app.services import scene_prompt_service
from app.services.asset_mode_config import get_pexels_quality_threshold
from app.services.asset_priority_classifier import effective_pexels_threshold
from app.services.asset_ranking_service import select_best_with_score
from app.services.asset_selector import download_candidate, get_candidates
from app.services import image_service
from app.services import media_policy
from app.services.character_consistency_engine import CHARACTER_SCENE_FIELD
from app.services.search_query_extractor import extract_search_query
from app.services.visual_type_classifier import VISUAL_TYPE_AI, VISUAL_TYPE_REAL


def resolve_image_style(scene: dict) -> str:
    """
    scene이 어떤 이미지 스타일로 생성되어야 하는지 정한다. 순수
    함수입니다.

    Sprint71 - provider 라우팅(visual_type)과 스타일을 갈라 놓는
    지점이다. 인물 scene은 라우팅상으로는 Imagen 우선("ai")이지만
    스타일은 의료 일러스트가 아니라 인물이어야 한다 - 두 값을 한
    필드로 쓰던 동안에는 인물 프롬프트가 해부학 단면도로 렌더됐다.

    인물 판정이 의료 판정보다 우선한다. "혈관을 든 사람"처럼 둘 다
    걸릴 수 있는 장면에서는 사람 쪽을 지키는 편이 낫다 - 인물
    일관성이 무너지면 영상 전체가 무너지지만, 배경 그림체가 조금
    달라지는 것은 그만큼 치명적이지 않다.
    """

    scene = scene or {}

    if scene.get(CHARACTER_SCENE_FIELD):
        return image_service.IMAGE_STYLE_CHARACTER

    if scene.get("visual_type") == VISUAL_TYPE_AI:
        return image_service.IMAGE_STYLE_MEDICAL

    return image_service.IMAGE_STYLE_DEFAULT


# 프롬프트로 만든 이미지들. 스톡과 confidence·outcome 판정이 다르다.
# Sprint130 FLUX, Sprint131 GPT Image. 이름 -> 이미지 한 장을 만드는
# 모듈. 부를 때 import한다 - 고르지 않은 사람이 남의 Provider까지
# 짊어질 이유가 없다.
#
# 여기 한 줄이 곧 새 Provider다. 분기를 늘리면 세 번째부터 서로
# 조금씩 다른 모양을 돌려주기 시작한다 - 이 저장소가 반복해서 겪은
# 결함이다.
SINGLE_IMAGE_PROVIDERS = {
    provider_selection.FLUX: "app.providers.flux_provider",
    provider_selection.GPT_IMAGE: "app.providers.gpt_image_provider",
    # Sprint150 - 이쪽은 만들지 않고 고른다. 다리가 보기에는 같다 -
    # 프롬프트를 받아 그 자리에 그림 파일을 놓는다.
    provider_selection.LOCAL_STOCK: "app.providers.local_stock_provider",
}

# 프롬프트로 만든 것들. 검색으로 찾은 스톡(0.8)과 confidence가 다르다.
# 표에서 끌어온다 - 새 Provider를 붙이면서 여기를 잊으면 같은 AI
# 이미지가 프로젝트마다 다른 신뢰도를 갖게 된다.
AI_SOURCES = ("ai_image",) + tuple(SINGLE_IMAGE_PROVIDERS)

# Sprint223 - 받아 온 스톡 영상이 사는 자리. 프로젝트 폴더 아래다.
#
# 산출물이 사는 video/(단수)와 한 글자 차이라는 것을 알고 둔다 - 사양이
# 정한 이름이고, 이 이름을 아는 곳은 여기와 video_builder 뿐이다.
FOOTAGE_DIRNAME = "videos"


def _ai_result(image_prompt, staging_path, channel, is_hook_scene,
               image_style=image_service.IMAGE_STYLE_DEFAULT,
               candidate_count=1, scene=None, provider=None,
               project_path=None):
    """
    Sprint74 - Imagen을 부르는 유일한 지점. Best-of-N이 여기 붙는다.

    Sprint127 - 그래서 다른 Provider가 붙는다면 여기 붙는다. 프로젝트가
    고른 이름이 여기까지 온다. 아직 붙은 것이 하나도 없으므로 current
    (=고르지 않음)가 아니면 정직하게 거절한다 - 되는 척하지 않는다.

    candidate_count가 1이면 예전과 완전히 같은 경로다 - generate_image를
    한 번 부르고 끝난다. 플래그가 꺼져 있으면 항상 1이 들어온다.

    여러 장일 때는 뽑고, 고르고, 나머지를 지운다. 고른 결과는
    selection에 담아 호출자에게 돌려준다 - 어떤 후보를 왜 골랐는지는
    scene에 남아야 하고, 그것이 이 엔진이 실제로 무엇을 했는지 확인할
    유일한 기록이다.
    """

    # 고른 것이 없으면(None) 예전 경로 그대로다.
    provider_selection.require_wired("image", provider)

    # Sprint241 - 돈이 나가는 것만 막는다.
    #
    # 이 함수가 유료 모델로 가는 유일한 지점이다(위 docstring). 세
    # 갈래가 전부 여기로 모이므로 관문도 하나면 된다.
    #
    #   visual_type 없음   스톡 실패/품질 미달 -> 여기
    #   visual_type real   스톡 실패           -> 여기
    #   visual_type ai     처음부터            -> 여기
    #
    # 그런데 이 함수는 유료 전용이 아니다. local_stock(내 PC 자료)도
    # 여기를 지나간다 - 만들지 않고 고를 뿐이라 돈이 들지 않는다.
    # 관문을 함수 입구에 두었더니 그 무료 경로까지 막혔고, "모델을
    # 부르지 않는다"를 재던 시험들이 걸렸다(실측: test_the_journey_
    # calls_no_model · test_nothing_external_was_called).
    #
    # 그래서 부르는 것이 무엇인지 보고 나서 막는다. 그 판단은
    # provider_selection.calls_api 가 이미 한다 - 여기서 다시 짓지
    # 않는다.
    #
    # 던지는 것이 곧 답이다. visual_type=ai 갈래는 이미 예외를 잡아
    # 스톡으로 이어 가고(_select_ai_first), 나머지 둘은 스톡이 이미
    # 실패한 자리라 사람이 읽을 수 있는 말로 멈춘다.
    #
    # 결제가 잠긴 채 배포된 EXE 가 Imagen 404 로 500을 내던 그 경로다.
    if provider_selection.calls_api("image", provider):
        media_policy.require_ai_allowed(media_policy.mode_for(project_path))

    if provider in SINGLE_IMAGE_PROVIDERS:
        # Sprint130, Sprint131 - 이들은 이미지 한 장을 만드는
        # Provider다. current의 Best-of-N·품질 게이트를 대신하지 않는다
        # - 그 둘은 후보를 여럿 뽑아 고르는 일이고 여기는 한 장이다.
        # 뒤 단계가 차이를 모르도록 같은 모양으로 돌려준다.
        module = importlib.import_module(SINGLE_IMAGE_PROVIDERS[provider])

        # Sprint224 - 무엇을 놓았는지까지 말할 수 있는 Provider가 있다.
        #
        # 말할 수 있는 쪽(local_stock)은 place로 부르고, 그렇지 않은
        # 쪽은 예전 부름말 그대로다 - flux·gpt_image는 한 글자도 바뀌지
        # 않는다. 셋에게 새 계약을 강요하지 않는 것이 요점이다.
        placed = (
            module.place(image_prompt, staging_path)
            if hasattr(module, "place")
            else {"path": module.generate_image(image_prompt, staging_path)}
        )

        return {
            "source": provider,
            "local_path": staging_path,
            "metadata": {"query": extract_search_query(image_prompt)},
            "candidate_count": 1,
            "selected_candidate": 0,
            "selection": None,
            # 사람의 폴더에 있는 영상에서 뽑은 그림이면 그 영상의 자리.
            # 그림을 그대로 가져온 것이면 None이다.
            "footage_source": placed.get("footage_source"),
        }

    candidate_paths = best_of_n_service.generate_candidates(
        image_prompt,
        staging_path,
        candidate_count,
        channel=channel,
        is_hook_scene=is_hook_scene,
        image_style=image_style,
        # Sprint75 - scene이 정한 슬롯을 그대로 넘긴다. 프로필은
        # 여기 비어 있는 것만 채운다.
        elements=scene_prompt_service.scene_elements(scene or {}),
    )

    winner, selection = best_of_n_service.select_best(
        candidate_paths, scene or {},
    )

    best_of_n_service.discard_losers(candidate_paths, winner)

    return {
        "source": "ai_image",
        "local_path": candidate_paths[winner],
        "metadata": {"query": extract_search_query(image_prompt)},
        "candidate_count": len(candidate_paths),
        "selected_candidate": winner,
        "selection": selection,
    }


def _select_real_first(image_prompt, staging_path, channel, is_hook_scene,
                       image_style=image_service.IMAGE_STYLE_DEFAULT,
                       scene=None, provider=None, project_path=None):
    """
    Sprint60 - visual_type == "real": Pexels(스톡) 우선, 실패 시 Imagen
    폴백. "실패"는 후보가 아예 없는 경우와, 후보는 있었지만 다운로드
    자체가 실패한 경우(네트워크 오류 등) 둘 다 포함한다.
    """

    stock_candidates = get_candidates(
        image_prompt, allow_video=True, scene=scene,
    )
    best_candidate, _ = select_best_with_score(
        stock_candidates, is_hook_scene=is_hook_scene, scene=scene,
    )

    if best_candidate is not None:
        try:
            return download_candidate(best_candidate, staging_path), False
        except Exception as exc:
            print(
                f"[AssetIntegration] visual_type=real, Pexels 다운로드 "
                f"실패, Imagen으로 폴백: {exc}"
            )

    # Sprint74 - 여기 오는 것은 Pexels가 실패한 폴백 상황이다. 후보
    # 배정(plan_candidates)은 Imagen을 먼저 보는 scene만 계산하므로,
    # 이 경로에는 예산이 잡혀 있지 않다. 한 장으로 간다.
    return (
        _ai_result(
            image_prompt, staging_path, channel, is_hook_scene, image_style,
            candidate_count=1, scene=scene, provider=provider,
            project_path=project_path,
        ),
        False,
    )


def _select_ai_first(image_prompt, staging_path, channel, is_hook_scene,
                     image_style=image_service.IMAGE_STYLE_DEFAULT,
                     candidate_count=1, scene=None, provider=None,
                     project_path=None):
    """
    Sprint60 - visual_type == "ai": Imagen 우선, 실패 시 Pexels 폴백.

    반환값: (result_dict, ai_was_deliberate_choice). ai_was_deliberate_
    choice는 Imagen이 첫 시도에서 바로 성공했는지(True) - 스톡 검색
    실패로 인한 어쩔 수 없는 폴백(False)과 구분해 feedback outcome을
    정확히 기록하기 위함이다.
    """

    try:
        return (
            _ai_result(
                image_prompt, staging_path, channel, is_hook_scene, image_style,
                candidate_count=candidate_count, scene=scene,
                provider=provider, project_path=project_path,
            ),
            True,
        )
    except Exception as exc:
        # Sprint127/130 - 폴백은 current 엔진의 성질이다(Imagen이
        # 안 되면 Pexels). 사용자가 Provider를 골랐는데 실패했다고
        # 스톡 사진을 주면 조용히 틀린 결과가 된다 - 고른 것이
        # 있으면 대체하지 않고 그대로 내보낸다.
        if provider:
            raise

        print(
            f"[AssetIntegration] visual_type=ai, Imagen 생성 실패, "
            f"Pexels로 폴백: {exc}"
        )

    stock_candidates = get_candidates(
        image_prompt, allow_video=True, scene=scene,
    )
    best_candidate, _ = select_best_with_score(
        stock_candidates, is_hook_scene=is_hook_scene, scene=scene,
    )

    if best_candidate is None:
        raise Exception(
            "visual_type=ai 폴백 실패: Imagen과 Pexels 모두 사용할 수 "
            "없습니다."
        )

    return download_candidate(best_candidate, staging_path), False


def _extract_first_frame(video_path: str, output_image_path: str) -> str:
    """
    비디오 파일의 첫 프레임을 이미지로 추출합니다. 기존
    audio_service.py/final_video_service.py와 동일하게 bare "ffmpeg"
    명령어(PATH 의존)와 subprocess.run 패턴을 사용합니다.
    """

    command = [
        media_tools.resolve(media_tools.FFMPEG),
        "-y",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_image_path,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise Exception(f"비디오 첫 프레임 추출 실패: {result.stderr}")

    return output_image_path


def _keep_footage(project_path: str, scene_number, raw_path: str) -> str:
    """
    받아 온 영상을 프로젝트에 남긴다. 남긴 자리를 돌려준다.

    Sprint223 - 왜 이 함수가 생겼는가
    ---------------------------------
    지금까지 이 저장소는 스톡 영상을 받아 첫 프레임만 뽑고 원본을
    지웠다. 이미 값을 치르고 내려받은 움직임을 매번 버린 것이다.

    이름은 videos/scene{N}.mp4 다. 사양이 정한 이름이고, video_builder 가
    scene 번호로 찾을 수 있어야 한다.

    주의 - 이 폴더는 산출물이 사는 video/(단수, short.mp4·
    final_short.mp4)와 한 글자 차이다. 둘을 섞어 읽으면 안 된다.
    """

    footage_path = _footage_path(project_path, scene_number)

    os.replace(raw_path, footage_path)

    return footage_path


def _copy_footage(project_path: str, scene_number, source_path: str) -> str:
    """
    사람의 폴더에 있는 영상을 프로젝트로 복사한다. 복사한 자리를
    돌려준다.

    Sprint224 - 왜 옮기지 않고 복사하는가
    -------------------------------------
    받아 온 영상(_keep_footage)은 우리가 방금 임시 자리에 내려놓은
    것이라 옮겨도 잃을 것이 없다. 이것은 다르다 - 사람이 제 폴더에
    모아 둔 자료이고, 다음 영상에도 쓸 것이다. 옮기면 그 폴더에서
    사라지고, 사람은 우리가 지웠다는 사실조차 모른다.

    image_import._place 가 "원본은 손대지 않는다"고 적어 둔 것과 같은
    규칙이다.

    확장자를 바꾸지 않는다
    ----------------------
    .mkv 를 받아 scene1.mp4 로 적으면 이름이 거짓말을 한다. 고른 것이
    무엇이었는지는 파일 이름이 마지막으로 남기는 단서다.
    """

    _, extension = os.path.splitext(source_path)

    footage_path = _footage_path(project_path, scene_number, extension)

    shutil.copyfile(source_path, footage_path)

    return footage_path


def _footage_path(project_path: str, scene_number, extension=".mp4") -> str:
    """영상이 놓일 자리. 폴더가 없으면 만든다."""

    where = os.path.join(project_path, FOOTAGE_DIRNAME)

    os.makedirs(where, exist_ok=True)

    return os.path.join(where, f"scene{scene_number}{extension}")


def integrate_asset(
    scene: dict,
    project_path: str,
    channel: str = "wellbeing",
    prefer_ai: bool = False,
    candidate_count: int = 1,
) -> dict:
    """
    Sprint30 - Multi-Candidate + Scoring 기반 선택.
    Sprint38 - Hybrid Asset Engine: prefer_ai 품질 게이트.
    Sprint60 - Smart Visual Selection v1: scene["visual_type"]("real"/
    "ai", visual_type_classifier.apply_visual_type()이 미리 채워둠)이
    있으면 소프트 게이트 대신 하드 분기한다 - "real"은 Pexels 우선(실패
    시 Imagen 폴백), "ai"는 Imagen 우선(실패 시 Pexels 폴백). visual_type
    이 없는 scene은 기존 prefer_ai 경로를 그대로 탄다(완전 하위 호환).

    Scene 하나에 대해 후보 자산을 모두 수집(get_candidates)하고,
    Asset Ranking Service로 최고 점수 후보를 선택한 뒤 그 결과를
    반영한 새 scene dict를 반환합니다. 입력 scene dict는 변경하지
    않습니다. 후보가 하나도 없으면(모든 provider 실패/결과 없음)
    기존 AI Image Generator로 폴백합니다.

    prefer_ai=True(인물/의료 등 정확도가 중요한 scene - 호출자가 배치
    단위로 판단해 전달)여도 Pexels/Pixabay 검색 자체는 그대로
    수행합니다 - 비용보다 품질을 우선하므로, 검색된 최고 후보의 점수가
    ASSET_MODE의 pexels_quality_threshold 이상이면 그대로 그 스톡
    자산을 채택합니다. 임계값 미만일 때만 AI로 생성합니다. prefer_ai가
    아닌 scene(기본값 False)은 기존 Sprint30 동작과 완전히 동일하게
    후보가 하나라도 있으면 그대로 채택합니다.

    AssetSelector가 비디오(asset_type == "video")를 선택한 경우,
    ffmpeg로 첫 프레임을 추출해 이미지로 저장합니다 - Video Builder는
    이 함수를 거친 뒤에는 항상 이미지 파일만 다루면 되므로 전혀
    수정할 필요가 없습니다 (Video -> frame extract -> image pipeline).

    추가/갱신되는 필드:
      - search_query: 실제 스톡 검색에 사용된 키워드
      - provider: "pexels_video" | "pexels_image" | "pixabay_video" |
        "pixabay_image" | "ai_image"
      - asset_type: "video" | "image" - 원본 자산의 실제 종류를
        그대로 기록 (비디오였다면 프레임 추출 후에도 "video"로 남음)
      - asset_path: 항상 이미지 파일 경로 (비디오였던 경우 추출된
        프레임의 경로)
      - confidence: AI Image는 프롬프트로 직접 생성되므로 1.0, 스톡
        자산은 검색 키워드 기반 매칭이라 0.8 (관련성 스코어링은 아직
        없음 - Sprint28 설계 문서에 명시된 열린 이슈)

    기존 image_prompt/narration 등 다른 필드는 그대로 보존됩니다.
    """

    scene_number = scene["scene"]
    image_prompt = scene["image_prompt"]
    is_hook_scene = (scene_number == 1)

    images_dir = os.path.join(project_path, "images")

    final_image_path = os.path.join(images_dir, f"scene{scene_number}.png")
    staging_path = os.path.join(images_dir, f"scene{scene_number}.raw")

    visual_type = scene.get("visual_type")
    image_style = resolve_image_style(scene)

    # Sprint127 - 이 프로젝트가 어느 Provider로 만들기로 했는가.
    # 환경변수를 읽지 않는다 - project_path를 이미 받고 있으므로 그
    # 프로젝트의 결정을 읽는다. 스레드가 겹쳐도 서로 섞이지 않는다.
    provider = provider_selection.selected(project_path, "image")

    if visual_type == VISUAL_TYPE_REAL:
        result, ai_priority_choice = _select_real_first(
            image_prompt, staging_path, channel, is_hook_scene, image_style,
            scene=scene, provider=provider, project_path=project_path,
        )
    elif visual_type == VISUAL_TYPE_AI:
        result, ai_priority_choice = _select_ai_first(
            image_prompt, staging_path, channel, is_hook_scene, image_style,
            candidate_count=candidate_count, scene=scene, provider=provider,
            project_path=project_path,
        )
    else:
        # Sprint38 - visual_type이 없는 scene(구버전 데이터/다른 호출부)은
        # 기존 prefer_ai 소프트 품질 게이트 경로를 그대로 유지한다.
        stock_candidates = get_candidates(
            image_prompt, allow_video=True, scene=scene,
        )
        best_candidate, best_score = select_best_with_score(
            stock_candidates, is_hook_scene=is_hook_scene, scene=scene,
        )

        ai_priority_choice = (
            prefer_ai
            and best_candidate is not None
            and best_score < effective_pexels_threshold(
                scene, get_pexels_quality_threshold(),
            )
        )

        if best_candidate is not None and not ai_priority_choice:
            result = download_candidate(best_candidate, staging_path)
        else:
            # Sprint225 - 고른 것을 여기에도 넘긴다.
            #
            # 위 두 갈래는 Sprint127부터 provider를 넘겨 왔는데 이 갈래만
            # 빠져 있었다. 그래서 visual_type이 없는 scene은 사람이 무엇을
            # 골랐든 current 엔진(Imagen)으로 갔다 - 검수 화면이 만드는
            # scene에는 visual_type이 없으므로(apply_visual_type을 부르는
            # 곳은 파이프라인 하나뿐이다) 그 화면에서 "내 PC 자료"를 고른
            # 사람이 유료 엔진을 부르고 있었다.
            #
            # 고르는 순서는 바뀌지 않는다. 스톡을 먼저 보는 것도, 품질
            # 게이트도 위 그대로다 - 달라지는 것은 "만들어야 할 때 무엇이
            # 만드는가" 하나뿐이고, 그것이 원래 이 값의 뜻이다.
            result = _ai_result(
                image_prompt, staging_path, channel, is_hook_scene, image_style,
                candidate_count=candidate_count, scene=scene,
                provider=provider, project_path=project_path,
            )

    source = result["source"]

    # 사람의 폴더에 있는 영상에서 나온 그림인가(Sprint224). 그렇다면
    # local_path 는 이미 뽑아 놓은 **그림**이고, 영상은 저 자리에 따로
    # 있다 - 받아 온 스톡 영상(local_path 가 곧 영상이다)과 반대다.
    given_footage = result.get("footage_source")

    # 이름에 video 가 든 것은 스톡에서 받은 영상이다(pexels_video ·
    # pixabay_video). 내 자료 영상은 이름이 local_stock 이라 그것으로는
    # 알 수 없고, 위의 사실이 알려 준다.
    asset_type = "video" if ("video" in source or given_footage) else "image"

    # Sprint130 - 프롬프트로 만든 것들. 스톡(검색으로 찾은 것)과
    # 구분한다. current 경로(ai_image)의 판정은 그대로다.
    generated_by_ai = source in AI_SOURCES

    footage_path = None

    if asset_type == "video" and not given_footage:
        # 받아 온 영상. local_path 가 그 영상이다.
        try:
            _extract_first_frame(result["local_path"], final_image_path)

            # Sprint223 - 그리고 원본을 남긴다. 예전에는 여기서 지웠다 -
            # 20초짜리 영상을 받아 0초 프레임 한 장만 남기고 버렸다.
            footage_path = _keep_footage(
                project_path, scene_number, result["local_path"],
            )
        finally:
            # 옮기지 못했으면(첫 프레임 추출 실패 등) 예전처럼 치운다.
            # 옮겼으면 이 자리에는 이미 아무것도 없다.
            if os.path.exists(result["local_path"]):
                os.remove(result["local_path"])
    else:
        # 그림을 놓는 길. 내 자료 영상도 여기로 온다 - Provider 가 이미
        # 첫 프레임을 뽑아 놓았기 때문이다. 이 줄은 예전 그대로다.
        os.replace(result["local_path"], final_image_path)

        if given_footage:
            # Sprint224 - 그리고 그 영상을 프로젝트로 **복사**한다.
            # 옮기면 사람의 폴더에서 사라진다.
            footage_path = _copy_footage(
                project_path, scene_number, given_footage,
            )

    confidence = 1.0 if generated_by_ai else 0.8

    if not generated_by_ai:
        outcome = "success"
    elif ai_priority_choice:
        # AI가 의도적으로 선택된 경우 - (a) 기존 prefer_ai 품질 게이트가
        # Pexels 품질 미달로 AI를 택했거나, (b) visual_type="ai" scene이
        # Imagen을 첫 시도에서 그대로 성공한 경우. 스톡 검색/다운로드
        # 자체가 실패해 어쩔 수 없이 AI로 넘어간 "fallback"과는 구분한다.
        outcome = "ai_priority"
    else:
        outcome = "fallback"

    try:
        asset_feedback_service.record(
            scene_id=scene_number,
            provider=source,
            asset_type=asset_type,
            selected_asset=final_image_path,
            outcome=outcome,
        )
    except Exception as exc:
        # Learning Layer는 optional overlay이므로, 기록 실패가 asset
        # 선택 자체를 막아서는 안 된다.
        print(f"[AssetIntegration] feedback 기록 실패(무시): {exc}")

    # Sprint77 - 이 scene이 최종적으로 무엇을 썼는지. enriched에는
    # 넣지 않는다 - script.json의 바이트가 달라지면 안 된다.
    asset_observatory.record_outcome(
        scene_number, provider=source, asset_path=final_image_path,
    )

    enriched = dict(scene)
    enriched["search_query"] = result["metadata"].get("query")
    enriched["provider"] = source
    enriched["asset_type"] = asset_type
    enriched["asset_path"] = final_image_path
    enriched["confidence"] = confidence

    # Sprint223 - 영상을 받은 scene 에만 붙는다. 그림 scene 의
    # script.json 은 한 바이트도 달라지지 않는다.
    if footage_path:
        enriched["footage_path"] = footage_path

    # Sprint74 - 후보를 여러 장 뽑은 경우에만 기록을 남긴다. 한 장이면
    # 고른 것이 없으므로 남길 결정도 없고, 예전 scene dict와 필드가
    # 완전히 같다.
    if result.get("candidate_count", 1) > 1:
        selection = result.get("selection")

        enriched["candidate_count"] = result["candidate_count"]
        enriched["selected_candidate"] = result["selected_candidate"]
        # 세 항목의 평균. 합계가 아니라 평균인 이유는 이 프로젝트의
        # 다른 점수가 전부 0-100이라 그래야 나란히 읽히기 때문이다.
        enriched["candidate_scores"] = (
            [] if selection is None else [
                round(
                    (score.prompt_fidelity + score.character_match
                     + score.composition) / 3
                )
                for score in selection.candidates
            ]
        )
        enriched["selection_reason"] = (
            None if selection is None else selection.reason
        )

    return enriched
