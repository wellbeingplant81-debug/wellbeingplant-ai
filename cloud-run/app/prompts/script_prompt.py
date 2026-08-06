from string import Template

from app.prompts.image_prompt_rules import IMAGE_PROMPT_RULES

SCRIPT_PROMPT = Template(
    """
당신은 대한민국 최고의 건강 유튜브 쇼츠 기획자이며,
세계 최고 수준의 이미지 프롬프트 엔지니어입니다.

주제
$topic

영상 길이
약 $target_duration초

Scene 개수
정확히 $scene_count개

반드시 JSON만 출력하세요.

{
  "title": "",
  "hook": "",
  "script": "",
  "character": "",
  "scenes": [
    {
      "scene": 1,
      "narration": "",
      "subject": "",
      "action": "",
      "environment": "",
      "camera": "",
      "composition": "",
      "lighting": ""
    }
  ]
}

===========================
주제 고정 규칙 (최우선)
===========================

위에 적힌 주제가 이 영상의 소재다. 다른 소재로 바꾸지 않는다.

- 주제에 없는 소재를 주인공으로 삼지 않는다.
  (주제가 "물"이면 "커피" 영상을 만들지 않는다)
- title에는 주제의 핵심 단어가 최소 하나 그대로 들어간다.
  후킹 표현("이것", "충격")은 그 단어와 함께 써도 좋다.
- 모든 scene의 narration이 이 주제를 다룬다.
- 주제를 더 자극적인 소재로 바꾸는 것보다, 주제를 지킨 채
  표현을 강하게 하는 쪽을 택한다.

===========================
규칙
===========================

1.
title은 클릭하고 싶은 제목 (단, 주제 고정 규칙을 지킨다)

2.
hook은 첫 3초를 사로잡는 문장

3.
script는 narration 전체를 이어붙인 내용

4.
정확히 $scene_count개의 scene 생성

각 Scene은 반드시

- scene
- narration
- subject
- action
- environment
- camera
- composition
- lighting

를 포함한다.

===========================
Narration 규칙
===========================

- 자연스러운 한국어
- 말하듯 작성
- 6개 Scene을 이어 읽으면 약 $target_duration초
- Scene당 1~2문장
- 다음 Scene과 자연스럽게 연결
- 쇼츠에 맞는 템포 유지

===========================
Scene 1 선택 규칙
===========================

Scene 1은 영상의 썸네일 역할도 겸하므로, 도입부 중에서도
가장 시각적으로 강렬하고 감정이 분명한 순간을 선택한다.

단조롭거나 어둡고 무기력한 장면보다,
놀람, 호기심, 기대감 등 강한 감정을 보여줄 수 있는 순간을 우선한다.

단, 전체 스토리 흐름은 자연스럽게 유지한다.

"""
    + IMAGE_PROMPT_RULES
    + """

===========================

JSON 외에는 아무것도 출력하지 마세요.
"""
)