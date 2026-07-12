"""Discord Webhook へのリザルト送信。"""
from __future__ import annotations

import io
import json
import traceback

import requests

from src.classes import clear_lamp
from src.logger import get_logger

logger = get_logger(__name__)

_SENDABLE_LAMPS = {
    clear_lamp.puc: 'PUC',
    clear_lamp.maxxive: 'MAXXIVE',
    clear_lamp.exc: 'EXC-COMP',
    clear_lamp.clear: 'COMP',
    clear_lamp.played: 'PLAYED',
}


def discord_lamp_name(lamp: clear_lamp | None) -> str:
    if lamp is None:
        return ''
    return _SENDABLE_LAMPS.get(lamp, str(lamp))


def should_send_discord_result(config, result, is_updated: bool) -> bool:
    """Discord設定とリザルト内容から送信対象か判定する。"""
    if not getattr(config, 'discord_webhook_url', '').strip():
        return False

    if getattr(config, 'discord_updated_results_only', False) and not is_updated:
        return False

    if getattr(config, 'discord_level_filter_enabled', False):
        levels = set(int(v) for v in getattr(config, 'discord_levels', []) or [])
        if result.level not in levels:
            return False

    if getattr(config, 'discord_lamp_filter_enabled', False):
        lamps = set(str(v) for v in getattr(config, 'discord_lamps', []) or [])
        if discord_lamp_name(result.lamp) not in lamps:
            return False

    return True


def _fmt_score(value: int | None) -> str:
    return f"{value:,}" if value is not None else "-"


def _fmt_delta(current: int | None, previous: int | None) -> str:
    if current is None:
        return ""
    if previous is None:
        delta = current
    else:
        delta = current - previous
    return f" ({delta:+,})"


def _image_to_png_bytes(screen) -> bytes | None:
    if screen is None:
        return None
    try:
        buf = io.BytesIO()
        screen.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        logger.error(f"Discord添付画像エンコード失敗:\n{traceback.format_exc()}")
        return None


def build_discord_content(result, artist: str = '',
                          pre_score: int | None = None,
                          pre_exscore: int | None = None,
                          extra_lines: list[str] | None = None,
                          show_delta: bool = True) -> str:
    artist_part = artist or "-"
    level_part = f"Lv.{result.level}" if result.level else "Lv.-"
    lines = [
        f"{artist_part} / {result.title} [{result.difficulty}] {level_part}",
        f"lamp: {discord_lamp_name(result.lamp)}",
        f"score: {_fmt_score(result.score)}"
        f"{_fmt_delta(result.score, pre_score) if show_delta else ''}",
    ]
    if result.exscore is not None:
        lines.append(
            f"ex-score: {_fmt_score(result.exscore)}"
            f"{_fmt_delta(result.exscore, pre_exscore) if show_delta else ''}"
        )
    if extra_lines:
        lines.extend(extra_lines)
    return "\n".join(lines)


def post_result_to_discord(config, result, artist: str = '',
                           pre_score: int | None = None,
                           pre_exscore: int | None = None,
                           screen=None,
                           extra_lines: list[str] | None = None,
                           show_delta: bool = True) -> bool:
    """Discord Webhookへ送信する。呼び出し側でバックグラウンド実行すること。"""
    url = getattr(config, 'discord_webhook_url', '').strip()
    if not url:
        return False

    content = build_discord_content(
        result,
        artist=artist,
        pre_score=pre_score,
        pre_exscore=pre_exscore,
        extra_lines=extra_lines,
        show_delta=show_delta,
    )
    payload = {
        'content': content,
        'allowed_mentions': {'parse': []},
    }
    data = {
        'payload_json': json.dumps(payload, ensure_ascii=False),
    }
    files = None
    image_bytes = _image_to_png_bytes(screen)
    if image_bytes:
        files = {
            'file': ('result.png', image_bytes, 'image/png'),
        }

    try:
        resp = requests.post(url, data=data, files=files, timeout=15)
        ok = 200 <= resp.status_code < 300
        if ok:
            logger.info(f"Discord送信完了: {result}")
        else:
            logger.warning(f"Discord送信失敗: HTTP {resp.status_code} {resp.text[:200]}")
        return ok
    except Exception:
        logger.error(f"Discord送信エラー:\n{traceback.format_exc()}")
        return False
