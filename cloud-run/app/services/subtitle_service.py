import glob
import json
import os
import re
import unicodedata
from datetime import timedelta

from app.services.duration_optimizer import get_audio_duration
from app.services.kenburns import VIDEO_WIDTH

# Sprint59 - Subtitle Timing Precision. 마지막 cue의 종료 시간이
# 실제 final_audio.mp3보다 짧아지는 극단적인 경우(예: 측정값이 마지막
# cue의 시작 시간보다도 작게 나오는 경우) end가 start 이하로 붕괴하지
# 않도록 두는 최소 안전 여유값.
MIN_LAST_CUE_DURATION_SECONDS = 0.05

# Sprint61 - Silence-Aware Subtitle Timing. app/steps/step03_tts.py가
# 저장하는 파일명과 반드시 같아야 한다(두 모듈이 공유하는 암묵적
# 계약) - step03_tts.DURATION_OPTIMIZATION_METADATA_FILENAME 참고.
DURATION_OPTIMIZATION_METADATA_FILENAME = "duration_optimization.json"

MAX_CHARS = 18
MIN_CHARS = 4

# Sprint39 - Semantic Subtitle Engine.
#
# 실측 보정(2026-07-10, Sprint68-1 재보정): final_video_service.py와
# 동일한 force_style(FontName=Malgun Gothic, FontSize=18, Bold=1,
# Outline=4)로 1080x1920 검정 배경에 순수 한글 자막을 실제로 렌더링한
# 뒤, 흰 글자의 픽셀 bounding box를 직접 측정했다(폰트 메트릭 API가
# 아니라 libass가 실제로 그린 결과를 측정 - PlayRes 관련 내부 스케일링
# 까지 그대로 반영됨). Sprint68-1은 Shorts 가독성을 위해 FontSize를
# 22 -> 18(약 18% 축소, 요구사항 15~20% 범위)로 낮췄으므로 이 폭 상수도
# 함께 다시 재야 한다 - 폰트가 작아진 만큼 한 줄에 더 많은 글자가
# 들어간다.
#
#   한글 3자 "가나다" (FontSize=18) -> 263px (약 87.7px/자)
#
# 즉 전각(한글) 1자 ≈ 87.7px, 이 모듈의 폭 단위(_display_width, 전각=2)
# 기준으로 1 unit ≈ 43.83px다.
_MEASURED_PX_PER_UNIT = 43.83

# 화면 폭 중 자막에 실제로 쓸 안전 영역 비율(좌우 각 7.5% 여백).
SAFE_AREA_WIDTH_RATIO = 0.85

# 화면 1줄 안전 영역에 들어갈 수 있는 최대 표시 폭(전각=2/반각=1 단위,
# _display_width 참고) - VIDEO_WIDTH가 바뀌어도(예: 다른 해상도)
# 자동으로 다시 계산되도록 상수가 아니라 계산식으로 둔다.
SAFE_AREA_MAX_LINE_WIDTH = int(
    VIDEO_WIDTH * SAFE_AREA_WIDTH_RATIO / _MEASURED_PX_PER_UNIT
)

MAX_LINES_PER_CUE = 2

# _split_sentence_by_words()에 넘길 조각 상한(문자 수 기준). 최악의
# 경우(공백 없이 한글만 이어지는 경우, 1글자=2 unit)를 가정해 2줄 폭
# 예산을 문자 수로 보수적으로 환산한다 - 실제 문장은 단어 사이 공백이
# 섞여 있어 이보다 조금 더 들어가는 경우가 많지만, 안전한 쪽으로
# 잡는다(넘치는 것보다 조각이 하나 더 생기는 편이 낫다).
CUE_GROUPING_MAX_CHARS = (SAFE_AREA_MAX_LINE_WIDTH * MAX_LINES_PER_CUE) // 2

# 균형 분할 후보 중, 마지막 줄이 단어 1개뿐이고 표시 폭이 이 값
# 이하이면 "조사만 혼자 남은 것"으로 보고 그 분할은 피한다.
MIN_ORPHAN_LINE_WIDTH = 6

QUOTE_CHARS = set("'\"‘’“”")

# 다음 줄 맨 앞에 오면 자연스러운 접속사/접속부사 - 이 앞에서 끊는
# 분할을 우선한다.
CONJUNCTIONS = {
    "그리고", "그러나", "하지만", "그래서", "또한", "그런데", "즉",
    "따라서", "또", "그러면", "그러므로", "왜냐하면", "반면에", "게다가",
}


def format_srt_time(seconds: float):

    td = timedelta(seconds=seconds)

    total = int(td.total_seconds())

    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60

    ms = int((seconds - total) * 1000)

    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _split_sentence_by_words(sentence: str, max_chars: int):
    """
    문장 하나를 공백(단어/어절) 단위로만 묶어 max_chars(display-width
    단위, _display_width() 참고 - 한글 등 전각은 2, 반각은 1) 이하의
    자연스러운 조각으로 나눕니다. 쉼표를 우선 분리 기준으로 쓰지
    않으므로 "한 잔," 같은 쉼표 앞의 짧은 절이 단독 조각으로 남지
    않고 다음 단어들과 함께 묶입니다. 글자(음절) 단위 분할은 절대
    하지 않습니다 - 한 단어가 max_chars보다 길어도 그 단어를 쪼개지
    않고 그대로 한 조각으로 둡니다.

    Sprint60 Hotfix - 문제2: 예전에는 len(word)(순수 문자 수)로 폭을
    쟀는데, 이 함수를 호출하는 split_subtitle()의 max_chars(=
    CUE_GROUPING_MAX_CHARS)는 display-width 단위(SAFE_AREA_MAX_LINE_
    WIDTH*MAX_LINES_PER_CUE에서 유도)라서 단위가 서로 달랐다. 그
    결과 실제보다 훨씬 넉넉한 예산으로 착각해 조각을 넓게 묶었고,
    조각 안에 공백 없는 긴 복합명사+조사(예: "프로바이오틱스가")가
    끼면 wrap_to_safe_lines()가 2줄 안에 안전하게 못 넣어 화면 밖으로
    잘려나갔다(2026-07-09 E2E 실측). _display_width()로 통일해 실제
    화면 폭 기준과 그룹핑 기준을 맞춘다.
    """

    words = sentence.split()

    if not words:
        return []

    groups = []
    current = []
    current_len = 0

    for word in words:

        extra = _display_width(word) + (1 if current else 0)

        if current and current_len + extra > max_chars:
            groups.append(" ".join(current))
            current = [word]
            current_len = _display_width(word)
        else:
            current.append(word)
            current_len += extra

    if current:
        groups.append(" ".join(current))

    # 너무 짧은 자투리 조각(예: 쉼표 하나짜리 절)은 인접 조각과 합쳐
    # 의미 있는 단위로 유지한다 - 첫 조각이면 다음 조각과, 그 외에는
    # 이전 조각과 합친다. Sprint60 Hotfix 문제2: display-width 기준
    # 으로 그룹 예산이 빡빡해지면서(위 참고) 자투리가 맨 앞/중간
    # 어디에도 생길 수 있게 됐다 - 병합 한 번으로 이웃도 자투리가
    # 되는 경우까지 대비해 더 합칠 게 없을 때까지 반복한다.
    merged = True

    while merged and len(groups) >= 2:

        merged = False

        for i, group in enumerate(groups):

            if len(group) >= MIN_CHARS:
                continue

            if i == 0:
                groups[0:2] = [f"{groups[0]} {groups[1]}"]
            else:
                groups[i - 1:i + 1] = [f"{groups[i - 1]} {groups[i]}"]

            merged = True
            break

    return groups


def split_subtitle(text: str):
    """
    narration을 자막 조각으로 나눕니다. 항상 "문장 -> (너무 길면)
    단어 단위 묶음" 순서로만 나누고, 글자(음절) 단위 분할은 하지
    않습니다.

    Sprint39: 조각 하나의 상한을 MAX_CHARS(1줄 분량)가 아니라
    CUE_GROUPING_MAX_CHARS(약 2줄 분량)로 넉넉하게 잡는다 - 실제 화면
    줄바꿈은 create_subtitle()에서 wrap_to_safe_lines()가 별도로
    결정하므로, 여기서는 예전보다 더 잘게 쪼개질 필요가 없다.
    """

    text = text.strip()

    if not text:
        return []

    result = []

    # 문장 단위 우선 분리 (마침표/물음표/느낌표 기준)
    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        # 짧으면 문장을 그대로 유지한다.
        if len(sentence) <= CUE_GROUPING_MAX_CHARS:
            result.append(sentence)
            continue

        result.extend(_split_sentence_by_words(sentence, CUE_GROUPING_MAX_CHARS))

    return result


def _display_width(text: str) -> int:
    """
    전각(한글 등 East Asian Wide/Fullwidth) 문자는 2, 그 외(영문/숫자/
    기호 등 narrow/halfwidth/neutral)는 1로 계산한 표시 폭 근사치.
    실제 폰트 파일을 렌더링해 재는 게 아니라(배포 환경에 폰트가 없을
    수 있어 이식성이 떨어짐), 표준 라이브러리(unicodedata)만으로
    한글/영문 폭 차이를 반영한다.
    """

    width = 0

    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ("W", "F") else 1

    return width


def _quote_open_after_each_word(words: list) -> list:
    """
    각 단어 뒤 시점에 따옴표가 열린 채로 남아있는지 여부를 반환한다.
    단어 하나에 따옴표가 홀수 개 있으면 그 단어에서 열림/닫힘 상태가
    뒤집힌다고 본다 - "'이"에서 열리고 "물'"에서 닫히는 식으로, 같은
    구를 감싼 따옴표를 문자 단위가 아니라 단어 단위로 추적한다.
    """

    states = []
    inside = False

    for word in words:

        quote_count = sum(1 for ch in word if ch in QUOTE_CHARS)

        if quote_count % 2 == 1:
            inside = not inside

        states.append(inside)

    return states


def wrap_to_safe_lines(text: str, max_line_width: int = SAFE_AREA_MAX_LINE_WIDTH) -> str:
    """
    Sprint39 - Semantic Subtitle Engine.

    자막 조각 하나를 화면 Safe Area 안에 들어가는 최대
    MAX_LINES_PER_CUE(2)줄로 나눕니다. 이미 한 줄에 들어가면 그대로
    반환합니다. 단어 경계에서만 끊고(음절 단위 분할 절대 없음), 여러
    분할 후보 중 아래 우선순위로 고릅니다(우선순위가 앞설수록 먼저
    적용, 그 다음 기준은 동점일 때만 사용):

    1. 조사 고아 방지: 마지막 줄이 단어 1개뿐이고 너무 짧으면 피한다.
    2. 쉼표: 앞 줄이 쉼표로 끝나는 지점을 우선한다.
    3. 따옴표: 따옴표로 감싼 구를 두 줄로 쪼개는 지점은 피한다.
    4. 접속사: 다음 줄이 접속사로 시작하는 지점을 우선한다.
    5. 균형: 위 조건이 모두 동률이면 두 줄의 표시 폭 차이가 가장
       작은(가장 균형 잡힌) 지점을 고른다.

    두 줄 다 max_line_width 이내로 들어가는 분할이 하나도 없으면(단어
    하나가 유독 길거나 등), 단어 경계는 지키되 첫 줄을 최대한 채우는
    방식으로 안전하게 폴백합니다.
    """

    if _display_width(text) <= max_line_width:
        return text

    words = text.split()

    if len(words) <= 1:
        return text

    quote_open_after = _quote_open_after_each_word(words)

    candidates = []

    for i in range(1, len(words)):

        line1 = " ".join(words[:i])
        line2 = " ".join(words[i:])

        width1 = _display_width(line1)
        width2 = _display_width(line2)

        if width1 > max_line_width or width2 > max_line_width:
            continue

        orphan_penalty = 1 if (
            len(words[i:]) == 1 and width2 <= MIN_ORPHAN_LINE_WIDTH
        ) else 0

        comma_penalty = 0 if words[i - 1].rstrip().endswith(",") else 1
        quote_break_penalty = 1 if quote_open_after[i - 1] else 0
        conjunction_penalty = 0 if words[i] in CONJUNCTIONS else 1
        imbalance = abs(width1 - width2)

        score = (
            orphan_penalty,
            comma_penalty,
            quote_break_penalty,
            conjunction_penalty,
            imbalance,
        )

        candidates.append((score, line1, line2))

    if not candidates:
        return _greedy_two_line_fallback(words, max_line_width)

    _best_score, best_line1, best_line2 = min(candidates, key=lambda c: c[0])

    return f"{best_line1}\n{best_line2}"


def _greedy_two_line_fallback(words: list, max_line_width: int) -> str:
    """
    두 줄 다 max_line_width 이내로 들어가는 조합이 하나도 없을 때만
    쓰는 안전 장치. 단어 경계는 지키면서 첫 줄을 최대한 채우고 나머지를
    둘째 줄로 넘긴다 - 둘째 줄이 살짝 넘칠 수 있지만, 단어를 쪼개는
    일은 절대 없다.
    """

    line1_words = []
    width = 0

    for index, word in enumerate(words):

        extra = _display_width(word) + (1 if line1_words else 0)

        if line1_words and width + extra > max_line_width:
            break

        line1_words.append(word)
        width += extra

    if not line1_words:
        line1_words = [words[0]]

    line2_words = words[len(line1_words):]

    if not line2_words:
        return " ".join(line1_words)

    return " ".join(line1_words) + "\n" + " ".join(line2_words)


def _load_last_scene_pause_seconds(project_path: str):
    """
    Sprint61 - Silence-Aware Subtitle Timing.

    Duration Optimizer(duration_optimizer.optimize_scene_audio())가
    43초 미만인 내레이션을 43~47초 목표로 맞추려고 마지막 scene 오디오
    뒤에 무음을 이어붙이는 경우가 있다(action="expand"). 이 무음은
    실제 발화가 아니므로, cue 타이밍을 그 길이만큼까지 늘리면 마지막
    자막이 목소리보다 한참 오래 화면에 남는다(2026-07-09 QA 실측 -
    최대 3초 이상 어긋남).

    app/steps/step03_tts.py가 optimize_scene_audio()의 반환값을
    audio/duration_optimization.json에 저장해 두므로, 여기서 그
    pause_seconds(무음 길이)를 읽어온다. 다음 중 하나라도 해당하면
    None을 반환하고, 호출자는 무음 보정 없이 기존 로직 그대로
    진행해야 한다 - 어떤 경우에도 예외를 던지지 않는다:

    - 메타데이터 파일이 없음(과거 프로젝트, 하위 호환)
    - JSON이 손상됨
    - 최상위 값이 dict가 아님
    - action이 "expand"가 아님(무음을 붙이지 않았다는 뜻 - 정상 상태)
    - pause_seconds가 없거나, 숫자가 아니거나(bool 포함), 0 이하
    """

    path = os.path.join(
        project_path, "audio", DURATION_OPTIMIZATION_METADATA_FILENAME,
    )

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception:
        return None

    if not isinstance(metadata, dict):
        return None

    if metadata.get("action") != "expand":
        return None

    pause_seconds = metadata.get("pause_seconds")

    if isinstance(pause_seconds, bool) or not isinstance(pause_seconds, (int, float)):
        return None

    if pause_seconds <= 0:
        return None

    return float(pause_seconds)


def _snap_last_cue_to_final_audio_duration(
    cues: list, project_path: str, pause_seconds: float = None,
) -> None:
    """
    Sprint59 - Subtitle Timing Precision.

    (재조사 결과) cue 타이밍이 어긋나던 진짜 원인은 concat/BGM
    믹싱 재인코딩이 아니었다 - concat_scene_audio()로 씬 mp3들을
    이어 붙인 결과는 각 씬의 ffprobe 실측 길이 합과 소수점까지
    정확히 일치했다(무손실). 실제 원인은 씬 duration을 측정하던
    moviepy(AudioFileClip)가 ffprobe/실제 concat 결과와 씬마다 수 ms씩
    달랐던 것이었고(특히 Duration Optimizer가 후처리하는 마지막 씬은
    수십 ms까지 벌어짐), 그게 create_subtitle()에서 get_audio_duration()
    (ffprobe)으로 교체되며 해결됐다.

    이 함수는 그 근본 수정 이후에도 남겨두는 **최종 안전장치**다 -
    get_audio_duration()이 0.0을 반환하는 극단적 상황이나 향후 다른
    원인으로 생기는 잔여 오차가 있더라도, 최소한 화면에 보이는 마지막
    cue의 끝은 실제 final_audio.mp3 길이를 벗어나지 않도록 보장한다.
    final_audio.mp3가 없거나, ffprobe 측정이 실패하거나(0.0 반환),
    예외가 나면 아무것도 하지 않고 기존 계산값을 그대로 둔다 - 이
    보정 하나 때문에 자막 생성 자체가 실패해서는 안 된다.

    Sprint61 - pause_seconds(Duration Optimizer가 마지막 scene 뒤에
    붙인 무음 길이, _load_last_scene_pause_seconds() 참고)가 주어지면
    목표 시각에서 그만큼을 뺀다 - "파일이 끝나는 시점"이 아니라
    "실제 발화가 끝나는 시점"에 맞춘다. pause_seconds가 비정상(전체
    길이보다 크거나 같음)이면 무시하고 기존처럼 전체 길이를 그대로
    쓴다 - 이 보정도 실패 시 예외 없이 조용히 폴백해야 한다.
    """

    if not cues:
        return

    final_audio_path = os.path.join(
        project_path,
        "audio",
        "final_audio.mp3",
    )

    if not os.path.exists(final_audio_path):
        return

    try:
        actual_duration = get_audio_duration(final_audio_path)
    except Exception:
        return

    if not actual_duration or actual_duration <= 0:
        return

    target_duration = actual_duration

    if pause_seconds is not None:
        candidate = actual_duration - pause_seconds
        if candidate > 0:
            target_duration = candidate

    last_cue = cues[-1]

    if target_duration <= last_cue["start"]:
        last_cue["end"] = last_cue["start"] + MIN_LAST_CUE_DURATION_SECONDS
        return

    last_cue["end"] = target_duration


def create_subtitle(project_path: str):

    script_path = os.path.join(
        project_path,
        "script.json",
    )

    with open(
        script_path,
        "r",
        encoding="utf-8",
    ) as f:

        data = json.load(f)

    scenes = data["scenes"]

    scene_audio_folder = os.path.join(
        project_path,
        "audio",
        "scenes",
    )

    scene_audios = sorted(
        glob.glob(
            os.path.join(
                scene_audio_folder,
                "*.mp3",
            )
        )
    )

    if len(scene_audios) != len(scenes):

        raise Exception(
            "Scene MP3 개수와 Scene 개수가 다릅니다."
        )

    subtitle_dir = os.path.join(
        project_path,
        "subtitle",
    )

    os.makedirs(
        subtitle_dir,
        exist_ok=True,
    )

    srt_path = os.path.join(
        subtitle_dir,
        "subtitle.srt",
    )

    current = 0
    cues = []

    # Sprint61 - Silence-Aware Subtitle Timing. Duration Optimizer는
    # 항상 마지막 scene 오디오만 후처리하므로(duration_optimizer.py의
    # scene_audio_paths[-1]), 여기서도 마지막 scene에만 무음 보정을
    # 적용한다.
    last_scene_pause_seconds = _load_last_scene_pause_seconds(project_path)
    last_scene_index = len(scenes) - 1

    for index, (scene, audio_path) in enumerate(zip(
        scenes,
        scene_audios,
    )):

        narration = scene["narration"].strip()

        print("\n" + "=" * 60)
        print("NARRATION")
        print(narration)

        subtitles = split_subtitle(
            narration
        )

        print("GENERATED SUBTITLES")
        print(subtitles)
        print("=" * 60)

        # Sprint59 - moviepy(AudioFileClip)의 duration 추정치는 ffprobe/
        # 실제 concat 결과와 씬마다 수 ms씩 어긋나고(특히 Duration
        # Optimizer가 후처리하는 마지막 씬에서 수십 ms까지 벌어짐), 이
        # 오차가 씬을 거칠수록 누적돼 뒤쪽 cue일수록 실제 음성과
        # 어긋난다. concat_scene_audio()가 실제로 무손실(각 씬의 ffprobe
        # 길이 합 == final_audio.mp3 실측 길이)임을 확인했으므로,
        # get_audio_duration()(ffprobe)로 측정치를 실제 오디오 파이프
        # 라인과 일치시킨다.
        scene_duration = get_audio_duration(audio_path)

        # Sprint61 - 마지막 scene이고 유효한 pause_seconds가 있으면,
        # 무음 패딩을 뺀 "실제 발화 길이"로 이 scene의 cue들을 배분한다
        # - 안 그러면 cue가 무음 구간까지 늘어난다. pause_seconds가
        # scene_duration 이상(비정상)이면 무시하고 기존처럼 전체
        # 길이를 그대로 쓴다.
        if index == last_scene_index and last_scene_pause_seconds is not None:
            effective_duration = scene_duration - last_scene_pause_seconds
            if effective_duration > 0:
                scene_duration = effective_duration

        lengths = [
            max(1, len(x))
            for x in subtitles
        ]

        total_len = sum(lengths)

        local_time = 0

        for subtitle, length in zip(
            subtitles,
            lengths,
        ):

            part_duration = (
                scene_duration
                * length
                / total_len
            )

            start = current + local_time
            end = start + part_duration

            cues.append({
                "start": start,
                "end": end,
                "text": wrap_to_safe_lines(subtitle),
            })

            local_time += part_duration

        current += scene_duration

    # Sprint59 - 마지막 cue의 종료 시간만 실제 final_audio.mp3 길이에
    # 맞춘다(중간 cue는 위에서 계산한 값을 그대로 유지). Sprint61 -
    # pause_seconds가 있으면 그 길이만큼 뺀 "실제 발화 끝"에 맞춘다.
    _snap_last_cue_to_final_audio_duration(
        cues, project_path, pause_seconds=last_scene_pause_seconds,
    )

    with open(
        srt_path,
        "w",
        encoding="utf-8",
    ) as srt:

        for index, cue in enumerate(cues, start=1):

            srt.write(f"{index}\n")

            srt.write(
                f"{format_srt_time(cue['start'])} --> {format_srt_time(cue['end'])}\n"
            )

            srt.write(cue["text"])

            srt.write("\n\n")

    print(f"\nSRT SAVED : {srt_path}")

    return srt_path