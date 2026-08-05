QUALITY_MAX_RETRY = 3

# Sprint45 - Scene Planner Integration Engine.
#
# Sprint68 (Stage 3)에서 켜고 실제 A/B를 돌린 뒤 되돌렸다. 이유는
# ENABLE_PROMPT_ENRICHMENT 쪽에 적어 뒀다 - Planner 자체는 scene을
# 건드리지 않지만, 이 계획을 Enrichment가 프롬프트에 반영하는 순간
# 화질이 떨어졌기 때문에 둘을 함께 끈다.
#
# 핵심 결함: camera가 scene 위치만으로 정해진다(첫 scene=close_up,
# 마지막=medium_shot, 나머지=wide_shot). 원본 프롬프트가 이미 카메라를
# 지시하고 있어도 그걸 읽지 않는다. 실측한 6개 scene 중 3개에서
# 지시가 정면으로 충돌했다(예: "dynamic low-angle close-up shot"에
# "wide shot"을 덧붙임).
ENABLE_SCENE_PLANNER = False

# Sprint46 - Prompt Enrichment Engine.
#
# Sprint68 (Stage 3)에서 켜서 실제 A/B 영상을 두 벌 만들어 본 뒤
# 되돌렸다. 같은 대본/같은 나레이션 오디오로 에셋만 다시 수집했고,
# 실제로 달라진 이미지는 Imagen이 만드는 2개뿐이었다(나머지 4개는
# Pexels이고 검색어가 안 바뀌어 바이트 단위로 동일했다).
#
# 그 2개 중 하나가 눈에 띄게 나빠졌다. scene 4는 원본 프롬프트가
# "dynamic low-angle close-up shot"인데 Planner가 "wide shot"을
# 덧붙였고, 결과 이미지에 'Meticin'/'Croupic'/'Visulation' 같은 뜻
# 없는 가짜 라벨이 박혔다. Gemini Vision 평가도 realism 90->40,
# composition 90->50, 재생성 권고 false->true로 뒤집혔다.
#
# 주의할 점 하나: prompt_effectiveness 점수는 오히려 90 -> 100으로
# 올랐다. 그 루브릭은 "계획대로 문구가 들어갔는가"를 보기 때문에
# Enrichment를 켜면 정의상 점수가 오른다 - 이미지가 좋아졌다는
# 뜻이 아니다. 내부 점수와 실제 화질이 반대로 움직인 사례다.
#
# 다시 켜려면 최소한 camera 결정이 원본 프롬프트에 이미 있는 카메라
# 지시를 읽고 충돌을 피해야 한다.
#
# 별개의 알려진 한계: 스톡 검색은 enrichment가 끝난 프롬프트를 그대로
# 쓰고 extract_search_query()는 앞 8개 내용어만 본다. 실제 대본의
# 프롬프트는 내용어가 15개를 넘어 descriptor가 창 밖에 떨어지지만,
# 8개에 못 미치는 짧은 프롬프트에서는 검색어가 바뀐다
# (tests/test_stage3_planner_enrichment.py에 못을 박아 뒀다).
ENABLE_PROMPT_ENRICHMENT = False

# Sprint47 - Prompt Effectiveness Engine.
#
# Sprint66 (Stage 1)에서 켰다. 측정 전용이라 data["scenes"]도, 그 밖의
# 어떤 생성 산출물도 건드리지 않는다 - 켜고 끄는 것이 바꾸는 것은
# project_data["prompt_metrics"]가 채워지는지 여부와, 그 결과가
# prompt_metrics.json으로 나가는지 여부뿐이다. script.json을 비롯한
# 생성 산출물은 바이트 단위로 동일하다(pipeline.MEASUREMENT_ONLY_KEYS
# 참고).
#
# 주의: ENABLE_SCENE_PLANNER가 꺼져 있는 동안에는 scene_plan이 없어서
# camera/visual_type/purpose 항목이 "확인 대상 없음 -> 통과"로 처리되고
# keywords는 항상 0점이다. 즉 지금 점수는 enrichment 이전의 기준선이며,
# 실질적인 변별력은 Planner를 켜는 단계에서 생긴다.
ENABLE_PROMPT_EFFECTIVENESS = True

# Sprint48 - Adaptive Prompt Optimization Engine. Off by default. Only
# takes effect when ENABLE_PROMPT_EFFECTIVENESS also produced
# prompt_metrics - if Effectiveness is disabled (or failed), image_prompt
# stays byte-for-byte identical regardless of this flag.
ENABLE_PROMPT_OPTIMIZATION = False

# Sprint49 - Self-Learning Prompt Engine.
#
# Sprint66 (Stage 1)에서 켰다. 인메모리 카운터만 갱신하고 project_data에
# 키를 추가하지도, data["scenes"]를 바꾸지도 않으므로 생성 산출물에
# 영향이 없다. ENABLE_PROMPT_EFFECTIVENESS가 만들어 준 prompt_metrics가
# 있어야만 동작한다.
#
# 학습 상태는 프로세스 메모리에만 있다 - 재시작하면 사라진다. Stage 1은
# 그 스냅샷을 prompt_metrics.json에 관측용으로 기록하기만 하고,
# 영속화는 Optimization이 학습 결과를 실제로 소비하는 단계의 과제로
# 남겨 둔다.
ENABLE_PROMPT_LEARNING = True

# Sprint50 - AI Director v1.
#
# Sprint67 (Stage 2)에서 켰다. 다른 엔진들의 결과만 읽어 scene마다
# accept/review/regenerate 권고를 계산하는 순수 규칙 엔진이다 - LLM도,
# DB도, 파일 I/O도 없고 data["scenes"]를 비롯한 어떤 생성 산출물도
# 건드리지 않는다. 결정은 script.json이 아니라 관측 산출물로 나간다
# (pipeline.MEASUREMENT_ONLY_KEYS 참고).
#
# 주의: asset_quality_service는 아직 파이프라인에 연결되어 있지 않아
# asset 쪽 판단은 항상 unknown이고, ENABLE_SCENE_PLANNER가 꺼져 있어
# best_pattern 매칭도 일어나지 않는다. 즉 지금 결정은 사실상
# prompt_metrics 하나에만 근거한다.
ENABLE_AI_DIRECTOR = True

# Sprint51 Phase 1 - Viral Writer Engine. Off by default. Only swaps which
# prompt template script_service.generate_script() sends to Gemini - the
# output JSON shape (title/hook/script/scenes[scene,narration,image_prompt])
# is unchanged either way, so every downstream module (Sprint44-50) keeps
# working without modification. Flag off means byte-for-byte identical
# behavior to pre-Sprint51.
ENABLE_VIRAL_WRITER = False
