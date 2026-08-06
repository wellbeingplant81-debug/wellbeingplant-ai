"""
Sprint93 - Metadata Intelligence 이식 (Epic 47).

OneDrive 저장소의 app/services/playlist_recommendation_service.py
(Epic 47 Sprint005)를 가져왔다. "어떤 Playlist에 넣을지 결정"만 한다 -
Lookup/Create/Add는 이미 이식된 YouTubePlaylistService(Sprint89, 무수정)
가 하고, YouTubeUploadProvider가 metadata["playlist_title"]을 보고
알아서 부른다.

새 주제 분류기를 만들지 않는다 - TopicIntelligenceService.
build_topic_profile()의 medical_domain(규칙 기반, AI 호출 없음)을
그대로 쓴다.

원본의 build_playlist_creation_request()/select_or_create_playlist()는
가져오지 않았다. 앞의 것은 PlaylistCreationRequest 모델을 하나 더
끌고 오는데 이 저장소에서 부를 곳이 없고, 뒤의 것이 하는 일은
YouTubeUploadProvider._add_to_playlist()가 이미 하고 있다 - 같은 일을
두 군데 두지 않는다.
"""

from app.models.playlist_recommendation import PlaylistRecommendation
from app.services.topic_intelligence_service import TopicIntelligenceService

MEDICAL_DOMAIN_PLAYLIST_TITLES = {
    "metabolism": "당뇨·대사 관리",
    "cardiovascular": "혈압·혈관 건강",
    "neurology": "뇌 건강·치매 예방",
    "nutrition": "건강 식재료 정보",
    "general": "건강 정보",
}


def recommend_playlist(topic: str) -> PlaylistRecommendation:
    topic_profile = TopicIntelligenceService.build_topic_profile(topic)
    medical_domain = topic_profile.medical_domain

    playlist_title = MEDICAL_DOMAIN_PLAYLIST_TITLES.get(
        medical_domain,
        MEDICAL_DOMAIN_PLAYLIST_TITLES["general"],
    )
    reason = (
        f"주제 '{topic}'의 medical_domain='{medical_domain}' 분류에 따라 "
        f"'{playlist_title}' Playlist를 추천합니다."
    )

    return PlaylistRecommendation(playlist_title=playlist_title, reason=reason)
