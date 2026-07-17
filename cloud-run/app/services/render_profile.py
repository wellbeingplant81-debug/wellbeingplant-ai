"""
Sprint122 (GREEN) - Longform Production Profile Foundation.

production_profile.py(development/upload - duration_target/tts_provider/
asset_strategy 축)와 완전히 분리된 새 축이다 - 과거 3번(scene_role/
scene_shot/scene_intent, scene_planner_service.purpose) 반복된
naming-collision을 피하기 위해 별도 모듈로 둔다.

"shorts"가 기본값이고, 오늘의 하드코딩된 값(kenburns.VIDEO_WIDTH=1080/
VIDEO_HEIGHT=1920, image_service의 aspect_ratio="9:16", final_video_
service의 FontSize=18/MarginV=115)과 정확히 같다 - render_profile_name을
안 넘기는 모든 호출부가 100% 기존과 동일하게 동작하는 근거다.

longform의 subtitle_font_size/subtitle_margin_v는 이번 스프린트에서
Shorts 값을 그대로 물려받는다 - 인터페이스만 완성하고, 16:9 기준 실측
재보정(Sprint68-1과 동일한 방법론)은 Sprint123 범위다.
"""

DEFAULT_RENDER_PROFILE = "shorts"

RENDER_PROFILES = {
    "shorts": {
        "profile": "shorts",
        "width": 1080,
        "height": 1920,
        "image_aspect_ratio": "9:16",
        "thumbnail_aspect_ratio": "9:16",
        "subtitle_font_size": 18,
        "subtitle_margin_v": 115,
    },
    "longform": {
        "profile": "longform",
        "width": 1920,
        "height": 1080,
        "image_aspect_ratio": "16:9",
        "thumbnail_aspect_ratio": "16:9",
        "subtitle_font_size": 18,
        "subtitle_margin_v": 115,
    },
}


class RenderProfile:

    @staticmethod
    def get(profile_name):
        return RENDER_PROFILES.get(profile_name, RENDER_PROFILES[DEFAULT_RENDER_PROFILE])


def _is_longform(render_profile: dict = None) -> bool:
    return render_profile is not None and render_profile.get("profile") == "longform"


# Sprint123 - Production Policy: Longform 산출물은 Shorts 명칭을
# 재사용하지 않는다. render_profile이 없거나 "longform"이 아니면
# (기본값) 오늘의 하드코딩된 파일명과 100% 동일하다 - 이 세 함수를
# 쓰는 모든 호출부(video_builder/final_video_service/thumbnail_service/
# technical_validation_service/quality_service/qa_report_service)가
# render_profile=None일 때 완전히 하위 호환된다.

def silent_video_filename(render_profile: dict = None) -> str:
    return "longform.mp4" if _is_longform(render_profile) else "short.mp4"


def final_video_filename(render_profile: dict = None) -> str:
    return "final_longform.mp4" if _is_longform(render_profile) else "final_short.mp4"


def thumbnail_filename(render_profile: dict = None) -> str:
    return "thumbnail_longform.png" if _is_longform(render_profile) else "thumbnail.png"
