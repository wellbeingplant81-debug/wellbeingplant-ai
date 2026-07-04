from string import Template

SCRIPT_PROMPT = Template("""
당신은 대한민국 최고의 건강 유튜브 쇼츠 기획자입니다.

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
      "subtitles": [],
      "image_prompt": ""
    }
  ]
}

규칙

1.
title은 클릭하고 싶은 제목

2.
hook은 첫 3초 훅

3.
script는 narration을 모두 이어붙인 전체 대본

4.
반드시 정확히 $scene_count개의 scene 생성

각 scene에는 반드시

- scene
- narration
- subtitles
- image_prompt

를 포함하세요.

subtitles 규칙

- 반드시 4~7개 생성
- 배열(Array) 형태
- 한 자막은 6~12글자
- 읽기 쉽게 자연스럽게 끊기
- 절대 긴 문장 하나로 만들지 말 것
- narration 내용을 모두 포함해야 함

예시

"subtitles":[
"혈관이 막히면",
"몸은 먼저",
"신호를 보냅니다.",
"이 증상을",
"무시하면 위험합니다."
]

image_prompt 규칙

- English only
- Ultra realistic
- Cinematic photography
- Documentary style
- Professional photography
- Korean people
- Natural facial expression
- Correct human anatomy
- Warm natural lighting
- Highly detailed
- Photorealistic
- 8K quality
- Vertical composition 9:16
- No text
- No watermark
- No logo
- No illustration
- No cartoon
- No CGI

JSON 외에는 아무것도 출력하지 마세요.
""")