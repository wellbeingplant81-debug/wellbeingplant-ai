"""
Sprint94 - Metadata Quality, 한국어 명사 추출.

Sprint93이 이식한 추출기는 대본에서 2글자 이상 한글 토큰을 빈도순으로
뽑았다. 그러니 이런 것이 해시태그가 됐다.

    #그냥 #방금 #손에 #들다가 #혹시 #평생 #넘기면

조사가 붙은 형태("손에"), 동사 활용형("들다가"), 부사("그냥/방금/혹시")
가 그대로 남는다. 검색에 아무 값이 없고, 채널 설명란에 그대로 노출된다.

형태소 분석기를 쓰지 않는다. morphological_normalization_service가
같은 이유로 그렇게 만들어졌고(순수 정규식/문자열 치환), 여기에만
KoNLPy/Kiwi를 들이면 저장소에 한국어 처리 방식이 두 갈래가 된다.

대신 문법에서 나오는 사실 하나를 쓴다 - 한국어에서 조사는 명사류에만
붙는다. "혈압이/혈압을/혈압은"이 본문에 있으면 "혈압"은 명사다.
부사 "그냥"에는 조사가 붙지 않는다. 이것은 추측이 아니라 관측이다.

그래서 판정을 세 겹으로 한다.

  1. 조사가 붙은 채로 나타난 적이 있는가 (명사의 직접 증거)
  2. "X합니다/X하는/X됩니다"처럼 하다/되다가 붙은 적이 있는가
     (그 X는 명사다 - 서술성 명사)
  3. 위 증거가 없으면, 기능어 목록과 활용형 꼬리로 걸러 낸다

증거가 있는 쪽만 통과시킨다. 애매하면 버린다 - 해시태그는 빠지는
것보다 이상한 것이 나가는 쪽이 나쁘다.
"""

import re
from typing import Dict, List

# 조사를 두 갈래로 나눈다. 실측에서 나온 구분이다.
#
# 처음에는 조사를 한 목록으로 두고 "떼어졌으면 명사"로 봤더니
# #마시 #쌓이 #가져오 #깨우 가 나왔다. "마시는/쌓이는"의 "는"을 조사로
# 읽었기 때문인데, 그 "는"은 조사가 아니라 관형사형 어미다. "는/은/도/
# 나"는 명사 뒤에도 용언 뒤에도 붙어서 그것만으로는 아무것도 증명하지
# 못한다.
#
# 그래서 명사에만 붙는 조사(목적격/주격/속격/처격 등)를 따로 두고,
# 그것이 붙어 나타난 적이 있을 때만 명사로 인정한다.
_STRONG_PARTICLES = [
    "에서부터", "으로부터", "에게서", "에서만", "에서도", "이라는",
    "라는", "에서", "으로", "부터", "까지", "라도", "만큼", "처럼",
    "에게", "한테", "보다", "마다", "조차", "밖에", "이란", "께서",
    "이", "가", "을", "를", "의", "에", "로", "와", "과",
]

# 명사 뒤에도 용언 뒤에도 붙는다. 떼기는 하되 증거로 삼지 않는다.
_WEAK_PARTICLES = ["은", "는", "도", "만", "나", "야", "랑", "이나"]

_PARTICLES = _STRONG_PARTICLES + _WEAK_PARTICLES

# 서술성 명사를 만드는 꼬리. "X합니다"의 X는 명사다(관리하다, 예방하다,
# 후회하다). 이 꼬리가 붙어 있으면 앞부분을 명사 후보로 본다.
# "한"/"된" 한 글자는 넣지 않는다. "간단한/미지근한"의 앞부분은 형용사
# 어간이지 명사가 아닌데, 그것까지 통과시켜 #간단 #미지근 이 나왔다.
_NOMINAL_PREDICATE_TAILS = [
    "하겠습니다", "했습니다", "합니다", "하십시오", "하세요", "하려면",
    "되었습니다", "됐습니다", "됩니다", "되세요",
    "하는", "하고", "해서", "하면", "하며", "하지", "해도",
    "되는", "되고", "돼서", "되면",
]

# 활용형 꼬리. 이것으로 끝나면 용언(동사/형용사)이다 - 명사가 아니다.
# "넘기면/들다가/말해주지/빠진/처져"처럼 조사를 벗겨도 남는 것들.
_VERBAL_TAILS = [
    "습니다", "ㅂ니다", "다가", "으면", "면서", "는데", "지만", "려고",
    "려면", "도록", "든지", "니까", "어서", "아서", "여서", "어도", "아도",
    "거나", "면서", "고서", "자마자", "잖아", "는지", "던지",
    "어요", "아요", "여요", "네요", "군요", "구나", "세요", "십시오",
    "느냐", "냐고", "라고", "다고",
    "다", "요", "죠", "지", "며", "고", "면", "서", "게", "든", "든가",
]

# 기능어. 조사가 붙지 않은 채로도 자주 나오지만 명사가 아니거나,
# 명사여도 검색에 아무 값이 없는 것들.
_FUNCTION_WORDS = {
    # 부사
    "그냥", "방금", "혹시", "정말", "특히", "절대", "아주", "매우", "너무",
    "다시", "이제", "벌써", "항상", "자주", "가끔", "만약", "결국", "심지어",
    "오히려", "물론", "역시", "바로", "무려", "겨우", "거의", "조금", "많이",
    "함께", "각각", "서로", "이미", "아직", "곧바로", "실제로", "실제",
    "제대로", "완전히", "충분히", "훨씬", "약간", "잠깐", "미리", "직접",
    "빨리", "천천히", "계속", "먼저", "나중", "반드시", "꼭꼭", "그대로",
    "살짝", "그만", "하루종일", "언제", "어디", "누구", "얼마", "왜냐",
    # 접속/지시
    "하지만", "그러나", "그리고", "그래서", "따라서", "그런데", "그러면",
    "왜냐하면", "그러니까", "그러다", "이렇게", "그렇게", "저렇게", "이런",
    "그런", "저런", "어떤", "무슨", "여기", "거기", "저기", "이것", "그것",
    "저것", "이거", "그거", "저거", "무엇", "어떻게", "이번", "저번",
    # 대명사
    "우리", "저희", "여러분", "당신", "자신", "본인", "누구나", "모두",
    # 의존명사/형식명사
    "때문", "경우", "정도", "가지", "번째", "동안", "사실", "이상", "이하",
    "종류", "부분", "상태", "방법", "이유", "필요", "생각", "느낌", "시작",
    # 시간 일반어
    "오늘", "내일", "어제", "지금", "요즘", "평생", "당장", "최근",
    # 수량/불특정
    "하나", "둘", "여러", "몇몇", "약간", "전부", "일부",
}

# 2글자 미만 어간은 버린다. "손에"->"손", "컵을"->"컵"처럼 실제 명사여도
# 한 글자 해시태그는 검색에 쓸모가 없다.
_MIN_LENGTH = 2

_TOKEN_PATTERN = re.compile(r"[가-힣]+")


def _strip_suffix(word: str, suffixes: List[str]):
    """
    가장 긴 꼬리 하나를 뗀다. 뗐으면 (어간, True).

    Sprint240 - 길이 때문에 막히면 **다른 꼬리로 갈아타지 않는다.**

    예전에는 짧은 꼬리로 내려갔다. 그래서 실제로 이런 것이 채널에
    나갔다(2026-08-19 실측).

        손으로
          꼬리 '으로'  남는 것 '손'   길이 1  -> 건너뜀
          꼬리 '로'    남는 것 '손으'  길이 2  -> 채택

    "손으" 는 한국어 낱말이 아니다. '으로' 가 조사인 것은 맞고, 떼면
    '손' 이 남는데 그것이 짧아서 못 쓸 뿐이다. 짧아서 못 쓰는 것을
    짧지 않게 만들려고 조사 한 글자를 낱말에 남기면, 사람이 읽을 수
    없는 것이 나간다 - 빠지는 것보다 이상한 것이 나가는 쪽이 나쁘다는
    이 파일의 원칙 그대로다.

    그래서 붙어 있는 것 중 가장 긴 것 하나만 본다. 그것을 떼서 남는
    것이 짧으면 그 낱말은 후보에서 빠진다.
    """

    for suffix in sorted(suffixes, key=len, reverse=True):
        if not word.endswith(suffix):
            continue

        if len(word) - len(suffix) < _MIN_LENGTH:
            # 이 낱말은 여기서 끝이다. 덜 떼지 않는다.
            return word, False

        return word[: -len(suffix)], True

    return word, False


def _strip_particles(word: str) -> str:
    """조사를 반복해 뗀다. "혈압으로는"처럼 겹친 경우가 있다."""

    stem = word
    for _ in range(3):
        stripped, removed = _strip_suffix(stem, _PARTICLES)
        if not removed:
            break
        stem = stripped
    return stem


# 과거시제 선어말어미. 명사가 이것으로 끝나는 일은 없다.
#
# "켜졌을"에서 "을"을 목적격 조사로 떼면 "켜졌"이 남아 명사 행세를
# 한다(실측). 그 "을"은 조사가 아니라 관형사형 어미다("켜졌을 때").
# 조사인지 어미인지는 앞말을 봐야 알 수 있고, 앞말이 과거형이면
# 어미다.
_PAST_TENSE_TAILS = (
    "았", "었", "였", "졌", "했", "랐", "렀", "왔", "뒀", "췄", "셨",
    "냈", "댔", "봤", "줬", "혔", "겼", "쳤",
)


def _looks_verbal(word: str) -> bool:
    if any(word.endswith(tail) for tail in _PAST_TENSE_TAILS):
        return True
    return any(word.endswith(tail) for tail in _VERBAL_TAILS)


def extract_nouns(text: str) -> List[str]:
    """
    명사로 볼 근거가 있는 것만, 빈도 내림차순으로 돌려준다.

    같은 빈도면 먼저 나온 순서를 지킨다 - 대본 앞쪽이 대개 주제어다.
    """

    if not text:
        return []

    tokens = _TOKEN_PATTERN.findall(text)

    counts: Dict[str, int] = {}
    order: List[str] = []
    evidence: Dict[str, bool] = {}

    def _note(noun: str, has_evidence: bool):
        if len(noun) < _MIN_LENGTH or noun in _FUNCTION_WORDS:
            return
        if noun not in counts:
            counts[noun] = 0
            order.append(noun)
            evidence[noun] = False
        counts[noun] += 1
        evidence[noun] = evidence[noun] or has_evidence

    for token in tokens:
        # 0. 기능어는 조사를 떼기 전에 먼저 버린다. "제대로"에서 "로"를
        #    조사로 떼면 "제대"가 남아 명사 행세를 한다(실측).
        if token in _FUNCTION_WORDS:
            continue

        # 1. 하다/되다가 붙어 있었나 - 앞부분은 서술성 명사다.
        #
        # 활용형 검사보다 먼저 해야 한다. "관리합니다"는 "습니다"로
        # 끝나서 활용형 검사에 먼저 걸리는데, 그러면 "관리"라는 명사를
        # 통째로 잃는다(실측). "X합니다"는 활용형이면서 동시에 X가
        # 명사라는 증거이고, 여기서 필요한 것은 그 X다.
        nominal, removed = _strip_suffix(token, _NOMINAL_PREDICATE_TAILS)
        if removed:
            if not _looks_verbal(nominal):
                _note(nominal, True)
            continue

        # 2. 순수 활용형은 버린다. "먹어도"에서 "도"를 조사로 떼면
        #    "먹어"가 남아 명사 행세를 한다.
        if _looks_verbal(token):
            continue

        # 2. 명사에만 붙는 조사가 떨어졌나 - 명사의 직접 증거.
        strong, had_strong = _strip_suffix(token, _STRONG_PARTICLES)
        if had_strong:
            # 조사를 뗀 뒤에도 활용형이면 명사가 아니다. "피곤해서가"의
            # "가"를 떼면 "피곤해서"가 남는데 그것은 명사가 아니다(실측).
            stem = _strip_particles(strong)
            if not _looks_verbal(stem) and stem not in _FUNCTION_WORDS:
                _note(stem, True)
            continue

        # 3. 애매한 조사는 떼되 증거로 치지 않는다. 본문 어딘가에서
        #    강한 조사와 함께 나타난 적이 있어야 살아남는다.
        weak, had_weak = _strip_suffix(token, _WEAK_PARTICLES)
        _note(weak if had_weak else token, False)

    # 증거가 있는 것을 먼저, 그다음 빈도, 그다음 등장 순서.
    ranked = sorted(
        order,
        key=lambda noun: (not evidence[noun], -counts[noun], order.index(noun)),
    )

    return [noun for noun in ranked if evidence[noun]] or ranked


def extract_nouns_from_script(script_data: dict, topic: str = None) -> List[str]:
    """
    제목과 본문, 그리고 주제어를 함께 본다.

    주제어를 넣는 이유가 있다. "치매를 늦추는 생활 습관"으로 만든
    영상에서 해시태그에 "치매"가 빠졌다(실측). 대본에는 "치매"가
    조사 없이 "치매", "치매?"로만 나와 명사라는 증거가 없었기
    때문이다. 정작 주제어에는 "치매를"이 있었다.

    주제어는 사람이 직접 적은 그 영상의 주제이고, 대개 핵심 명사가
    조사와 함께 들어 있다. 새로 만들어 내는 것이 아니라 이미 있는
    사실을 마저 읽는 것이다.
    """

    text = " ".join(
        part for part in (
            topic, script_data.get("title"), script_data.get("script"),
        ) if part
    )

    return extract_nouns(text)
