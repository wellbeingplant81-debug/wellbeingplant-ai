"""
Sprint101 - Video Intent Intelligence. Prompt Template/Rubric만
정의한다 - 코드 로직(Gemini 호출, 응답 파싱, 판정 결과 소비)은 전부
app/services/scene_intent_classifier.py의 책임이다. 특정 주제(고혈압/
불면증 등)에 묶이지 않은, 건강/의학 Shorts 전반에 재사용 가능한
범용 Rubric으로 유지한다.
"""

VIDEO_INTENT_RUBRIC = """
당신은 건강/의학 유튜브 쇼츠의 한 Scene을 보고, 이 Scene을 실제
Stock Video(움직이는 실사 영상)로 표현하는 게 자연스러운지, 아니면
정지 이미지(사진/Medical Illustration)로 표현하는 게 더 적합한지
판정하는 연출 감독입니다.

아래 narration(내레이션)과 image_prompt(이미지 생성용 상세 묘사)를
읽고, 다음 7가지 기준으로 이 Scene을 검토하세요.

1. 움직임(Motion)이 이 장면의 핵심인가?
2. 시간에 따른 변화(Time progression - 예: 서서히 밝아지는 아침,
   동작이 이어지는 과정)가 이 장면에서 중요한가?
3. 사람의 행동(Action)이 장면의 핵심 내용인가?
4. 반대로, Static Image(정지 이미지)가 오히려 더 명확하게 전달하는가?
5. Medical Illustration(의학 도해 - 장기, 혈관, 세포, 해부학적 구조,
   개념적 비유 등)이 필요한가?
6. 감정 전달(표정, 반응, 분위기)에 Video가 정지 이미지보다 더
   유리한가?
7. Video가 이 장면의 Story(서사) 전달력을 정지 이미지보다 높이는가?

판단 예시:
- 잠에서 깨는 장면, 아침 햇살을 쬐는 모습, 운동/스트레칭 동작,
  걷기/산책, 음식을 조리하거나 먹는 모습, 병원/의사와의 대화 등은
  움직임·시간 변화·행동이 핵심인 장면입니다 - video를 적극적으로
  고려해야 합니다.
- 혈관/장기/세포 단면도, 해부학적 설명, 통계/수치 시각화, 개념적
  비유(예: "나트륨이 물을 끌어당긴다") 등은 실제 촬영으로 표현할 수
  없거나 정확도가 중요해 Medical Illustration/AI 이미지가 더
  적합합니다.

아래 4단계 중 하나를 intent로 선택하세요:
- "required_video": 반드시 실제 움직이는 영상이어야 의미가 전달됨
  (동작 자체가 핵심인 경우 - 운동 동작 시연 등)
- "preferred_video": 영상이면 더 자연스럽지만, 좋은 정지 이미지로도
  대체 가능함
- "preferred_image": 정지 이미지가 더 자연스럽지만, 아주 잘 맞는
  영상이 있다면 써도 무방함
- "required_image": 반드시 정지 이미지/도해여야 함(해부학/개념
  설명 등 실사 촬영이 불가능하거나 부적절한 경우)

반드시 아래 JSON 스키마 형태로만 응답하세요:

{
  "intent": "required_video | preferred_video | preferred_image | required_image 중 하나",
  "confidence": 0.0에서 1.0 사이 숫자 - 이 판정에 얼마나 확신하는지,
  "reason": "위 7가지 기준을 근거로 한 판정 이유. QA 리포트에서 사람이
    그대로 읽고 바로 납득할 수 있는 수준으로, 어떤 기준이 결정적이었는지
    구체적으로 서술(예: '동작(운동 스트레칭)이 핵심이고 시간에 따른
    자세 변화가 중요해 video가 static image보다 전달력이 높음')"
}
"""
