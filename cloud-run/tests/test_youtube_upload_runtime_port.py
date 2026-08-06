"""
Sprint91 - Upload Runtime 이식 (Porting Phase 4).

OneDrive 저장소의 real_youtube_runtime과 youtube_upload_step_service를
가져온다. Sprint89가 Upload Core를, Sprint90이 OAuth Manager를 가져왔고,
이제 그 둘을 실제로 부르는 층이다.

여기서 지켜야 할 것이 하나 있다. credential_loader.get_valid_credential()
은 저장된 토큰이 없으면 oauth_service.authenticate()를 부르고, 그것은
InstalledAppFlow.run_local_server()로 브라우저를 연다. Qt 데스크톱
앱에서는 사용자가 그 앞에 앉아 있으니 맞는 동작이었다. 여기서는
FastAPI 서버다 - 업로드 요청 하나가 서버에서 브라우저를 띄우고 아무도
동의하지 않아 영원히 멈춘다.

그래서 업로드 경로는 OAuth Manager의 check_health()(로컬 파일만 읽는다)
로 먼저 막는다. Sprint90이 verify_now()에서 같은 이유로
get_valid_credential()을 피한 것과 같은 판단이다.
"""

import ast
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.upload.oauth_credential import OAuthCredential
from app.providers.upload.upload_provider import UploadResult
from app.services import oauth_health, real_youtube_runtime, youtube_upload_step_service
from app.services.publishing_runtime_protocol import (
    NonRetryableRuntimeError,
    PublishingRuntimeProtocol,
    RuntimeCapabilities,
)
from app.services.real_youtube_runtime import (
    DISABLED_MESSAGE,
    RealYouTubeRuntime,
    YouTubeAPIError,
    _classify_upload_error,
)


def _imported_names(module):
    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(a.name for a in node.names)
    return names


def _called_names(module):
    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute):
                called.add(target.attr)
            elif isinstance(target, ast.Name):
                called.add(target.id)
    return called


def _credential(account_id="default", expires_at=None):
    return OAuthCredential(
        account_id=account_id,
        access_token="at",
        refresh_token="rt",
        expires_at=expires_at or datetime(2100, 1, 1, tzinfo=timezone.utc),
    )


class _Provider:
    """YouTubeUploadProvider 자리. 실제 네트워크는 부르지 않는다."""

    last = None

    def __init__(self, credential=None, result=None):
        self.credential = credential
        self._result = result or UploadResult(
            success=True, upload_id="vid123",
            url="https://youtu.be/vid123", error=None,
        )

    def upload(self, video_path, metadata):
        _Provider.last = {"video_path": video_path, "metadata": metadata}
        return self._result


class TestClassificationIsPortedVerbatim(unittest.TestCase):
    """분류 규칙은 실제 YouTube Data API 응답에서 나온 값이다.
    다시 쓰면 추측이 된다."""

    def test_a_missing_local_file_is_not_a_network_problem(self):
        """자동 재시도 허용 목록에 절대 들어가면 안 된다."""

        from app.providers.upload.youtube_upload_provider import (
            FILE_NOT_FOUND_REASON,
        )

        self.assertEqual(
            _classify_upload_error(None, FILE_NOT_FOUND_REASON), "FILE_NOT_FOUND",
        )

    def test_a_connection_failure_has_no_status_code_but_is_still_network(self):
        from app.providers.upload.youtube_upload_provider import (
            CONNECTION_ERROR_REASON,
        )

        self.assertEqual(
            _classify_upload_error(None, CONNECTION_ERROR_REASON), "NETWORK_ERROR",
        )

    def test_401_is_token_expired(self):
        self.assertEqual(_classify_upload_error(401, "unauth"), "TOKEN_EXPIRED")

    def test_403_with_quota_is_quota_exceeded_not_rate_limit(self):
        """일일 할당량은 태평양 시간 자정에만 풀린다. 초 단위로 풀리는
        Rate Limit과 이름이 같으면 자동 재시도 목록에 섞여 들어간다."""

        self.assertEqual(
            _classify_upload_error(403, "quotaExceeded"), "QUOTA_EXCEEDED",
        )

    def test_403_without_quota_is_a_permission_problem(self):
        self.assertEqual(
            _classify_upload_error(403, "forbidden"), "PERMISSION_ERROR",
        )

    def test_5xx_is_network(self):
        for code in (500, 502, 503, 599):
            with self.subTest(code=code):
                self.assertEqual(
                    _classify_upload_error(code, "server"), "NETWORK_ERROR",
                )

    def test_a_non_integer_status_falls_through_instead_of_raising(self):
        self.assertEqual(
            _classify_upload_error("403", "quota"), "UNKNOWN_ERROR",
        )

    def test_quota_exceeded_is_never_named_rate_limit(self):
        """설명 주석이 RATE_LIMIT을 언급한다(Instagram과 왜 다른 이름을
        쓰는지 적느라). 원문을 문자열로 훑으면 거기에 걸린다 - 함수가
        실제로 돌려주는 값만 본다."""

        tree = ast.parse(
            open(real_youtube_runtime.__file__, encoding="utf-8").read(),
        )
        func = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and n.name == "_classify_upload_error"
        )
        returned = {
            n.value.value for n in ast.walk(func)
            if isinstance(n, ast.Return)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        }

        self.assertIn("QUOTA_EXCEEDED", returned)
        self.assertNotIn("RATE_LIMIT", returned)


class TestRuntimeContract(unittest.TestCase):

    def test_it_implements_the_protocol(self):
        self.assertTrue(issubclass(RealYouTubeRuntime, PublishingRuntimeProtocol))

    def test_capabilities_match_what_youtube_actually_does(self):
        caps = RealYouTubeRuntime.capabilities

        self.assertIsInstance(caps, RuntimeCapabilities)
        # 리샘블 업로드가 그 자체로 최종 게시다 - Instagram식 2단계가 없다.
        self.assertFalse(caps.two_phase_publish)
        # 로컬 파일 경로를 직접 읽는다 - 공개 URL이 필요 없다.
        self.assertFalse(caps.requires_public_url)
        self.assertTrue(caps.supports_thumbnail)
        self.assertTrue(caps.supports_playlist)
        self.assertTrue(caps.supports_shorts)
        self.assertTrue(caps.supports_permalink)

    def test_a_permalink_is_built_from_the_video_id_without_an_api_call(self):
        runtime = RealYouTubeRuntime()

        self.assertEqual(
            runtime.get_permalink(None, "abc123"), "https://youtu.be/abc123",
        )

    def test_an_empty_media_id_gives_an_empty_permalink(self):
        self.assertEqual(RealYouTubeRuntime().get_permalink(None, ""), "")

    def test_publish_media_is_a_passthrough(self):
        self.assertEqual(RealYouTubeRuntime().publish_media(None, "x"), "x")

    def test_status_is_always_finished_because_there_is_no_polling(self):
        self.assertEqual(
            RealYouTubeRuntime().get_publish_status(None, "x"), "FINISHED",
        )


class TestTheFlagIsTheOuterGate(unittest.TestCase):
    """ENABLE_YOUTUBE_UPLOAD가 False면 자격증명 체인을 아예 건드리지
    않는다 - 실제 토큰이 있어도 마찬가지다."""

    def test_login_refuses_while_the_flag_is_off(self):
        with patch.object(real_youtube_runtime.config,
                          "ENABLE_YOUTUBE_UPLOAD", False):
            with self.assertRaises(NonRetryableRuntimeError) as caught:
                RealYouTubeRuntime().login("default")

        self.assertIn(DISABLED_MESSAGE, str(caught.exception))

    def test_login_never_reaches_the_credential_chain_while_off(self):
        with patch.object(real_youtube_runtime.config,
                          "ENABLE_YOUTUBE_UPLOAD", False), \
             patch.object(real_youtube_runtime, "get_valid_credential") as loader, \
             patch.object(real_youtube_runtime, "GoogleOAuthService") as svc:
            with self.assertRaises(NonRetryableRuntimeError):
                RealYouTubeRuntime().login("default")

        loader.assert_not_called()
        svc.assert_not_called()

    def test_the_shipped_default_is_off(self):
        """Evaluation Policy v3 - Production Flag를 True로 올리려면
        Level 3 Release Gate가 필요하다. 실제 업로드는 아직 한 번도
        검증되지 않았다."""

        from app import config

        self.assertFalse(config.ENABLE_YOUTUBE_UPLOAD)


class TestUploadMediaCarriesTheRealFailure(unittest.TestCase):

    def _run(self, result):
        runtime = RealYouTubeRuntime()
        with patch.object(real_youtube_runtime, "YouTubeUploadProvider",
                          lambda credential: _Provider(credential, result)):
            return runtime.upload_media(_credential(), "v.mp4", "cap")

    def test_a_successful_upload_returns_the_video_id(self):
        self.assertEqual(
            self._run(UploadResult(True, "vid9", "u", None)), "vid9",
        )

    def test_a_failure_raises_with_the_classified_category(self):
        result = UploadResult(
            False, None, None, "boom", error_status_code=401,
            error_reason="unauth",
        )

        with self.assertRaises(YouTubeAPIError) as caught:
            self._run(result)

        self.assertEqual(caught.exception.error_category, "TOKEN_EXPIRED")

    def test_a_plan_supplies_metadata_and_a_cover_becomes_the_thumbnail(self):
        class _Plan:
            title = "제목"
            description = "설명"
            hashtags = ["#a"]

        runtime = RealYouTubeRuntime()
        with patch.object(real_youtube_runtime, "YouTubeUploadProvider",
                          lambda credential: _Provider(credential)):
            runtime.upload_media(
                _credential(), "v.mp4", "cap", cover_url="t.png", plan=_Plan(),
            )

        meta = _Provider.last["metadata"]
        self.assertEqual(meta["title"], "제목")
        self.assertEqual(meta["description"], "설명")
        self.assertEqual(meta["hashtags"], ["#a"])
        self.assertEqual(meta["thumbnail_path"], "t.png")

    def test_no_plan_still_produces_a_usable_metadata_dict(self):
        runtime = RealYouTubeRuntime()
        with patch.object(real_youtube_runtime, "YouTubeUploadProvider",
                          lambda credential: _Provider(credential)):
            runtime.upload_media(_credential(), "v.mp4", "cap")

        meta = _Provider.last["metadata"]
        self.assertEqual(meta["title"], "")
        self.assertEqual(meta["hashtags"], [])
        self.assertNotIn("thumbnail_path", meta)


class _StepCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = os.path.join(self._tmp.name, "20260101_000001")
        os.makedirs(os.path.join(self.project, "video"))

        self.secret = os.path.join(self._tmp.name, "client_secret.json")
        with open(self.secret, "w", encoding="utf-8") as f:
            json.dump({"installed": {"client_id": "x"}}, f)

        self.tokens = os.path.join(self._tmp.name, "tokens.json")
        _Provider.last = None

    def _video(self):
        path = os.path.join(self.project, "video", "final_short.mp4")
        with open(path, "wb") as f:
            f.write(b"mp4")
        return path

    def _thumbnail(self, size=10):
        path = os.path.join(self.project, "thumbnail.png")
        with open(path, "wb") as f:
            f.write(b"p" * size)
        return path

    def _data(self, **extra):
        base = {"title": "제목", "script": "본문", "hashtags": ["#건강"]}
        base.update(extra)
        return base

    def _run(self, health_status=oauth_health.READY, result=None, **kwargs):
        health = oauth_health.CredentialHealth(health_status, "msg", 0.0)

        with patch.dict(os.environ, {
            "YOUTUBE_OAUTH_CLIENT_SECRET_PATH": self.secret,
            "YOUTUBE_OAUTH_TOKEN_STORE_PATH": self.tokens,
            "YOUTUBE_OAUTH_ACCOUNT_ID": "default",
        }), patch.object(
            youtube_upload_step_service, "_check_health", lambda *a, **k: health,
        ), patch.object(
            youtube_upload_step_service, "get_valid_credential",
            lambda *a, **k: _credential(),
        ), patch.object(
            youtube_upload_step_service, "YouTubeUploadProvider",
            lambda credential: _Provider(credential, result),
        ), patch.object(
            youtube_upload_step_service.config, "ENABLE_YOUTUBE_UPLOAD", True,
        ):
            return youtube_upload_step_service.run_youtube_upload_step(
                kwargs.pop("topic", "혈관 건강"),
                self.project,
                kwargs.pop("data", self._data()),
                **kwargs
            )


class TestTheStepResolvesThisEnginesRealFilenames(_StepCase):
    """원본은 render_profile(longform/shorts 축)로 파일명을 골랐다.
    이 저장소에는 longform이 없다 - 엔진이 실제로 쓰는 이름만 본다."""

    def test_the_video_path_matches_what_the_engine_writes(self):
        from app.services.studio_service import MEDIA_KINDS

        self._video()
        self._run()

        self.assertEqual(
            _Provider.last["video_path"],
            os.path.join(self.project, *MEDIA_KINDS["video"].split("/")),
        )

    def test_the_thumbnail_path_matches_what_the_engine_writes(self):
        from app.services.studio_service import MEDIA_KINDS

        self._video()
        self._thumbnail()
        self._run()

        self.assertEqual(
            _Provider.last["metadata"]["thumbnail_path"],
            os.path.join(self.project, MEDIA_KINDS["thumbnail"]),
        )

    def test_no_longform_axis_is_imported(self):
        """모듈 설명이 render_profile을 왜 안 쓰는지 적고 있어서 원문
        훑기로는 판정할 수 없다 - import만 본다."""

        for name in _imported_names(youtube_upload_step_service):
            with self.subTest(imported=name):
                self.assertNotIn("render_profile", name)


class TestMetadataIsPassedThrough(_StepCase):

    def test_title_description_and_hashtags_reach_the_provider(self):
        self._video()
        self._run()

        meta = _Provider.last["metadata"]
        self.assertEqual(meta["title"], "제목")
        self.assertEqual(meta["description"], "본문")
        self.assertEqual(meta["hashtags"], ["#건강"])

    def test_a_missing_title_falls_back_to_the_topic(self):
        self._video()
        self._run(data={"script": "본문"})

        self.assertEqual(_Provider.last["metadata"]["title"], "혈관 건강")

    def test_the_publish_package_wins_when_it_exists(self):
        """Metadata Intelligence가 만든 단일 Source of Truth다.
        이 저장소에는 아직 그것을 만드는 단계가 없지만, 읽는 쪽 계약은
        원본 그대로 유지한다."""

        self._video()
        with open(os.path.join(self.project, "publish_package.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"title": "패키지 제목", "description": "패키지 설명",
                       "tags": ["#p"], "playlist_title": "재생목록",
                       "privacy_status": "private"}, f, ensure_ascii=False)

        self._run()

        meta = _Provider.last["metadata"]
        self.assertEqual(meta["title"], "패키지 제목")
        self.assertEqual(meta["description"], "패키지 설명")
        self.assertEqual(meta["hashtags"], ["#p"])
        self.assertEqual(meta["playlist_title"], "재생목록")
        self.assertEqual(meta["privacy_status"], "private")

    def test_a_corrupt_publish_package_does_not_block_the_upload(self):
        self._video()
        with open(os.path.join(self.project, "publish_package.json"),
                  "w", encoding="utf-8") as f:
            f.write("{ broken")

        self._run()

        self.assertEqual(_Provider.last["metadata"]["title"], "제목")

    def test_the_caller_data_dict_is_never_mutated(self):
        self._video()
        data = self._data()
        before = json.dumps(data, ensure_ascii=False, sort_keys=True)

        self._run(data=data)

        self.assertEqual(
            json.dumps(data, ensure_ascii=False, sort_keys=True), before,
        )


class TestThumbnailIsPassedThrough(_StepCase):

    def test_a_present_thumbnail_is_attached(self):
        self._video()
        self._thumbnail()

        self._run()

        self.assertIn("thumbnail_path", _Provider.last["metadata"])

    def test_a_missing_thumbnail_does_not_block_the_video_upload(self):
        self._video()

        payload = self._run()

        self.assertNotIn("thumbnail_path", _Provider.last["metadata"])
        self.assertTrue(payload["success"])

    def test_an_oversized_thumbnail_is_optimized_and_the_original_is_kept(self):
        """YouTube Thumbnail API는 2MB를 넘으면 거부한다. 원본은
        시각 검수용으로 그대로 둔다."""

        from app.services import thumbnail_size_optimizer

        self._video()
        original = self._thumbnail()
        before = os.path.getsize(original)

        with patch.object(thumbnail_size_optimizer,
                          "optimize_thumbnail_for_upload",
                          lambda p: p + "_optimized.png"):
            self._run()

        self.assertTrue(
            _Provider.last["metadata"]["thumbnail_path"].endswith(
                "_optimized.png"),
        )
        self.assertEqual(os.path.getsize(original), before)

    def test_a_thumbnail_failure_does_not_flip_the_upload_to_failed(self):
        self._video()
        result = UploadResult(
            True, "vid1", "u", None, thumbnail_error="Media larger than: 2097152",
        )

        payload = self._run(result=result)

        self.assertTrue(payload["success"])
        self.assertEqual(
            payload["thumbnail_error"], "Media larger than: 2097152",
        )


class TestPlaylistIsPassedThrough(_StepCase):

    def test_a_playlist_title_reaches_the_provider(self):
        self._video()
        with open(os.path.join(self.project, "publish_package.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"playlist_title": "혈관 건강 시리즈"}, f,
                      ensure_ascii=False)

        self._run()

        self.assertEqual(
            _Provider.last["metadata"]["playlist_title"], "혈관 건강 시리즈",
        )

    def test_no_playlist_key_when_none_was_asked_for(self):
        self._video()

        self._run()

        self.assertNotIn("playlist_title", _Provider.last["metadata"])

    def test_a_playlist_failure_does_not_flip_the_upload_to_failed(self):
        self._video()
        result = UploadResult(
            True, "vid1", "u", None, playlist_error="playlist not found",
        )

        payload = self._run(result=result)

        self.assertTrue(payload["success"])
        self.assertEqual(payload["playlist_error"], "playlist not found")


class TestRetryLivesInTheProviderAndIsUnchanged(unittest.TestCase):
    """Sprint89가 이미 가져온 계층이다. Sprint91은 그것을 다시 만들지
    않는다 - 여기서는 그 계약이 그대로인지만 확인한다."""

    def test_only_transient_5xx_codes_are_retried(self):
        from app.providers.upload import youtube_upload_provider as provider

        self.assertEqual(
            provider._RETRYABLE_STATUS_CODES, {500, 502, 503, 504},
        )
        self.assertNotIn(401, provider._RETRYABLE_STATUS_CODES)
        self.assertNotIn(403, provider._RETRYABLE_STATUS_CODES)

    def test_the_retry_budget_is_finite(self):
        from app.providers.upload import youtube_upload_provider as provider

        self.assertEqual(provider._MAX_RETRIES, 3)
        self.assertGreater(provider._RETRY_BACKOFF_SECONDS, 0)

    def test_a_retryable_error_is_retried_up_to_the_budget(self):
        from app.providers.upload import youtube_upload_provider as provider

        class _Resp:
            status = 503

        class _Err(Exception):
            resp = _Resp()

        calls = {"n": 0}

        class _Request:
            def next_chunk(self):
                calls["n"] += 1
                raise _Err("503")

        instance = provider.YouTubeUploadProvider.__new__(
            provider.YouTubeUploadProvider,
        )
        instance.progress_callback = None

        with patch.object(provider, "HttpError", _Err), \
             patch.object(provider.time, "sleep", lambda s: None):
            with self.assertRaises(_Err):
                instance._execute_with_retry(_Request())

        self.assertEqual(calls["n"], provider._MAX_RETRIES + 1)

    def test_a_non_retryable_error_is_raised_immediately(self):
        from app.providers.upload import youtube_upload_provider as provider

        class _Resp:
            status = 403

        class _Err(Exception):
            resp = _Resp()

        calls = {"n": 0}

        class _Request:
            def next_chunk(self):
                calls["n"] += 1
                raise _Err("403")

        instance = provider.YouTubeUploadProvider.__new__(
            provider.YouTubeUploadProvider,
        )
        instance.progress_callback = None

        with patch.object(provider, "HttpError", _Err), \
             patch.object(provider.time, "sleep", lambda s: None):
            with self.assertRaises(_Err):
                instance._execute_with_retry(_Request())

        self.assertEqual(calls["n"], 1)


class TestTheUploadPathNeverOpensABrowser(_StepCase):
    """Sprint90이 verify_now()에서 내린 판단과 같다.
    get_valid_credential()은 저장된 토큰이 없으면 브라우저를 연다."""

    def test_no_stored_login_is_refused_before_the_credential_chain(self):
        self._video()

        with patch.dict(os.environ, {
            "YOUTUBE_OAUTH_CLIENT_SECRET_PATH": self.secret,
            "YOUTUBE_OAUTH_TOKEN_STORE_PATH": self.tokens,
        }), patch.object(
            youtube_upload_step_service, "_check_health",
            lambda *a, **k: oauth_health.CredentialHealth(
                oauth_health.REAUTH_REQUIRED, "저장된 Google 로그인이 없습니다.",
                0.0),
        ), patch.object(
            youtube_upload_step_service, "get_valid_credential",
        ) as loader, patch.object(
            youtube_upload_step_service.config, "ENABLE_YOUTUBE_UPLOAD", True,
        ):
            payload = youtube_upload_step_service.run_youtube_upload_step(
                "혈관 건강", self.project, self._data(),
            )

        loader.assert_not_called()
        self.assertFalse(payload["success"])
        self.assertIn("로그인", payload["error"])

    def test_an_expired_token_is_allowed_because_refresh_needs_no_browser(self):
        self._video()

        payload = self._run(health_status=oauth_health.EXPIRED)

        self.assertTrue(payload["success"])

    def test_the_real_health_check_runs_without_a_stored_login(self):
        """다른 테스트는 _check_health를 갈아끼운다. 그러면 실제
        OAuthManager 조립이 한 번도 안 돌아본 채로 남는다."""

        health = youtube_upload_step_service._check_health(
            self.secret, self.tokens, "default",
        )

        self.assertEqual(health.status, oauth_health.REAUTH_REQUIRED)

    def test_the_real_health_check_reads_an_expired_token_as_expired(self):
        from app.providers.upload.file_token_store import FileTokenStore

        FileTokenStore(storage_path=self.tokens).save(
            _credential(expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc)),
        )

        health = youtube_upload_step_service._check_health(
            self.secret, self.tokens, "default",
        )

        self.assertEqual(health.status, oauth_health.EXPIRED)

    def test_the_step_module_never_calls_authenticate(self):
        """브라우저를 여는 두 함수다. 설명에서 언급하는 것과 실제로
        부르는 것은 다르다 - 호출식만 본다."""

        called = _called_names(youtube_upload_step_service)

        self.assertNotIn("authenticate", called)
        self.assertNotIn("run_local_server", called)


class TestMissingClientSecretIsReportedNotCreated(_StepCase):
    """Acceptance 7 - 자동 생성 금지."""

    def _run_without_secret(self):
        missing = os.path.join(self._tmp.name, "nope", "client_secret.json")

        with patch.dict(os.environ, {
            "YOUTUBE_OAUTH_CLIENT_SECRET_PATH": missing,
            "YOUTUBE_OAUTH_TOKEN_STORE_PATH": self.tokens,
        }), patch.object(
            youtube_upload_step_service.config, "ENABLE_YOUTUBE_UPLOAD", True,
        ), patch.object(
            youtube_upload_step_service, "get_valid_credential",
        ) as loader:
            payload = youtube_upload_step_service.run_youtube_upload_step(
                "혈관 건강", self.project, self._data(),
            )
        return payload, missing, loader

    def test_the_error_names_the_missing_path(self):
        self._video()

        payload, missing, _ = self._run_without_secret()

        self.assertFalse(payload["success"])
        self.assertIn(missing, payload["error"])

    def test_nothing_is_created_on_disk(self):
        self._video()

        _, missing, _ = self._run_without_secret()

        self.assertFalse(os.path.exists(missing))
        self.assertFalse(os.path.exists(os.path.dirname(missing)))

    def test_the_credential_chain_is_never_reached(self):
        self._video()

        _, _, loader = self._run_without_secret()

        loader.assert_not_called()


class TestTheFlagGatesTheStepToo(_StepCase):

    def test_the_step_refuses_while_the_flag_is_off(self):
        self._video()

        with patch.dict(os.environ, {
            "YOUTUBE_OAUTH_CLIENT_SECRET_PATH": self.secret,
        }), patch.object(
            youtube_upload_step_service.config, "ENABLE_YOUTUBE_UPLOAD", False,
        ), patch.object(
            youtube_upload_step_service, "get_valid_credential",
        ) as loader:
            payload = youtube_upload_step_service.run_youtube_upload_step(
                "혈관 건강", self.project, self._data(),
            )

        loader.assert_not_called()
        self.assertFalse(payload["success"])
        self.assertIn(DISABLED_MESSAGE, payload["error"])


class TestTheResultIsRecorded(_StepCase):

    def test_the_payload_carries_every_field_the_caller_needs(self):
        self._video()

        payload = self._run()

        for field in ("success", "upload_id", "url", "error",
                      "thumbnail_error", "playlist_error"):
            with self.subTest(field=field):
                self.assertIn(field, payload)

    def test_the_result_is_written_next_to_the_project(self):
        self._video()

        self._run()

        path = os.path.join(self.project, "youtube_upload_result.json")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["upload_id"], "vid123")

    def test_a_refusal_is_recorded_too_so_it_is_not_silent(self):
        self._video()

        with patch.dict(os.environ, {
            "YOUTUBE_OAUTH_CLIENT_SECRET_PATH": self.secret,
        }), patch.object(
            youtube_upload_step_service.config, "ENABLE_YOUTUBE_UPLOAD", False,
        ):
            youtube_upload_step_service.run_youtube_upload_step(
                "혈관 건강", self.project, self._data(),
            )

        path = os.path.join(self.project, "youtube_upload_result.json")
        with open(path, encoding="utf-8") as f:
            self.assertFalse(json.load(f)["success"])

    def test_production_artifacts_are_not_touched(self):
        """업로드는 읽기만 한다. 영상도 썸네일도 그대로다."""

        video = self._video()
        thumb = self._thumbnail()
        before = (os.path.getsize(video), os.path.getsize(thumb))

        self._run()

        self.assertEqual(
            (os.path.getsize(video), os.path.getsize(thumb)), before,
        )


class TestNothingQtCameAcross(unittest.TestCase):
    """Sprint90과 같은 검사다. 문자열 grep은 설명 주석에 걸려 거짓
    통과한다 - import를 AST로 본다."""

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_no_qt_and_no_desktop_layer(self):
        for module in (real_youtube_runtime, youtube_upload_step_service):
            for name in self._imports(module):
                with self.subTest(module=module.__name__, imported=name):
                    self.assertNotIn("PySide", name)
                    self.assertNotIn("desktop", name)


class TestTheEngineIsUntouched(unittest.TestCase):

    def test_the_pipeline_does_not_import_the_upload_step(self):
        """Sprint91은 Runtime만 이식한다. Pipeline 연결은 다음 단계다."""

        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        self.assertNotIn("youtube_upload_step_service", source)
        self.assertNotIn("real_youtube_runtime", source)

    def test_the_upload_step_imports_no_engine_module(self):
        tree = ast.parse(
            open(youtube_upload_step_service.__file__, encoding="utf-8").read(),
        )
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")

        for forbidden in ("factory_service", "image_service", "quality_service",
                          "regeneration_service", "final_video_service",
                          "pipeline"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in name for name in names), forbidden,
                )


if __name__ == "__main__":
    unittest.main()
