"""
設定ダイアログ（SDVX版）
基本設定を行うためのダイアログウィンドウ
"""

import datetime
import json
import pickle
import traceback
import os

from PySide6.QtCore import Signal, QThread, QUrl, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLineEdit, QSpinBox, QCheckBox, QPushButton,
                               QGroupBox, QFileDialog, QTabWidget, QWidget,
                               QLabel, QDialogButtonBox, QRadioButton,
                               QButtonGroup, QMessageBox, QComboBox,
                               QProgressBar, QListWidget, QListWidgetItem)
from PySide6.QtGui import QIntValidator, QDesktopServices

from src.config import Config
from src.logger import get_logger
from src.funcs import load_ui_text, convert_difficulty, convert_lamp
from src.result import OneResult
from src.classes import detect_mode
from src.result_image import expand_result_info_area
from src.portal_uploaded_scores import (
    ManageUploadedScores,
    load_uploaded_scores_from_path,
)
logger = get_logger(__name__)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.ui_jp import UIText
    from src.result_database import ResultDatabase
    from src.rival_data import RivalManager
    from src.portal_manager import PortalManager


# ── v1 alllog.pkl インポート ──────────────────────────────────────────────────

class _AlllogProxy:
    """sdvxh_classes.OnePlayData の代替クラス（pickle 復元用）"""
    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state: dict):
        self.__dict__.update(state)
        if 'cur_exscore' not in self.__dict__:
            self.cur_exscore = 0
        if 'pre_exscore' not in self.__dict__:
            self.pre_exscore = 0


class _AlllogUnpickler(pickle.Unpickler):
    """sdvxh_classes をインポートせずに alllog.pkl を読むカスタム Unpickler"""
    def find_class(self, module, name):
        if name == 'OnePlayData':
            return _AlllogProxy
        try:
            return super().find_class(module, name)
        except Exception:
            # 依存ライブラリのクラスが見つからない場合は汎用プロキシで代替
            return _AlllogProxy


# v1 ランプ文字列 → convert_lamp() が解釈できる形式
_V1_LAMP = {
    'puc':   'PUC',
    'uc':    'UC',
    'hard':  'EXC-COMP',
    'exh':   'MAXXIVE',
    'clear': 'CLEAR',
}

# v1 難易度フルネーム・内部キー → 短縮形
_V1_DIFF = {
    'NOVICE':   'NOV',
    'ADVANCED': 'ADV',
    'EXHAUST':  'EXH',
    'MAXIMUM':  'MXM',
    'INFINITE': 'INF',
    'GRAVITY':  'GRV',
    'HEAVENLY': 'HVN',
    'VIVID':    'VVD',
    'EXCEED':   'XCD',
    'APPEND':   'MXM',  # v1 内部キー (MXM/INF/GRV/HVN/VVD/XCD を統合)
}


class AlllogImportWorker(QThread):
    """alllog.pkl をバックグラウンドでインポートするワーカー"""
    progress = Signal(int, int)   # (current, total)
    finished = Signal(int, int)   # (registered, total)
    error    = Signal(str)

    def __init__(self, pkl_path: str, result_database):
        super().__init__()
        self.pkl_path        = pkl_path
        self.result_database = result_database
        self._cancelled      = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            with open(self.pkl_path, 'rb') as f:
                data = _AlllogUnpickler(f).load()

            if not isinstance(data, (list, tuple)):
                self.error.emit("pkl のフォーマットが不正です (list/tuple が期待されます)")
                return

            total      = len(data)
            registered = 0

            for i, item in enumerate(data):
                if self._cancelled:
                    break
                
                # 100件ごと、または最初と最後のみ進捗を更新してUIへの負荷を下げる
                if i == 0 or (i + 1) % 100 == 0 or (i + 1) == total:
                    self.progress.emit(i + 1, total)

                try:
                    # 難易度変換（フルネーム・短縮形の両方に対応）
                    diff_raw = str(getattr(item, 'difficulty', '')).upper()
                    diff_raw = _V1_DIFF.get(diff_raw, diff_raw)
                    diff = convert_difficulty(diff_raw)
                    if diff is None:
                        continue

                    # ランプ変換
                    lamp_v1 = str(getattr(item, 'lamp', '')).lower()
                    lamp = convert_lamp(_V1_LAMP.get(lamp_v1, 'PLAYED'))

                    # スコア・EXスコア
                    score   = int(getattr(item, 'cur_score',   0) or 0)
                    exscore = int(getattr(item, 'cur_exscore', 0) or 0) or None

                    # 日時 → UNIX タイムスタンプ
                    date_str = str(getattr(item, 'date', ''))
                    ts = None
                    for fmt in ('%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M',
                                '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S',
                                '%Y%m%d_%H%M%S', '%Y%m%d_%H%M'):
                        try:
                            ts = int(datetime.datetime.strptime(date_str, fmt).timestamp())
                            break
                        except ValueError:
                            continue

                    title = str(getattr(item, 'title', ''))
                    title = self.result_database.song_database.convert_v1_title(title)

                    result = OneResult(
                        title       = title,
                        difficulty  = diff,
                        lamp        = lamp,
                        score       = score,
                        exscore     = exscore,
                        timestamp   = ts,
                        detect_mode = detect_mode.result,
                    )
                    if self.result_database.add(result, commit=False):
                        registered += 1
                except Exception:
                    # ログ出力を制限（大量に失敗するとここも負荷になるため）
                    if registered % 100 == 0:
                        logger.debug(f"alllog item skip: {traceback.format_exc()}")
                    continue

            if registered > 0:
                self.result_database.commit()

            self.finished.emit(registered, total)

        except Exception as e:
            self.error.emit(str(e))



class ImageImportWorker(QThread):
    """リザルト画像フォルダをスキャンしてインポートするワーカー"""
    progress = Signal(int, int)   # (current, total)
    finished = Signal(int, int)   # (registered, total)
    error    = Signal(str)

    def __init__(self, folder_path: str, result_database, screen_reader):
        super().__init__()
        self.folder_path     = folder_path
        self.result_database = result_database
        self.screen_reader   = screen_reader
        self._cancelled      = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from pathlib import Path
            from PIL import Image
            import os

            p = Path(self.folder_path)
            files = sorted(
                f
                for pattern in ("*.png", "*.jpg", "*.jpeg")
                for f in p.glob(pattern)
            )
            total = len(files)
            registered = 0

            for i, f in enumerate(files):
                if self._cancelled:
                    break
                
                self.progress.emit(i + 1, total)

                try:
                    with Image.open(f) as img:
                        self.screen_reader.update_screen(expand_result_info_area(img))
                        mode = self.screen_reader.detect_screen()
                        
                        if mode.is_result_screen():
                            data = self.screen_reader.read_from_result()
                            if not data:
                                continue

                            score   = data.get('score')
                            lamp    = data.get('lamp')
                            exscore = data.get('exscore')
                            title   = data.get('title')
                            diff    = data.get('difficulty')

                            if score is None or lamp is None:
                                continue

                            # ファイルの更新日時をタイムスタンプとして使用
                            ts = int(os.path.getmtime(f))

                            result = OneResult(
                                title=title or "UNKNOWN",
                                difficulty=diff,
                                lamp=lamp,
                                score=score,
                                exscore=exscore,
                                timestamp=ts,
                                detect_mode=data.get('detect_mode') or detect_mode.result,
                            )
                            if self.result_database.add(result, commit=False):
                                registered += 1
                except Exception as e:
                    logger.debug(f"Image import skip ({f.name}): {e}")
                    continue

            if registered > 0:
                self.result_database.commit()

            self.finished.emit(registered, total)

        except Exception as e:
            logger.error(f"ImageImportWorker error: {traceback.format_exc()}")
            self.error.emit(str(e))


class _PortalUploadAllWorker(QThread):
    """全プレーログをPortalにアップロードするワーカー"""
    result_ready = Signal(bool, str)  # (success, detail)

    def __init__(self, portal_manager, result_database,
                 player_name: str, volforce: str):
        super().__init__()
        self.portal_manager  = portal_manager
        self.result_database = result_database
        self.player_name     = player_name
        self.volforce        = volforce

    def run(self):
        try:
            # マスター未取得なら先に取得する
            if not self.portal_manager.master_db:
                ok = self.portal_manager.get_musiclist()
                if not ok:
                    self.result_ready.emit(False, 'musiclist fetch failed')
                    return

            res = self.portal_manager.upload_scores(
                self.result_database,
                upload_all=True,
                player_name=self.player_name,
                volforce=self.volforce,
            )
            if res is None:
                detail = getattr(
                    self.portal_manager,
                    'last_upload_error',
                    '',
                ) or 'no data or token not set'
                self.result_ready.emit(False, detail)
            elif res.status_code == 200:
                self.result_ready.emit(True, '')
            else:
                self.result_ready.emit(False, f'HTTP {res.status_code}')
        except Exception as e:
            self.result_ready.emit(False, str(e))


class ConfigDialog(QDialog):
    """設定ダイアログクラス"""

    # リザルト画像フォルダ取り込みリクエスト (folder_path)
    result_images_import_requested = Signal(str)

    # インポート完了通知 (alllog / images)
    import_finished = Signal()

    def __init__(self, config: Config, result_database=None,
                 rival_manager=None, portal_manager=None,
                 screen_reader=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.result_database: ResultDatabase = result_database
        self.rival_manager: RivalManager = rival_manager
        self.portal_manager: PortalManager = portal_manager
        self.screen_reader = screen_reader
        self.ui: UIText = load_ui_text(config)
        self._alllog_worker = None
        self._img_worker = None

        self.setWindowTitle(self.ui.window.settings_title)
        self.setMinimumSize(750, 600)

        self.init_ui()
        self.load_config_values()
        if rival_manager is not None:
            rival_manager.rivals_loaded.connect(
                self._update_rival_status, Qt.QueuedConnection
            )

    def init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        tab_widget.addTab(self.create_feature_tab(), self.ui.tab.feature)
        tab_widget.addTab(self.create_image_save_tab(), self.ui.tab.image_save)
        tab_widget.addTab(self.create_capture_tab(), self.ui.tab.capture)
        tab_widget.addTab(self.create_rival_tab(), self.ui.tab.rival)
        tab_widget.addTab(self.create_portal_tab(), self.ui.tab.portal)
        tab_widget.addTab(self.create_import_tab(), self.ui.tab.import_data)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    # ── タブ作成 ─────────────────────────────────────────────────────────────

    def create_feature_tab(self):
        """機能設定タブ"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        other_group = QGroupBox(self.ui.feature.other_group)
        other_layout = QFormLayout()
        other_group.setLayout(other_layout)

        self.autoload_offset_spin = QSpinBox()
        self.autoload_offset_spin.setRange(0, 100000)
        other_layout.addRow(self.ui.feature.autoload_offset, self.autoload_offset_spin)

        self.websocket_data_port_edit = QLineEdit()
        validator = QIntValidator(1000, 65535)
        self.websocket_data_port_edit.setValidator(validator)
        other_layout.addRow(self.ui.feature.websocket_port, self.websocket_data_port_edit)

        self.mobile_score_server_enabled_check = QCheckBox(
            self.ui.feature.mobile_score_server_enabled
        )
        other_layout.addRow(self.mobile_score_server_enabled_check)

        self.mobile_score_server_port_edit = QLineEdit()
        self.mobile_score_server_port_edit.setValidator(validator)
        other_layout.addRow(
            self.ui.feature.mobile_score_server_port,
            self.mobile_score_server_port_edit,
        )

        self.keep_on_top_check = QCheckBox(self.ui.feature.keep_on_top)
        other_layout.addRow(self.keep_on_top_check)

        layout.addWidget(other_group)

        csv_group = QGroupBox(self.ui.feature.csv_group)
        csv_layout = QFormLayout()
        csv_group.setLayout(csv_layout)

        self.csv_export_path_edit = QLineEdit()
        csv_browse_button = QPushButton(self.ui.dialog.browse)
        csv_browse_button.clicked.connect(self._browse_csv_path)

        csv_row = QHBoxLayout()
        csv_row.addWidget(self.csv_export_path_edit)
        csv_row.addWidget(csv_browse_button)
        csv_layout.addRow(self.ui.feature.csv_export_path, csv_row)

        layout.addWidget(csv_group)
        layout.addStretch()
        return widget

    def create_image_save_tab(self):
        """画像保存設定タブ"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        path_group = QGroupBox(self.ui.image_save.path_group)
        path_layout = QFormLayout()
        path_group.setLayout(path_layout)

        self.image_save_path_edit = QLineEdit()
        browse_button = QPushButton(self.ui.dialog.browse)
        browse_button.clicked.connect(self._browse_image_path)

        path_row = QHBoxLayout()
        path_row.addWidget(self.image_save_path_edit)
        path_row.addWidget(browse_button)
        path_layout.addRow(self.ui.image_save.image_save_path, path_row)

        self.image_format_group = QButtonGroup()
        self.image_format_png_radio = QRadioButton(self.ui.image_save.image_format_png)
        self.image_format_jpg_radio = QRadioButton(self.ui.image_save.image_format_jpg)
        self.image_format_group.addButton(self.image_format_png_radio, 0)
        self.image_format_group.addButton(self.image_format_jpg_radio, 1)

        format_row = QHBoxLayout()
        format_row.addWidget(self.image_format_png_radio)
        format_row.addWidget(self.image_format_jpg_radio)
        format_row.addStretch()
        path_layout.addRow(self.ui.image_save.image_format, format_row)

        self.autosave_image_check = QCheckBox(self.ui.image_save.autosave_image)
        path_layout.addRow(self.autosave_image_check)

        self.autosave_result_info_area_only_check = QCheckBox(
            self.ui.image_save.autosave_result_info_area_only
        )
        path_layout.addRow(self.autosave_result_info_area_only_check)

        self.autosave_updated_score_only_check = QCheckBox(
            self.ui.image_save.autosave_updated_score_only
        )
        path_layout.addRow(self.autosave_updated_score_only_check)

        self.summary_updated_results_only_check = QCheckBox(
            self.ui.image_save.summary_updated_results_only
        )
        path_layout.addRow(self.summary_updated_results_only_check)

        self.summary_min_rows_spin = QSpinBox()
        self.summary_min_rows_spin.setRange(0, 1000)
        path_layout.addRow(
            self.ui.image_save.summary_min_rows,
            self.summary_min_rows_spin,
        )

        self.summary_bg_alpha_spin = QSpinBox()
        self.summary_bg_alpha_spin.setRange(0, 255)
        path_layout.addRow(
            self.ui.image_save.summary_bg_alpha,
            self.summary_bg_alpha_spin,
        )

        self.save_summary_on_exit_check = QCheckBox(
            self.ui.image_save.save_summary_on_exit
        )
        self.save_summary_on_exit_check.toggled.connect(
            self._update_summary_exit_filename_enabled
        )
        path_layout.addRow(self.save_summary_on_exit_check)

        self.summary_exit_filename_group = QButtonGroup()
        self.summary_exit_filename_datetime_radio = QRadioButton(
            self.ui.image_save.summary_exit_filename_datetime
        )
        self.summary_exit_filename_date_radio = QRadioButton(
            self.ui.image_save.summary_exit_filename_date
        )
        self.summary_exit_filename_group.addButton(
            self.summary_exit_filename_datetime_radio, 0
        )
        self.summary_exit_filename_group.addButton(
            self.summary_exit_filename_date_radio, 1
        )

        summary_filename_row = QHBoxLayout()
        summary_filename_row.addWidget(self.summary_exit_filename_datetime_radio)
        summary_filename_row.addWidget(self.summary_exit_filename_date_radio)
        summary_filename_row.addStretch()
        self.summary_exit_filename_label = QLabel(
            self.ui.image_save.summary_exit_filename
        )
        path_layout.addRow(self.summary_exit_filename_label, summary_filename_row)

        layout.addWidget(path_group)

        layout.addStretch()
        return widget

    def _update_summary_exit_filename_enabled(self, checked: bool):
        """終了時レシート保存が有効な場合だけファイル名形式を選べるようにする。"""
        self.summary_exit_filename_label.setEnabled(checked)
        self.summary_exit_filename_datetime_radio.setEnabled(checked)
        self.summary_exit_filename_date_radio.setEnabled(checked)

    def create_capture_tab(self):
        """キャプチャ設定タブ"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        method_group = QGroupBox(self.ui.capture.method_group)
        method_layout = QFormLayout()
        method_group.setLayout(method_layout)

        self.capture_method_group = QButtonGroup()
        self.capture_method_direct_radio = QRadioButton(self.ui.capture.method_direct_window)
        self.capture_method_obs_radio = QRadioButton(self.ui.capture.method_obs_websocket)
        self.capture_method_group.addButton(self.capture_method_direct_radio, 0)
        self.capture_method_group.addButton(self.capture_method_obs_radio, 1)

        method_radio_row = QHBoxLayout()
        method_radio_row.addWidget(self.capture_method_direct_radio)
        method_radio_row.addWidget(self.capture_method_obs_radio)
        method_radio_row.addStretch()
        method_layout.addRow(self.ui.capture.method_label, method_radio_row)

        self.direct_capture_all_monitors_check = QCheckBox(self.ui.capture.direct_capture_all_monitors)
        self.direct_capture_all_monitors_check.setToolTip(self.ui.capture.direct_capture_all_monitors_tip)
        method_layout.addRow(self.direct_capture_all_monitors_check)
        self.capture_method_group.idClicked.connect(self._update_direct_capture_option_enabled)

        layout.addWidget(method_group)

        orient_group = QGroupBox(self.ui.capture.orientation_group)
        orient_layout = QVBoxLayout()
        orient_group.setLayout(orient_layout)

        self.orientation_group = QButtonGroup()
        self.orient_auto_radio  = QRadioButton(self.ui.capture.orientation_auto)
        self.orient_up_radio    = QRadioButton(self.ui.capture.orientation_top_up)
        self.orient_right_radio = QRadioButton(self.ui.capture.orientation_top_right)
        self.orient_left_radio  = QRadioButton(self.ui.capture.orientation_top_left)

        self.orientation_group.addButton(self.orient_auto_radio,  0)
        self.orientation_group.addButton(self.orient_up_radio,    1)
        self.orientation_group.addButton(self.orient_right_radio, 2)
        self.orientation_group.addButton(self.orient_left_radio,  3)

        for radio in [self.orient_auto_radio, self.orient_up_radio,
                      self.orient_right_radio, self.orient_left_radio]:
            orient_layout.addWidget(radio)

        layout.addWidget(orient_group)
        layout.addStretch()
        return widget

    def _update_direct_capture_option_enabled(self):
        """直接取得向けの詳細設定を、直接取得選択時だけ操作可能にする。"""
        is_direct_capture = self.capture_method_group.checkedId() == 0
        self.direct_capture_all_monitors_check.setEnabled(is_direct_capture)

    def create_rival_tab(self):
        """ライバル登録タブ"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # ヒント
        hint_label = QLabel(self.ui.rival.url_hint)
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        # ── 追加 ──
        add_group = QGroupBox("ライバル追加")
        add_form = QFormLayout()
        add_group.setLayout(add_form)

        self._rival_name_edit = QLineEdit()
        self._rival_name_edit.setPlaceholderText("ライバル名")
        add_form.addRow("名前:", self._rival_name_edit)

        self._rival_url_edit = QLineEdit()
        self._rival_url_edit.setPlaceholderText("Google Drive URL またはファイルID")
        add_form.addRow("URL:", self._rival_url_edit)

        add_btn = QPushButton("追加")
        add_btn.clicked.connect(self._rival_add)
        add_form.addRow(add_btn)

        layout.addWidget(add_group)

        # ── 有効/無効・削除・再取得 ──
        mgmt_group = QGroupBox("ライバル管理")
        mgmt_v = QVBoxLayout()
        mgmt_group.setLayout(mgmt_v)

        self._rival_list = QListWidget()
        self._rival_list.setMinimumHeight(120)
        self._rival_list.itemChanged.connect(self._rival_item_changed)
        mgmt_v.addWidget(self._rival_list)

        del_row = QHBoxLayout()
        del_btn = QPushButton("削除")
        del_btn.clicked.connect(self._rival_delete)
        del_row.addWidget(del_btn)
        del_row.addStretch()
        mgmt_v.addLayout(del_row)

        refetch_row = QHBoxLayout()
        refetch_btn = QPushButton("再取得")
        refetch_btn.clicked.connect(self._rival_refetch)
        refetch_row.addWidget(refetch_btn)
        self._rival_status_label = QLabel("")
        refetch_row.addWidget(self._rival_status_label)
        refetch_row.addStretch()
        mgmt_v.addLayout(refetch_row)

        layout.addWidget(mgmt_group)
        layout.addStretch()
        return widget

    def create_import_tab(self):
        """データ取り込みタブ"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # alllog.pkl グループ
        alllog_group = QGroupBox(self.ui.import_data.alllog_group)
        alllog_layout = QFormLayout()
        alllog_group.setLayout(alllog_layout)

        self.alllog_path_edit = QLineEdit()
        alllog_browse_btn = QPushButton(self.ui.dialog.browse)
        alllog_browse_btn.clicked.connect(self._browse_alllog_path)

        alllog_path_row = QHBoxLayout()
        alllog_path_row.addWidget(self.alllog_path_edit)
        alllog_path_row.addWidget(alllog_browse_btn)
        alllog_layout.addRow(self.ui.import_data.alllog_label, alllog_path_row)

        self._alllog_import_btn = QPushButton(self.ui.import_data.alllog_button)
        self._alllog_import_btn.clicked.connect(self._on_alllog_import)
        alllog_layout.addRow(self._alllog_import_btn)

        self._alllog_progress = QProgressBar()
        self._alllog_progress.setVisible(False)
        alllog_layout.addRow(self._alllog_progress)

        alllog_status_row = QHBoxLayout()
        self._alllog_status_label = QLabel("")
        self._alllog_cancel_btn = QPushButton("キャンセル")
        self._alllog_cancel_btn.setVisible(False)
        self._alllog_cancel_btn.clicked.connect(self._on_alllog_import_cancel)
        alllog_status_row.addWidget(self._alllog_status_label)
        alllog_status_row.addStretch()
        alllog_status_row.addWidget(self._alllog_cancel_btn)
        alllog_layout.addRow(alllog_status_row)

        self._alllog_worker = None

        layout.addWidget(alllog_group)

        # リザルト画像フォルダ グループ
        img_group = QGroupBox(self.ui.import_data.result_image_group)
        img_layout = QFormLayout()
        img_group.setLayout(img_layout)

        self.result_image_path_edit = QLineEdit()
        img_browse_btn = QPushButton(self.ui.dialog.browse)
        img_browse_btn.clicked.connect(self._browse_result_image_path)

        img_path_row = QHBoxLayout()
        img_path_row.addWidget(self.result_image_path_edit)
        img_path_row.addWidget(img_browse_btn)
        img_layout.addRow(self.ui.import_data.result_image_label, img_path_row)

        self._img_import_btn = QPushButton(self.ui.import_data.result_image_button)
        self._img_import_btn.clicked.connect(self._on_result_images_import)
        img_layout.addRow(self._img_import_btn)

        self._img_progress = QProgressBar()
        self._img_progress.setVisible(False)
        img_layout.addRow(self._img_progress)

        img_status_row = QHBoxLayout()
        self._img_status_label = QLabel("")
        self._img_cancel_btn = QPushButton("キャンセル")
        self._img_cancel_btn.setVisible(False)
        self._img_cancel_btn.clicked.connect(self._on_result_images_import_cancel)
        img_status_row.addWidget(self._img_status_label)
        img_status_row.addStretch()
        img_status_row.addWidget(self._img_cancel_btn)
        img_layout.addRow(img_status_row)

        layout.addWidget(img_group)

        # v1 settings.json グループ
        settings_group = QGroupBox(self.ui.import_data.settings_group)
        settings_layout = QFormLayout()
        settings_group.setLayout(settings_layout)

        self.v1_settings_path_edit = QLineEdit()
        settings_browse_btn = QPushButton(self.ui.dialog.browse)
        settings_browse_btn.clicked.connect(self._browse_v1_settings_path)

        settings_path_row = QHBoxLayout()
        settings_path_row.addWidget(self.v1_settings_path_edit)
        settings_path_row.addWidget(settings_browse_btn)
        settings_layout.addRow(
            self.ui.import_data.settings_label,
            settings_path_row,
        )

        self._v1_settings_import_btn = QPushButton(
            self.ui.import_data.settings_rival_button
        )
        self._v1_settings_import_btn.clicked.connect(
            self._on_v1_settings_rivals_import
        )
        settings_layout.addRow(self._v1_settings_import_btn)

        self._v1_settings_status_label = QLabel("")
        settings_layout.addRow(self._v1_settings_status_label)

        layout.addWidget(settings_group)
        layout.addStretch()
        return widget

    def create_portal_tab(self):
        """Portal連携タブ"""
        from src.portal_manager import PORTAL_URL
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # ── Portal URL ──
        url_group = QGroupBox(self.ui.portal.url_group)
        url_layout = QHBoxLayout()
        url_group.setLayout(url_layout)

        url_label = QLabel(f'<a href="{PORTAL_URL}">{PORTAL_URL}</a>')
        url_label.setOpenExternalLinks(True)
        url_layout.addWidget(url_label)

        open_btn = QPushButton(self.ui.portal.open_button)
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(PORTAL_URL)))
        url_layout.addWidget(open_btn)
        url_layout.addStretch()

        layout.addWidget(url_group)

        # ── トークン・プレイヤー名 ──
        token_group = QGroupBox(self.ui.portal.token_group)
        token_form = QFormLayout()
        token_group.setLayout(token_form)

        self._portal_token_edit = QLineEdit()
        self._portal_token_edit.setPlaceholderText(self.ui.portal.token_placeholder)
        self._portal_token_edit.setEchoMode(QLineEdit.Password)
        token_form.addRow(self.ui.portal.token_label, self._portal_token_edit)

        self._portal_player_name_edit = QLineEdit()
        token_form.addRow(self.ui.portal.player_name_label, self._portal_player_name_edit)

        layout.addWidget(token_group)

        # ── データ送信 ──
        upload_group = QGroupBox(self.ui.portal.upload_group)
        upload_v = QVBoxLayout()
        upload_group.setLayout(upload_v)

        upload_row = QHBoxLayout()
        self._portal_upload_btn = QPushButton(self.ui.portal.upload_all_button)
        self._portal_upload_btn.clicked.connect(self._on_portal_upload_all)
        upload_row.addWidget(self._portal_upload_btn)
        upload_row.addStretch()
        upload_v.addLayout(upload_row)

        self._portal_status_label = QLabel(self.ui.portal.upload_status_idle)
        upload_v.addWidget(self._portal_status_label)

        self._portal_upload_worker = None

        layout.addWidget(upload_group)
        layout.addStretch()
        return widget

    # ── ファイルブラウザ ──────────────────────────────────────────────────────

    def _browse_image_path(self):
        current = self.image_save_path_edit.text()
        if not os.path.exists(current):
            current = os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(
            self, self.ui.dialog.select_image_path, current
        )
        if dir_path:
            self.image_save_path_edit.setText(dir_path)

    def _browse_csv_path(self):
        current = self.csv_export_path_edit.text()
        if not os.path.exists(current):
            current = os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(self, "CSV出力先フォルダを選択", current)
        if dir_path:
            self.csv_export_path_edit.setText(dir_path)

    def _browse_alllog_path(self):
        current = self.alllog_path_edit.text()
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "alllog.pkl を選択", start_dir, "Pickle files (*.pkl)"
        )
        if file_path:
            self.alllog_path_edit.setText(file_path)

    def _browse_result_image_path(self):
        current = self.result_image_path_edit.text()
        if not os.path.exists(current):
            current = os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(self, "リザルト画像フォルダを選択", current)
        if dir_path:
            self.result_image_path_edit.setText(dir_path)

    def _browse_v1_settings_path(self):
        current = self.v1_settings_path_edit.text()
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "v1 settings.json を選択", start_dir, "JSON files (*.json)"
        )
        if file_path:
            self.v1_settings_path_edit.setText(file_path)

    # ── ライバル操作 ──────────────────────────────────────────────────────────

    def _rival_load_del_combo(self):
        """ライバル一覧を config.rivals から更新する。"""
        current_item = self._rival_list.currentItem()
        current = current_item.data(Qt.UserRole) if current_item else ''
        self._rival_list.blockSignals(True)
        self._rival_list.clear()
        for rival in self.config.rivals:
            name = rival.get('name', '')
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if rival.get('enabled', True) is not False else Qt.Unchecked
            )
            item.setData(Qt.UserRole, name)
            item.setToolTip(rival.get('url', ''))
            self._rival_list.addItem(item)
            if name == current:
                self._rival_list.setCurrentItem(item)
        self._rival_list.blockSignals(False)

    def _rival_selected_name(self) -> str:
        item = self._rival_list.currentItem()
        return item.data(Qt.UserRole) if item else ''

    def _reload_rivals_from_config(self):
        """設定変更を RivalManager に反映して表示対象を更新する。"""
        if self.rival_manager is not None:
            self.rival_manager.load_cache(
                self.config.rivals,
                include_portal=bool(self.config.portal_token),
            )
        self._update_rival_status()

    def _update_rival_status(self):
        """rival_manager の状態をステータスラベルに反映"""
        if self.rival_manager is None:
            self._rival_status_label.setText("")
            return
        tm = getattr(self.rival_manager, 'last_fetch_time', None)
        csv_rivals = [
            r for r in self.rival_manager.rivals
            if getattr(r, 'source', 'csv') != 'portal'
        ]
        disabled_count = sum(
            1 for r in self.config.rivals
            if r.get('enabled', True) is False
        )
        portal_rivals = [
            r for r in self.rival_manager.rivals
            if getattr(r, 'source', 'csv') == 'portal'
        ]
        n  = len(csv_rivals)
        suffix = f" + Portal {len(portal_rivals)}人" if portal_rivals else ""
        disabled_suffix = f" / 無効 {disabled_count}人" if disabled_count else ""
        if tm:
            ok = sum(1 for r in csv_rivals if not r.error)
            self._rival_status_label.setText(
                f"取得: {tm}  ({ok}/{n}人{suffix}{disabled_suffix})"
            )
        elif n:
            self._rival_status_label.setText(
                f"キャッシュ ({n}人{suffix}{disabled_suffix})"
            )
        elif portal_rivals:
            self._rival_status_label.setText(
                f"キャッシュ (Portal {len(portal_rivals)}人{disabled_suffix})"
            )
        elif disabled_count:
            self._rival_status_label.setText(f"無効 {disabled_count}人")
        else:
            self._rival_status_label.setText("")

    def _rival_item_changed(self, item: QListWidgetItem):
        """一覧のチェック状態を enabled として保存する。"""
        name = item.data(Qt.UserRole)
        enabled = item.checkState() == Qt.Checked
        updated = False
        for rival in self.config.rivals:
            if rival.get('name') == name:
                if rival.get('enabled', True) is not enabled:
                    rival['enabled'] = enabled
                    updated = True
                break
        if not updated:
            return
        self.config.save_config()
        self._reload_rivals_from_config()

    def _rival_add(self):
        """ライバルを追加してフェッチ開始"""
        name = self._rival_name_edit.text().strip()
        url  = self._rival_url_edit.text().strip()
        if not name or not url:
            QMessageBox.warning(self, self.ui.message.warning_title,
                                "名前とURLを入力してください")
            return
        if any(r['name'] == name for r in self.config.rivals):
            QMessageBox.warning(self, self.ui.message.warning_title,
                                f"'{name}' は既に登録されています")
            return
        self.config.rivals.append({'name': name, 'url': url, 'enabled': True})
        self.config.save_config()
        self._rival_name_edit.clear()
        self._rival_url_edit.clear()
        self._rival_load_del_combo()
        if self.rival_manager is not None:
            self._rival_status_label.setText("取得中...")
            portal_fn = (self.portal_manager.get_rivals
                         if self.portal_manager and self.config.portal_token else None)
            self.rival_manager.start_fetch(self.config.rivals, portal_fetch_fn=portal_fn)

    def _rival_delete(self):
        """選択ライバルを削除"""
        name = self._rival_selected_name()
        if not name:
            return
        self.config.rivals = [r for r in self.config.rivals if r['name'] != name]
        self.config.save_config()
        self._rival_load_del_combo()
        if self.rival_manager is not None:
            self.rival_manager.delete_cached_rival(name)
        self._update_rival_status()

    def _rival_refetch(self):
        """全ライバルデータを再取得"""
        if self.rival_manager is None:
            return
        self._rival_status_label.setText("取得中...")
        portal_fn = (self.portal_manager.get_rivals
                     if self.portal_manager and self.config.portal_token else None)
        if not self.config.rivals and portal_fn is None:
            self._rival_status_label.setText("未登録")
            return
        self.rival_manager.start_fetch(self.config.rivals, portal_fetch_fn=portal_fn)

    # ── ボタンハンドラ ────────────────────────────────────────────────────────

    def _on_alllog_import(self):
        path = self.alllog_path_edit.text().strip()
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, self.ui.message.warning_title, "有効なファイルを指定してください")
            return
        if self.result_database is None:
            QMessageBox.warning(self, self.ui.message.warning_title, "データベースが初期化されていません")
            return

        self._confirm_and_import_uploaded_scores(path)

        self._alllog_import_btn.setEnabled(False)
        self._alllog_cancel_btn.setVisible(True)
        self._alllog_progress.setVisible(True)
        self._alllog_progress.setValue(0)
        self._alllog_status_label.setText("読み込み中...")

        self._alllog_worker = AlllogImportWorker(path, self.result_database)
        self._alllog_worker.progress.connect(self._on_alllog_progress)
        self._alllog_worker.finished.connect(self._on_alllog_finished)
        self._alllog_worker.error.connect(self._on_alllog_error)
        self._alllog_worker.start()

    def _on_alllog_progress(self, current: int, total: int):
        self._alllog_progress.setMaximum(total)
        self._alllog_progress.setValue(current)
        self._alllog_status_label.setText(f"{current} / {total}")

    def _on_alllog_finished(self, registered: int, total: int):
        self._alllog_import_btn.setEnabled(True)
        self._alllog_cancel_btn.setVisible(False)
        self._alllog_progress.setValue(self._alllog_progress.maximum())
        self._alllog_status_label.setText(f"完了: {registered} / {total} 件登録")
        self._alllog_worker = None
        self.import_finished.emit()

    def _on_alllog_error(self, msg: str):
        self._alllog_import_btn.setEnabled(True)
        self._alllog_cancel_btn.setVisible(False)
        self._alllog_progress.setVisible(False)
        self._alllog_status_label.setText(f"エラー: {msg}")
        self._alllog_worker = None
        QMessageBox.critical(self, "エラー", f"alllog.pkl の読み込みに失敗しました:\n{msg}")

    def _on_alllog_import_cancel(self):
        if self._alllog_worker:
            self._alllog_worker.cancel()
        self._alllog_import_btn.setEnabled(True)
        self._alllog_cancel_btn.setVisible(False)
        self._alllog_status_label.setText("キャンセルしました")

    def _confirm_and_import_uploaded_scores(self, alllog_path: str):
        """alllog.pkl と同じ v1 ルート配下の uploaded_score.pkl を任意で取り込む。"""
        v1_root = os.path.dirname(os.path.abspath(alllog_path))
        uploaded_path = os.path.join(v1_root, 'out', 'uploaded_score.pkl')
        if not os.path.isfile(uploaded_path):
            return

        reply = QMessageBox.question(
            self,
            self.ui.message.confirm_title,
            'v1の out/uploaded_score.pkl が見つかりました。\n'
            'sdvx_helper portal 送信済み履歴も取り込みますか？',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            imported = load_uploaded_scores_from_path(uploaded_path)
            mng = ManageUploadedScores()
            added = mng.merge(imported)
            if added > 0:
                mng.save()
                if self.portal_manager is not None:
                    self.portal_manager._uploaded_scores_mng = mng
            QMessageBox.information(
                self,
                self.ui.message.completed_title,
                f'portal 送信済み履歴を取り込みました。\n'
                f'{added} / {len(imported)} 件を追加しました。',
            )
        except Exception as e:
            logger.warning(f'uploaded_score.pkl import failed:\n{traceback.format_exc()}')
            QMessageBox.warning(
                self,
                self.ui.message.warning_title,
                f'uploaded_score.pkl の取り込みに失敗しました:\n{e}',
            )

    def _on_portal_upload_all(self):
        """全プレーログをPortalに送信"""
        if self.portal_manager is None or self.result_database is None:
            QMessageBox.warning(self, self.ui.message.warning_title,
                                self.ui.portal.upload_no_token)
            return
        token = self._portal_token_edit.text().strip()
        if not token:
            QMessageBox.warning(self, self.ui.message.warning_title,
                                self.ui.portal.upload_no_token)
            return
        # トークンをワーカー実行前に反映（ダイアログを開いたまま変更した場合のため）
        self.portal_manager.update_token(token)

        player_name = self._portal_player_name_edit.text().strip() or 'NONAME'
        total_vf = self.result_database.get_total_vf()
        self._portal_upload_btn.setEnabled(False)
        self._portal_status_label.setText(self.ui.portal.upload_status_running)

        self._portal_upload_worker = _PortalUploadAllWorker(
            self.portal_manager,
            self.result_database,
            player_name=player_name,
            volforce=f'{total_vf / 1000:.3f}',
        )
        self._portal_upload_worker.result_ready.connect(
            self._on_portal_upload_finished,
            Qt.QueuedConnection,
        )
        self._portal_upload_worker.finished.connect(
            self._cleanup_portal_upload_worker,
            Qt.QueuedConnection,
        )
        self._portal_upload_worker.start()

    def _on_portal_upload_finished(self, success: bool, detail: str):
        self._portal_upload_btn.setEnabled(True)
        if success:
            self._portal_status_label.setText(self.ui.portal.upload_status_ok)
        else:
            self._portal_status_label.setText(
                self.ui.portal.upload_status_error.format(detail=detail)
            )

    def _cleanup_portal_upload_worker(self):
        worker = self._portal_upload_worker
        if worker is not None:
            worker.deleteLater()
            self._portal_upload_worker = None

    def _on_result_images_import(self):
        path = self.result_image_path_edit.text().strip()
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, self.ui.message.warning_title, "有効なフォルダを指定してください")
            return
        
        if self.screen_reader is None:
            QMessageBox.warning(self, self.ui.message.warning_title, "認識エンジンが準備できていません")
            return

        self._img_import_btn.setEnabled(False)
        self._img_progress.setVisible(True)
        self._img_progress.setValue(0)
        self._img_status_label.setText("解析中...")
        self._img_cancel_btn.setVisible(True)

        self._img_worker = ImageImportWorker(path, self.result_database, self.screen_reader)
        self._img_worker.progress.connect(self._on_img_import_progress)
        self._img_worker.finished.connect(self._on_img_import_finished)
        self._img_worker.error.connect(self._on_img_import_error)
        self._img_worker.start()

    def _on_img_import_progress(self, current, total):
        self._img_progress.setMaximum(total)
        self._img_progress.setValue(current)
        self._img_status_label.setText(f"解析中... ({current}/{total})")

    def _on_img_import_finished(self, registered, total):
        self._img_import_btn.setEnabled(True)
        self._img_progress.setVisible(False)
        self._img_cancel_btn.setVisible(False)
        self._img_status_label.setText(f"完了: {registered}/{total} 件を登録しました")
        self._img_worker = None
        self.import_finished.emit()
        # MainWindow側でデータを再読み込みさせるためにリクエストを飛ばす
        self.result_images_import_requested.emit(self.result_image_path_edit.text().strip())

    def _on_img_import_error(self, message):
        self._img_import_btn.setEnabled(True)
        self._img_progress.setVisible(False)
        self._img_cancel_btn.setVisible(False)
        self._img_status_label.setText(f"エラー: {message}")
        self._img_worker = None

    def _on_result_images_import_cancel(self):
        if self._img_worker:
            self._img_worker.cancel()
            self._img_status_label.setText("キャンセル中...")
            self._img_cancel_btn.setEnabled(False)

    def _on_v1_settings_rivals_import(self):
        path = self.v1_settings_path_edit.text().strip()
        if not path or not os.path.isfile(path):
            QMessageBox.warning(
                self,
                self.ui.message.warning_title,
                "有効な settings.json を指定してください",
            )
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except UnicodeDecodeError:
            try:
                with open(path, 'r', encoding='cp932') as f:
                    data = json.load(f)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    self.ui.message.error_title,
                    f"settings.json の読み込みに失敗しました:\n{e}",
                )
                return
        except Exception as e:
            QMessageBox.critical(
                self,
                self.ui.message.error_title,
                f"settings.json の読み込みに失敗しました:\n{e}",
            )
            return

        if not isinstance(data, dict):
            QMessageBox.warning(
                self,
                self.ui.message.warning_title,
                "settings.json のフォーマットが不正です",
            )
            return

        names = data.get('rival_names')
        urls = data.get('rival_googledrive')
        if not isinstance(names, list) or not isinstance(urls, list):
            QMessageBox.warning(
                self,
                self.ui.message.warning_title,
                "rival_names / rival_googledrive が見つかりません",
            )
            return

        existing_names = {
            str(r.get('name', '')).strip()
            for r in self.config.rivals
            if isinstance(r, dict)
        }
        existing_urls = {
            str(r.get('url', '')).strip()
            for r in self.config.rivals
            if isinstance(r, dict)
        }

        imported = 0
        skipped = 0
        for name_raw, url_raw in zip(names, urls):
            name = str(name_raw).strip()
            url = str(url_raw).strip()
            if not name or not url:
                skipped += 1
                continue
            if name in existing_names or url in existing_urls:
                skipped += 1
                continue
            self.config.rivals.append({'name': name, 'url': url, 'enabled': True})
            existing_names.add(name)
            existing_urls.add(url)
            imported += 1

        if len(names) != len(urls):
            skipped += abs(len(names) - len(urls))

        if imported <= 0:
            self._v1_settings_status_label.setText(
                f"追加なし: {skipped} 件スキップ"
            )
            QMessageBox.information(
                self,
                self.ui.message.info_title,
                "追加できるライバルはありませんでした",
            )
            return

        self.config.save_config()
        self._rival_load_del_combo()
        self._v1_settings_status_label.setText(
            f"完了: {imported} 件追加 / {skipped} 件スキップ"
        )

        if self.rival_manager is not None:
            self._rival_status_label.setText("取得中...")
            portal_fn = (self.portal_manager.get_rivals
                         if self.portal_manager and self.config.portal_token else None)
            self.rival_manager.start_fetch(self.config.rivals, portal_fetch_fn=portal_fn)
        else:
            self._update_rival_status()

        QMessageBox.information(
            self,
            self.ui.message.completed_title,
            f"ライバル一覧を取り込みました。\n"
            f"{imported} 件追加 / {skipped} 件スキップ",
        )

    # ── 設定読み書き ─────────────────────────────────────────────────────────

    def load_config_values(self):
        """設定値をUIに反映"""
        self.keep_on_top_check.setChecked(self.config.keep_on_top)
        self.autoload_offset_spin.setValue(self.config.autoload_offset)
        self.websocket_data_port_edit.setText(str(self.config.websocket_data_port))
        self.mobile_score_server_enabled_check.setChecked(
            bool(getattr(self.config, 'mobile_score_server_enabled', True))
        )
        self.mobile_score_server_port_edit.setText(
            str(getattr(self.config, 'mobile_score_server_port', 8787))
        )

        self.image_save_path_edit.setText(self.config.image_save_path)
        self.autosave_image_check.setChecked(self.config.autosave_image)
        self.autosave_result_info_area_only_check.setChecked(
            getattr(self.config, 'autosave_result_info_area_only', False)
        )
        self.autosave_updated_score_only_check.setChecked(
            getattr(self.config, 'autosave_updated_score_only', False)
        )
        self.summary_updated_results_only_check.setChecked(
            getattr(self.config, 'summary_updated_results_only', False)
        )
        try:
            summary_min_rows = int(getattr(self.config, 'summary_min_rows', 15))
        except Exception:
            summary_min_rows = 15
        self.summary_min_rows_spin.setValue(max(0, min(1000, summary_min_rows)))
        try:
            summary_bg_alpha = int(getattr(self.config, 'summary_bg_alpha', 200))
        except Exception:
            summary_bg_alpha = 200
        self.summary_bg_alpha_spin.setValue(max(0, min(255, summary_bg_alpha)))
        save_summary_on_exit = getattr(self.config, 'save_summary_on_exit', False)
        self.save_summary_on_exit_check.setChecked(save_summary_on_exit)
        if getattr(self.config, 'summary_exit_filename', 'datetime') == 'date':
            self.summary_exit_filename_date_radio.setChecked(True)
        else:
            self.summary_exit_filename_datetime_radio.setChecked(True)
        self._update_summary_exit_filename_enabled(save_summary_on_exit)
        if getattr(self.config, 'image_save_format', 'png') == 'jpg':
            self.image_format_jpg_radio.setChecked(True)
        else:
            self.image_format_png_radio.setChecked(True)
        self.csv_export_path_edit.setText(self.config.csv_export_path)

        capture_method = getattr(self.config, 'capture_method', 'direct_window')
        if capture_method == 'direct_window':
            self.capture_method_direct_radio.setChecked(True)
        else:
            self.capture_method_obs_radio.setChecked(True)

        self.direct_capture_all_monitors_check.setChecked(
            bool(getattr(self.config, 'direct_capture_all_monitors', False))
        )
        self._update_direct_capture_option_enabled()

        orient_map = {None: 0, 'top_up': 1, 'top_right': 2, 'top_left': 3}
        btn_id = orient_map.get(self.config.screen_orientation_override, 0)
        btn = self.orientation_group.button(btn_id)
        if btn:
            btn.setChecked(True)

        self._rival_load_del_combo()
        self._update_rival_status()

        self._portal_token_edit.setText(self.config.portal_token)
        self._portal_player_name_edit.setText(self.config.player_name)

    def accept(self):
        """OKボタン: UIから設定値を取得して保存"""
        self.config.keep_on_top = self.keep_on_top_check.isChecked()
        self.config.autoload_offset = self.autoload_offset_spin.value()

        try:
            port = int(self.websocket_data_port_edit.text())
            if 1000 <= port <= 65535:
                self.config.websocket_data_port = port
        except ValueError:
            pass

        self.config.mobile_score_server_enabled = (
            self.mobile_score_server_enabled_check.isChecked()
        )
        try:
            port = int(self.mobile_score_server_port_edit.text())
            if 1000 <= port <= 65535:
                self.config.mobile_score_server_port = port
        except ValueError:
            pass

        self.config.image_save_path = self.image_save_path_edit.text()
        self.config.autosave_image = self.autosave_image_check.isChecked()
        self.config.autosave_result_info_area_only = (
            self.autosave_result_info_area_only_check.isChecked()
        )
        self.config.autosave_updated_score_only = (
            self.autosave_updated_score_only_check.isChecked()
        )
        self.config.summary_updated_results_only = (
            self.summary_updated_results_only_check.isChecked()
        )
        self.config.summary_min_rows = self.summary_min_rows_spin.value()
        self.config.summary_bg_alpha = self.summary_bg_alpha_spin.value()
        self.config.save_summary_on_exit = (
            self.save_summary_on_exit_check.isChecked()
        )
        self.config.summary_exit_filename = (
            'date'
            if self.summary_exit_filename_group.checkedId() == 1
            else 'datetime'
        )
        self.config.image_save_format = (
            'jpg'
            if self.image_format_group.checkedId() == 1
            else 'png'
        )
        self.config.csv_export_path = self.csv_export_path_edit.text()
        self.config.capture_method = (
            'direct_window'
            if self.capture_method_group.checkedId() == 0
            else 'obs_websocket'
        )

        self.config.direct_capture_all_monitors = self.direct_capture_all_monitors_check.isChecked()

        orient_map = {0: None, 1: 'top_up', 2: 'top_right', 3: 'top_left'}
        self.config.screen_orientation_override = orient_map.get(
            self.orientation_group.checkedId(), None
        )

        self.config.portal_token = self._portal_token_edit.text().strip()
        self.config.player_name  = self._portal_player_name_edit.text().strip()
        if self.portal_manager is not None:
            self.portal_manager.update_token(self.config.portal_token)

        self.config.save_config()
        logger.info("設定を保存しました")
        super().accept()
