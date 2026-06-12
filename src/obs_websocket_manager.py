import time
import threading
import traceback
import functools
from typing import Callable, Optional, List, Dict, Any
from PySide6.QtCore import QObject, Signal

import logging
from src.config import Config
from src.direct_window_capture import DirectWindowCapture
from src.logger import get_logger
from src.funcs import load_ui_text
logger = get_logger(__name__)

# obsws_pythonライブラリの接続エラートレースバックを抑制
logging.getLogger('obsws_python').setLevel(logging.CRITICAL)


def _require_connection(func):
    """OBS接続が必要なメソッド用デコレータ"""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.is_connected or not self.client:
            logger.warning(f"OBS not connected (calling {func.__name__})")
            return None
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            # logger.error(f"Failed to {func.__name__}: {e}")
            return None
    return wrapper

try:
    from obsws_python import ReqClient
    OBSWS_AVAILABLE = True
except ImportError:
    ReqClient = None
    OBSWS_AVAILABLE = False
    logger.warning("obsws_python not installed. Install with: pip install obsws-python")

class OBSWebSocketManager(QObject):
    """
    OBS WebSocket接続管理クラス（改善版）
    
    機能:
    - 自動再接続
    - 切断検出
    - 接続状態変化通知(Qtシグナル)
    - 監視対象ソース設定状態チェック
    """
    
    # Qtシグナル定義
    connection_changed = Signal(bool, str)  # (is_connected, message)
    
    def __init__(self):
        super().__init__()
        self.ui = None
        
        self.config: Optional[Config] = None
        self.client: Optional[ReqClient] = None
        self.is_connected = False
        
        # 再接続設定
        self.auto_reconnect = True  # 自動再接続を有効化
        self.reconnect_interval = 5.0  # 再接続試行間隔（秒）
        self.max_reconnect_attempts = 0  # 0=無限に再試行
        
        # 接続監視スレッド
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_running = False
        self.stop_event = threading.Event()
        # screenshot() 失敗の連続回数（切断検出用）
        self._screenshot_failures = 0
        
        # 画面サイズ設定
        self.picw = 1920
        self.pich = 1080
        self.screen = None
        self.direct_capture: Optional[DirectWindowCapture] = None

        # 起動時シーンコレクション切り替えフラグ（disconnect後にリセット）
        self._scene_collection_applied = False
    
    def set_config(self, config: Config):
        """設定をセット"""
        self.config = config
        self.ui = load_ui_text(config)
        if self.direct_capture is None:
            self.direct_capture = DirectWindowCapture(config)
        else:
            self.direct_capture.set_config(config)
        logger.info(f"OBS WebSocket config set: {config.websocket_host}:{config.websocket_port}")

    def is_direct_capture(self) -> bool:
        return bool(self.config and getattr(self.config, 'capture_method', 'direct_window') == 'direct_window')
    
    def connect(self):
        """OBSに接続"""
        if self.is_direct_capture():
            self.stop_monitor()
            if self.client:
                try:
                    self.client.disconnect()
                except:
                    pass
                self.client = None
            self.is_connected = False
            self._emit_status("直接取得モード", True)
            return True

        if not OBSWS_AVAILABLE:
            self._emit_status("obsws_python がインストールされていません", False)
            return False
        
        if not self.config:
            self._emit_status(self.ui.obs.not_configured, False)
            return False
        
        try:
            # 既存の接続を切断
            if self.client:
                try:
                    self.client.disconnect()
                except:
                    pass
                self.client = None
            
            # 新しい接続を確立
            logger.info(f"Connecting to OBS WebSocket: {self.config.websocket_host}:{self.config.websocket_port}")
            
            self.client = ReqClient(
                host=self.config.websocket_host,
                port=self.config.websocket_port,
                password=self.config.websocket_password,
                timeout=5
            )
            
            # 接続テスト
            self.client.get_version()
            
            self.is_connected = True
            self._emit_status(f"{self.ui.obs.status_connected} ({self.config.websocket_host}:{self.config.websocket_port})", True)

            # 起動時シーンコレクション切り替え
            self._apply_scene_collection()

            # 接続監視スレッドを開始
            self.start_monitor()

            return True
            
        except Exception as e:
            self.is_connected = False
            if self.client:
                self.client.disconnect()
                self.client = None
            error_msg = f"{self.ui.obs.status_connection_failed}: {str(e)}"
            self._emit_status(error_msg, False)
            logger.error(f"OBS WebSocket connection failed: {e}")
            
            # 自動再接続が有効な場合は監視スレッドを開始
            if self.auto_reconnect:
                self.start_monitor()
            
            return False
    
    def disconnect(self):
        """OBSから切断"""
        if self.is_direct_capture():
            self.stop_monitor()
            self.is_connected = False
            if self.ui:
                self._emit_status(self.ui.obs.status_disconnected, False)
            return

        logger.info("Disconnecting from OBS WebSocket")
        
        # 監視スレッドを停止
        self.stop_monitor()
        
        # 接続を切断
        if self.client:
            try:
                self.client.disconnect()
            except:
                pass
            self.client = None

        self.is_connected = False
        self._scene_collection_applied = False
        self._emit_status(self.ui.obs.status_disconnected, False)
    
    def start_monitor(self):
        """接続監視スレッドを開始"""
        if self.monitor_running:
            return
        
        self.monitor_running = True
        self.stop_event.clear()
        
        self.monitor_thread = threading.Thread(
            target=self._monitor_connection,
            daemon=True,
            name="OBSMonitorThread"
        )
        self.monitor_thread.start()
        
        logger.info("Connection monitor thread started")
    
    def stop_monitor(self):
        """接続監視スレッドを停止"""
        if not self.monitor_running:
            return
        
        self.monitor_running = False
        self.stop_event.set()
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
            self.monitor_thread = None
        
        logger.info("Connection monitor thread stopped")
    
    def _monitor_connection(self):
        """
        接続監視ループ（バックグラウンドスレッド）
        
        機能:
        1. 定期的に接続状態をチェック
        2. 切断を検出したら自動再接続を試みる
        """
        consecutive_failures = 0
        check_interval = 2.0  # 接続確認間隔（秒）
        
        while self.monitor_running and not self.stop_event.is_set():
            try:
                # 設定チェック
                if not self.config:
                    time.sleep(check_interval)
                    continue
                
                # 接続状態チェック
                if self.is_connected and self.client:
                    # 接続中は何もしない。
                    # 切断検出はメインスレッドの screenshot() 失敗が担う
                    # （モニタースレッドと self.client を同時使用する race condition を避けるため）
                    consecutive_failures = 0

                else:
                    # 未接続の場合、自動再接続を試みる
                    if self.auto_reconnect:
                        # 最大再接続試行回数チェック
                        if self.max_reconnect_attempts > 0 and consecutive_failures >= self.max_reconnect_attempts:
                            logger.error(f"Max reconnection attempts reached: {self.max_reconnect_attempts}")
                            self._emit_status(f"{self.ui.obs.status_reconnect_failed}（{self.max_reconnect_attempts}回試行）", False)
                            time.sleep(check_interval)
                            continue
                        
                        # 再接続試行
                        # logger.info(f"Attempting to reconnect to OBS... (attempt {consecutive_failures + 1})")
                        self._emit_status(f"{self.ui.obs.status_reconnecting} ({consecutive_failures + 1}回目)", False)
                        
                        try:
                            self.client = ReqClient(
                                host=self.config.websocket_host,
                                port=self.config.websocket_port,
                                password=self.config.websocket_password,
                                timeout=5
                            )
                            
                            # 接続テスト
                            self.client.get_version()
                            
                            # 成功
                            self.is_connected = True
                            self._emit_status(f"{self.ui.obs.status_reconnected} ({self.config.websocket_host}:{self.config.websocket_port})", True)
                            logger.info("OBS reconnection successful")
                            consecutive_failures = 0

                            # 起動時シーンコレクション切り替え（未適用の場合のみ）
                            self._apply_scene_collection()
                            
                        except Exception as e:
                            # 再接続失敗
                            self.is_connected = False
                            self.client = None
                            consecutive_failures += 1
                            # logger.debug(f"Reconnection failed: {e}")
                            
                            # 次の再接続まで待機
                            time.sleep(self.reconnect_interval)
                            continue
                
            except Exception as e:
                logger.error(f"Monitor thread error: {e}\n{traceback.format_exc()}")
            
            # 次のチェックまで待機
            time.sleep(check_interval)
        
        logger.info("Monitor thread terminated")
    
    def _emit_status(self, message: str, is_connected: bool):
        """接続状態変化を通知"""
        self.is_connected = is_connected
        # logger.info(f"OBS status: {message} (connected={is_connected})")
        try:
            self.connection_changed.emit(is_connected, message)
        except: # アプリ終了時にエラーを吐かないようにする
            pass
    
    def is_monitor_source_configured(self) -> bool:
        """監視対象ソースが設定されているかチェック"""
        if not self.config:
            return False
        if self.is_direct_capture():
            return True
        return bool(self.config.monitor_source_name and self.config.monitor_source_name.strip())

    def is_capture_ready(self) -> bool:
        """メインループがキャプチャを試行してよい状態か。"""
        if not self.config:
            return False
        if self.is_direct_capture():
            return True
        return self.is_connected and self.is_monitor_source_configured()
    
    def get_status(self) -> tuple[str, bool]:
        """
        現在のステータスを取得
        
        Returns:
            tuple[str, bool]: (ステータスメッセージ, 正常状態かどうか)
                正常状態 = OBS接続済み かつ 監視対象ソース設定済み
        """
        if not self.config:
            return self.ui.obs.not_configured, False
        elif self.is_direct_capture():
            error = self.direct_capture.last_error if self.direct_capture else ""
            if error:
                return f"直接取得: {error}", False
            return f"直接取得: {self.config.direct_capture_title}", True
        elif not OBSWS_AVAILABLE:
            return "obsws_python がインストールされていません", False
        elif not self.is_connected:
            return self.ui.obs.not_connected, False
        elif not self.is_monitor_source_configured():
            return self.ui.obs.no_source, False
        else:
            return f"{self.ui.obs.connected} ({self.config.websocket_host}:{self.config.websocket_port})", True
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """
        詳細なステータス情報を取得
        
        Returns:
            dict: {
                'is_connected': bool,  # OBS接続状態
                'is_source_configured': bool,  # 監視対象ソース設定状態
                'is_ready': bool,  # 両方が正常
                'message': str  # ステータスメッセージ
            }
        """
        message, is_ready = self.get_status()
        return {
            'is_connected': self.is_connected,
            'is_source_configured': self.is_monitor_source_configured(),
            'is_ready': is_ready,
            'message': message
        }
    
    @_require_connection
    def send_command(self, command_name: str, **kwargs):
        """
        OBSにコマンドを送信（汎用メソッド）

        Args:
            command_name: 実行するコマンド名
            **kwargs: コマンドのパラメータ

        Returns:
            コマンドの実行結果、またはエラー時はNone
        """
        method = getattr(self.client, command_name)
        result = method(**kwargs)
        logger.debug(f"OBS command executed: {command_name}")
        return result
    
    @_require_connection
    def get_scene_list(self) -> List[Dict]:
        """シーン一覧を取得"""
        res = self.client.get_scene_list()
        return res.scenes

    @_require_connection
    def get_scene_collection_list(self) -> List[str]:
        """シーンコレクション一覧を取得"""
        res = self.client.get_scene_collection_list()
        return res.scene_collections

    @_require_connection
    def set_scene_collection(self, name: str) -> bool:
        """シーンコレクションを切り替え"""
        self.client.set_current_scene_collection(name)
        logger.info(f"シーンコレクションを切り替えました: {name}")
        return True

    def _apply_scene_collection(self):
        """起動時に設定されたシーンコレクションへ切り替え（未適用の場合のみ）"""
        if self._scene_collection_applied:
            return
        if not self.config or not self.config.obs_scene_collection:
            return
        try:
            self.set_scene_collection(self.config.obs_scene_collection)
            self._scene_collection_applied = True
            logger.info(f"起動時シーンコレクション適用: {self.config.obs_scene_collection}")
        except Exception as e:
            logger.error(f"起動時シーンコレクション切り替えエラー: {e}")

    @_require_connection
    def get_source_list(self, scene: str) -> List[str]:
        """指定シーンのソース一覧を取得"""
        ret = []
        allitem = self.client.get_scene_item_list(scene).scene_items
        for x in allitem:
            if x['isGroup']:
                grp = self.client.get_group_scene_item_list(x['sourceName']).scene_items
                for y in grp:
                    ret.append(y['sourceName'])
            ret.append(x['sourceName'])
        ret.reverse()
        return ret

    @_require_connection
    def change_scene(self, name: str):
        """シーンを変更"""
        self.client.set_current_program_scene(name)
        return True

    @_require_connection
    def change_text(self, source: str, text: str):
        """テキストソースを変更"""
        self.client.set_input_settings(source, {'text': text}, True)
        return True
    
    def screenshot(self):
        """設定された方式のキャプチャをself.screenに格納 (PIL Image)"""
        if self.is_direct_capture():
            if self.direct_capture is None:
                self.direct_capture = DirectWindowCapture(self.config)
            self.screen = self.direct_capture.read_frame()
            return

        """OBSソースのキャプチャをself.screenに格納 (PIL Image)"""
        from PIL import Image
        import os
        os.makedirs('out', exist_ok=True)
        dst = os.path.abspath('out/capture.png')
        # configから解像度を取得（0はネイティブサイズ）
        self.picw = getattr(self.config, 'screenshot_width', 0) or None
        self.pich = getattr(self.config, 'screenshot_height', 0) or None
        try:
            if self.save_screenshot_dst(self.config.monitor_source_name, dst):
                self.screen = Image.open(dst).convert('RGB')
                self._screenshot_failures = 0  # 成功: カウンタリセット
            else:
                self._on_screenshot_failed()
                self.screen = None
        except Exception:
            self._on_screenshot_failed()
            self.screen = None

    def _on_screenshot_failed(self):
        """screenshot() 失敗を記録し、連続3回で切断と判定してモニタースレッドに通知する。
        メインスレッドからのみ呼ばれる前提（モニタースレッドとの self.client 競合を排除）。
        """
        if not self.is_connected:
            return
        self._screenshot_failures += 1
        if self._screenshot_failures >= 3:
            logger.warning(f"OBS connection lost (screenshot failed {self._screenshot_failures} times)")
            self._screenshot_failures = 0
            self.is_connected = False
            self.client = None
            if self.ui:
                self._emit_status(self.ui.obs.status_lost, False)
    
    @_require_connection
    def save_screenshot_dst(self, source: str, dst: str, disable_wh:bool=False) -> bool:
        """スクリーンショットを保存"""
        if disable_wh:
            picw = None
            pich = None
        else:
            picw = self.picw
            pich = self.pich
        self.client.save_source_screenshot(
            source, 'png', dst,
            picw, pich, 100
        )
        return True

    @_require_connection
    def enable_source(self, scenename: str, sourceid: int):
        """ソースを有効化"""
        self.client.set_scene_item_enabled(scenename, sourceid, enabled=True)
        return True

    @_require_connection
    def disable_source(self, scenename: str, sourceid: int):
        """ソースを無効化"""
        self.client.set_scene_item_enabled(scenename, sourceid, enabled=False)
        return True

    @_require_connection
    def search_itemid(self, scene: str, target: str) -> tuple[str, Optional[int]]:
        """ソースのIDを検索"""
        ret = scene, None
        allitem = self.client.get_scene_item_list(scene).scene_items
        for x in allitem:
            if x['sourceName'] == target:
                ret = scene, x['sceneItemId']
            if x['isGroup']:
                grp = self.client.get_group_scene_item_list(x['sourceName']).scene_items
                for y in grp:
                    if y['sourceName'] == target:
                        ret = x['sourceName'], y['sceneItemId']
        return ret
    
    def __del__(self):
        """デストラクタ"""
        self.disconnect()

# メイン関数（テスト用）
if __name__ == "__main__":
    # テスト用のダミー設定
    class DummyConfig:
        def __init__(self):
            self.websocket_host = "localhost"
            self.websocket_port = 4455
            self.websocket_password = ""
            self.enable_register_conditions = True
    
    # テスト用のダミーOBSマネージャー
    class DummyOBSManager:
        def __init__(self):
            self.is_connected = False
        
        def get_scene_list(self):
            return None
        
        def send_command(self, command, **kwargs):
            return None
    
    root = tk.Tk()
    root.withdraw()  # メインウィンドウを非表示
    
    config = DummyConfig()
    obs_manager = DummyOBSManager()
    control_window = OBSControlWindow(root, obs_manager, config)
    
    root.mainloop()
