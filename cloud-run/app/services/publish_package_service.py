"""
Epic 17 - Metadata Intelligence, Publish Package.

Metadata + duration(영상 길이 - 이 시점에는 TTS/Render가 아직 실행되지
않았으므로 실제 값이 아니라 duration_estimator의 추정치)을 업로드에
필요한 publish_package.json 모양(dict)으로 조립한다.

Epic 18 - Thumbnail Intelligence. thumbnail_plan(app.models.thumbnail_
plan.ThumbnailPlan)이 주어지면 thumbnail_mode/thumbnail_prompt/
render_profile 3개 키를 추가하고, thumbnail_text는 ThumbnailPlan의
값으로 덮어쓴다(Metadata의 값과 이미 같은 값이거나 Planner가 더
구체화한 값이므로 ThumbnailPlan 쪽을 우선한다). 주어지지 않으면(기본값
None) Epic 17과 100% 동일한 dict 모양을 유지한다.

Epic 19 P4 - PublishPackage를 새 Domain으로 만들지 않고 이 dict를
확장한다(사용자 확정 방향). tags가 주어지면 "tags" 키를 추가한다 -
hashtag_generator.generate_seo_keywords()가 만드는 구(phrase) 형태
키워드 자리다("keywords"는 Epic 17의 단일 토큰 추출과 구분된다).
주어지지 않으면(기본값 None) 키 자체가 생기지 않아 기존 dict 모양을
그대로 유지한다.

Epic 47 Sprint 008 - AI Metadata Engine, Pipeline Integration. 같은
확장 방식으로 metadata_strategy(Sprint006 MetadataStrategy)/
playlist_recommendation(Sprint005 PlaylistRecommendation)이 주어지면
각각의 키를 추가한다. playlist_title 키 이름은 Epic46
YouTubeUploadProvider가 이미 찾는 metadata["playlist_title"]과
의도적으로 동일하다(향후 통합을 쉽게 하기 위한 이름 정합 - 이번
Sprint에서 실제로 그 파이프라인에 연결하지는 않는다). 둘 다
주어지지 않으면(기본값 None) 기존 dict 모양을 100% 유지한다.
"""

from typing import Optional


def build_publish_package(
    metadata,
    duration: Optional[float] = None,
    thumbnail_plan=None,
    tags: Optional[list] = None,
    metadata_strategy=None,
    playlist_recommendation=None,
) -> dict:
    package = {
        "title": metadata.title,
        "subtitle": metadata.subtitle,
        "description": metadata.description,
        "hashtags": metadata.hashtags,
        "keywords": metadata.keywords,
        "category": metadata.category,
        "thumbnail_text": metadata.thumbnail_text,
        "duration": duration,
    }

    if thumbnail_plan is not None:
        package["thumbnail_mode"] = (
            thumbnail_plan.thumbnail_mode.value
            if thumbnail_plan.thumbnail_mode
            else None
        )
        package["thumbnail_text"] = thumbnail_plan.thumbnail_text
        package["thumbnail_prompt"] = thumbnail_plan.thumbnail_prompt
        package["render_profile"] = thumbnail_plan.render_profile

    if tags is not None:
        package["tags"] = tags

    if metadata_strategy is not None:
        package["category_id"] = metadata_strategy.category_id
        package["language"] = metadata_strategy.language
        package["privacy_status"] = metadata_strategy.privacy_status
        package["publish_strategy"] = metadata_strategy.publish_strategy

    if playlist_recommendation is not None:
        package["playlist_title"] = playlist_recommendation.playlist_title
        package["playlist_recommendation_reason"] = playlist_recommendation.reason

    return package
