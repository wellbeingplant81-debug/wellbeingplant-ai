IMAGE_PROMPT_RULES = """===========================
Image Prompt 규칙
===========================

반드시 영어만 사용.

한 문장으로 작성.

Scene 내용을 실제 사진처럼 묘사한다.

각 image_prompt에는 다음 요소를 자연스럽게 녹여서 작성한다.

- Subject (누가/무엇이 등장하는지)
- Action (어떤 행동을 하고 있는지)
- Environment (어디에 있는지, 배경)
- Lighting (조명)
- Camera angle (카메라 앵글)
- Mood (전체적인 분위기)

Emotion과 Composition은 장면을 더 살릴 때만 선택적으로 포함한다.

인물이 중심인 장면(웰빙/건강 정보 등)에서는 자연스럽게 Korean people로 묘사한다.
음식, 동물, 풍경처럼 사람이 중심이 아닌 장면에서는 인종을 임의로 지정하지 않고
장면에 맞는 피사체를 그대로 묘사한다.

문장은 간결하고 정보 밀도가 높게 작성한다.
불필요한 수식어나 키워드 나열로 문장을 늘리지 않는다.

Ultra realistic, Photorealistic, Magazine quality, Correct anatomy와 같은
일반적인 화질/스타일 키워드는 이미지 생성 단계에서 채널 스타일로
별도 적용되므로 image_prompt에 다시 반복하지 않는다.

image_prompt는 오직 이 장면만의 구체적인 내용(피사체, 행동, 배경,
카메라, 조명, 분위기)에 집중한다.

===========================
Scene 1 (Hook Scene) 규칙
===========================

Scene 1은 영상의 커버 프레임이자 첫인상 역할을 하므로,
다른 Scene보다 시각적으로 더 강해야 한다.

Scene 1의 image_prompt는 다음을 우선한다.

- 인물이 등장하면 강한 표정 (놀람, 호기심, 강한 감정)
- 보는 사람의 호기심을 자극하는 구도
- 강한 시각적 대비
- 깔끔하고 단순한 구도
- 크고 명확하게 보이는 피사체
- 배경 잡동사니 최소화
- 강하고 인상적인 조명

===========================
Scene 구성 규칙
===========================

Scene 1은 위 Hook Scene 규칙을 최우선으로 따른다.

Scene 2 ~ 마지막 Scene은 Scene 1 및 서로 간에 반드시

- 다른 카메라 앵글
- 다른 거리
- 다른 구도
- 다른 표정
- 다른 조명
- 다른 배경

을 사용한다.

예시

Close-up, framing tightly on the subject's face or a key detail

Medium shot, showing the subject from the waist up

Wide shot, showing the subject within their full surrounding environment

Over-the-shoulder shot, camera positioned behind a person's shoulder with the main subject visible past the foreground shoulder or silhouette

Low angle, camera positioned below the subject looking upward

High angle, camera positioned above the subject looking downward

Top-down view, camera directly above the subject looking straight down

Eye-level shot, camera at the same height as the subject's eyes

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

bad anatomy"""
