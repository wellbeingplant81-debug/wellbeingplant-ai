"""
Sprint75 - 이미지 프롬프트의 슬롯 어휘.

프롬프트를 문장이 아니라 구조로 만든다. 슬롯 이름을 한 곳에 모아 두는
이유는, 이 저장소에서 반복된 결함이 전부 "한 슬롯을 두 곳에서 쓴다"
였기 때문이다 - visual_type이 라우팅과 스타일을 겸했고, 채널 스타일
블록의 카메라가 scene의 카메라와 싸웠다. 슬롯이 이름을 갖고 있으면
누가 그 슬롯을 채우는지 물을 수 있다.
"""


SUBJECT = "subject"
ACTION = "action"
ENVIRONMENT = "environment"
CAMERA = "camera"
COMPOSITION = "composition"
LIGHTING = "lighting"
STYLE = "style"
NEGATIVE = "negative"
REFERENCE = "reference"
CONSTRAINTS = "constraints"


# 긍정 프롬프트에 들어가는 순서.
#
# scene이 정하는 것(무엇을, 무엇을 하고, 어디서)이 먼저 오고, 그 다음이
# 찍는 방법(카메라/구도/조명), 그 다음이 인물 앵커, 마지막이 매체와
# 제약이다. 구체적인 내용을 앞에 두는 것은 확산 모델이 앞쪽 토큰에 더
# 무게를 두기 때문이다 - 오트밀 그릇을 그리는데 스타일 블록 40줄이
# 먼저 오고 정작 그릇이 마지막에 오던 것이 지금까지의 순서였다.
POSITIVE_ORDER = (
    SUBJECT,
    ACTION,
    ENVIRONMENT,
    CAMERA,
    COMPOSITION,
    LIGHTING,
    REFERENCE,
    STYLE,
    CONSTRAINTS,
)

# NEGATIVE는 여기 없다. 부정은 negative_prompt로만 간다 - 확산 모델은
# 긍정문 안의 부정을 잘 처리하지 못하는데, 지금까지 "No text, No
# watermark"가 긍정 프롬프트에 들어가 있었고 같은 내용이 negative로도
# 따로 갔다.
ELEMENTS = POSITIVE_ORDER + (NEGATIVE,)


LABELS = {
    SUBJECT: "Subject",
    ACTION: "Action",
    ENVIRONMENT: "Environment",
    CAMERA: "Camera",
    COMPOSITION: "Composition",
    LIGHTING: "Lighting",
    REFERENCE: "Character reference",
    STYLE: "Style",
    CONSTRAINTS: "Constraints",
}
