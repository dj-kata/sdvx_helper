"""
SDVX Helper - メインプログラム
OBS連携による自動リザルト保存アプリケーション
"""

import sys
import datetime
import traceback
import os
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer, Qt

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
from src.define import DETECT_WAIT
from src.logger import get_logger

from src.config_dialog import ConfigDialog
from src.score_viewer import ScoreViewer
from src.obs_dialog import OBSControlDialog
from src.main_window import MainWindowUI
from src.rival_data import RivalManager
from src.portal_manager import PortalManager
from src.summary_generator import generate_summary, generate_summary_from_screenshots

logger = get_logger('sdvx_helper')

try:
    with open('version.txt', 'r') as f:
        SWVER = f.readline().strip().lstrip('v')
except Exception:
    SWVER = "0.0.0"


class MainWindow(MainWindowUI):
    """メインウィンドウクラス - 制御ロジックを担当"""

    def __init__(self):
        self.config = Config()
        super().__init__(self.config)

        update_musiclist_from_remote()
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

        # 起動時プレイ数を集計
        self._count_today_plays()

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

    # ── OBS関連 ──────────────────────────────────────────────────────────────

    def _check_obs_configuration(self):
        """OBS設定の問題があればダイアログを表示"""
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
        if source and self.obs_manager.is_connected:
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
        if not self.obs_manager.is_connected:
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
            if not (self.obs_manager.is_connected
                    and self.config.monitor_source_name):
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
        """楽曲情報画面の処理: DETECT_WAIT秒後に曲情報を読み取る"""
        import time
        if self.detect_read_done:
            return
        if time.time() - self.detect_enter_time < DETECT_WAIT:
            return

        data = self.screen_reader.read_from_detect()
        if not data:
            return

        title = data.get('title')
        diff  = data.get('difficulty')
        if not title or diff is None:
            return

        self.current_title = title
        self.current_diff  = diff
        self.detect_read_done = True

        # OBSテキストに曲情報を書く
        info = self.song_database.get_song_info(title)
        level = info.get_level(diff) if info else None
        lv_str = f"Lv.{level}" if level else ""
        self._write_obs_text(f"{title}\n{diff} {lv_str}")

        logger.info(f"detect: {get_title_with_chart(title, diff)} {lv_str}")
        self.statusBar().showMessage(f"detect: {get_title_with_chart(title, diff)} {lv_str}", 5000)

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

            # テキスト版サマリー画像生成（バックグラウンドで実行）
            generate_summary(
                self.result_database.get_today_results(self.start_time_with_offset)
            )

            # 画像保存 + スクリーンショット版サマリー生成
            if self.config.autosave_image:
                self.save_image(score=score, exscore=exscore, lamp=lamp)
                generate_summary_from_screenshots(
                    self.config.image_save_path,
                    self.start_time_with_offset,
                )

            logger.info(f"リザルト登録: {result}")
            self.statusBar().showMessage(f"リザルト登録: {get_title_with_chart(title, diff)}", 10000)

    # ── 画像保存 ──────────────────────────────────────────────────────────────

    def save_image(self, score=None, exscore=None, lamp=None):
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
            screen = self.screen_reader.corrected_screen or self.obs_manager.screen
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
