"""
Sprint102 - 제작 단계 (Epic 54, Architecture Phase 1).

지금 파이프라인이 실제로 만드는 것에 이름을 붙였을 뿐이다. 새 단계를
발명하지 않았다 - 아래 산출물 경로는 studio_service가 이미 판정에 쓰고
있는 그 경로다.

Provider가 붙는 자리는 다섯이다. subtitle/video/quality는 제외했다 -
자막은 narration과 실제 오디오 길이에서 나오고, 영상은 렌더이고,
품질은 평가다. 셋 다 "어디서 가져올까"를 사용자가 고를 성질이 아니다.
"""

SCRIPT = "script"
IMAGE = "image"
VOICE = "voice"
MUSIC = "music"
METADATA = "metadata"

STAGES = (SCRIPT, IMAGE, VOICE, MUSIC, METADATA)

LABELS = {
    SCRIPT: "대본",
    IMAGE: "이미지",
    VOICE: "음성",
    MUSIC: "배경음악",
    METADATA: "메타데이터",
}

# 각 단계가 실제로 남기는 산출물. 이름을 여기서 새로 정하지 않는다 -
# studio_service._STAGES/MEDIA_KINDS와 같은 값이어야 하고, 그것을
# 테스트로 묶어 두었다.
ARTIFACTS = {
    SCRIPT: "script.json",
    IMAGE: "images",
    VOICE: "audio/final_audio.wav",
    MUSIC: None,          # BGM은 최종 영상에 섞여 들어간다 - 별도 산출물이 없다
    METADATA: "publish_package.json",
}


def is_stage(value: str) -> bool:
    return value in STAGES


def require_stage(value: str) -> str:
    if not is_stage(value):
        raise ValueError(
            f"알 수 없는 단계입니다: {value!r}. 사용 가능한 값: {list(STAGES)}"
        )
    return value
