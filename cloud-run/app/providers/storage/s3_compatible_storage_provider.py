"""
EPIC S3-Compatible Storage Provider (Production) - S3CompatibleStorageProvider.

첫 번째 실제(Local/Mock이 아닌) StorageProvider 구현체다 - 하지만
AWS 전용도, Cloudflare R2 전용도 아니다. boto3(AWS 공식 SDK)의 S3
클라이언트가 endpoint_url 하나만 바꾸면 AWS S3/Cloudflare R2(공식
문서화된 방식)/MinIO 어디든 동일하게 접속된다는 사실 위에 서 있다 -
이 파일 어디에도 "R2"나 "AWS"라는 이름이 등장하지 않는다("설정만
바꾸면 사용할 수 있어야 한다").

새 의존성(boto3) 사용 이유 - S3 호환 API는 AWS Signature V4라는
복잡하고 보안에 민감한 서명 프로토콜을 요구한다(OpenAI/Instagram처럼
단순 Bearer 토큰이 아니다). 이 프로젝트의 기존 관례(requests 직접
호출)로 손수 재구현하면 서명 버그가 인증 실패나 보안 문제로 이어질
위험이 크다 - boto3는 이 서명을 대신 처리해 주는 검증된 표준 라이브러리
이고, endpoint_url 재정의가 공식적으로 지원되는 1급 시나리오다.

upload()가 만드는 key는 원본 파일명 앞에 uuid4 hex를 붙인다 - 같은
파일명(예: final_short.mp4)을 여러 번 올려도 서로 덮어쓰지 않는다.
public_url()은 presigned URL을 만들지 않는다 - public_base_url이
설정돼 있다는 것은 버킷/CDN이 이미 공개 읽기로 구성돼 있다는 뜻이라,
단순 문자열 결합만으로 충분하다(불필요한 서명 왕복을 만들지 않는다).
"""

import logging
import os
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.providers.storage.cloud_storage_provider import CloudStorageProvider
from app.providers.storage.s3_compatible_storage_config import S3CompatibleStorageConfig
from app.providers.storage.storage_provider import StorageHealth

logger = logging.getLogger(__name__)

_NOT_FOUND_ERROR_CODES = {"404", "NoSuchKey", "NotFound"}


def _mask_access_key(access_key: str) -> str:
    # Storage 연결 테스트 디버깅 확인 - Secret Key는 로그에 절대 남기지
    # 않는다(디스크 평문 로그 파일 = 자격 증명 유출). Access Key ID는
    # AWS/R2 관례상 Secret만큼 민감하지 않지만(공개 식별자에 가깝다),
    # 그래도 앞부분만 남긴다.
    if not access_key:
        return "(empty)"
    if len(access_key) <= 8:
        return "***"
    return f"{access_key[:8]}..."

# Storage 연결 테스트 400 Bad Request 확인 - botocore 1.36+가 S3
# 요청(특히 Put/Get류)에 기본으로 Checksum 헤더(x-amz-sdk-checksum-
# algorithm 등)를 추가하기 시작했다(boto3 공식 공지, GitHub Issue
# #4392 - "AWS SDK for Python v1.36.0... adopts new default integrity
# protections"). AWS S3는 이를 이해하지만, Cloudflare R2를 포함한 대부분
# S3 호환 서비스는 이 헤더를 모른다 - HeadBucket은 스펙상 본문 없는
# 400/403/404만 돌려줘 원인을 알 수 없다(AWS 공식 문서: "the HEAD
# request returns a generic 400 Bad Request, 403 Forbidden, or 404 Not
# Found... A message body isn't included"). boto3/botocore 공식 권장
# 해결책(when_required)을 그대로 적용한다 - 실제 AWS S3에도 안전하다
# (그저 기본 정책보다 덜 적극적으로 Checksum을 요구할 뿐).
_S3_COMPATIBILITY_CONFIG = Config(
    request_checksum_calculation="when_required",
    response_checksum_validation="when_required",
)


class S3CompatibleStorageProvider(CloudStorageProvider):

    def __init__(self, config: S3CompatibleStorageConfig, client=None):
        self.config = config
        self._client = client or self._build_client()

    def _build_client(self):
        # Storage 연결 테스트 디버깅 확인 - "boto3.client 생성 시 실제
        # 실행값을 로그로 출력해달라"는 요청. Secret Key는 아예 포함하지
        # 않는다.
        logger.info(
            "S3-compatible client config: endpoint_url=%s region_name=%s bucket=%s "
            "aws_access_key_id=%s signature_version=s3v4(boto3 기본값) "
            "addressing_style=path(custom endpoint_url일 때 boto3 기본값) "
            "checksum_compat=request:%s,response:%s",
            self.config.endpoint_url, self.config.region, self.config.bucket,
            _mask_access_key(self.config.access_key),
            _S3_COMPATIBILITY_CONFIG.request_checksum_calculation,
            _S3_COMPATIBILITY_CONFIG.response_checksum_validation,
        )
        return boto3.client(
            "s3",
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=self.config.access_key,
            config=_S3_COMPATIBILITY_CONFIG,
            aws_secret_access_key=self.config.secret_key,
            region_name=self.config.region,
        )

    def upload(self, local_path: str) -> str:
        if not os.path.exists(local_path):
            raise FileNotFoundError(local_path)

        key = f"{uuid.uuid4().hex}_{os.path.basename(local_path)}"
        self._client.upload_file(local_path, self.config.bucket, key)
        return key

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.config.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.config.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND_ERROR_CODES:
                return False
            raise
        return True

    def public_url(self, key: str) -> str:
        if not self.config.public_base_url:
            return ""
        return f"{self.config.public_base_url.rstrip('/')}/{key}"

    def health(self) -> StorageHealth:
        request_log = {}
        events = getattr(self._client, "meta", None)
        events = getattr(events, "events", None) if events is not None else None

        def _capture_request(request, **kwargs):
            request_log["method"] = request.method
            request_log["url"] = request.url

        if events is not None:
            events.register("before-send.s3.HeadBucket", _capture_request)
        try:
            try:
                self._client.head_bucket(Bucket=self.config.bucket)
            finally:
                if events is not None:
                    events.unregister("before-send.s3.HeadBucket", _capture_request)
        except Exception as exc:
            message = str(exc)
            # Storage 연결 테스트 디버깅 확인 - "HeadBucket 요청 직전의
            # HTTP Request(URL)를 출력해달라"는 요청.
            logger.info(
                "HeadBucket failed: bucket=%s request=%s %s error=%s",
                self.config.bucket, request_log.get("method"), request_log.get("url"), message,
            )
            message = self._diagnose_with_list_buckets(message)
            return StorageHealth(available=False, message=message)
        return StorageHealth(available=True, message=f"{self.config.bucket} 연결됨")

    def _diagnose_with_list_buckets(self, original_message: str) -> str:
        # Storage 연결 테스트 디버깅 확인 - "HeadBucket 대신 list_buckets()
        # 를 실행해 원인을 찾아달라"는 요청. HeadBucket은 스펙상 원인
        # 없는 400/403/404만 돌려준다(AWS 공식 문서: "A message body
        # isn't included") - list_buckets()는 실제 오류 본문이 있는
        # API라 자격 증명 자체가 유효한지(계정 문제) vs 이 특정 Bucket만
        # 문제인지(이름 오타/대소문자/권한 범위)를 구분하는 데 쓴다.
        #
        # 주 연결 테스트 자체를 list_buckets()로 바꾸지는 않는다 - R2
        # API Token을 "Object Read & Write"로 특정 Bucket에만 좁혀
        # 발급한 경우(Cloudflare 공식 권장 사례) list_buckets()(계정
        # 전체 조회, Admin 권한 필요)는 그 자체로 권한 부족 실패한다 -
        # HeadBucket(Bucket 범위 권한과 호환)이 더 넓은 Token 구성과
        # 호환된다. AWS 전용 코드는 이 파일 어디에도 없다(코드 자체는
        # AWS S3에도 동일하게 쓰인다 - endpoint_url만 다를 뿐).
        try:
            response = self._client.list_buckets()
        except Exception as list_exc:
            logger.info("ListBuckets도 실패: %s", list_exc)
            return original_message

        visible = [b["Name"] for b in response.get("Buckets", [])]
        logger.info("ListBuckets 성공 - 보이는 Bucket: %s", visible)
        if self.config.bucket in visible:
            return original_message

        return (
            f"{original_message} | 자격 증명은 유효합니다(ListBuckets 성공) - 하지만 "
            f"Bucket '{self.config.bucket}'이(가) 보이는 목록에 없습니다: {visible}. "
            f"이름 철자/대소문자를 확인해주세요(R2는 대문자를 허용하지 않습니다)."
        )
