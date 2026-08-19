"""
EPIC Instagram Connector (Production) - Instagram Token Store.

app.providers.upload.file_token_store.FileTokenStore(Google/YouTube
전용, 무수정)와 동일한 save(credential)/load(account_id) 관례를
따르되, InstagramCredential(refresh_token 없음, obtained_at 있음)
모양에 맞춘 별도 구현체다 - FileTokenStore는 credential.refresh_token
을 직접 읽는 코드가 있어 그대로 재사용할 수 없다(억지로 끼워 맞추지
않는다).
"""

import json
import os
from datetime import datetime
from typing import Optional

from app.providers.upload.instagram_credential import InstagramCredential
from app.services import secret_box


class InstagramTokenStore:

    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    def save(self, credential: InstagramCredential) -> None:
        data = self._read_all()
        data[credential.account_id] = {
            "access_token": credential.access_token,
            "obtained_at": credential.obtained_at.isoformat(),
            "expires_at": credential.expires_at.isoformat(),
            "ig_user_id": credential.ig_user_id,
        }
        self._write_all(data)

    def load(self, account_id: str) -> Optional[InstagramCredential]:
        entry = self._read_all().get(account_id)

        if entry is None:
            return None

        return InstagramCredential(
            account_id=account_id,
            access_token=entry["access_token"],
            obtained_at=datetime.fromisoformat(entry["obtained_at"]),
            expires_at=datetime.fromisoformat(entry["expires_at"]),
            ig_user_id=entry.get("ig_user_id", ""),
        )

    def delete(self, account_id: str) -> None:
        # EPIC Instagram Production Ready - RealInstagramRuntime.revoke()
        # (로컬 로그아웃)이 쓴다. 없는 계정을 지워도 조용히 무시한다 -
        # "로그아웃 상태를 보장한다"가 목적이지 "이미 로그아웃 상태였다"를
        # 오류로 취급할 이유가 없다.
        data = self._read_all()
        data.pop(account_id, None)
        self._write_all(data)

    # Sprint217 - FileTokenStore와 같이 secret_box를 지나간다.
    # Instagram의 장기 토큰은 60일짜리 하나뿐이라 그것이 곧
    # refresh_token 노릇을 한다 - 평문으로 둘 이유가 더 없다.
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
