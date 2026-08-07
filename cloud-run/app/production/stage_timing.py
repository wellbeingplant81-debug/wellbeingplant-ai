"""
Sprint109 - 단계별 소요 시간 (Epic 54, Phase 8).

지어낸 숫자가 없다. 이 저장소가 실제로 만든 영상 37편이
quality_report.json의 technical_validation.performance_metrics에
남긴 값의 중앙값이다.

평균이 아니라 중앙값을 쓴 이유가 있다. 범위가 넓다 - 대본 생성은
0.0초에서 117.8초까지, 렌더는 0.0초에서 561.0초까지 나온다. 평균을
쓰면 몇 번의 긴 실행이 전체를 끌어올려 "보통 이만큼 걸린다"와
멀어진다.

    측정 대상   output/*/quality_report.json 37편
    측정 시점   2026-08-07

    script_generation      31.5초   (0.0 ~ 117.8)
    image_generation        4.2초   (0.0 ~  49.1)
    tts_generation         14.2초   (0.0 ~  19.0)
    subtitle_generation     0.6초   (0.0 ~  10.5)
    video_rendering       259.1초   (0.0 ~ 561.0)
    thumbnail_generation   11.1초   (0.0 ~  27.5)
    quality_evaluation     32.3초   (0.0 ~  45.9)
    total_generation      383.8초  (10.2 ~ 735.9)

이미지 4.2초가 낮아 보이는 것은 대부분의 scene이 스톡에서 오고
step02가 병렬로 돌기 때문이다 - Imagen을 많이 쓴 실행은 49초까지
갔다. 중앙값이 그 두 세계의 가운데를 가리킨다.

배경음악과 메타데이터는 따로 잰 적이 없다.

    BGM은 렌더 중에 섞여 들어가 video_rendering 안에 이미 포함돼
    있고, 메타데이터는 규칙 기반이라 잴 만한 시간이 아니다(Sprint93).

그래서 둘은 0으로 둔다. 이것은 "빠르다"가 아니라 "따로 세지 않는다"는
뜻이고, 배경음악을 건너뛴다고 예상 시간이 줄지 않는 이유이기도 하다.

이 파일은 아무것도 import하지 않는다. 표일 뿐이다.
"""

SAMPLE_SIZE = 37
MEASURED_AT = "2026-08-07"

# 사용자가 고를 수 있는 단계가 각각 얼마나 걸리는가.
STAGE_SECONDS = {
    "script": 31.5,
    "image": 4.2,
    "voice": 14.2,
    # 렌더 안에 이미 포함돼 있다 - 따로 세지 않는다.
    "music": 0.0,
    # 규칙 기반이라 잴 만한 시간이 아니다.
    "metadata": 0.0,
}

# 고를 수 있는 것이 아닌 단계들. 무엇을 고르든 항상 돈다.
FIXED_STAGE_SECONDS = {
    "subtitle_generation": 0.6,
    "video_rendering": 259.1,
    "thumbnail_generation": 11.1,
    "quality_evaluation": 32.3,
}

FIXED_SECONDS = sum(FIXED_STAGE_SECONDS.values())

# 실제로 관측된 전체 중앙값. 위 항목들의 합과 정확히 같지 않다 -
# 중앙값은 더해지지 않는다. 화면이 "이 값과 비슷하게 걸린다"고
# 말할 근거로만 둔다.
OBSERVED_TOTAL_SECONDS = 383.8


def seconds_for(stage: str) -> float:
    return STAGE_SECONDS.get(stage, 0.0)
