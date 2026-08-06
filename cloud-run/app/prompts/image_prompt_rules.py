"""
Sprint75 - Prompt Intelligence v2.

Writer가 이미지 프롬프트를 문장 하나로 쓰지 않는다. 요소를 하나씩
적으면 Prompt Composer가 조립한다.

문장으로 받던 동안의 문제는 두 가지였다. 첫째, 어느 요소가 들어 있고
어느 것이 빠졌는지 알 수 없었다. 둘째, 조립 단계에서 채널 스타일
블록을 통째로 앞에 붙이는데 그 안에도 카메라와 조명과 인물 묘사가
들어 있어서, 대본이 정한 것과 정면으로 싸웠다.

이제 스타일/화질/부정어는 프로필이 담당한다. 이 규칙은 scene마다
다른 것만 요구한다.
"""


IMAGE_PROMPT_RULES = """===========================
Image Prompt 규칙
===========================

각 Scene의 이미지는 문장 하나가 아니라 아래 여섯 요소로 적는다.
전부 영어로 쓴다.

- subject      : 무엇이 화면에 있는가. 사람이면 인물 묘사, 사물이면
                 그 사물.
- action       : 그 피사체가 무엇을 하고 있는가. 정적인 장면이면
                 상태를 적는다.
- environment  : 어디인가. 배경과 장소.
- camera       : 카메라 앵글과 거리. 아래 목록에서 고른다.
- composition  : 화면 구성. 특별히 요구할 것이 없으면 비워 둔다.
- lighting     : 조명.

각 요소는 짧은 영어 구(phrase)로 적는다. 문장 부호로 여러 요소를
한 칸에 몰아넣지 않는다.

===========================
적지 말아야 할 것
===========================

화질/스타일 키워드는 적지 않는다. 이미지 생성 단계에서 채널 스타일로
따로 적용된다.

  예: ultra realistic, photorealistic, magazine quality,
      8k, highly detailed, professional photography

부정 표현은 적지 않는다. "no text", "without people" 같은 것은 별도의
negative prompt가 담당한다.

세로 화면 비율(9:16)도 적지 않는다. 생성 단계에서 지정된다.

===========================
camera 목록
===========================

close-up, framing tightly on the subject's face or a key detail

medium shot, showing the subject from the waist up

wide shot, showing the subject within their full surrounding environment

over-the-shoulder shot, camera behind a person's shoulder

low angle, camera below the subject looking upward

high angle, camera above the subject looking downward

top-down view, camera directly above looking straight down

eye-level shot, camera at the height of the subject's eyes

Scene마다 서로 다른 camera를 쓴다. 같은 앵글을 연속으로 쓰지 않는다.
거리(close/medium/wide)도 번갈아 쓴다.

===========================
Scene 1 (Hook Scene)
===========================

Scene 1은 영상의 커버 프레임이다. 다른 Scene보다 시각적으로 강해야
한다.

- 인물이 등장하면 강한 표정(놀람, 호기심, 강한 감정)을 subject에 적는다
- 피사체가 크고 명확하게 보이는 camera를 고른다
- 배경이 단순한 environment를 고른다

===========================
인물이 있는 Scene과 없는 Scene
===========================

사람이 등장하는 Scene의 subject에는 인물을 구체적으로 적는다.
웰빙/건강 주제에서는 Korean으로 적는다.

사람이 등장하지 않는 Scene(인체 내부, 음식, 사물, 풍경)의 subject에는
인물 묘사를 절대 넣지 않는다. 사람을 암시하는 표현("hands holding",
"a person's view")도 넣지 않는다. 억지로 사람을 등장시키지 않는다.

===========================
상황별 참고
===========================

의료 장면은 실제 병원 다큐멘터리처럼.
건강 장면은 실제 건강 프로그램 촬영처럼.
음식 장면은 프리미엄 음식 광고처럼.
운동 장면은 실제 스포츠 광고처럼."""
