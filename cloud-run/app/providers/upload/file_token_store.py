"""
Epic 46 Sprint 003 - Real Google OAuth Integration.

TokenStore(Sprint002, In-Memory, 무수정)와 완전히 같은 save(credential)/
load(account_id) 인터페이스를 갖는 파일 기반 구현체다 - Duck Typing이라
CredentialLoader(Sprint002, 무수정)가 이 클래스도 그대로 쓸 수 있다.
"프로그램 재시작 후 Credential 복원"을 위해 JSON 파일로 영속화한다.
저장 경로는 생성자 인자로 받아 설정 가능하다(하드코딩 금지).
"""

import json
import os
from datetime import datetime

from app.providers.upload.oauth_credential import OAuthCredential
from app.services import secret_box


class FileTokenStore:

    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    def save(self, credential: OAuthCredential) -> None:
        data = self._read_all()
        data[credential.account_id] = {
            "access_token": credential.access_token,
            "refresh_token": credential.refresh_token,
            "expires_at": credential.expires_at.isoformat(),
        }
        self._write_all(data)

    def load(self, account_id: str) -> OAuthCredential | None:
        entry = self._read_all().get(account_id)

        if entry is None:
            return None

        return OAuthCredential(
            account_id=account_id,
            access_token=entry["access_token"],
            refresh_token=entry["refresh_token"],
            expires_at=datetime.fromisoformat(entry["expires_at"]),
        )

    def delete(self, account_id: str) -> None:
        # EPIC Multi Platform Publishing Runtime - RealYouTubeRuntime.
        # revoke()(로컬 로그아웃)가 쓴다. 없는 계정을 지워도 조용히
        # 무시한다(InstagramTokenStore.delete()와 동일한 관례).
        data = self._read_all()
        data.pop(account_id, None)
        self._write_all(data)

    # Sprint217 - refresh_token을 평문으로 두지 않는다.
    #
    # 감싸는 일은 secret_box(Windows DPAPI)가 한다. 여기서는 읽고 쓰는
    # 자리만 그것을 지나가게 한다 - 파일 모양을 아는 곳이 두 곳이 되면
    # 한쪽만 고치는 날이 온다.
    #
    # 예전에 평문으로 적힌 파일도 그대로 읽는다(secret_box.unwrap이
    # 열쇠말이 없으면 준 것을 돌려준다). 이미 로그인해 둔 사람의
    # 로그인이 판올림 한 번에 사라지면 안 되고, 다음 save()에서
    # 감싸인 것으로 바뀐다.
    def _read_all(self) -> dict:
        if not os.path.exists(self.storage_path):
            return {}

        with open(self.storage_path, encoding="utf-8") as f:
            raw = json.load(f)

        data = secret_box.unwrap(raw)

        # Sprint236 - 평문이면 그 자리에서 감싸 다시 적는다.
        #
        # 예전에는 다음 save() 를 기다렸다. 그런데 access_token 이
        # 살아 있는 동안에는 저장할 일이 없고, refresh_token 은
        # 만료되지 않는다 - 이 PC 에서 그 파일은 13일 동안 평문으로
        # 남아 있었고 그 사이 프로그램은 여러 번 실행됐다.
        #
        # 실패해도 읽기는 성공시킨다. 감싸는 것은 곁다리이고, 그것
        # 때문에 로그인이 사라지면 사람은 이유도 모른 채 다시
        # 로그인해야 한다.
        if secret_box.needs_protecting(raw):
            try:
                self._write_all(data)
            except Exception:
                pass

        return data

    def _write_all(self, data: dict) -> None:
        directory = os.path.dirname(self.storage_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(secret_box.wrap(data), f, ensure_ascii=False, indent=2)
