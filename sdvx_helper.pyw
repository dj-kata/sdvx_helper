"""
SDVX Helper - メインプログラム
OBS連携による自動リザルト保存アプリケーション
"""

import sys
import base64
import datetime
import io
import traceback
import os
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer, Qt, Signal, Slot

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

from src.config import Config
from src.classes import detect_mode
from src.funcs import get_title_with_chart, escape_for_filename
from src.obs_websocket_manager import OBSWebSocketManager
from src.songinfo import SongDatabase, update_musiclist_from_remote
from src.screen_reader import ScreenReader
from src.result import OneResult
from src.result_database import ResultDatabase
from src.define import DETECT_CAPTURE_DELAY
from src.logger import get_logger

from src.config_dialog import ConfigDialog
from src.score_viewer import ScoreViewer
from src.obs_dialog import OBSControlDialog
from src.main_window import MainWindowUI
from src.rival_data import RivalManager
from src.portal_manager import PortalManager
from src.summary_generator import (
    capture_summary_item_from_screen,
    generate_summary,
    generate_summary_from_items,
)

logger = get_logger('sdvx_helper')

try:
    with open('version.txt', 'r') as f:
        SWVER = f.readline().strip().lstrip('v')
except Exception:
    SWVER = "0.0.0"


class MainWindow(MainWindowUI):
    """メインウィンドウクラス - 制御ロジックを担当"""

    musiclist_update_finished = Signal(bool)

    def __init__(self):
        self.config = Config()
        super().__init__(self.config)
        self._prepare_output_templates()

        self.song_database = SongDatabase()
        self.result_database = ResultDatabase(config=self.config)
        self.screen_reader = ScreenReader(
            song_db=self.song_database,
            orientation=self._parse_orientation(self.config.screen_orientation_override),
        )

        # OBS接続マネージャー
        self.obs_manager = OBSWebSocketManager()
        self.obs_manager.set_config(self.config)
        # QueuedConnection を明示: OBSMonitorThread（バックグラウンド）からの emit が
        # DirectConnection になってバックグラウンドスレッドで UI 操作されないよう保証する
        self.obs_manager.connection_changed.connect(
            self.on_obs_connection_changed, Qt.QueuedConnection
        )

        # Portal連携マネージャー
        self.portal_manager = PortalManager(token=self.config.portal_token)
        self.portal_manager.load_cache()   # 前回キャッシュを即時反映
        self.result_database.portal_manager = self.portal_manager # ResultDatabaseにPortalManagerを連携
        self.result_database.broadcast_vf_data()   # マスタ反映後のデータを配信
        self.result_database.broadcast_stats_data()
        if self.config.portal_token:
            QTimer.singleShot(3000, self._portal_fetch_musiclist)

        self.musiclist_update_finished.connect(
            self._on_musiclist_update_finished, Qt.QueuedConnection
        )
        QTimer.singleShot(100, self._update_musiclist_async)

        # ライバルマネージャー（Portal取得も同時に行う）
        self.rival_manager = RivalManager(parent=self)
        self.rival_manager.load_cache()
        self.result_database.rival_manager = self.rival_manager
        portal_fn = (self.portal_manager.get_rivals
                     if self.config.portal_token else None)
        QTimer.singleShot(2000, lambda: self.rival_manager.start_fetch(
            self.config.rivals, portal_fetch_fn=portal_fn))

        # アプリケーション状態
        self.current_mode: detect_mode = detect_mode.init
        self._start_time: int = int(datetime.datetime.now().timestamp())
        self.play_count: int = 0
        self.last_saved_song: str = "---"
        self.score_viewer = None

        # 状態変数
        self.detect_enter_time: float = 0.0   # detect状態に入った時刻
        self.detect_read_done: bool = False    # detect読み取り済みフラグ
        self.current_title: str | None = None  # detect/selectで確定した曲タイトル
        self.current_diff = None               # detect/selectで確定した難易度
        self._last_select_cursong_key = None   # 選曲画面から最後に履歴表示へ配信した譜面
        self.result_timestamp: int = 0         # リザルト画面に入った時刻
        self.result_pre = None                 # 前回のリザルト読み取り結果
        self._result_summary_items = []        # 保存有無に関係なく当日summaryへ使う切り出しパーツ
        self._text_summary_results = []        # テキスト版summary用の当日リザルト

        # 起動時プレイ数を集計
        self._count_today_plays()
        QTimer.singleShot(100, lambda: self.result_database.broadcast_today_results_data(
            self.start_time_with_offset
        ))
        QTimer.singleShot(100, self._load_recent_result_images_for_summary)

        # UI初期化
        self.init_ui()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.config.keep_on_top)

        # OBS接続
        self.obs_manager.connect()

        # 起動直後のOBS設定警告
        QTimer.singleShot(1000, self._check_obs_configuration)

        # OBSトリガー: アプリ起動時
        self._execute_obs_triggers('app_start')

        # メインループ (100ms)
        self.main_timer = QTimer()
        self.main_timer.timeout.connect(self.main_loop)
        self.main_timer.start(100)

        # 表示更新 (500ms)
        self.display_timer = QTimer()
        self.display_timer.timeout.connect(self.update_display)
        self.display_timer.start(500)

        # グローバルホットキー
        self.setup_global_hotkeys()

        logger.info("アプリケーション起動完了")

    def _prepare_output_templates(self):
        """OBSへ登録しやすいようにtemplate/*.htmlをout/へ同期する。"""
        out_dir = Path('out')
        out_dir.mkdir(exist_ok=True)
        for name in ('nowplaying.html',):
            src = Path('template') / name
            dst = out_dir / name
            try:
                if src.exists():
                    dst.write_bytes(src.read_bytes())
            except Exception:
                logger.error(f"HTMLテンプレート同期失敗: {src} -> {dst}\n{traceback.format_exc()}")

    # ── プロパティ ────────────────────────────────────────────────────────────

    @property
    def start_time(self) -> int:
        return self._start_time

    @property
    def start_time_with_offset(self) -> int:
        return self._start_time - self.config.autoload_offset * 3600

    # ── ユーティリティ ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_orientation(value: str | None):
        """設定文字列を screen_orientation Enum に変換"""
        from src.classes import screen_orientation
        _MAP = {
            'top_up':    screen_orientation.top_up,
            'top_right': screen_orientation.top_right,
            'top_left':  screen_orientation.top_left,
        }
        return _MAP.get(value)

    def _count_today_plays(self):
        """起動時にオフセット範囲内のresultリザルト数をカウント"""
        self.play_count = sum(
            1 for r in self.result_database.results
            if r.detect_mode == detect_mode.result
            and r.timestamp >= self.start_time_with_offset
        )

    def _load_recent_result_images_for_summary(self):
        """起動時に保存済みリザルト画像からsummary用パーツを復元する。"""
        try:
            image_dir = Path(self.config.image_save_path)
            if not image_dir.exists():
                return

            start_time = self.start_time_with_offset
            candidates = sorted(
                (
                    p for p in image_dir.glob("*.png")
                    if p.is_file() and int(p.stat().st_mtime) >= start_time
                ),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not candidates:
                return

            loaded = 0
            skipped_non_result = 0
            skipped_no_update = 0
            items = []

            from PIL import Image

            for path in candidates:
                if len(items) >= 30:
                    break
                try:
                    with Image.open(path) as img:
                        self.screen_reader.update_screen(img)
                        if self.screen_reader.detect_screen() != detect_mode.result:
                            skipped_non_result += 1
                            continue

                        mtime = int(path.stat().st_mtime)
                        data = self.screen_reader.read_from_result()
                        if not self._should_include_saved_summary_image(data, mtime):
                            skipped_no_update += 1
                            continue

                        screen = self.screen_reader.corrected_screen
                        if screen is None:
                            continue
                        item = capture_summary_item_from_screen(screen, mtime)
                        if item is not None:
                            items.append(item)
                            loaded += 1
                except Exception:
                    logger.debug(f"起動時summary画像読み込みスキップ: {path}\n{traceback.format_exc()}")

            if items:
                self._result_summary_items = sorted(
                    items,
                    key=lambda item: item.timestamp,
                    reverse=True,
                )[:30]
                generate_summary_from_items(self._result_summary_items)
                logger.info(
                    "起動時summary復元: "
                    f"{loaded}件 読み込み / 非リザルト {skipped_non_result}件 / "
                    f"更新なし {skipped_no_update}件"
                )
        except Exception:
            logger.error(f"起動時summary復元エラー:\n{traceback.format_exc()}")

    # ── OBS関連 ──────────────────────────────────────────────────────────────

    def _check_obs_configuration(self):
        """OBS設定の問題があればダイアログを表示"""
        if self.obs_manager.is_direct_capture():
            return
        status = self.obs_manager.get_detailed_status()
        warnings = []
        if not status['is_connected']:
            warnings.append("• OBS WebSocketに接続できていません")
        if not status['is_source_configured']:
            warnings.append("• 監視対象ソースが設定されていません")
        if warnings:
            msg = "OBS設定に問題があります:\n\n" + "\n".join(warnings)
            msg += "\n\nOBSが起動していることと本アプリの設定を確認してください。"
            msg += "\n(メニュー: ファイル → OBS制御設定)"
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Warning)
            mb.setWindowTitle("OBS設定の警告")
            mb.setText(msg)
            mb.exec()

    def _execute_obs_triggers(self, trigger: str):
        """指定トリガーのOBS制御を実行"""
        if self.obs_manager.is_direct_capture():
            return
        try:
            from src.obs_control import OBSControlData
            control_data = OBSControlData()
            control_data.set_config(self.config)
            settings = control_data.get_settings_by_trigger(trigger)
            if not settings or not self.obs_manager.is_connected:
                return
            for setting in settings:
                try:
                    action = setting.get("action")
                    if action == "switch_scene":
                        target = setting.get("scene")
                        if target:
                            self.obs_manager.change_scene(target)
                    elif action in ("show_source", "hide_source"):
                        scene = setting.get("scene")
                        source = setting.get("source")
                        if scene and source:
                            mod_scene, item_id = self.obs_manager.search_itemid(scene, source)
                            if item_id:
                                if action == "show_source":
                                    self.obs_manager.enable_source(mod_scene, item_id)
                                else:
                                    self.obs_manager.disable_source(mod_scene, item_id)
                    elif action == "autosave_source":
                        scene = setting.get("scene")
                        source = setting.get("source")
                        if scene and source:
                            _, item_id = self.obs_manager.search_itemid(scene, source)
                            if item_id:
                                fname = (os.path.splitext(source)[0]
                                         + f"_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.png")
                                dst = Path(self.config.image_save_path).resolve() / fname
                                self.obs_manager.save_screenshot_dst(source, str(dst), disable_wh=True)
                except Exception:
                    logger.error(f"トリガー実行エラー ({trigger}):\n{traceback.format_exc()}")
        except ImportError:
            pass  # obs_control.py が未実装の場合はスキップ
        except Exception:
            logger.error(f"トリガー実行エラー ({trigger}):\n{traceback.format_exc()}")

    def _write_obs_text(self, text: str):
        """OBSテキストソースに楽曲情報を書き込む"""
        source = self.config.obs_text_source_name
        if source and self.obs_manager.is_connected and not self.obs_manager.is_direct_capture():
            self.obs_manager.change_text(source, text)

    # ── 設定ダイアログ ────────────────────────────────────────────────────────

    def _portal_fetch_musiclist(self):
        """バックグラウンドで楽曲マスタを取得する"""
        import threading
        def _fetch():
            ok = self.portal_manager.get_musiclist()
            if ok:
                logger.info(f'Portal楽曲マスタ取得完了: {len(self.portal_manager.master_db)} 曲')
                # 取得完了後に再配信
                self.result_database.broadcast_vf_data()
                self.result_database.broadcast_stats_data()
            else:
                logger.warning('Portal楽曲マスタ取得失敗')
        threading.Thread(target=_fetch, daemon=True).start()

    def _update_musiclist_async(self):
        """楽曲DB更新フック。v2では旧musiclist.pkl更新を行わない。"""
        import threading

        def _fetch():
            ok = update_musiclist_from_remote()
            self.musiclist_update_finished.emit(ok)

        threading.Thread(target=_fetch, daemon=True, name="MusiclistRefreshThread").start()

    @Slot(bool)
    def _on_musiclist_update_finished(self, ok: bool):
        """楽曲DB更新後、参照中のDBを再読み込みする。"""
        if not ok:
            return
        self.song_database.load()
        self.result_database.song_database.load()
        self.result_database.broadcast_vf_data()
        self.result_database.broadcast_stats_data()
        logger.info(f"楽曲DB再読み込み完了: {len(self.song_database)} 曲")

    def open_config_dialog(self):
        """設定ダイアログを開く"""
        dialog = ConfigDialog(self.config, self.result_database,
                              rival_manager=self.rival_manager,
                              portal_manager=self.portal_manager,
                              screen_reader=self.screen_reader, parent=self)
        dialog.result_images_import_requested.connect(self._on_result_images_imported)
        dialog.import_finished.connect(self._on_any_data_imported)
        if dialog.exec():
            self._apply_config_changes()
            # トークンが更新された場合は楽曲マスタを再取得
            if self.config.portal_token and not self.portal_manager.master_db:
                self._portal_fetch_musiclist()
            self.statusBar().showMessage("設定を更新しました", 3000)

    def open_obs_dialog(self):
        """OBS制御設定ダイアログを開く"""
        dialog = OBSControlDialog(self.config, self.obs_manager, parent=self)
        if dialog.exec():
            self._apply_config_changes()
            self.statusBar().showMessage("OBS制御設定を更新しました", 3000)

    def open_score_viewer(self):
        """スコアビューワを開く"""
        if self.score_viewer is not None and self.score_viewer.isVisible():
            self.score_viewer.raise_()
            self.score_viewer.activateWindow()
            return
        self.score_viewer = ScoreViewer(
            self.config, self.result_database,
            rival_manager=self.rival_manager,
            portal_manager=self.portal_manager,
        )
        self.score_viewer.show()

    def _on_result_images_imported(self):
        """画像インポート完了時の処理"""
        if self.score_viewer is not None and self.score_viewer.isVisible():
            self.score_viewer.refresh_data()

    def _on_any_data_imported(self):
        """何らかのデータ（alllog / images）がインポートされた際の処理"""
        if self.score_viewer is not None and self.score_viewer.isVisible():
            self.score_viewer.refresh_data()

    def _apply_config_changes(self):
        """設定変更を全モジュールに反映"""
        self.config.load_config()
        self.obs_manager.set_config(self.config)
        self.screen_reader = ScreenReader(
            song_db=self.song_database,
            orientation=self._parse_orientation(self.config.screen_orientation_override),
        )
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.config.keep_on_top)
        self.show()
        if self.obs_manager.is_direct_capture() or not self.obs_manager.is_connected:
            self.obs_manager.connect()

    def show_about(self):
        """バージョン情報表示"""
        QMessageBox.about(
            self, self.ui.window.about_title,
            f"SDVX Helper {SWVER}\n\nauthor: dj-kata"
        )

    # ── メインループ ──────────────────────────────────────────────────────────

    def main_loop(self):
        """メインループ - 100ms毎に呼ばれる"""
        try:
            if not self.obs_manager.is_capture_ready():
                return

            self.obs_manager.screenshot()
            if self.obs_manager.screen is None:
                return

            self.screen_reader.update_screen(self.obs_manager.screen)

            new_mode = self.screen_reader.detect_screen()

            if new_mode != self.current_mode:
                self._on_mode_changed(self.current_mode, new_mode)
                self.current_mode = new_mode

            # 各モード処理
            if self.current_mode == detect_mode.select:
                self._process_select()
            elif self.current_mode == detect_mode.detect:
                self._process_detect()
            elif self.current_mode == detect_mode.result:
                self._process_result()

        except Exception:
            logger.error(f"メインループエラー:\n{traceback.format_exc()}")

    def _on_mode_changed(self, old: detect_mode, new: detect_mode):
        """モード変更時の処理"""
        import time
        logger.info(f"モード変更: {old.name} → {new.name}")
        if old == detect_mode.detect and new != detect_mode.detect and not self.detect_read_done:
            elapsed = time.time() - self.detect_enter_time if self.detect_enter_time else 0.0
            logger.warning(
                f"detect読み取り前に画面遷移: {old.name} → {new.name}, "
                f"elapsed={elapsed:.3f}s"
            )

        # OBSトリガー実行
        trigger_map = {
            (detect_mode.select, detect_mode.detect): ("select_end", "detect_start"),
            (detect_mode.init,   detect_mode.detect): (None, "detect_start"),
            (detect_mode.detect, detect_mode.play):   ("detect_end", "play_start"),
            (detect_mode.detect, detect_mode.init):   ("detect_end", None),
            (detect_mode.play,   detect_mode.result): ("play_end",  "result_start"),
            (detect_mode.play,   detect_mode.init):   ("play_end",  None),
            (detect_mode.result, detect_mode.select): ("result_end","select_start"),
            (detect_mode.result, detect_mode.init):   ("result_end", None),
            (detect_mode.init,   detect_mode.select): (None, "select_start"),
        }
        triggers = trigger_map.get((old, new), (None, None))
        for t in triggers:
            if t:
                self._execute_obs_triggers(t)

        # detect状態に入った時刻を記録
        if new == detect_mode.detect:
            self.detect_enter_time = time.time()
            self.detect_read_done = False
            self.current_title = None
            self.current_diff = None
            logger.info(f"detect切り出し短期待機開始: delay={DETECT_CAPTURE_DELAY:.3f}s")

        # result状態に入った時刻を記録
        if new == detect_mode.result:
            self.result_timestamp = int(datetime.datetime.now().timestamp())
            self.result_pre = None

    # ── 各モードの処理 ────────────────────────────────────────────────────────

    def _process_select(self):
        """選曲画面の処理: OBSテキスト更新 & スコアビューワ編集パネル更新。
        DB への登録はスコアビューワの「自動登録」モード有効時のみ行う。
        """
        data = self.screen_reader.read_from_select()
        if not data:
            return

        title   = data.get('title')
        diff    = data.get('difficulty')
        lamp    = data.get('lamp')
        score   = data.get('score')
        exscore = data.get('exscore')

        if not title or diff is None or lamp is None or score is None:
            return

        # OBSテキストに曲情報を書く
        info = self.song_database.get_song_info(title)
        level = info.get_level(diff) if info else None
        lv_str = f"Lv.{level}" if level else ""
        self._write_obs_text(f"{title}\n{diff} {lv_str}")

        self.current_title = title
        self.current_diff  = diff

        # v1の gen_history_cursong 相当: 選曲画面で認識した曲の履歴/ライバル表示を更新
        cursong_key = (title, diff)
        if cursong_key != self._last_select_cursong_key:
            self.result_database.broadcast_cursong_data(title, diff)
            self._last_select_cursong_key = cursong_key

        # スコアビューワが開いていれば編集パネルを更新（自動登録も内部で判断）
        if self.score_viewer is not None and self.score_viewer.isVisible():
            self.score_viewer.update_select_data(title, diff, score, exscore, lamp)

    def _process_detect(self):
        """楽曲情報画面の処理: detect判定後、短く待って曲情報を読み取る"""
        import time
        if self.detect_read_done:
            return
        elapsed = time.time() - self.detect_enter_time

        if elapsed < DETECT_CAPTURE_DELAY:
            return

        logger.info(f"detect読み取り開始: elapsed={elapsed:.3f}s, delay={DETECT_CAPTURE_DELAY:.3f}s")
        image_data = self.screen_reader.read_detect_images()
        if image_data:
            logger.info(f"detect切り出し成功: keys={list(image_data.keys())}")
            self._save_nowplaying_images(image_data)
        else:
            logger.warning("detect切り出し失敗: read_detect_images returned None")

        data = self.screen_reader.read_from_detect()
        if not data:
            logger.warning("detect認識失敗: read_from_detect returned None")
            if image_data:
                self.detect_read_done = True
                self._broadcast_nowplaying(image_data, '', '', None, '')
            return

        title = data.get('title')
        diff  = data.get('difficulty')
        logger.info(f"detect認識結果: title={title!r}, difficulty={diff}")
        if not title or diff is None:
            logger.warning(f"detect認識不足: title={title!r}, difficulty={diff}")
            if image_data:
                self.detect_read_done = True
                self._broadcast_nowplaying(data, title or '', diff if diff is not None else '', None, '')
            return

        self.current_title = title
        self.current_diff  = diff
        self.detect_read_done = True

        # OBSテキストに曲情報を書く
        info = self.song_database.get_song_info(title)
        level = info.get_level(diff) if info else None
        lv_str = f"Lv.{level}" if level else ""
        self._write_obs_text(f"{title}\n{diff} {lv_str}")
        self._broadcast_nowplaying(data, title, diff, info, level)

        logger.info(f"detect: {get_title_with_chart(title, diff)} {lv_str}")
        self.statusBar().showMessage(f"detect: {get_title_with_chart(title, diff)} {lv_str}", 5000)

    def _image_data_url(self, image) -> str:
        """PIL ImageをHTMLでそのまま表示できるdata URLに変換する。"""
        if image is None:
            return ''
        try:
            buf = io.BytesIO()
            image.save(buf, format='PNG')
            encoded = base64.b64encode(buf.getvalue()).decode('ascii')
            return f'data:image/png;base64,{encoded}'
        except Exception:
            logger.error(f"画像エンコード失敗:\n{traceback.format_exc()}")
            return ''

    def _save_nowplaying_images(self, data: dict):
        """v1互換: 曲決定画面の切り出し画像をout/select_*.pngへ保存する。"""
        out_dir = Path('out')
        out_dir.mkdir(exist_ok=True)
        targets = {
            'jacket_img': 'select_jacket.png',
            'whole_img': 'select_whole.png',
            'title_img': 'select_title.png',
            'lv_img': 'select_level.png',
            'diff_img': 'select_difficulty.png',
            'bpm_img': 'select_bpm.png',
            'ef_img': 'select_effector.png',
            'illust_img': 'select_illustrator.png',
        }
        try:
            for key, filename in targets.items():
                image = data.get(key)
                if image is not None:
                    path = out_dir / filename
                    image.save(path)
                    logger.info(f"nowplaying画像保存: {path} size={getattr(image, 'size', None)}")
                else:
                    logger.warning(f"nowplaying画像なし: key={key}, file={filename}")
        except Exception:
            logger.error(f"nowplaying画像保存失敗:\n{traceback.format_exc()}")

    def _broadcast_nowplaying(self, data: dict, title: str, diff, info, level):
        """曲決定画面の表示用データをWebSocketへ配信する。"""
        payload = {
            'title': title,
            'difficulty': str(diff),
            'level': level or '',
            'artist': info.artist if info else '',
            'bpm': info.bpm if info else '',
            'images': {
                'jacket': self._image_data_url(data.get('jacket_img')),
                'title': self._image_data_url(data.get('title_img')),
                'level': self._image_data_url(data.get('lv_img')),
                'bpm': self._image_data_url(data.get('bpm_img')),
                'effector': self._image_data_url(data.get('ef_img')),
                'illustrator': self._image_data_url(data.get('illust_img')),
            },
        }
        self.result_database.broadcast_nowplaying_data(payload)

    def _process_result(self):
        """リザルト画面の処理: スコアを DB に登録して画像保存"""
        data = self.screen_reader.read_from_result()
        if not data:
            return

        score      = data.get('score')
        lamp       = data.get('lamp')
        exscore    = data.get('exscore')
        bestscore  = data.get('bestscore')
        bestex     = data.get('bestexscore')

        if score is None or lamp is None:
            return

        title = data.get('title') or self.current_title
        diff  = data.get('difficulty') or self.current_diff
        if not title or diff is None:
            return

        self.current_title = title
        self.current_diff  = diff

        info  = self.song_database.get_song_info(title)
        level = info.get_level(diff) if info else None

        result = OneResult(
            title=title,
            difficulty=diff,
            lamp=lamp,
            score=score,
            exscore=exscore,
            level=level,
            timestamp=self.result_timestamp,
            detect_mode=detect_mode.result,
            bestscore=bestscore,
            bestexscore=bestex,
        )

        # 同一内容を2回連続で読み取ったら確定
        if result != self.result_pre:
            self.result_pre = result
            return

        pre_score, pre_exscore, pre_lamp = self.result_database.get_best(
            title=title,
            diff=diff,
        )
        is_result_updated = self._is_result_updated(
            result,
            pre_score,
            pre_exscore,
            pre_lamp,
        )
        should_include_summary = self._should_include_summary_result(is_result_updated)

        if self.result_database.add(result):
            # ジャケット画像を保存
            self.result_database.save_jacket_image(result.chart_id, data.get('jacket_img'))
            self.result_database.save()
            self.play_count += 1
            self.last_saved_song = get_title_with_chart(title, diff)
            if self.score_viewer is not None and self.score_viewer.isVisible():
                self.score_viewer.refresh_data()

            # WebSocket配信
            self.result_database.broadcast_today_results_data(self.start_time_with_offset)
            self.result_database.broadcast_vf_data()
            self.result_database.broadcast_cursong_data(title, diff)
            self.result_database.broadcast_stats_data()

            # 画像保存が無効な場合のみテキスト版summaryを使う。
            # 有効時は下の切り出し版summaryが同じ出力先を更新する。
            if not self.config.autosave_image:
                if should_include_summary:
                    self._text_summary_results.append(result)
                    self._text_summary_results = self._text_summary_results[-30:]
                summary_results = (
                    self._text_summary_results
                    if getattr(self.config, 'summary_updated_results_only', False)
                    else self.result_database.get_today_results(self.start_time_with_offset)
                )
                generate_summary(summary_results)

            # 画像保存 + スクリーンショット版サマリー生成
            if self.config.autosave_image:
                screen = self._current_result_screen()
                if screen is not None and should_include_summary:
                    summary_item = capture_summary_item_from_screen(
                        screen,
                        result.timestamp,
                    )
                    if summary_item is not None:
                        self._result_summary_items.append(summary_item)
                        self._result_summary_items = self._result_summary_items[-30:]
                        generate_summary_from_items(self._result_summary_items)

                if self._should_save_result_image(is_result_updated):
                    self.save_image(
                        score=score,
                        exscore=exscore,
                        lamp=lamp,
                        screen=screen,
                    )
                else:
                    logger.info(f"画像保存スキップ(更新なし): {result}")

            logger.info(f"リザルト登録: {result}")
            self.statusBar().showMessage(f"リザルト登録: {get_title_with_chart(title, diff)}", 10000)

    # ── 画像保存 ──────────────────────────────────────────────────────────────

    def _current_result_screen(self):
        """回転補正済みの現在画面を返す。"""
        return self.screen_reader.corrected_screen or self.obs_manager.screen

    @staticmethod
    def _is_result_updated(result, pre_score, pre_exscore, pre_lamp) -> bool:
        """スコア・EXスコア・ランプのいずれかが自己ベスト更新しているか。"""
        if pre_score is None:
            return True
        if result.score is not None and result.score > pre_score:
            return True
        if pre_exscore is None and result.exscore is not None:
            return True
        if (
            pre_exscore is not None
            and result.exscore is not None
            and result.exscore > pre_exscore
        ):
            return True
        if pre_lamp is not None and result.lamp is not None and result.lamp > pre_lamp:
            return True
        return False

    def _should_save_result_image(self, is_result_updated: bool) -> bool:
        """画像保存設定に基づき、今回のリザルト画像を保存するかを返す。"""
        if not getattr(self.config, 'autosave_updated_score_only', False):
            return True
        return is_result_updated

    def _should_include_summary_result(self, is_result_updated: bool) -> bool:
        """summary_*.png に今回のリザルトを含めるかを返す。"""
        if not getattr(self.config, 'summary_updated_results_only', False):
            return True
        return is_result_updated

    def _should_include_saved_summary_image(self, data: dict | None, image_mtime: int) -> bool:
        """保存済み画像を起動時summary復元に含めるかを返す。"""
        if not getattr(self.config, 'summary_updated_results_only', False):
            return True
        if not data:
            return True

        title = data.get('title')
        diff = data.get('difficulty')
        score = data.get('score')
        lamp = data.get('lamp')
        if not title or diff is None or score is None or lamp is None:
            return True

        candidates = [
            r for r in self.result_database.search(title=title, diff=diff)
            if r.detect_mode == detect_mode.result
            and r.score == score
            and r.lamp == lamp
            and abs(r.timestamp - image_mtime) <= 600
        ]
        if data.get('exscore') is not None:
            candidates = [
                r for r in candidates
                if r.exscore is None or r.exscore == data.get('exscore')
            ]

        if not candidates:
            logger.debug(f"起動時summary復元: 対応するDBリザルトなし title={title} diff={diff}")
            return True

        matched = min(candidates, key=lambda r: abs(r.timestamp - image_mtime))
        return self._is_result_updated(
            matched,
            matched.bestscore,
            matched.bestexscore,
            None,
        )

    def save_image(self, score=None, exscore=None, lamp=None, screen=None):
        """現在の画面キャプチャを保存する"""
        try:
            date_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            if self.current_title and self.current_diff:
                parts = [
                    "sdvx",
                    self.current_title,
                    str(self.current_diff),
                ]
                if score is not None:
                    parts.append(str(score//10000))
                if exscore is not None:
                    parts.append(f"ex{exscore}")
                if lamp is not None:
                    parts.append(str(lamp))
                parts.append(date_str)
                filename = "_".join(parts) + ".png"
            else:
                filename = f"sdvx_{date_str}.png"

            filename = escape_for_filename(filename)
            os.makedirs(self.config.image_save_path, exist_ok=True)
            full_path = Path(self.config.image_save_path) / filename

            # 回転補正済み画像を優先、なければ生キャプチャ
            screen = screen or self._current_result_screen()
            if screen is not None:
                screen.save(str(full_path))
                logger.info(f"画像保存: {full_path}")
                self.statusBar().showMessage(f"保存: {filename}", 5000)
                return True
        except Exception:
            logger.error(f"画像保存エラー:\n{traceback.format_exc()}")
            self.statusBar().showMessage("画像保存エラー", 3000)
        return False

    # ── 終了処理 ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        """アプリ終了時の処理"""
        self._execute_obs_triggers('app_end')
        self.remove_global_hotkeys()
        self.obs_manager.disconnect()
        self.rival_manager.shutdown()
        self.result_database.shutdown()
        self.save_window_geometry()

        # CSV出力
        csv_path = self.config.csv_export_path or None
        self.result_database.write_best_csv(csv_path=csv_path)

        # Portal: 今日のプレーログをバックグラウンドで送信（最大15秒待機）
        # 起動直後などでプレー回数が 0 の場合はスキップして高速終了
        if self.config.portal_token and (self.play_count > 0 or self.result_database.get_today_results(self.start_time_with_offset)):
            import threading
            total_vf = self.result_database.get_total_vf()
            def _upload():
                try:
                    self.portal_manager.upload_scores(
                        self.result_database,
                        start_time=self.start_time_with_offset,
                        player_name=self.config.player_name or 'NONAME',
                        volforce=f'{total_vf / 1000:.3f}',
                    )
                except Exception:
                    logger.error(f'Portal送信エラー:\n{traceback.format_exc()}')
            t = threading.Thread(target=_upload, daemon=False)
            t.start()
            t.join(timeout=15)

        if self.score_viewer is not None:
            self.score_viewer.close()

        self.main_timer.stop()
        self.display_timer.stop()

        logger.info("アプリケーション終了")
        event.accept()


def main():
    """メイン関数"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    icon_path = Path('src/icon.ico')
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
