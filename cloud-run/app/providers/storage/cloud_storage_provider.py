"""
EPIC AssetPublisher (Production Infrastructure) - CloudStorageProvider.

실제 클라우드 저장소(AWS S3/Cloudflare R2/Google Cloud Storage/Azure
Blob 등)를 구현할 때 상속받을 추상 기반 클래스다. 이 Epic은 이 클래스를
구현하는 어떤 구체 클래스도 만들지 않는다("실제 Cloud Provider 구현
금지") - StorageProvider의 5개 계약(upload/delete/exists/public_url/
health)을 그대로 물려받을 뿐, 새 메서드를 추가하지 않는다.

이 클래스가 존재하는 이유는 순전히 의미적 구분이다 - "이건 클라우드
저장소를 위한 자리"라는 것을 코드 구조로 표시해 둔다(다음 Epic이
S3Provider(CloudStorageProvider)처럼 상속만 하면 되도록). Local/Mock
Provider는 이 클래스를 상속하지 않는다 - 클라우드가 아니기 때문이다.
"""

from app.providers.storage.storage_provider import StorageProvider


class CloudStorageProvider(StorageProvider):
    pass
