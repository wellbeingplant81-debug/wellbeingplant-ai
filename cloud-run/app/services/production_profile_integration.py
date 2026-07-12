"""
Sprint91 (GREEN) - Production Profile Integration v1.

Pipeline이 ProductionProfile을 읽을지 말지 결정하는 Feature Flag
진입점. enabled=False(기본값)면 profile_name과 무관하게 항상
"development" 프로파일을 반환해 기존 Pipeline 동작을 그대로 유지하고,
enabled=True일 때만 요청받은 profile_name(생략 시 "development")을
ProductionProfile에서 읽어 반환한다. 지금은 읽기만 할 뿐 Pipeline에는
아직 적용하지 않는다.
"""

from app.services.production_profile import ProductionProfile


class ProductionProfileIntegration:

    @staticmethod
    def load_profile(profile_name=None, enabled=False):

        if not enabled:
            return ProductionProfile.get("development")

        return ProductionProfile.get(profile_name)
