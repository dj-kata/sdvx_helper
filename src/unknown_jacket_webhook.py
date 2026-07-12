"""未登録ジャケット情報を開発用 Discord Webhook へ送信する。"""
from __future__ import annotations

import io
import json
import os
import threading
import traceback
from pathlib import Path
from typing import Optional

import imagehash
import requests
from PIL import Image

from src.classes import difficulty
from src.logger import get_logger

logger = get_logger(__name__)

RESULT_UNKNOWN_NOV_URL_ENV = 'SDVX_HELPER_UNKNOWN_JACKET_RESULT_NOV_WEBHOOK_URL'
RESULT_UNKNOWN_ADV_URL_ENV = 'SDVX_HELPER_UNKNOWN_JACKET_RESULT_ADV_WEBHOOK_URL'
RESULT_UNKNOWN_EXH_URL_ENV = 'SDVX_HELPER_UNKNOWN_JACKET_RESULT_EXH_WEBHOOK_URL'
RESULT_UNKNOWN_APPEND_URL_ENV = 'SDVX_HELPER_UNKNOWN_JACKET_RESULT_APPEND_WEBHOOK_URL'
EDIT_MISSING_HASH_URL_ENV = 'SDVX_HELPER_MISSING_JACKET_HASH_EDIT_WEBHOOK_URL'

RESULT_UNKNOWN_ROUTE_BY_DIFF = {
    difficulty.novice: RESULT_UNKNOWN_NOV_URL_ENV,
    difficulty.advanced: RESULT_UNKNOWN_ADV_URL_ENV,
    difficulty.exhaust: RESULT_UNKNOWN_EXH_URL_ENV,
    difficulty.maximum: RESULT_UNKNOWN_APPEND_URL_ENV,
}

RESULT_UNKNOWN_CROP_RECT = (42, 860, 42 + 757, 860 + 335)

_env_loaded = False
_sent_keys: set[tuple[str, str, str]] = set()
_sent_lock = threading.Lock()


def _load_dotenv_once(path: str | Path = '.env') -> None:
    """python-dotenvを増やさず、単純な KEY=VALUE だけ読み込む。"""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True

    env_path = Path(path)
    if not env_path.exists():
        return

    try:
        for raw_line in env_path.read_text(encoding='utf-8').splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in ('"', "'")
            ):
                value = value[1:-1]
            os.environ[key] = value
    except Exception:
        logger.warning(f".env の読み込みをスキップしました:\n{traceback.format_exc()}")


def _webhook_url(env_name: str) -> str:
    _load_dotenv_once()
    return os.environ.get(env_name, '').strip()


def jacket_hash_hex(jacket_img: Image.Image | None) -> Optional[str]:
    if jacket_img is None:
        return None
    try:
        return str(imagehash.average_hash(jacket_img))
    except Exception:
        logger.warning(f"ジャケットhash計算失敗:\n{traceback.format_exc()}")
        return None


def crop_unknown_result_attachment(screen: Image.Image | None) -> Image.Image | None:
    if screen is None:
        return None
    try:
        return screen.crop(RESULT_UNKNOWN_CROP_RECT)
    except Exception:
        logger.warning(f"未登録ジャケット添付画像の切り出し失敗:\n{traceback.format_exc()}")
        return None


def has_registered_jacket_hash(song_database, title: str, diff: difficulty) -> bool:
    try:
        info = song_database.get_song_info(title)
        return bool(info and info.get_jacket_hash(diff))
    except Exception:
        logger.warning(f"ジャケットhash登録確認失敗:\n{traceback.format_exc()}")
        return True


def _difficulty_label(diff: difficulty | None) -> str:
    if diff is None:
        return 'UNKNOWN'
    return diff.to_db_key() if diff == difficulty.maximum else str(diff)


def _image_to_png_bytes(image: Image.Image | None) -> bytes | None:
    if image is None:
        return None
    try:
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        logger.warning(f"Webhook添付画像エンコード失敗:\n{traceback.format_exc()}")
        return None


def _post_unknown_jacket(
    url: str,
    route_name: str,
    diff: difficulty,
    hash_hex: str,
    version: str,
    attachment_img: Image.Image | None,
) -> bool:
    content = (
        f"- hash: `{hash_hex}`\n"
        f"- difficulty: {_difficulty_label(diff)}, sdvx_helper: {version}"
    )
    payload = {
        'content': content,
        'allowed_mentions': {'parse': []},
    }
    data = {'payload_json': json.dumps(payload, ensure_ascii=False)}

    files = None
    image_bytes = _image_to_png_bytes(attachment_img)
    if image_bytes:
        files = {'file': (f'unknown_jacket_{hash_hex}.png', image_bytes, 'image/png')}

    try:
        resp = requests.post(url, data=data, files=files, timeout=15)
        ok = 200 <= resp.status_code < 300
        if ok:
            logger.info(f"未登録ジャケットWebhook送信完了: {route_name} {hash_hex}")
        else:
            logger.warning(
                f"未登録ジャケットWebhook送信失敗: {route_name} "
                f"HTTP {resp.status_code} {resp.text[:200]}"
            )
        return ok
    except Exception:
        logger.warning(f"未登録ジャケットWebhook送信エラー:\n{traceback.format_exc()}")
        return False


def post_unknown_result_jacket(
    diff: difficulty | None,
    jacket_img: Image.Image | None,
    screen: Image.Image | None,
    version: str,
) -> bool:
    """リザルト画面で曲名認識できなかったジャケットを送信する。"""
    if diff is None:
        return False

    env_name = RESULT_UNKNOWN_ROUTE_BY_DIFF.get(diff)
    if not env_name:
        return False
    url = _webhook_url(env_name)
    if not url:
        return False

    hash_hex = jacket_hash_hex(jacket_img)
    if not hash_hex:
        return False

    route_name = env_name.removesuffix('_WEBHOOK_URL')
    key = (route_name, _difficulty_label(diff), hash_hex)
    with _sent_lock:
        if key in _sent_keys:
            return False
        _sent_keys.add(key)

    attachment = crop_unknown_result_attachment(screen) or jacket_img
    threading.Thread(
        target=_post_unknown_jacket,
        args=(url, route_name, diff, hash_hex, version, attachment),
        daemon=True,
        name='UnknownJacketWebhookThread',
    ).start()
    return True


def post_missing_hash_from_edit(
    diff: difficulty | None,
    jacket_img: Image.Image | None,
    version: str,
) -> bool:
    """スコアビューワ編集登録でDBにhashが無い譜面のジャケットを送信する。"""
    if diff is None:
        return False

    url = _webhook_url(EDIT_MISSING_HASH_URL_ENV)
    if not url:
        return False

    hash_hex = jacket_hash_hex(jacket_img)
    if not hash_hex:
        return False

    route_name = EDIT_MISSING_HASH_URL_ENV.removesuffix('_WEBHOOK_URL')
    key = (route_name, _difficulty_label(diff), hash_hex)
    with _sent_lock:
        if key in _sent_keys:
            return False
        _sent_keys.add(key)

    threading.Thread(
        target=_post_unknown_jacket,
        args=(url, route_name, diff, hash_hex, version, jacket_img),
        daemon=True,
        name='MissingJacketHashWebhookThread',
    ).start()
    return True
