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

narration 목표 글자 수
전체 약 $target_chars자 (문장부호/공백 제외 기준) - 이 글자 수에 최대한
맞춰 작성하세요.

Scene 개수
정확히 $scene_count개
$retry_feedback
반드시 JSON만 출력하세요.

{
  "title": "",
  "hook": "",
  "script": "",
  "scenes": [
    {
      "scene": 1,
      "narration": "",
      "image_prompt": ""
    }
  ]
}

===========================
규칙
===========================

1.
title은 클릭하고 싶은 제목

2.
hook은 첫 3초를 사로잡는 문장

3.
script는 narration 전체를 이어붙인 내용

4.
정확히 $scene_count개의 scene 생성

각 Scene은 반드시

- scene
- narration
- image_prompt

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