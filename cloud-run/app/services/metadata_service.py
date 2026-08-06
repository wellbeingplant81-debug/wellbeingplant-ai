"""
Sprint93 - Metadata Intelligence Foundation (Epic 47).

Script만을 입력으로 YouTube 업로드 메타데이터를 조립한다. OneDrive
저장소의 metadata_service(Epic 17)와 같은 자리이고, 같은 원칙을 그대로
따른다 - "Metadata는 Script만을 입력으로 생성한다".

원본과 다른 곳이 하나 있고, 그것이 이 모듈에서 가장 중요한 결정이다.

제목을 새로 만들지 않는다.

원본은 title_generator(Gemini 1회 호출)로 제목을 따로 만든다. 여기서는
script.json에 이미 있는 제목을 그대로 쓴다.

이유는 비용이 아니라 정합성이다. 이 저장소의 파이프라인은 step01이
만든 제목을 기준으로 영상을 만들고, step06이 그 제목으로 썸네일 문구를
잡는다. 여기서 제목을 또 만들면 한 영상에 제목이 둘이 된다 - 썸네일에
쓰인 문장과 YouTube에 올라가는 제목이 다른 영상이 나온다. 한 슬롯을
두 곳에서 쓰는 구조는 이 저장소에서 이미 여러 번 사고를 냈다.

"Topic을 벗어나지 않는다"는 요구에도 이쪽이 맞다 - 대본을 쓴 모델이
정한 제목이 대본에서 가장 멀지 않다.

Gemini/Imagen을 한 번도 부르지 않는다. 해시태그는 대본 텍스트의 빈도
기반 추출이고, 설명은 고정 템플릿 조립이며, 카테고리/언어/공개상태는
정책 표에서, Playlist는 주제의 규칙 기반 분류에서 온다.
"""

import json
import os
from typing import Optional

from app import config
from app.models.metadata import Metadata
from app.services import (
    description_generator,
    hashtag_generator,
    metadata_strategy_service,
    playlist_recommendation_service,
    publish_package_service,
)

PACKAGE_FILENAME = "publish_package.json"


def build_metadata(script_data: dict) -> Metadata:
    """Script만 보고 만든다. 제목은 이미 있는 것을 쓴다."""

    title = script_data.get("title") or ""
    hashtags = hashtag_generator.generate_hashtags(script_data)
    keywords = hashtag_generator.extract_keywords(script_data)[
        : config.HASHTAG_MAX_COUNT
    ]
    description = description_generator.generate_description(script_data, hashtags)

    return Metadata(
        title=title,
        subtitle=None,
        description=description,
        hashtags=hashtags,
        category=config.DEFAULT_CATEGORY,
        keywords=keywords,
        thumbnail_text=title,
        warnings=config.MEDICAL_DISCLAIMER_TEXT,
    )


def build_package(
    script_data: dict,
    topic: str,
    duration: Optional[float] = None,
) -> dict:
    """
    업로드가 읽을 모양으로 조립한다.

    publish_package_service(무수정 이식)가 metadata_strategy와
    playlist_recommendation을 받아 category_id/language/privacy_status/
    playlist_title 키를 붙인다 - 그 키 이름들은 이미 Sprint89의
    YouTubeUploadProvider가 찾고 있는 이름과 같다.
    """

    metadata = build_metadata(script_data)
    strategy = metadata_strategy_service.get_metadata_strategy()
    playlist = playlist_recommendation_service.recommend_playlist(topic or "")
    tags = hashtag_generator.generate_seo_keywords(script_data)

    return publish_package_service.build_publish_package(
        metadata,
        duration=duration,
        tags=tags,
        metadata_strategy=strategy,
        playlist_recommendation=playlist,
    )


def _load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _measured_duration(project_path: str) -> Optional[float]:
    """실제로 렌더된 길이. 원본은 이 단계가 렌더보다 앞이라 추정치를
    썼지만, 여기서는 파이프라인 끝에서 도니 측정값이 있다."""

    report = _load(os.path.join(project_path, "quality_report.json")) or {}
    checks = (report.get("technical_validation") or {}).get("checks") or {}

    return (checks.get("video_duration") or {}).get("duration_seconds")


def generate_publish_package(project_path: str) -> Optional[dict]:
    """
    프로젝트의 산출물을 읽어 publish_package.json을 남긴다.

    script.json이 없으면 아무것도 하지 않는다 - 만들 재료가 없는데
    빈 껍데기를 남기면 업로드가 그것을 진짜 메타데이터로 읽는다.
    """

    script_data = _load(os.path.join(project_path, "script.json"))

    if not isinstance(script_data, dict) or not script_data.get("title"):
        return None

    meta = _load(os.path.join(project_path, "project.json")) or {}

    package = build_package(
        script_data,
        meta.get("topic") or script_data.get("title") or "",
        duration=_measured_duration(project_path),
    )

    from app.utils.atomic_write import atomic_write_json

    atomic_write_json(os.path.join(project_path, PACKAGE_FILENAME), package)

    return package
