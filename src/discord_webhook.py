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
    clear_lamp.uc: 'UC',
    clear_lamp.clear: 'COMP',
    clear_lamp.played: 'PLAYED',
}


def discord_lamp_name(lamp: clear_lamp | None) -> str:
    if lamp is None:
        return ''
    return _SENDABLE_LAMPS.get(lamp, str(lamp))


def _legacy_discord_rule(config) -> dict:
    return {
        'name': '既定の送信先',
        'webhook_url': getattr(config, 'discord_webhook_url', ''),
        'enabled': True,
        'updated_results_only': getattr(config, 'discord_updated_results_only', False),
        'level_filter_enabled': getattr(config, 'discord_level_filter_enabled', False),
        'levels': getattr(config, 'discord_levels', []),
        'lamp_filter_enabled': getattr(config, 'discord_lamp_filter_enabled', False),
        'lamps': getattr(config, 'discord_lamps', []),
        'min_score': 0,
        'include_unrecognized_title': False,
    }


def discord_rule_matches(rule: dict, result, is_updated: bool) -> bool:
    """Discord通知ルールとリザルト内容から送信対象か判定する。"""
    if not isinstance(rule, dict):
        return False
    if rule.get('enabled', True) is False:
        return False
    if not str(rule.get('webhook_url', '')).strip():
        return False

    if rule.get('updated_results_only', False) and not is_updated:
        return False

    if rule.get('level_filter_enabled', False):
        levels = set()
        for value in rule.get('levels', []) or []:
            try:
                levels.add(int(value))
            except Exception:
                continue
        if result.level not in levels:
            return False

    if rule.get('lamp_filter_enabled', False):
        lamps = set(str(v) for v in rule.get('lamps', []) or [])
        if discord_lamp_name(result.lamp) not in lamps:
            return False

    try:
        min_score = int(rule.get('min_score') or 0)
    except Exception:
        min_score = 0
    if min_score and (result.score is None or result.score < min_score):
        return False

    return True


def matching_discord_rules(config, result, is_updated: bool) -> list[dict]:
    """今回のリザルトを送る Discord 通知ルールを返す。"""
    rules = getattr(config, 'discord_rules', None)
    if not isinstance(rules, list) or not rules:
        rules = [_legacy_discord_rule(config)]
    return [
        rule for rule in rules
        if discord_rule_matches(rule, result, is_updated)
    ]


def should_send_discord_result(config, result, is_updated: bool) -> bool:
    """Discord設定とリザルト内容から送信対象か判定する。"""
    return bool(matching_discord_rules(config, result, is_updated))


def matching_unrecognized_discord_rules(config) -> list[dict]:
    """曲名未認識リザルトを送る Discord 通知ルールを返す。"""
    rules = getattr(config, 'discord_rules', None)
    if not isinstance(rules, list) or not rules:
        rules = [_legacy_discord_rule(config)]
    return [
        rule for rule in rules
        if (
            isinstance(rule, dict)
            and rule.get('enabled', True) is not False
            and rule.get('include_unrecognized_title', False)
            and str(rule.get('webhook_url', '')).strip()
        )
    ]


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


def build_unrecognized_discord_content(score: int | None = None,
                                       exscore: int | None = None,
                                       lamp: clear_lamp | None = None,
                                       extra_lines: list[str] | None = None) -> str:
    """曲名未認識リザルトは本文なしで画像だけ送る。"""
    return ""


def post_result_to_discord(config, result, artist: str = '',
                           pre_score: int | None = None,
                           pre_exscore: int | None = None,
                           screen=None,
                           extra_lines: list[str] | None = None,
                           show_delta: bool = True,
                           webhook_url: str | None = None) -> bool:
    """Discord Webhookへ送信する。呼び出し側でバックグラウンド実行すること。"""
    url = (webhook_url or getattr(config, 'discord_webhook_url', '')).strip()
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


def post_unrecognized_result_to_discord(config,
                                        score: int | None = None,
                                        exscore: int | None = None,
                                        lamp: clear_lamp | None = None,
                                        screen=None,
                                        extra_lines: list[str] | None = None,
                                        webhook_url: str | None = None) -> bool:
    """曲名未認識リザルトをDiscord Webhookへ送信する。"""
    url = (webhook_url or getattr(config, 'discord_webhook_url', '')).strip()
    if not url:
        return False

    image_bytes = _image_to_png_bytes(screen)
    if not image_bytes:
        logger.warning("Discord曲名未認識リザルト送信スキップ: 添付画像なし")
        return False

    payload = {
        'allowed_mentions': {'parse': []},
    }
    data = {
        'payload_json': json.dumps(payload, ensure_ascii=False),
    }
    files = {
        'file': ('unrecognized_result.png', image_bytes, 'image/png'),
    }

    try:
        resp = requests.post(url, data=data, files=files, timeout=15)
        ok = 200 <= resp.status_code < 300
        if ok:
            logger.info("Discord曲名未認識リザルト送信完了")
        else:
            logger.warning(f"Discord曲名未認識リザルト送信失敗: HTTP {resp.status_code} {resp.text[:200]}")
        return ok
    except Exception:
        logger.error(f"Discord曲名未認識リザルト送信エラー:\n{traceback.format_exc()}")
        return False
