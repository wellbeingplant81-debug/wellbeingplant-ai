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
# Sprint68 (Stage 3)에서 켰다가 되돌렸고, Sprint69에서 카메라 충돌을
# 없앤 v2로 다시 재 봤지만 여전히 켜지 않았다. 이유는 "나빠져서"가
# 아니라 "좋아졌다고 말할 근거가 없어서"다.
#
# Sprint69 A/B가 뜻밖에 알려 준 것: 같은 설정으로 두 번 돌린 결과가
# Gemini Vision 기준 overall_quality 40 vs 90, image_realism 50 vs 85,
# character_consistency 20 vs 80으로 갈렸다. 프롬프트가 완전히 동일한
# 두 실행이다 - Imagen이 매번 다른 그림을 그리고 평가자도 흔들리기
# 때문이다. 이 잡음 폭(overall 기준 ~50점)이 Enrichment가 낼 수 있는
# 어떤 효과보다 크다. 실행 한 번짜리 A/B로는 판정 자체가 불가능하다.
#
# Sprint68에서 "scene 4의 가짜 라벨은 카메라 충돌 탓"이라고 적었던 것은
# 과했다. Sprint69에서는 enrichment를 전혀 걸지 않은 baseline 쪽에
# 'IMPROVED 3LOO' 같은 가짜 텍스트가 나왔다. 텍스트 아티팩트는
# Imagen 샘플링의 성질이지 Enrichment가 만든 것이 아니다.
#
# 다만 Sprint69의 v2 자체는 유지한다. Planner가 프롬프트에 이미 있는
# 카메라 지시를 덮어쓰지 않는 것은 A/B와 무관하게 옳고, 결정론적
# 테스트로 검증된다(tests/test_scene_planner_v2.py).
#
# 다시 켜려면 필요한 것은 더 나은 프롬프트가 아니라 더 나은 측정이다 -
# arm당 여러 번 생성해 평균을 내거나, 사람이 직접 비교 판정하는 절차.
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

# Sprint48 - Adaptive Prompt Optimization Engine.
#
# Sprint72에서 켜지 않기로 확정했다. 이 엔진은 prompt_metrics 점수를
# 올리는 방향으로 프롬프트를 고치는데, 그 점수가 실제 품질과 상관이
# 있다는 근거가 없다.
#
# 실측(프로젝트 36개, scene 216개, 기존 평가 산출물 재분석):
#
#   항목               변동    realism 상관   composition 상관
#   prompt_preserved   없음(216/216 통과)   -          -
#   camera             없음(216/216 통과)   -          -
#   visual_type        없음(216/216 통과)   -          -
#   purpose            없음(216/216 통과)   -          -
#   duplicate_free     없음(216/216 통과)   -          -
#   length             있음               r=0.098    r=0.221
#   keywords           있음               r=-0.001   r=0.050
#   score(합계)        있음               r=-0.023   r=0.000
#
# 100점 중 85점을 차지하는 다섯 항목이 216개 관측치에서 한 번도 실패한
# 적이 없다. 상수는 무엇도 예측할 수 없다 - 상관이 0이라는 뜻이 아니라
# 애초에 재고 있는 것이 없다는 뜻이다. 나머지 항목도 |r| < 0.3으로
# 약하고, 총점과 realism의 상관은 사실상 0(-0.023)이다.
#
# 그래서 Optimization을 켜면 품질과 무관한 숫자를 향해 프롬프트를
# 고치게 된다. Stage 3에서 실제로 그런 일이 있었다 - 점수가 90 -> 100으로
# 오르는 동안 이미지는 나빠졌다.
#
# 착수 조건: 목적함수를 먼저 다시 정의해야 한다. 지금 있는 신호 중
# 품질과 연결된 것은 Gemini Vision 평가뿐이고, 그건 생성 후에만 나온다.
# scripts/validate_prompt_metrics.py로 언제든 다시 잴 수 있다.
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

# Sprint71 - Character Consistency Engine v1.
#
# Release Gate를 통과해서 켰다. 이 저장소에서 A/B로 승인된 첫 엔진이다.
#
# 무엇을 고쳤나: character_consistency가 5회 측정에서 전부 0점이었는데,
# 원인은 렌더가 아니라 대본이었다. Writer가 scene 1에 "middle-aged
# Korean man", scene 3에 "Korean woman in her 50s", scene 5에 "elderly
# Korean couple"을 써 놓으니 같은 사람이 나올 수가 없었다.
#
# 이 플래그는 두 가지를 함께 켠다. 분리할 수 없다 - 대본만 고치면
# Pexels 스톡이 매번 다른 실제 사람을 돌려주고, 라우팅만 바꾸면 대본이
# 여전히 다른 사람을 요구한다.
#
# 1. Writer에게 "인물은 한 명, 외형 묘사는 매 scene 동일" 규칙을 준다
#    (app/prompts/character_consistency_rules.py).
# 2. 인물이 등장하는 scene을 Imagen으로 보낸다
#    (app/services/character_consistency_engine.py).
#
# Release Gate (Evaluation Framework v2, arm당 5회, 단측 정확 순열검정):
#
#   character_consistency   0.0 -> 86.6   p=0.0040
#   overall_quality        11.0 -> 75.0   p=0.0040
#   composition            39.0 -> 88.0   p=0.0079
#   image_realism          67.0 -> 72.0   p(열세)=0.6151  악화 없음
#
# 앞의 두 지표는 p가 1/252로 이 표본에서 나올 수 있는 최소값이다 -
# candidate 5회가 baseline 5회보다 전부 높았다는 뜻이다.
# character_consistency는 baseline이 5회 모두 0, candidate가 65~100으로
# 분포가 아예 겹치지 않았다.
#
# 비용: 인물 scene이 Pexels(무료)에서 Imagen으로 옮겨가므로 영상당
# Imagen 호출이 3~4회 늘어난다. 그만한 값을 한다는 것이 위 수치다.
ENABLE_CHARACTER_CONSISTENCY = True

# Sprint73 - Intelligent Regeneration Engine 비용 상한.
#
# 재생성 루프는 원래 재시도 횟수(QUALITY_MAX_RETRY)로만 제한됐다.
# scene 6개짜리 영상이면 최대 18번의 Imagen 호출이 가능하고, 그 사이
# 사이클마다 Gemini 평가도 한 번씩 붙는다.
#
# 이 값은 영상 하나에 쓸 수 있는 재생성 이미지 생성의 총 횟수다.
# 6으로 둔 것은 "한 영상의 scene 수만큼"이라는 감각 - 평균적으로
# 문제 있는 scene을 한 번씩 다시 그릴 만큼이고, 그 이상은 개선이
# 확인될 때만 의미가 있는데 그 확인은 MIN_IMPROVEMENT가 따로 한다.
#
# 예산이 남아도 품질이 오르지 않으면 멈추고, 품질이 올라도 예산이
# 없으면 멈춘다. 둘 다 로그에 사유가 남는다.
REGENERATION_MAX_IMAGE_CALLS = 6

# Sprint74 - Best-of-N Asset Selection Engine.
#
# 지금은 Imagen이 그린 첫 장을 그대로 쓴다. 그 장이 나쁘면 렌더가 끝나고
# Gemini 평가가 나온 뒤에야 알게 되고, 거기서부터 재생성 사이클이 돈다 -
# 이미지 한 장, 전체 평가 한 번, 그리고 영상 전체 재렌더.
#
# Best-of-N은 그 판단을 렌더 앞으로 당긴다. 후보를 N장 뽑아 그 자리에서
# 고르고, 재생성은 그러고도 안 될 때만 돈다.
#
# 근거: 축적된 평가 53건에서 ai_image scene 점수는 평균 78.9, 표준편차
# 24.2, 재생성 권고 20%였다. Best-of-N이 버는 것은 전적으로 그 분산인데,
# 그 표본은 스프린트마다 설정이 다른 실행을 섞은 것이라 분산의 얼마가
# "같은 프롬프트의 후보 사이" 것인지는 구분되지 않는다.
#
# False로 둔다. Production 플래그를 True로 올리는 것은 Evaluation
# Policy v3에서 Level 3(Release Gate, arm당 5회, 통계 검정)를 요구한다.
ENABLE_BEST_OF_N = False

# scene 하나에 뽑을 후보 장수. 1이면 예전 동작 그대로다.
BEST_OF_N_CANDIDATES = 2

# 영상 하나에 쓸 수 있는 후보 이미지의 총량. scene의 첫 장도 여기
# 포함된다 - 그것이 실제로 나가는 Imagen 호출 수이고, 비용을 볼 때
# 필요한 숫자도 그것이기 때문이다.
#
# 12는 scene 6개짜리 영상에서 전부 2장씩 뽑을 수 있는 값이다. 예산이
# 모자라면 앞 scene부터 두 번째 장을 받고, 뒤 scene은 한 장으로 간다.
# 어느 scene도 0장이 되지는 않는다.
BEST_OF_N_MAX_CANDIDATES = 12


# Sprint91 - 실제 YouTube 업로드.
#
# RealYouTubeRuntime.login()과 youtube_upload_step_service가 둘 다 이
# 플래그를 먼저 본다. False면 자격증명 체인을 아예 건드리지 않는다 -
# 실제 토큰이 있어도 마찬가지다.
#
# 이 저장소에서 실제 업로드는 아직 한 번도 검증되지 않았다. Evaluation
# Policy v3에 따라 True로 올리려면 Level 3 Release Gate가 필요하다.
ENABLE_YOUTUBE_UPLOAD = False
