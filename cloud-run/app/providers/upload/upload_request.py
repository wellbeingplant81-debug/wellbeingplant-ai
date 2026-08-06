"""
Epic 46 Sprint 001 - Publisher Foundation.

UploadProvider.upload(file_path, metadata)의 두 인자를 하나로 묶어
전달하고 싶을 때 쓰는 값 객체다. 기존 UploadProvider/MockUploadProvider/
YouTubeUploadProvider/UploadService의 upload() 시그니처는 전혀 바꾸지
않는다 - 이 클래스는 순수 추가(Additive)이며, 기존 15개 이상의 호출부/
테스트에 영향을 주지 않는다(Regression Zero).
"""

from dataclasses import dataclass, field


@dataclass
class UploadRequest:
    file_path: str
    metadata: dict = field(default_factory=dict)
