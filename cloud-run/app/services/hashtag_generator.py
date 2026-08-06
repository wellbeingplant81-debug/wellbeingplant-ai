"""
Epic 17 - Metadata Intelligence, Hashtag Generator.

Gemini를 호출하지 않는다.

Sprint94 - 위에 적혀 있던 "조사가 붙은 형태 그대로 남는 것은 알려진
한계다"는 더 이상 사실이 아니다. 빈도순 토큰 나열과 불용어 12개로는
#그냥 #방금 #손에 #들다가 를 막지 못했고(Sprint93 실측), 그것이 실제
채널 설명란에 나갔다.

이제 추출은 korean_noun_filter가 한다 - 조사가 붙어 나타난 적이
있는지를 명사의 증거로 삼는 규칙 기반 판정이다. 이 파일은 그 결과를
해시태그/SEO 키워드 모양으로 담는 일만 한다.

Epic 19 P4 - generate_seo_keywords()를 이 파일에 추가한다(별도 모듈로
중복 구현하지 않는다 - extract_keywords()를 그대로 재사용).

Epic 47 Sprint 004 - AI Metadata Engine, Hashtag Engine 품질 개선(사용자
확정 방향 - 새 Generator를 만들지 않는다). 위 문서화된 한계("간은" 같은
조사 부착형)를 새 선택 파라미터 merge_similar_forms(기본 False)로
additive하게 개선한다 - 새 형태소 분석기를 만들지 않고 Epic 43의
morphological_normalization_service.extract_stem()(이미 검증된 규칙
기반 어간 추출, 무수정)을 재사용해 "혈압이"/"혈압을"/"혈압은"처럼 조사만
다른 변형을 하나의 어간으로 묶는다 - 근접 중복 해시태그를 줄인다.
기본값 False면 100% 기존과 동일하다(Regression Zero).
"""

import re
from typing import Dict, Optional

from app import config
from app.services import korean_noun_filter
from app.services.morphological_normalization_service import extract_stem

STOPWORDS = {
    "합니다",
    "습니다",
    "됩니다",
    "있습니다",
    "해보세요",
    "됩니다",
    "중요합니다",
    "좋습니다",
    "필요합니다",
    "때문에",
    "위해서",
    "그리고",
}

TOKEN_PATTERN = re.compile(r"[가-힣]{2,}")


def _identity(token: str) -> str:
    return token


def extract_keywords(script_data: dict, merge_similar_forms: bool = False,
                     topic: str = None) -> list:
    """
    Sprint94 - 명사만 돌려준다.

    이 함수는 원래 2글자 이상 한글 토큰을 전부 빈도순으로 돌려줬다.
    그래서 #그냥 #방금 #손에 #들다가 가 해시태그로 나갔다(Sprint93
    실측). 불용어 12개로는 조사 부착형도 활용형도 걸러지지 않는다.

    판정은 korean_noun_filter가 한다 - 조사가 붙어 나타난 적이 있는지를
    명사의 증거로 쓰는 규칙 기반 추출이다. AI를 부르지 않는다.

    호출 형태와 반환 모양은 그대로다 - generate_hashtags()도
    generate_seo_keywords()도 이 함수만 보고 있어서, 여기 하나로 셋이
    같이 좋아진다.
    """

    nouns = korean_noun_filter.extract_nouns_from_script(script_data, topic)

    if not merge_similar_forms:
        return nouns

    # 조사만 다른 변형을 어간으로 묶는다. 명사 추출이 이미 조사를
    # 떼므로 남는 것은 "혈관/혈관들"류의 차이뿐이다.
    merged = []
    seen = set()
    for noun in nouns:
        key = extract_stem(noun)
        if key in seen:
            continue
        seen.add(key)
        merged.append(noun)

    return merged


def generate_hashtags(
    script_data: dict,
    min_count: Optional[int] = None,
    max_count: Optional[int] = None,
    merge_similar_forms: bool = False,
    topic: str = None,
) -> list:
    min_count = min_count if min_count is not None else config.HASHTAG_MIN_COUNT
    max_count = max_count if max_count is not None else config.HASHTAG_MAX_COUNT

    keywords = extract_keywords(
        script_data, merge_similar_forms=merge_similar_forms, topic=topic,
    )[:max_count]

    # Sprint94 - 모자랄 때 제목을 통째로 붙이지 않는다.
    #
    # 원본은 min_count를 못 채우면 script_data["title"]을 그대로 태그로
    # 넣었다. 짧은 주제어를 전제한 규칙인데, 이 저장소의 제목은 한
    # 문장짜리 후킹 문구라 "#이 증상, 그냥 넘기면 평생 후회합니다..."가
    # 나간다. 제목의 명사는 이미 extract_keywords()가 뽑아 오므로 이
    # 폴백은 값을 더하지도 않는다.
    #
    # 명사가 모자라면 모자란 채로 둔다 - 해시태그는 빠지는 것보다
    # 이상한 것이 나가는 쪽이 나쁘다.
    return [f"#{keyword}" for keyword in keywords]


def generate_seo_keywords(
    script_data: dict, min_count: Optional[int] = None,
    max_count: Optional[int] = None, topic: str = None,
) -> list:
    """
    Epic 19 P4 - SEO Keyword Generator. Hashtag(단일 토큰, # 접두어)와
    구분되는 검색 친화적 "구(phrase)" 형태의 키워드를 만든다 - 실제
    형태소 분석/구 추출이 아니라, topic 자체 + 빈도 상위 단일 토큰(기존
    extract_keywords() 재사용) + topic과 단일 토큰을 결합한 구(phrase)
    를 조합하는 규칙 기반 근사치다(예: "혈압" + "관리" -> "혈압 관리").
    """

    max_count = max_count if max_count is not None else config.SEO_KEYWORD_MAX_COUNT

    nouns = extract_keywords(script_data, topic=topic)

    # Sprint94 - 제목을 앞에 붙인 구(phrase)를 만들지 않는다.
    #
    # 원본은 "topic + 토큰"으로 구를 만들었는데, 여기서 topic은
    # script.json의 제목이고 이 저장소의 제목은 한 문장짜리 후킹
    # 문구다. 그래서 실제로 이런 태그가 나왔다(Sprint93 실측):
    #
    #   "이 증상, 그냥 넘기면 평생 후회합니다. 뇌졸중의 결정적 신호
    #    3가지 않는"
    #
    # 검색어가 아니라 문장이다. 짧은 주제어를 전제로 만든 규칙이
    # 이 저장소의 제목 형태와 맞지 않는다.
    #
    # 대신 상위 명사끼리 두 개를 붙여 실제 검색에 쓰일 만한 구를
    # 만든다("혈관 염증", "커피 카페인"). 단일 명사가 먼저 오고,
    # 자리가 남으면 구를 채운다.
    keywords = list(nouns[:max_count])

    for index in range(len(nouns) - 1):
        if len(keywords) >= max_count:
            break
        phrase = f"{nouns[index]} {nouns[index + 1]}"
        if phrase not in keywords:
            keywords.append(phrase)

    return keywords[:max_count]
