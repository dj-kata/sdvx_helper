"""SDVX Helper Portal 連携マネージャー。
https://sh-portal.maya2silence.com との通信を管理する。
"""
from __future__ import annotations

import bz2
import datetime
import hashlib
import hmac
import importlib.util
import os
import pickle
import sys
import traceback
from typing import TYPE_CHECKING, Optional

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

from src.classes import difficulty, clear_lamp
from src.logger import get_logger
from src.portal_uploaded_scores import ManageUploadedScores, OneUploadedScore

if TYPE_CHECKING:
    from src.result_database import ResultDatabase

logger = get_logger(__name__)

PORTAL_URL = 'https://sh-portal.maya2silence.com'


def _resolve_hmac_key() -> str:
    """HMAC署名キーを以下の優先順位で解決する。

    1. src/portal_secret.py の PORTAL_HMAC_KEY
       - 開発時: Python ファイルから import
       - cx_Freeze ビルド時: ビルド前に設定しておくとコンパイル済み .pyc に埋め込まれる
    2. exe 隣の portal_secret.txt（cx_Freeze 配布後に外部設定したい場合）
    3. sdvx_helper/params_secret.py の maya2_key（v1共存環境・開発時のみ）
    """
    # 1. Python import（開発時はソース、cx_Freeze時はコンパイル済み .pyc から）
    try:
        from src.portal_secret import PORTAL_HMAC_KEY
        if PORTAL_HMAC_KEY:
            logger.debug('HMAC key loaded from src/portal_secret.py')
            return PORTAL_HMAC_KEY
    except ImportError:
        pass

    is_frozen = getattr(sys, 'frozen', False)

    # 2. exe 隣の portal_secret.txt（cx_Freeze 配布時の外部設定用）
    if is_frozen:
        secret_file = os.path.join(os.path.dirname(sys.executable), 'portal_secret.txt')
        if os.path.exists(secret_file):
            try:
                with open(secret_file, encoding='utf-8') as f:
                    key = f.read().strip()
                if key:
                    logger.debug('HMAC key loaded from portal_secret.txt')
                    return key
            except Exception:
                logger.debug(f'portal_secret.txt 読み込み失敗:\n{traceback.format_exc()}')

    # 3. v1 の params_secret.py（開発環境のみ。frozen では __file__ が仮想パスになるためスキップ）
    if not is_frozen:
        v1_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), '..', 'sdvx_helper', 'params_secret.py')
        )
        if os.path.exists(v1_path):
            try:
                spec = importlib.util.spec_from_file_location('_params_secret_v1', v1_path)
                mod  = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                key = getattr(mod, 'maya2_key', '')
                if key:
                    logger.debug('HMAC key loaded from sdvx_helper/params_secret.py')
                    return key
            except Exception:
                logger.debug(f'v1 params_secret.py 読み込み失敗:\n{traceback.format_exc()}')


_HMAC_KEY = _resolve_hmac_key()

# v2 clear_lamp → portal ランプ文字列
_LAMP_TO_PORTAL = {
    clear_lamp.noplay:  'PLAYED',
    clear_lamp.played:  'PLAYED',
    clear_lamp.clear:   'COMP',
    clear_lamp.exc:     'EX_COMP',
    clear_lamp.maxxive: 'MAX_COMP',
    clear_lamp.uc:      'UC',
    clear_lamp.puc:     'PUC',
}

# portal ランプ優先度（インデックスが高いほど良い）
_LAMP_PRIORITY = ['PLAYED', 'COMP', 'EX_COMP', 'MAX_COMP', 'UC', 'PUC']


class PortalManager:
    """SDVX Helper Portal との連携を担当するクラス。"""

    MASTER_CACHE_PATH = os.path.join('out', 'portal_master.sdvxh')

    def __init__(self, token: str = ''):
        self.token = token
        self.master_db: list = []
        self._uploaded_scores_mng: Optional[ManageUploadedScores] = None
        if _HMAC_KEY:
            logger.info('PortalManager initialized (HMAC key OK)')
        else:
            logger.warning('PortalManager initialized (HMAC key NOT found)')

    # ── キャッシュ ────────────────────────────────────────────────────────────

    def load_cache(self):
        """起動時に楽曲マスタキャッシュを読み込む。失敗時は無視する。"""
        try:
            with bz2.BZ2File(self.MASTER_CACHE_PATH, 'rb') as f:
                self.master_db = pickle.load(f)
            logger.info(f'Portal楽曲マスタキャッシュ読み込み完了: {len(self.master_db)} 曲')
        except FileNotFoundError:
            logger.debug('Portal楽曲マスタキャッシュが見つかりません')
        except Exception:
            logger.warning(f'Portal楽曲マスタキャッシュ読み込み失敗:\n{traceback.format_exc()}')

    def _save_cache(self):
        """楽曲マスタをキャッシュファイルに保存する。"""
        try:
            os.makedirs('out', exist_ok=True)
            with bz2.BZ2File(self.MASTER_CACHE_PATH, 'wb', compresslevel=1) as f:
                pickle.dump(self.master_db, f)
            logger.info('Portal楽曲マスタキャッシュ保存完了')
        except Exception:
            logger.error(f'Portal楽曲マスタキャッシュ保存失敗:\n{traceback.format_exc()}')

    def _get_mng(self) -> ManageUploadedScores:
        """ManageUploadedScores のキャッシュインスタンスを返す（初回のみロード）。"""
        if self._uploaded_scores_mng is None:
            self._uploaded_scores_mng = ManageUploadedScores()
        return self._uploaded_scores_mng

    def update_token(self, token: str):
        self.token = token

    def is_alive(self) -> bool:
        """サーバが生きているか確認。トークン未設定時は False を返す。"""
        if not _REQUESTS_AVAILABLE:
            return False
        if not self.token:
            return False
        try:
            r = requests.get(PORTAL_URL + '/', timeout=5)
            return r.status_code == 200
        except Exception:
            logger.warning(f'portal server unreachable:\n{traceback.format_exc()}')
            return False

    def get_musiclist(self) -> bool:
        """楽曲マスタを受信して self.master_db にセットする。

        Returns:
            bool: 成功した場合 True
        """
        if not _REQUESTS_AVAILABLE:
            logger.warning('requests ライブラリが未インストールのためスキップ')
            return False
        if not self.token:
            logger.info('トークン未設定のためスキップ')
            return False
        try:
            header = {'X-Auth-Token': self.token}
            r = requests.post(
                PORTAL_URL + '/api/v1/export/musics',
                headers=header,
                timeout=30,
            )
            r.raise_for_status()
            self.master_db = r.json().get('musics', [])
            logger.info(f'楽曲マスタ受信完了: {len(self.master_db)} 曲')
            self._save_cache()
            return True
        except Exception:
            logger.error(f'楽曲マスタ受信失敗:\n{traceback.format_exc()}')
            self.master_db = []
            return False

    def get_rivals(self) -> dict:
        """ポータルに登録されているライバルのスコアを取得する。

        master_db を使って music_id → title を解決し、
        {rival_name: [{"title":str,"difficulty":str,"score":int,
                       "exscore":int|None,"lamp":str}]} 形式で返す。
        失敗時は空 dict を返す。
        """
        if not _REQUESTS_AVAILABLE:
            return {}
        if not self.token:
            return {}
        try:
            # master_db 未取得なら先に取得（music_id → title マップに必要）
            if not self.master_db:
                self.get_musiclist()

            r = requests.post(
                PORTAL_URL + '/api/v1/export/rival_scores',
                headers={'X-Auth-Token': self.token},
                timeout=20,
            )
            r.raise_for_status()
            raw = r.json().get('datas') or {}

            # music_id → title マップを master_db から構築
            id_to_title: dict[str, str] = {
                m['music_id']: m.get('title', '')
                for m in self.master_db
                if m.get('music_id')
            }

            # レスポンスを正規化: {rival_name: [{title,difficulty,score,...}]}
            normalized: dict[str, list] = {}
            for _key, val in raw.items():
                if not isinstance(val, dict):
                    continue
                rival_name = val.get('rival_name') or _key
                norm_scores = []
                for s in val.get('scores', []):
                    title = id_to_title.get(s.get('music_id', ''), '')
                    if not title:
                        continue
                    norm_scores.append({
                        'title':      title,
                        'difficulty': s.get('difficulty_type', ''),
                        'score':      s.get('score_value', 0),
                        'exscore':    s.get('exscore_value'),
                        'lamp':       s.get('lamp') or s.get('clear_type') or '',
                    })
                normalized[rival_name] = norm_scores

            logger.info(f'ポータルライバル取得完了: {len(normalized)} 人')
            return normalized
        except Exception:
            logger.error(f'ポータルライバル取得失敗:\n{traceback.format_exc()}')
            return {}

    def get_4th_diff_map(self) -> dict[tuple[str, int], str]:
        """(title, level) → 4th難易度名 (MXM/INF/GRV/HVN/VVD/XCD) のマップを返す。

        master_db が空の場合は空 dict を返す。
        """
        result: dict[tuple[str, int], str] = {}
        for music in self.master_db:
            title = music.get('title', '')
            if not title:
                continue
            for chart in music.get('charts', []):
                cdiff = chart.get('difficulty', '')
                lv    = chart.get('level', 0)
                if cdiff not in ('NOV', 'ADV', 'EXH') and lv > 0:
                    result[(title, lv)] = cdiff
        return result

    def get_tier_map(self) -> dict:
        """(title, difficulty_enum) → (s_tier, p_tier) マップを返す。

        s_tier/p_tier は portal チャートオブジェクトのフィールド値（文字列）。
        master_db が空の場合は空 dict を返す。
        """
        result: dict = {}
        for music in self.master_db:
            title = music.get('title', '')
            if not title:
                continue
            for chart in music.get('charts', []):
                cdiff   = chart.get('difficulty', '')
                s_tier  = str(chart.get('s_tier') or '').removeprefix('Tier ').strip()
                p_tier  = str(chart.get('p_tier') or '').removeprefix('Tier ').strip()
                if cdiff == 'NOV':
                    d = difficulty.novice
                elif cdiff == 'ADV':
                    d = difficulty.advanced
                elif cdiff == 'EXH':
                    d = difficulty.exhaust
                else:
                    d = difficulty.maximum
                result[(title, d)] = (s_tier, p_tier)
        return result

    def _find_chart(self, title: str, diff: difficulty):
        """楽曲マスタから指定の譜面を検索。

        Returns:
            (music dict, chart dict) or (None, None)
        """
        for music in self.master_db:
            if music.get('title') == title:
                for chart in music.get('charts', []):
                    cdiff = chart.get('difficulty', '')
                    # maximum (MXM枠) は NOV/ADV/EXH 以外の最初の譜面にマッチ
                    if diff == difficulty.maximum:
                        if cdiff not in ('NOV', 'ADV', 'EXH'):
                            return music, chart
                    else:
                        if cdiff == str(diff):  # 'NOV', 'ADV', 'EXH'
                            return music, chart
        return None, None

    def upload_scores(
        self,
        result_database: ResultDatabase,
        start_time: Optional[int] = None,
        upload_all: bool = False,
        player_name: str = 'NONAME',
        volforce: str = '0.000',
    ) -> Optional[object]:
        """スコアをポータルに送信する。

        Args:
            result_database: ResultDatabase インスタンス
            start_time:  この時刻以降の今日のリザルトのみ送信
                         (None かつ upload_all=False の場合は何もしない)
            upload_all:  True の場合は全自己ベストを送信
            player_name: プレイヤー名（CSVヘッダー用）
            volforce:    Volforce文字列（CSVヘッダー用）

        Returns:
            requests.Response or None
        """
        if not _REQUESTS_AVAILABLE:
            logger.warning('requests ライブラリが未インストールのためスキップ')
            return None
        if not self.token:
            logger.info('トークン未設定のためスキップ')
            return None
        if upload_all:
            bests = result_database.get_all_best_results()
            candidates = [
                (b.title, b.difficulty, b.best_score, b.best_exscore, b.best_lamp)
                for b in bests.values()
                if b.best_score > 0
            ]
        else:
            if start_time is None:
                logger.info('start_time 未指定かつ upload_all=False のためスキップ')
                return None
            today = result_database.get_today_results(start_time)
            if not today:
                logger.info('今日のリザルトなし、送信スキップ')
                return None
            candidates = [
                (r.title, r.difficulty, r.score, r.exscore, r.lamp)
                for r in today
                if r.score is not None and r.lamp is not None
            ]

        if not candidates:
            logger.info('送信データなし')
            return None

        if not self.master_db:
            logger.info('楽曲マスタ未取得のため取得を試みます...')
            if not self.get_musiclist() or not self.master_db:
                logger.warning('楽曲マスタ取得失敗のためスキップ')
                return None

        # ── portal 楽曲マスタとマッチング ────────────────────────────────────
        tmp: dict = {}  # key: "music_id___difficulty" → dict
        cnt_ok = 0
        cnt_ng = 0
        for title, diff, score, exscore, lamp in candidates:
            music, chart = self._find_chart(title, diff)
            if chart is None:
                cnt_ng += 1
                logger.debug(f'portal DBで未発見: {title} / {diff}')
                continue

            music_id = music.get('music_id')
            cdiff    = chart.get('difficulty')
            lamp_str = _LAMP_TO_PORTAL.get(lamp, 'PLAYED')
            key = f'{music_id}___{cdiff}'

            if key not in tmp:
                tmp[key] = {
                    'music_id':   music_id,
                    'difficulty': cdiff,
                    'score':      score or 0,
                    'exscore':    exscore or 0,
                    'lamp':       lamp_str,
                }
            else:
                existing = tmp[key]
                existing['score']   = max(existing['score'],   score or 0)
                existing['exscore'] = max(existing['exscore'], exscore or 0)
                p_new = _LAMP_PRIORITY.index(lamp_str) if lamp_str in _LAMP_PRIORITY else 0
                p_old = _LAMP_PRIORITY.index(existing['lamp']) if existing['lamp'] in _LAMP_PRIORITY else 0
                if p_new > p_old:
                    existing['lamp'] = lamp_str
            cnt_ok += 1

        logger.info(f'マッチング結果: OK={cnt_ok}, NG={cnt_ng}')
        if not tmp:
            logger.info('全曲マッチング失敗、送信スキップ')
            return None

        # ── CSV 生成 ──────────────────────────────────────────────────────────
        lines = [f'{player_name},{volforce}']
        for dat in tmp.values():
            lines.append(
                f"{dat['music_id']},{dat['difficulty']},{dat['score']},{dat['exscore']},{dat['lamp']}"
            )
        payload_str = '\r\n'.join(lines)

        now = datetime.datetime.now().replace(microsecond=0)
        cnt = len(tmp)

        # HMAC チェックサム
        key = _HMAC_KEY or _resolve_hmac_key()  # 起動後にファイルが置かれた場合も拾う
        if key:
            checksum = hmac.new(key.encode('utf-8'),
                                payload_str.encode('utf-8'),
                                hashlib.sha256).hexdigest()
        else:
            checksum = ''
            logger.warning(
                'HMAC キー未設定。src/portal_secret.py に PORTAL_HMAC_KEY を設定するか、'
                'sdvx_helper/params_secret.py に maya2_key が存在することを確認してください。'
            )

        full_csv = payload_str + '\r\n' + f'{now},{cnt},{checksum}'

        os.makedirs('out', exist_ok=True)
        csv_path = 'out/portal_payload.csv'
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            f.write(full_csv)

        # ── ポータルへ送信 ────────────────────────────────────────────────────
        try:
            header = {'X-Auth-Token': self.token}
            url    = PORTAL_URL + '/api/v1/import/scores'
            with open(csv_path, 'rb') as f:
                file_binary = f.read()
            files = {'regist_score': (csv_path, file_binary)}
            res   = requests.post(url, files=files, headers=header, timeout=10)
            logger.info(f'portal upload: status={res.status_code}')
            logger.debug(f'portal response: {res.text[:200]}')

            # 成功時: リビジョン番号を送信済みスコアリストに記録
            if res.status_code == 200:
                try:
                    revision = res.json().get('revision', -1)
                    logger.info(f'portal revision: {revision}')
                    mng = self._get_mng()
                    for dat in tmp.values():
                        mng.push(OneUploadedScore(
                            revision=revision,
                            music_id=dat['music_id'],
                            difficulty=dat['difficulty'],
                            score=dat['score'],
                            exscore=dat['exscore'],
                            lamp=dat['lamp'],
                            uploaded_at=now,
                        ))
                    mng.save()
                except Exception:
                    logger.warning(f'revision 記録失敗:\n{traceback.format_exc()}')

            return res
        except Exception:
            logger.error(f'portal upload 失敗:\n{traceback.format_exc()}')
            return None

    def get_uploaded_scores(self, title: str, diff: difficulty) -> list:
        """指定譜面のportal送信済みスコアリストを返す。

        master_db が未取得またはタイトル未発見の場合は空リストを返す。
        """
        music, chart = self._find_chart(title, diff)
        if chart is None:
            return []
        music_id = music.get('music_id')
        cdiff    = chart.get('difficulty')
        mng = self._get_mng()
        return [s for s in mng.scores if s.music_id == music_id and s.difficulty == cdiff]

    def delete_score(self, revision: int, music_id: str, cdiff: str) -> Optional[object]:
        """portal上のスコアを1件削除する。

        成功時は uploaded_score.pkl から該当エントリを除去して保存する。

        Returns:
            requests.Response or None
        """
        if not _REQUESTS_AVAILABLE:
            logger.warning('requests ライブラリが未インストールのためスキップ')
            return None
        if not self.token:
            logger.info('トークン未設定のためスキップ')
            return None

        # CSV 生成（v1 互換フォーマット）
        now = datetime.datetime.now().replace(microsecond=0)
        lines = [str(revision), f'{music_id},{cdiff},,,,1']
        payload_str = '\r\n'.join(lines)

        key = _HMAC_KEY or _resolve_hmac_key()
        if key:
            checksum = hmac.new(key.encode('utf-8'),
                                payload_str.encode('utf-8'),
                                hashlib.sha256).hexdigest()
        else:
            checksum = ''
            logger.warning('HMAC キー未設定のため checksum なしで送信します')

        full_csv = payload_str + '\r\n' + f'{now},1,{checksum}'

        os.makedirs('out', exist_ok=True)
        csv_path = 'out/portal_modify.csv'
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            f.write(full_csv)

        try:
            url   = PORTAL_URL + '/api/v1/import/modify'
            with open(csv_path, 'rb') as f:
                file_binary = f.read()
            files = {'modify': (csv_path, file_binary)}
            res   = requests.post(url, files=files,
                                  headers={'X-Auth-Token': self.token}, timeout=5)
            logger.info(f'portal delete: status={res.status_code}')
            logger.debug(f'portal delete response: {res.text[:200]}')

            # portal 側にリビジョンがなかった場合も含め、
            # レスポンスに関わらずローカルの記録は常に削除する
            mng = self._get_mng()
            mng.delete(revision, music_id, cdiff)
            mng.save()

            return res
        except Exception:
            logger.error(f'portal delete 失敗:\n{traceback.format_exc()}')
            return None
