"""
Sprint89 (GREEN) - Production Profile Foundation v1.

"development"/"upload" 두 프로파일의 설정(duration_target/tts_provider/
asset_strategy)을 조회하는 단일 진입점. 설정값만 제공하고 Pipeline/
Planner/UploadAssetStrategy는 전혀 건드리지 않는다.
"""

DEFAULT_PROFILE_NAME = "development"

PROFILES = {
    "development": {
        "profile": "development",
        "duration_target": 45,
        "tts_provider": "chirp",
        "asset_strategy": "default",
    },
    "upload": {
        "profile": "upload",
        "duration_target": 55,
        "tts_provider": "elevenlabs",
        "asset_strategy": "upload",
    },
}


class ProductionProfile:

    @staticmethod
    def get(profile_name):
        return PROFILES.get(profile_name, PROFILES[DEFAULT_PROFILE_NAME])
