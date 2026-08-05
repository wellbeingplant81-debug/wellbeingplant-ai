QUALITY_MAX_RETRY = 3

# Sprint45 - Scene Planner Integration Engine. Off by default: the
# pipeline's default behavior/output (script.json shape included) must
# stay byte-for-byte identical unless this is explicitly turned on.
ENABLE_SCENE_PLANNER = False

# Sprint46 - Prompt Enrichment Engine. Off by default. Only takes effect
# when ENABLE_SCENE_PLANNER also produced a scene_plan - if Planner is
# disabled (or failed), image_prompt stays byte-for-byte identical
# regardless of this flag.
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
