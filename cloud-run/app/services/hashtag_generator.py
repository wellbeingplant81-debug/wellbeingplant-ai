"""
Epic 17 - Metadata Intelligence, Hashtag Generator.

Gemini를 호출하지 않는다 - Script(title/script)의 narration 텍스트를
공백/구두점으로 나눈 뒤 흔한 조사/어미가 붙은 짧은 상용구를 불용어로
제거하고, 남은 토큰을 빈도 내림차순(정렬 규칙)으로 나열하는 규칙 기반
추출이다. 실제 한국어 형태소 분석(조사 분리)이 아니다 - "간은"처럼
조사가 붙은 형태 그대로 하나의 토큰으로 남는 것은 알려진 한계다.

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


def extract_keywords(script_data: dict, merge_similar_forms: bool = False) -> list:
    text = " ".join(
        part for part in (script_data.get("title"), script_data.get("script")) if part
    )
    tokens = TOKEN_PATTERN.findall(text)

    key_fn = extract_stem if merge_similar_forms else _identity

    counts: Dict[str, int] = {}
    order = []
    display: Dict[str, str] = {}
    for token in tokens:
        if token in STOPWORDS:
            continue
        key = key_fn(token)
        if key not in counts:
            order.append(key)
            display[key] = token
        counts[key] = counts.get(key, 0) + 1

    ordered_keys = sorted(order, key=lambda key: (-counts[key], order.index(key)))
    return [display[key] for key in ordered_keys]


def generate_hashtags(
    script_data: dict,
    min_count: Optional[int] = None,
    max_count: Optional[int] = None,
    merge_similar_forms: bool = False,
) -> list:
    min_count = min_count if min_count is not None else config.HASHTAG_MIN_COUNT
    max_count = max_count if max_count is not None else config.HASHTAG_MAX_COUNT

    keywords = extract_keywords(script_data, merge_similar_forms=merge_similar_forms)[
        :max_count
    ]

    topic = script_data.get("title")
    if topic and topic not in keywords and len(keywords) < min_count:
        keywords.append(topic)

    return [f"#{keyword}" for keyword in keywords]


def generate_seo_keywords(
    script_data: dict, min_count: Optional[int] = None, max_count: Optional[int] = None
) -> list:
    """
    Epic 19 P4 - SEO Keyword Generator. Hashtag(단일 토큰, # 접두어)와
    구분되는 검색 친화적 "구(phrase)" 형태의 키워드를 만든다 - 실제
    형태소 분석/구 추출이 아니라, topic 자체 + 빈도 상위 단일 토큰(기존
    extract_keywords() 재사용) + topic과 단일 토큰을 결합한 구(phrase)
    를 조합하는 규칙 기반 근사치다(예: "혈압" + "관리" -> "혈압 관리").
    """

    min_count = min_count if min_count is not None else config.SEO_KEYWORD_MIN_COUNT
    max_count = max_count if max_count is not None else config.SEO_KEYWORD_MAX_COUNT

    topic = (script_data.get("title") or "").strip()
    single_tokens = extract_keywords(script_data)

    keywords = []
    if topic:
        keywords.append(topic)

    # 단일 토큰과 topic+토큰 구(phrase)를 절반씩 섞는다 - 단일 토큰만
    # 채워 phrase가 하나도 안 들어가는 것을 막는다.
    single_token_budget = max(1, max_count // 2)

    for token in single_tokens:
        if len(keywords) >= single_token_budget:
            break
        if token == topic or token in keywords:
            continue
        keywords.append(token)

    if topic:
        for token in single_tokens:
            if len(keywords) >= max_count:
                break
            if token == topic:
                continue
            phrase = f"{topic} {token}"
            if phrase not in keywords:
                keywords.append(phrase)

    return keywords[:max_count]
