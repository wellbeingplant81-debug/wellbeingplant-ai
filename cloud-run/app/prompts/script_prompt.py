from string import Template

SCRIPT_PROMPT = Template("""
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
Image Prompt 규칙
===========================

반드시 영어만 사용.

한 문장으로 작성.

Scene 내용을 실제 사진처럼 묘사한다.

다음 스타일을 자연스럽게 포함한다.

Authentic documentary photography,
Editorial photography,
National Geographic style,
Premium commercial photography,
Ultra realistic,
Hyper realistic,
Photorealistic,
Magazine quality,
Extremely detailed,
Ultra sharp focus,
Natural lighting,
Soft cinematic lighting,
Golden hour lighting,
High dynamic range,
Professional composition,
Rule of thirds,
Shallow depth of field,
85mm portrait lens,
Natural skin texture,
Realistic eyes,
Correct human anatomy,
Correct hands,
Correct fingers,
Natural facial expression,
Korean people,
Vertical composition 9:16

===========================
Scene 구성 규칙
===========================

각 Scene은 반드시

- 다른 카메라 앵글
- 다른 거리
- 다른 구도
- 다른 표정
- 다른 조명
- 다른 배경

을 사용한다.

예시

Close-up

Medium shot

Wide shot

Over shoulder

Low angle

High angle

Top view

Eye level

등을 적절히 섞는다.

===========================
상황별 규칙
===========================

의료 장면

실제 병원 다큐멘터리처럼.

건강 장면

실제 건강 프로그램 촬영처럼.

음식 장면

프리미엄 음식 광고처럼.

운동 장면

실제 스포츠 광고처럼.

인물

실제 한국인처럼.

===========================
절대 포함 금지
===========================

text

subtitle

caption

watermark

logo

illustration

cartoon

anime

CGI

3D render

plastic skin

low quality

blurry

extra fingers

deformed hands

duplicate person

cropped face

bad anatomy

===========================

JSON 외에는 아무것도 출력하지 마세요.
""")