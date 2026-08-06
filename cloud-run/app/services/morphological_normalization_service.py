"""
Epic 43 Sprint 1 - Morphological Normalization Service.

Epic 42가 밝힌 남은 Topic Alignment 실패의 주요 원인 - 한국어 활용형
(걷기/걷는다/걸음/걸어서/걸어도)이 리터럴/Cluster/Canonical Concept
어디와도 문자열이 겹치지 않는 문제 - 를 형태소 분석기 없이 최소
규칙만으로 얼마나 해결할 수 있는지 검증한다.

허용된 규칙만 사용한다:
1. 조사 제거
2. 기본 어미 제거
3. 공백 정규화
4. 연속 조사 제거(조사 목록을 길이 내림차순으로 반복 제거해 자연스럽게
   처리된다 - 별도 로직 불필요)
5. 동일 의미 반복 제거(연속된 동일 단어 중복 제거)
6. 최소 어간 추출(어미 제거 후 남는 부분 + ㄷ 불규칙 활용의 극소수
   고정 치환표)

형태소 분석기(KoNLPy/Mecab/Kiwi 등)나 외부 라이브러리를 전혀 쓰지
않는다 - 순수 정규식/문자열 치환뿐이다.
"""

import re


# 1. 조사 - 긴 것부터 매칭해야 짧은 조사가 먼저 잘못 걸리지 않는다
# (예: "에서만"을 "만"으로 먼저 자르면 "에서"가 남아 오작동한다).
_PARTICLES = [
    "에서부터", "에서만", "으로는", "에게서", "에서도",
    "에서", "으로", "부터", "까지", "이나", "라도", "만큼", "처럼", "에게", "한테",
    "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만", "나",
]

# 2. 어미 - 명사형 전성어미(기/음/ㅁ), 연결어미(어서/아서/여서/어도/아도/
# 여도/는데도/으면/면서), 종결어미(다/는다/습니다/어요/아요/네요/죠) 등.
# 마찬가지로 긴 것부터 매칭한다.
_ENDINGS = [
    "습니다", "합니다", "됩니다", "는데도", "면서도",
    "어서는", "아서는",
    "니다", "어서", "아서", "여서", "어도", "아도", "여도", "으면", "면서", "는데",
    "네요", "어요", "아요", "여요", "구나", "군요",
    "는다", "다면", "기는", "음은",
    "다", "요", "죠", "고", "면", "기", "음", "ㅁ",
]

# 6. 최소 어간 추출 보조 - ㄷ 불규칙 활용(어간 받침 ㄷ이 모음 어미 앞에서
# ㄹ로 바뀌는, 국어 문법상 닫힌 소수 부류) 동사만 담은 고정 치환표.
# 사전 검색/품사 태깅이 필요 없는 상수 매핑일 뿐이다 - 형태소 분석기가
# 아니다.
_IRREGULAR_STEM_MAP = {
    "걸": "걷",  # 걷다(walk) -> 걸어서/걸음/걸어도
    "들": "듣",  # 듣다(hear) -> 들어서/들음
    "물": "묻",  # 묻다(ask) -> 물어서/물음
    "실": "싣",  # 싣다(load) -> 실어서/실음
}

_MIN_STEM_LENGTH = 1


def normalize_whitespace(text: str) -> str:
    if not text:
        return text
    return re.sub(r"\s+", " ", text).strip()


def remove_duplicate_repetition(text: str) -> str:
    if not text:
        return text
    words = text.split(" ")
    deduped = []
    for word in words:
        if not deduped or deduped[-1] != word:
            deduped.append(word)
    return " ".join(deduped)


def _strip_longest_suffix(word: str, suffixes: list) -> str:
    for suffix in sorted(suffixes, key=len, reverse=True):
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_STEM_LENGTH:
            return word[: -len(suffix)]
    return word


_ALL_SUFFIXES = _PARTICLES + _ENDINGS


def extract_stem(word: str) -> str:
    if not word:
        return word

    # 조사와 어미를 하나의 목록으로 합쳐 길이 내림차순으로 검사한다 -
    # 그렇지 않으면 "걸어도"에서 어미 "어도"(2글자)보다 조사 "도"
    # (1글자)가 먼저 걸려 "걸어"만 남는 오류가 생긴다(실측으로 발견).
    # "걸음으로"(어미+조사 중첩)처럼 한 번에 안 끝나는 경우를 위해
    # 더 이상 줄어들지 않을 때까지 반복한다(최대 3회, 무한 루프 방지).
    stem = word
    for _ in range(3):
        stripped = _strip_longest_suffix(stem, _ALL_SUFFIXES)
        if stripped == stem:
            break
        stem = stripped

    stem = _IRREGULAR_STEM_MAP.get(stem, stem)

    return stem or word


def text_contains_concept_stem(text: str, concept: str) -> bool:
    if not text or not concept:
        return False

    concept_stem = extract_stem(concept)
    tokens = re.findall(r"[가-힣]{2,}", normalize_whitespace(text))

    return any(extract_stem(token) == concept_stem for token in tokens)
