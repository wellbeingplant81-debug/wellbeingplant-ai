"""
EPIC AssetPublisher (Production Infrastructure) - StorageAssetPublisher.

"AssetPublisher는 StorageProvider를 직접 선택하지 않는다. DI로 받는다."
이 클래스가 app.providers.storage.local_path_asset_publisher.
LocalPathAssetPublisher(Instagram Connector Epic)를 대체한다 - 이름을
바꾼 이유는 이제 이 클래스가 "Local 전용"이 아니기 때문이다(어떤
StorageProvider를 주입받느냐에 따라 실제로 공개 URL을 만들 수도 있다).
외부에서 이 클래스를 참조하는 곳은 이 파일의 테스트뿐이라 이름 변경의
위험이 낮다.

publish()는 두 가지 일만 한다 - (1) 로컬 파일의 실제 메타데이터(존재
여부/크기/MIME 타입)를 읽는다, (2) StorageProvider.upload()에 위임해
key를 얻고, StorageProvider.public_url(key)로 공개 URL을 얻는다. 어느
저장소를 쓰는지, 공개 URL을 실제로 만들 수 있는지는 전적으로 주입된
StorageProvider의 몫이다 - 이 클래스는 그 결과를 그대로 옮겨 담을
뿐이다. Provider가 예외를 던지면 그대로 전파한다(호출자, 예: Instagram
Adapter가 이미 공통 오류 처리를 한다 - 여기서 다시 잡지 않는다).

기본값(인자 없이 생성)은 LocalStorageProvider() - 지금 이 프로젝트의
실제 상태(공개 호스팅 인프라 없음)를 정직하게 반영한다.
"""

import mimetypes
import os

from app.providers.storage.asset_publisher import AssetPublisher
from app.providers.storage.asset_reference import AssetReference
from app.providers.storage.local_storage_provider import LocalStorageProvider
from app.providers.storage.storage_provider import StorageProvider


class StorageAssetPublisher(AssetPublisher):

    def __init__(self, storage_provider: StorageProvider = None):
        self.storage_provider = storage_provider or LocalStorageProvider()

    def publish(self, local_path: str) -> AssetReference:
        if not os.path.exists(local_path):
            # Phase 7, Sprint 3 - Retry Queue Root Cause Analysis(Sprint 2)
            # 에서 발견: 예전에는 FileNotFoundError(local_path)로 경로
            # 문자열 자체만 메시지였다 - Operations Center 화면에
            # 설명 없이 경로만 표시되어 운영자가 원인을 추측해야 했다.
            # 사람이 읽는 문장으로 바꾸되, 경로 자체는 그대로 포함해
            # 정보 손실은 없다.
            raise FileNotFoundError(f"동영상 파일을 찾을 수 없습니다: {local_path}")

        mime_type, _ = mimetypes.guess_type(local_path)
        file_size = os.path.getsize(local_path)

        key = self.storage_provider.upload(local_path)
        public_url = self.storage_provider.public_url(key)

        return AssetReference(
            local_path=local_path,
            public_url=public_url,
            mime_type=mime_type or "",
            file_size=file_size,
        )
