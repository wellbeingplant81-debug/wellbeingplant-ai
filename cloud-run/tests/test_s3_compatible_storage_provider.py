"""
EPIC S3-Compatible Storage Provider (Production) (RED->GREEN) -
desktop/application/assets/s3_compatible_storage_provider.py.

실제 boto3 Client는 전혀 만들지 않는다(Network/자격증명 불필요) -
FakeS3Client를 직접 주입해 upload/delete/exists/public_url/health의
실제 로직(키 생성, botocore ClientError 분류, 설정값 사용)만 검증한다.
별도로, client를 주입하지 않았을 때 boto3.client()가 config의 값
그대로(endpoint_url만 바꾸면 AWS/R2/MinIO 무엇이든) 호출되는지도
확인한다 - "Provider 내부에 하드코딩하지 않는다"는 요구를 직접 증명한다.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from botocore.exceptions import ClientError

from app.providers.storage.cloud_storage_provider import CloudStorageProvider
from app.providers.storage.s3_compatible_storage_config import S3CompatibleStorageConfig
from app.providers.storage.s3_compatible_storage_provider import (
    S3CompatibleStorageProvider,
)

_MODULE = "app.providers.storage.s3_compatible_storage_provider"


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Operation")


class FakeS3Client:

    def __init__(
        self, existing_keys=None, fail_head_bucket=False,
        list_buckets_result=None, fail_list_buckets=False,
    ):
        self.uploaded = []
        self.deleted = []
        self._existing_keys = set(existing_keys or [])
        self.fail_head_bucket = fail_head_bucket
        self._list_buckets_result = list_buckets_result
        self._fail_list_buckets = fail_list_buckets
        self.list_buckets_calls = 0

    def upload_file(self, Filename, Bucket, Key):
        self.uploaded.append((Filename, Bucket, Key))
        self._existing_keys.add(Key)

    def delete_object(self, Bucket, Key):
        self.deleted.append((Bucket, Key))
        self._existing_keys.discard(Key)

    def head_object(self, Bucket, Key):
        if Key not in self._existing_keys:
            raise _client_error("404")
        return {}

    def head_bucket(self, Bucket):
        if self.fail_head_bucket:
            raise _client_error("403")
        return {}

    def list_buckets(self):
        self.list_buckets_calls += 1
        if self._fail_list_buckets:
            raise _client_error("AccessDenied")
        names = self._list_buckets_result if self._list_buckets_result is not None else []
        return {"Buckets": [{"Name": name} for name in names]}


def _config(**overrides):
    fields = dict(
        endpoint_url="https://s3.amazonaws.com", bucket="my-bucket",
        region="us-east-1", access_key="ak", secret_key="sk",
        public_base_url="https://cdn.example.com",
    )
    fields.update(overrides)
    return S3CompatibleStorageConfig(**fields)


class TestS3CompatibleStorageProviderIsACloudStorageProvider(unittest.TestCase):

    def test_is_a_cloud_storage_provider_subclass(self):
        self.assertTrue(issubclass(S3CompatibleStorageProvider, CloudStorageProvider))


class TestS3CompatibleStorageProviderUpload(unittest.TestCase):

    def test_upload_calls_client_with_bucket_and_generated_key(self):
        client = FakeS3Client()
        provider = S3CompatibleStorageProvider(_config(), client=client)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"data")

            key = provider.upload(path)

        self.assertEqual(len(client.uploaded), 1)
        filename, bucket, uploaded_key = client.uploaded[0]
        self.assertEqual(filename, path)
        self.assertEqual(bucket, "my-bucket")
        self.assertEqual(uploaded_key, key)
        self.assertTrue(uploaded_key.endswith("video.mp4"))

    def test_upload_generates_unique_keys_for_same_filename(self):
        client = FakeS3Client()
        provider = S3CompatibleStorageProvider(_config(), client=client)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"data")

            key1 = provider.upload(path)
            key2 = provider.upload(path)

        self.assertNotEqual(key1, key2)  # 같은 파일명이어도 충돌하지 않는다.

    def test_upload_missing_local_file_raises_without_calling_client(self):
        client = FakeS3Client()
        provider = S3CompatibleStorageProvider(_config(), client=client)

        with self.assertRaises(FileNotFoundError):
            provider.upload("/no/such/file.mp4")

        self.assertEqual(client.uploaded, [])


class TestS3CompatibleStorageProviderDelete(unittest.TestCase):

    def test_delete_calls_client_with_bucket_and_key(self):
        client = FakeS3Client(existing_keys={"k1"})
        provider = S3CompatibleStorageProvider(_config(), client=client)

        provider.delete("k1")

        self.assertEqual(client.deleted, [("my-bucket", "k1")])


class TestS3CompatibleStorageProviderExists(unittest.TestCase):

    def test_exists_true_for_present_key(self):
        client = FakeS3Client(existing_keys={"k1"})
        provider = S3CompatibleStorageProvider(_config(), client=client)

        self.assertTrue(provider.exists("k1"))

    def test_exists_false_for_missing_key_404(self):
        client = FakeS3Client()
        provider = S3CompatibleStorageProvider(_config(), client=client)

        self.assertFalse(provider.exists("no-such-key"))

    def test_exists_reraises_unexpected_errors(self):
        client = MagicMock()
        client.head_object.side_effect = _client_error("500")
        provider = S3CompatibleStorageProvider(_config(), client=client)

        with self.assertRaises(ClientError):
            provider.exists("k1")


class TestS3CompatibleStorageProviderPublicUrl(unittest.TestCase):

    def test_public_url_combines_base_and_key(self):
        provider = S3CompatibleStorageProvider(_config(public_base_url="https://cdn.example.com"), client=FakeS3Client())

        self.assertEqual(provider.public_url("abc_video.mp4"), "https://cdn.example.com/abc_video.mp4")

    def test_public_url_strips_trailing_slash_on_base(self):
        provider = S3CompatibleStorageProvider(
            _config(public_base_url="https://cdn.example.com/"), client=FakeS3Client(),
        )

        self.assertEqual(provider.public_url("k"), "https://cdn.example.com/k")

    def test_public_url_empty_when_not_configured(self):
        provider = S3CompatibleStorageProvider(_config(public_base_url=""), client=FakeS3Client())

        self.assertEqual(provider.public_url("k"), "")


class TestS3CompatibleStorageProviderHealth(unittest.TestCase):

    def test_health_available_when_head_bucket_succeeds(self):
        provider = S3CompatibleStorageProvider(_config(), client=FakeS3Client())

        health = provider.health()

        self.assertTrue(health.available)

    def test_health_unavailable_when_head_bucket_fails(self):
        provider = S3CompatibleStorageProvider(
            _config(), client=FakeS3Client(fail_head_bucket=True),
        )

        health = provider.health()

        self.assertFalse(health.available)
        self.assertTrue(health.message)

    def test_health_calls_list_buckets_as_diagnostic_when_head_bucket_fails(self):
        """Storage 연결 테스트 디버깅 확인 - HeadBucket은 스펙상 원인
        없는 400/403/404만 돌려준다(AWS 공식 문서에 명시됨: "A message
        body isn't included"). list_buckets()는 실제 오류 본문이 있는
        API라 자격 증명 자체가 유효한지(계정 문제) vs 이 특정 Bucket만
        문제인지(이름 오타/대소문자/권한 범위)를 구분하는 데 쓴다."""
        client = FakeS3Client(fail_head_bucket=True, list_buckets_result=["other-bucket"])
        provider = S3CompatibleStorageProvider(_config(bucket="my-bucket"), client=client)

        health = provider.health()

        self.assertFalse(health.available)
        self.assertEqual(client.list_buckets_calls, 1)
        self.assertIn("other-bucket", health.message)
        self.assertIn("my-bucket", health.message)

    def test_health_message_confirms_credentials_valid_but_bucket_missing(self):
        client = FakeS3Client(fail_head_bucket=True, list_buckets_result=["a", "b"])
        provider = S3CompatibleStorageProvider(_config(bucket="my-bucket"), client=client)

        health = provider.health()

        self.assertIn("자격 증명은 유효", health.message)

    def test_health_falls_back_to_original_message_when_list_buckets_also_fails(self):
        client = FakeS3Client(fail_head_bucket=True, fail_list_buckets=True)
        provider = S3CompatibleStorageProvider(_config(), client=client)

        health = provider.health()

        self.assertFalse(health.available)
        self.assertEqual(client.list_buckets_calls, 1)
        self.assertNotIn("자격 증명은 유효", health.message)

    def test_health_does_not_call_list_buckets_when_head_bucket_succeeds(self):
        client = FakeS3Client()
        provider = S3CompatibleStorageProvider(_config(), client=client)

        provider.health()

        self.assertEqual(client.list_buckets_calls, 0)


class TestS3CompatibleStorageProviderLogsClientConstruction(unittest.TestCase):
    """Storage 연결 테스트 디버깅 확인 - "boto3.client 생성 시 실제
    실행값을 로그로 출력해달라"는 요청. Secret Key는 절대 로그에 남기지
    않는다(디스크 평문 로그 파일 = 자격 증명 유출) - Access Key만
    마스킹해서 남긴다(Secret Key는 아예 포함하지 않는다)."""

    @patch(f"{_MODULE}.boto3.client")
    def test_logs_endpoint_region_bucket_and_masked_access_key(self, mock_boto3_client):
        with self.assertLogs(_MODULE, level="INFO") as captured:
            S3CompatibleStorageProvider(_config(
                endpoint_url="https://account123.r2.cloudflarestorage.com",
                bucket="wellbeingplant-r2", region="auto",
                access_key="AKIAEXAMPLEACCESSKEY123", secret_key="super-secret-value",
            ))

        logged = "\n".join(captured.output)
        self.assertIn("https://account123.r2.cloudflarestorage.com", logged)
        self.assertIn("wellbeingplant-r2", logged)
        self.assertIn("auto", logged)
        self.assertIn("AKIAEXAM", logged)
        self.assertNotIn("super-secret-value", logged)
        self.assertNotIn("AKIAEXAMPLEACCESSKEY123", logged)


class TestS3CompatibleStorageProviderIsConfigDrivenNotHardcoded(unittest.TestCase):
    """핵심 원칙 - "Cloudflare R2를 위한 코드를 만들지 않는다. AWS 전용
    코드도 만들지 않는다." client를 주입하지 않으면 boto3.client()가
    config 값 그대로(endpoint_url만) 호출돼야 한다 - 이 값만 바꾸면
    AWS/R2/MinIO 무엇이든 동일한 Provider가 그대로 동작한다."""

    def _assert_checksum_compat_config(self, config):
        """Storage 연결 테스트 400 Bad Request 확인 - botocore 1.36+가
        S3 요청에 기본으로 Checksum(x-amz-sdk-checksum-algorithm 등)을
        추가하기 시작했다(boto3 공식 공지, GitHub Issue #4392) - AWS
        S3는 이를 이해하지만, Cloudflare R2를 포함한 대부분의 S3 호환
        서비스는 이 헤더를 이해하지 못해 HeadBucket 등에서 400 Bad
        Request로 거부한다(HeadBucket은 스펙상 본문 없는 400/403/404만
        돌려줘 원인을 알 수 없다 - AWS 공식 문서가 명시). 공식 권장
        해결책(when_required)을 그대로 적용한다."""
        self.assertEqual(config.request_checksum_calculation, "when_required")
        self.assertEqual(config.response_checksum_validation, "when_required")

    @patch(f"{_MODULE}.boto3.client")
    def test_builds_boto3_client_from_config_for_aws(self, mock_boto3_client):
        S3CompatibleStorageProvider(_config(endpoint_url="https://s3.amazonaws.com"))

        mock_boto3_client.assert_called_once()
        call = mock_boto3_client.call_args
        self.assertEqual(call[0], ("s3",))
        self.assertEqual(call[1]["endpoint_url"], "https://s3.amazonaws.com")
        self.assertEqual(call[1]["aws_access_key_id"], "ak")
        self.assertEqual(call[1]["aws_secret_access_key"], "sk")
        self.assertEqual(call[1]["region_name"], "us-east-1")
        self._assert_checksum_compat_config(call[1]["config"])

    @patch(f"{_MODULE}.boto3.client")
    def test_builds_boto3_client_from_config_for_cloudflare_r2(self, mock_boto3_client):
        # AWS와 완전히 같은 코드 경로 - endpoint_url만 다르다.
        S3CompatibleStorageProvider(_config(
            endpoint_url="https://account123.r2.cloudflarestorage.com", region="auto",
        ))

        call = mock_boto3_client.call_args
        self.assertEqual(call[0], ("s3",))
        self.assertEqual(call[1]["endpoint_url"], "https://account123.r2.cloudflarestorage.com")
        self.assertEqual(call[1]["aws_access_key_id"], "ak")
        self.assertEqual(call[1]["aws_secret_access_key"], "sk")
        self.assertEqual(call[1]["region_name"], "auto")
        self._assert_checksum_compat_config(call[1]["config"])

    @patch(f"{_MODULE}.boto3.client")
    def test_builds_boto3_client_from_config_for_minio(self, mock_boto3_client):
        S3CompatibleStorageProvider(_config(endpoint_url="http://localhost:9000", region=""))

        call = mock_boto3_client.call_args
        self.assertEqual(call[0], ("s3",))
        self.assertEqual(call[1]["endpoint_url"], "http://localhost:9000")
        self.assertEqual(call[1]["aws_access_key_id"], "ak")
        self.assertEqual(call[1]["aws_secret_access_key"], "sk")
        self.assertEqual(call[1]["region_name"], "")
        self._assert_checksum_compat_config(call[1]["config"])


if __name__ == "__main__":
    unittest.main()
