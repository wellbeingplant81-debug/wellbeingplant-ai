"""
Sprint75 - 이미지 프롬프트의 부정어.

여기 있던 긍정 스타일 블록(WELLBEING_STYLE 등)은 삭제했다. 그 블록들은
scene 문장 앞에 통째로 이어붙는 방식의 산물이었고, 한 문자열 안에
스타일, 인물 품질, 조명, 카메라, 구도, 부정어가 섞여 있었다. 그래서
사물 scene에 "Korean people"을 요구하고, scene이 정한 카메라와
"85mm portrait photography"가 싸웠다.

긍정 슬롯은 style_profiles.py가 담당한다. 부정어만 여기 남는다 -
슬롯 하나의 출처는 한 곳이어야 한다.
"""


MEDICAL_ILLUSTRATION_NEGATIVE_PROMPT = (
    "text, watermark, logo, person, people, human, human model, face, "
    "portrait, hands, fingers, skin, selfie"
)

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
