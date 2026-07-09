WELLBEING_STYLE = """
Ultra realistic,
Photorealistic,
Authentic documentary photography,
National Geographic photography,
Premium commercial photography,
Professional medical photography,
Editorial photography,

Korean people,
Natural facial expression,
Realistic eyes,
Natural skin pores,
Healthy skin,
Natural imperfections,
Correct human anatomy,
Realistic hands,
Correct fingers,

Soft cinematic lighting,
Warm natural sunlight,
Golden hour lighting,
High dynamic range lighting,

85mm portrait photography,
Professional depth of field,
Beautiful background separation,
Professional composition,
Rule of thirds,
Magazine quality,
Filmic color grading,
Ultra detailed,
Extremely sharp focus,
Hyper realistic,
Vertical composition 9:16,

No text,
No watermark,
No logo,
No illustration,
No cartoon,
No CGI,
No 3D render,
No plastic skin,
No deformed hands,
No extra fingers,
No blurry face
"""


# Sprint60 Hotfix - 문제1: visual_type="ai"(혈관/세포/장내세균/콜레스테롤
# 등 인체 내부·미생물·생화학 주제) scene 전용 스타일. WELLBEING_STYLE은
# "Korean people, Natural facial expression, Correct human anatomy, 85mm
# portrait photography"를 강제하고 "No illustration/No CGI"를 금지해서,
# image_prompt 자체가 깨끗한 의료/미생물 묘사여도 Imagen이 사람 얼굴과
# 의료 이미지를 억지로 합성하는 결과가 나왔다(2026-07-09 E2E 실측 -
# scene2.png에서 장내세균 사이에 사람 얼굴/손이 합성됨). 이 스타일은
# 정반대로 사람 요소를 금지하고 일러스트/과학 시각화를 허용한다.
MEDICAL_ILLUSTRATION_STYLE = """
Medical illustration,
Scientific visualization,
Cross-sectional anatomy diagram,
Microscopic macro photography,
Biology textbook illustration,
3D rendered medical animation,
Volumetric lighting,

Vivid saturated colors,
Dramatic dark background,
High contrast studio lighting,

Ultra detailed,
Extremely sharp focus,
Hyper realistic textures,
Scientifically accurate,
Vertical composition 9:16,

No text,
No watermark,
No logo,
No person,
No people,
No human,
No face,
No hands,
No fingers,
No portrait,
No skin,
No selfie
"""


MEDICAL_ILLUSTRATION_NEGATIVE_PROMPT = (
    "text, watermark, logo, person, people, human, human model, face, "
    "portrait, hands, fingers, skin, selfie"
)


FOODBEAT_STYLE = """
Ultra realistic food photography,
Premium food commercial,
Fresh water droplets,
Highly detailed texture,
Restaurant quality,
Luxury food advertisement,

Warm studio lighting,
Soft reflection,
Natural shadows,
Realistic colors,
Professional composition,
Magazine quality,
Extremely detailed,
Vertical composition 9:16,

No text,
No watermark,
No logo,
No illustration,
No cartoon,
No CGI
"""


MINDTAIL_STYLE = """
Emotional cinematic illustration,
Studio Ghibli inspired atmosphere,
Soft watercolor style,
Beautiful natural landscape,
Warm sunset lighting,
Dreamlike composition,
Emotional storytelling,
Cute expressive animals,
Highly detailed,
Premium animation concept art,
Beautiful color harmony,
Vertical composition 9:16,

No text,
No watermark,
No logo
"""


THUMBNAIL_STYLE = """
Ultra realistic,
Photorealistic,
Professional photography,
Cinematic lighting,
High dynamic range,
Bright color grading,
Extremely sharp focus,
Magazine quality,
Extremely detailed,
Vertical composition 9:16,

No text,
No watermark,
No logo,
No illustration,
No cartoon,
No CGI
"""


HOOK_SCENE_STYLE_BOOST = """
Strong dramatic lighting,
High visual contrast,
Extremely sharp focus,
Clean simple composition,
Large clear subject filling the frame,
Minimal background clutter
"""


WELLBEING_NEGATIVE_PROMPT = (
    "text, watermark, logo, illustration, cartoon, CGI, 3D render, "
    "plastic skin, deformed hands, extra fingers, blurry face"
)

FOODBEAT_NEGATIVE_PROMPT = (
    "text, watermark, logo, illustration, cartoon, CGI"
)

MINDTAIL_NEGATIVE_PROMPT = (
    "text, watermark, logo"
)

THUMBNAIL_NEGATIVE_PROMPT = (
    "text, watermark, logo, illustration, cartoon, CGI, 3D render, "
    "plastic skin, deformed hands, extra fingers, blurry face"
)

HOOK_SCENE_NEGATIVE_PROMPT = (
    "text, watermark, logo, illustration, cartoon, CGI, 3D render, "
    "plastic skin, deformed hands, extra fingers, blurry face"
)
