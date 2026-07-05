import hashlib
import json
import os

from app.utils.atomic_write import atomic_write_json

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))

DEFAULT_CACHE_ROOT = os.path.join(_APP_ROOT, ".cache", "assets")


def cache_key(
    provider: str,
    asset_type: str,
    query: str,
    orientation: str = "",
) -> str:
    """provider/asset_type/query/orientation 조합에 대한 결정적 캐시 키."""

    raw = f"{provider}|{asset_type}|{query.strip().lower()}|{orientation}"

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cache_dir(key: str, cache_root: str = DEFAULT_CACHE_ROOT) -> str:
    return os.path.join(cache_root, key)


def get_cached(key: str, cache_root: str = DEFAULT_CACHE_ROOT):
    """
    캐시에 이미 저장된 asset이 있으면 (asset_path, meta) 튜플을,
    없으면 None을 반환합니다.
    """

    directory = cache_dir(key, cache_root)
    meta_path = os.path.join(directory, "meta.json")

    if not os.path.exists(meta_path):
        return None

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        asset_path = os.path.join(directory, meta["filename"])

    except (json.JSONDecodeError, KeyError, OSError):
        # 손상된 캐시 항목은 캐시 미스로 취급하고 재다운로드를 유도한다.
        return None

    if not os.path.exists(asset_path):
        return None

    return asset_path, meta


def save_to_cache(
    key: str,
    content: bytes,
    filename: str,
    meta: dict,
    cache_root: str = DEFAULT_CACHE_ROOT,
) -> str:
    """다운로드한 콘텐츠와 메타데이터를 캐시에 저장하고 asset 경로를 반환."""

    directory = cache_dir(key, cache_root)

    os.makedirs(directory, exist_ok=True)

    asset_path = os.path.join(directory, filename)

    with open(asset_path, "wb") as f:
        f.write(content)

    meta_with_filename = dict(meta)
    meta_with_filename["filename"] = filename

    atomic_write_json(
        os.path.join(directory, "meta.json"),
        meta_with_filename,
    )

    return asset_path
