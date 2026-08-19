"""
Sprint217 - 토큰을 평문으로 두지 않는다 (Epic 61).

무엇이 문제였는가
-----------------
FileTokenStore와 InstagramTokenStore는 access_token과 refresh_token을
JSON 평문으로 적는다. 실제로 이 PC에 그렇게 놓여 있었다.

    credentials/youtube_oauth_tokens.json
      default/refresh_token = <103 chars>   ← 평문

refresh_token은 비밀번호보다 무겁다. 그것만 있으면 언제든 새
access_token을 받을 수 있고, 이 프로그램이 요구한 Scope에는
youtube.upload이 들어 있다 - 남의 채널에 영상을 올릴 수 있다는 뜻이다.

무엇으로 감싸는가
-----------------
Windows DPAPI(CryptProtectData). 고른 이유는 셋이다.

    1. 새 pip 패키지가 필요 없다. ctypes로 OS를 직접 부른다 -
       keyring도 pywin32도 넣지 않는다(이 저장소의 관례다).
    2. 열쇠를 우리가 들고 있지 않다. Windows 사용자 계정에 묶이므로
       파일만 훔쳐 다른 계정/다른 PC로 옮겨도 풀리지 않는다.
       cryptography로 직접 암호화하면 그 열쇠를 또 어딘가에 평문으로
       두어야 한다 - 문제를 한 칸 옮기는 것뿐이다.
    3. 프로그램이 조용히 쓸 수 있다. 사용자에게 암호를 묻지 않는다.

무엇을 지키지 못하는가 - 적어 둔다
----------------------------------
같은 Windows 계정으로 로그인한 다른 프로그램은 이 파일을 풀 수 있다.
DPAPI는 "이 계정의 것"까지만 가른다. 그보다 강한 것을 원하면 사용자
암호를 묻는 수밖에 없고, 그러면 무인 예약 발행이 불가능해진다.

없는 척하지 않는다
------------------
DPAPI를 못 쓰는 자리(Windows가 아니거나 호출이 실패)에서는 감싸지
않고 평문으로 적고, `available()`이 False를 돌려준다. 화면은 그것을
그대로 보여 준다 - "안전하게 저장했다"고 말해 놓고 평문으로 적는 것이
가장 나쁘다.
"""

import base64
import ctypes
import json
import os
import sys

# 감싼 파일의 첫 열쇠말. 이 글자가 있으면 감싼 것이고, 없으면 예전에
# 평문으로 적힌 것이다 - 예전 파일도 그대로 읽는다(아래 unwrap).
MARKER_KEY = "__protected__"
MARKER_DPAPI = "dpapi-v1"
PAYLOAD_KEY = "payload"

# 같은 계정의 다른 프로그램이 우연히 풀어 쓰지 못하게 하는 추가 재료.
# 비밀이 아니다 - 소스에 적혀 있다. 하는 일은 "이 blob은 영상제작소
# 것이다"라고 표시하는 것뿐이다(DPAPI의 pOptionalEntropy).
_ENTROPY = b"AI-VideoStudio/social-tokens/v1"

_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _Blob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _to_blob(data: bytes) -> _Blob:
    buffer = ctypes.create_string_buffer(data, len(data))

    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _from_blob(blob: _Blob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _free(blob: _Blob) -> None:
    if blob.pbData:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def _crypt(fn_name: str, data: bytes) -> bytes:
    """CryptProtectData / CryptUnprotectData 한 번. 실패하면 예외."""

    fn = getattr(ctypes.windll.crypt32, fn_name)

    given = _to_blob(data)
    entropy = _to_blob(_ENTROPY)
    out = _Blob()

    if fn_name == "CryptProtectData":
        ok = fn(ctypes.byref(given), None, ctypes.byref(entropy),
                None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
    else:
        ok = fn(ctypes.byref(given), None, ctypes.byref(entropy),
                None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))

    if not ok:
        raise OSError(
            f"{fn_name} 실패 (GetLastError={ctypes.get_last_error()})")

    try:
        return _from_blob(out)
    finally:
        _free(out)


def available() -> bool:
    """
    지금 이 자리에서 감쌀 수 있는가.

    있다고 짐작하지 않는다 - 실제로 한 번 감싸고 풀어 본다. Windows
    이름만 보고 판단하면 Wine이나 잠긴 프로필에서 거짓이 된다.
    """

    if os.environ.get("AI_STUDIO_TOKEN_PLAINTEXT") == "1":
        # 사람이 일부러 끈 것. 왜 끄고 싶은 사람이 있는가 - 토큰
        # 파일을 다른 계정/다른 PC로 옮겨야 할 때다.
        return False

    if not sys.platform.startswith("win"):
        return False

    try:
        return _crypt("CryptUnprotectData",
                      _crypt("CryptProtectData", b"probe")) == b"probe"
    except Exception:
        return False


def wrap(data: dict) -> dict:
    """
    적을 것을 감싼다. 못 감싸면 준 것을 그대로 돌려준다.

    감싸지 못한 것을 감싼 척하지 않는다 - 그 판단은 available()이
    말하고 화면이 보여 준다.
    """

    if not available():
        return data

    plain = json.dumps(data, ensure_ascii=False).encode("utf-8")

    try:
        sealed = _crypt("CryptProtectData", plain)
    except Exception:
        return data

    return {
        MARKER_KEY: MARKER_DPAPI,
        PAYLOAD_KEY: base64.b64encode(sealed).decode("ascii"),
    }


def needs_protecting(raw: dict) -> bool:
    """
    읽은 것이 평문이고, 지금 감쌀 수 있는가.

    Sprint236 - 감싸는 일이 save() 에만 붙어 있었다. load() 는 평문을
    읽어 넘기기만 해서, 예전에 적힌 파일은 다음 저장이 일어날 때까지
    그대로 남았다. 이 PC 에서 13일이었다 - access_token 이 살아 있는
    동안에는 저장할 일이 없고, refresh_token 은 만료되지 않으므로 그
    기간은 몇 달일 수도 있다.

    빈 것에는 거짓이다 - 적을 것이 없는데 파일을 건드릴 이유가 없다.
    못 감싸는 자리에서도 거짓이다 - 참이면 읽을 때마다 같은 평문을
    의미 없이 다시 적는다.
    """

    if not raw or not isinstance(raw, dict):
        return False

    if raw.get(MARKER_KEY):
        return False

    return available()


def unwrap(raw: dict) -> dict:
    """
    읽은 것을 푼다.

    예전에 평문으로 적힌 파일도 그대로 읽는다 - 이 프로그램을 쓰던
    사람의 로그인이 판올림 한 번에 사라지면 안 된다. 다음 save()에서
    감싸인 것으로 바뀐다.
    """

    if not isinstance(raw, dict) or raw.get(MARKER_KEY) != MARKER_DPAPI:
        return raw

    sealed = base64.b64decode(raw.get(PAYLOAD_KEY) or "")

    try:
        plain = _crypt("CryptUnprotectData", sealed)
    except Exception as exc:
        # 풀 수 없는 것을 빈 것으로 넘기지 않는다. 빈 것으로 넘기면
        # 화면은 "로그인 필요"라고 말하고, 사람은 다시 로그인하면
        # 되는 줄 안다 - 실제로는 다른 Windows 계정으로 열었거나
        # 파일이 상한 것이고, 그 사실을 알아야 한다.
        raise OSError(
            "저장된 로그인을 풀지 못했습니다. 이 파일은 다른 Windows "
            "계정에서 만들어졌거나 손상되었습니다. 다시 로그인하면 "
            f"새로 만들어집니다. ({exc})") from exc

    return json.loads(plain.decode("utf-8"))
