"""SDVX向け設定クラス。config.json と相互変換する。"""
import json
import traceback
from src.logger import get_logger

logger = get_logger(__name__)

_CONFIG_FILE = 'config.json'


class Config:
    """全設定を保持するクラス。"""

    def __init__(self, config_file: str = _CONFIG_FILE):
        self._config_file = config_file

        # ─── OBS WebSocket ────────────────────────────────────────────────
        self.websocket_host:     str  = 'localhost'
        self.websocket_port:     int  = 4444
        self.websocket_password: str  = ''
        self.monitor_source_name: str = ''
        """スクリーンショットを取得する OBS ソース名"""
        self.capture_method: str = 'obs_websocket'
        """'obs_websocket' = OBS WebSocket / 'direct_window' = ゲームウィンドウを直接取得"""
        self.direct_capture_exe: str = 'sv6c.exe'
        """直接取得対象のプロセス名"""
        self.direct_capture_title: str = 'SOUND VOLTEX EXCEED GEAR'
        """直接取得対象のウィンドウタイトル"""
        self.obs_scene_collection: str = ''
        """起動時に切り替えるシーンコレクション（空=切り替えなし）"""
        self.obs_control_settings: list = []
        """OBS 制御トリガー設定リスト"""

        # ─── 表示 ─────────────────────────────────────────────────────────
        self.keep_on_top: bool = False
        self.language:    str  = 'ja'
        self.main_window_geometry: str | None = None

        # ─── ログ読み込み範囲 ──────────────────────────────────────────────
        self.autoload_offset: int = 4
        """起動時刻からさかのぼる時間数。この範囲を「今日」として扱う。"""

        # ─── 画像保存 ─────────────────────────────────────────────────────
        self.image_save_path: str  = 'results'
        self.autosave_image:  bool = True
        """リザルト画面を自動保存するか"""
        self.autosave_updated_score_only: bool = False
        """True の場合、自己ベスト更新があったリザルト画像のみ保存する"""
        self.summary_updated_results_only: bool = False
        """True の場合、summary_*.png には自己ベスト更新があったリザルトのみ含める"""

        # ─── CSV 出力 ─────────────────────────────────────────────────────
        self.csv_export_path: str = ''
        """空文字なら out/ に書き出す"""

        # ─── WebSocket データ配信 ─────────────────────────────────────────
        self.websocket_data_port: int = 8767

        # ─── OBS テキストソース ───────────────────────────────────────────
        self.obs_text_source_name: str = ''
        """楽曲情報を書き込む OBS テキストソース名（空=書き込まない）"""

        # ─── 画面向き ─────────────────────────────────────────────────────
        self.screen_orientation_override: str | None = None
        """'top_up' / 'top_right' / 'top_left' / None(自動検出)"""

        # ─── スクリーンショットサイズ ─────────────────────────────────────
        self.screenshot_width:  int = 0
        """0 = OBS ソースのネイティブサイズを使用"""
        self.screenshot_height: int = 0

        # ─── Portal連携 ──────────────────────────────────────────────────────
        self.portal_token: str = ''
        """SDVX Helper Portal のアクセストークン"""
        self.player_name: str = ''
        """Portal に送信するプレイヤー名"""

        # ─── ライバル ─────────────────────────────────────────────────────
        self.rivals: list = []
        """ライバルリスト: [{"name": "名前", "url": "URL"}, ...]"""

        # ─── スコアビューワ ───────────────────────────────────────────────────
        self.score_viewer_geometry:    str | None = None
        self.score_viewer_diff_checks: list = []
        """チェック済み難易度の文字列リスト。空=全選択。"""
        self.score_viewer_lv_checks:   list = []
        """チェック済みレベルの整数リスト。空=全選択。"""
        self.score_viewer_sort_column: int = 9
        """スコアテーブルのソート列インデックス（9 = VF）"""
        self.score_viewer_sort_order:  int = 1
        """スコアテーブルのソート方向（0 = 昇順, 1 = 降順）"""

        self.load_config()

    # ─── 永続化 ───────────────────────────────────────────────────────────

    def load_config(self):
        """config.json から設定をロードする。"""
        try:
            with open(self._config_file, 'r', encoding='utf-8') as f:
                data: dict = json.load(f)
            for key, val in data.items():
                if hasattr(self, key):
                    setattr(self, key, val)
            logger.info(f"config.json ロード完了")
        except FileNotFoundError:
            logger.info("config.json が見つかりません。デフォルト設定を使用します。")
        except Exception:
            logger.error(f"config.json ロード失敗:\n{traceback.format_exc()}")

    def save_config(self):
        """設定を config.json に保存する。"""
        try:
            data = {k: v for k, v in self.__dict__.items()
                    if not k.startswith('_')}
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.error(f"config.json 保存失敗:\n{traceback.format_exc()}")
