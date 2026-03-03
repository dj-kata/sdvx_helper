"""
SDVX スコアビューワ
全プレーログを集計して自己ベスト情報をテーブル表示

レイアウト:
  上部左: 検索・フィルター（難易度/レベル/テキスト/ライバル）
  上部右: プレーログ + ライバル比較
  下部  : 各譜面ベストスコアテーブル
"""
from __future__ import annotations

import datetime
import traceback
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QLineEdit, QLabel, QGroupBox,
    QPushButton, QMessageBox, QComboBox, QListWidget,
)
from PySide6.QtCore import Qt, QByteArray, QObject, Signal, QTimer
from PySide6.QtGui import QColor, QBrush, QPainter

from src.result import OneBestData, OneResult
from src.result_database import ResultDatabase
from src.rival_data import RivalManager, RivalScoreEntry
from src.classes import difficulty, clear_lamp, detect_mode
from src.funcs import convert_difficulty, convert_lamp
from src.config import Config
from src.logger import get_logger

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.portal_manager import PortalManager

logger = get_logger(__name__)

# ── 色定義（白背景向け） ──────────────────────────────────────────────────────

# ランプセル自体の背景色（明るめの彩度高い色）
_LAMP_BG: dict[clear_lamp, QColor] = {
    clear_lamp.puc:     QColor(255, 210,   0),   # 金
    clear_lamp.uc:      QColor( 40, 190,  60),   # 緑
    clear_lamp.maxxive: QColor(210, 150,   0),   # 暗めの金
    clear_lamp.exc:     QColor(220,  80,   0),   # オレンジ
    clear_lamp.clear:   QColor( 50, 120, 220),   # 青
    clear_lamp.played:  QColor(130, 130, 130),   # グレー
    clear_lamp.noplay:  QColor(190, 190, 190),   # 薄グレー
}

# 行の背景色（ランプ色の薄い版）
_LAMP_ROW_BG: dict[clear_lamp, QColor] = {
    clear_lamp.puc:     QColor(255, 252, 218),
    clear_lamp.uc:      QColor(225, 255, 228),
    clear_lamp.maxxive: QColor(255, 248, 215),
    clear_lamp.exc:     QColor(255, 240, 225),
    clear_lamp.clear:   QColor(225, 238, 255),
    clear_lamp.played:  QColor(242, 242, 242),
    clear_lamp.noplay:  QColor(252, 252, 252),
}

# 難易度テキスト色（白背景で読みやすい）
_DIFF_FG: dict[difficulty, QColor] = {
    difficulty.novice:   QColor(120,  30, 170),   # 紫
    difficulty.advanced: QColor(155, 115,   0),   # 暗め金
    difficulty.exhaust:  QColor(195,  30,  30),   # 赤
    difficulty.maximum:  QColor( 50,  50,  50),   # 濃いグレー
}

_MAIN_STYLESHEET = """
QWidget {
    background-color: #FFFFFF;
    color: #1A1A1A;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #C8C8C8;
    border-radius: 5px;
    margin-top: 8px;
    padding-top: 6px;
    font-weight: bold;
    background-color: #FAFAFA;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    color: #333333;
}
QTableWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F6F6F6;
    gridline-color: #DCDCDC;
    selection-background-color: #C8DEFF;
    selection-color: #1A1A1A;
}
QHeaderView::section {
    background-color: #EFEFEF;
    color: #2A2A2A;
    border: 1px solid #CCCCCC;
    padding: 4px 6px;
    font-weight: bold;
}
QPushButton {
    background-color: #EBEBEB;
    border: 1px solid #BBBBBB;
    border-radius: 4px;
    padding: 4px 10px;
    color: #1A1A1A;
}
QPushButton:hover  { background-color: #D8D8D8; }
QPushButton:pressed { background-color: #C8C8C8; }
QPushButton:disabled { color: #999999; }
QLineEdit, QSpinBox, QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #BBBBBB;
    border-radius: 3px;
    padding: 2px 5px;
    color: #1A1A1A;
}
QLabel { background-color: transparent; }
QStatusBar { background-color: #F0F0F0; }
"""


_GRADE_ORDER: dict[str, int] = {
    'S': 9, 'AAA+': 8, 'AAA': 7, 'AA+': 6, 'AA': 5,
    'A+': 4, 'A': 3, 'B': 2, 'C': 1, 'D': 0,
}


class _PortalDeleteWorker(QObject):
    """portal削除をバックグラウンドスレッドで実行するワーカー。

    QThread + moveToThread は started→run の接続タイミング問題で
    done シグナルが届かないケースがあるため、Python の threading.Thread を使う。
    self は main thread に留まるため done → スロット接続はキュー接続で確実に届く。
    """
    done = Signal(object)  # requests.Response | None

    def start(self, portal_manager, revision: int, music_id: str, cdiff: str):
        import threading
        def _task():
            try:
                res = portal_manager.delete_score(revision, music_id, cdiff)
            except Exception:
                res = None
            self.done.emit(res)
        threading.Thread(target=_task, daemon=True).start()


class _WinLossBar(QWidget):
    """自分 vs ライバル 勝敗バー（比率表示）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wins = 0
        self._losses = 0
        self._draws = 0
        self.setFixedHeight(40)

    def set_data(self, wins: int, losses: int, draws: int):
        self._wins = wins
        self._losses = losses
        self._draws = draws
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w = self.width()
        bar_h = 22

        total = self._wins + self._losses + self._draws
        if total == 0:
            p.fillRect(0, 0, w, bar_h, QColor(220, 220, 220))
            p.setPen(QColor(120, 120, 120))
            p.drawText(0, 0, w, bar_h, Qt.AlignCenter, "ライバルを選択してください")
            p.end()
            return

        w_w = round(w * self._wins   / total) if self._wins   else 0
        l_w = round(w * self._losses / total) if self._losses else 0
        d_w = w - w_w - l_w

        if w_w > 0:
            p.fillRect(0,         0, w_w, bar_h, QColor(60, 130, 220))
        if d_w > 0:
            p.fillRect(w_w,       0, d_w, bar_h, QColor(180, 180, 180))
        if l_w > 0:
            p.fillRect(w_w + d_w, 0, l_w, bar_h, QColor(210, 60, 60))

        font = p.font()
        font.setPixelSize(11)
        p.setFont(font)
        if w_w >= 50:
            p.setPen(QColor(255, 255, 255))
            p.drawText(0, 0, w_w, bar_h, Qt.AlignCenter, f"自分: {self._wins}")
        if d_w >= 50:
            p.setPen(QColor(40, 40, 40))
            p.drawText(w_w, 0, d_w, bar_h, Qt.AlignCenter, f"引き分け: {self._draws}")
        if l_w >= 50:
            p.setPen(QColor(255, 255, 255))
            p.drawText(w_w + d_w, 0, l_w, bar_h, Qt.AlignCenter, f"ライバル: {self._losses}")

        font.setPixelSize(10)
        p.setFont(font)
        p.setPen(QColor(40, 40, 40))
        p.drawText(0, bar_h, w, self.height() - bar_h, Qt.AlignCenter,
                   f"自分 {self._wins}  /  引き分け {self._draws}  /  ライバル {self._losses}")
        p.end()


class _SortItem(QTableWidgetItem):
    """数値ソート対応テーブルアイテム"""
    def __lt__(self, other: QTableWidgetItem) -> bool:
        v1 = self.data(Qt.UserRole)
        v2 = other.data(Qt.UserRole)
        if v1 is not None and v2 is not None:
            return v1 < v2
        return self.text() < other.text()


class ScoreViewer(QMainWindow):
    """SDVX スコアビューワ"""

    _COL_LV           = 0
    _COL_S_TIER       = 1
    _COL_P_TIER       = 2
    _COL_TITLE        = 3
    _COL_DIFF         = 4
    _COL_SCORE        = 5
    _COL_GRADE        = 6
    _COL_EX           = 7
    _COL_LAMP         = 8
    _COL_VF           = 9
    _COL_DATE         = 10
    _COL_PLAYS        = 11
    _COL_RIVAL_SCORE  = 12
    _COL_RIVAL_LAMP   = 13
    _COL_SCORE_DIFF   = 14
    _HEADERS = ['LV', 'S Tier', 'P Tier', 'Title', 'Diff', 'Score', 'Grade', 'EXScore',
                'Lamp', 'VF', 'Last Played', 'Plays',
                'Rival Score', 'Rival Lamp', 'Score Diff']

    def __init__(self, config: Config, result_database: ResultDatabase,
                 rival_manager: RivalManager = None,
                 portal_manager: 'PortalManager' = None,
                 parent=None):
        super().__init__(parent)
        self.config = config
        self.result_database = result_database
        self.rival_manager = rival_manager
        self.portal_manager = portal_manager
        self._bests: dict = {}
        self._history_map: dict[int, object] = {}
        self._current_rival: str | None = None
        self._selected_title: str | None = None
        self._selected_diff = None
        self._selected_score: int | None = None
        # title → 4th難易度名 (MXM/INF/GRV/HVN/VVD/XCD)
        self._4th_diff_map: dict[str, str] = {}
        # (title, difficulty_enum) → (s_tier, p_tier)
        self._tier_map: dict = {}
        # スコアテーブルのソート状態（デフォルト: VF降順）
        self._sort_col   = self._COL_VF
        self._sort_order = Qt.DescendingOrder
        # 編集パネル用
        self._edit_data: dict = {}
        self._edit_autofill_title: str = ''  # 最後に自動補完したタイトル
        self._last_auto_registered: tuple | None = None
        self._all_titles: list[str] = []
        # portal削除ワーカー管理
        self._delete_worker: _PortalDeleteWorker | None = None
        self._pending_delete_entry = None

        self.setWindowTitle("Score Viewer - SDVX Helper")
        self.setMinimumSize(1000, 680)
        self._restore_geometry()
        self._init_ui()
        self._restore_filter_state()
        if rival_manager is not None:
            # QueuedConnection を明示: RivalFetchWorker (QThread) からの emit が
            # バックグラウンドスレッドで UI 操作を行わないよう保証する
            rival_manager.rivals_loaded.connect(
                self._on_rivals_loaded, Qt.QueuedConnection
            )
        self.refresh_data()

    # ── UI構築 ────────────────────────────────────────────────────────────────

    def _init_ui(self):
        central = QWidget()
        central.setStyleSheet(_MAIN_STYLESHEET)
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(6)

        # ── 上部エリア（左:フィルタ / 右:プレーログ+ライバル） ──
        top = QWidget()
        top_h = QHBoxLayout(top)
        top_h.setContentsMargins(0, 0, 0, 0)
        top_h.setSpacing(8)

        top_h.addWidget(self._make_filter_panel())
        top_h.addWidget(self._make_right_panel(), stretch=1)

        root.addWidget(top)

        # ── 入力補助パネル（編集モード時のみ表示） ──
        self._edit_panel = self._make_edit_panel()
        self._edit_panel.setVisible(False)
        self._edit_mode_cb.stateChanged.connect(self._on_edit_mode_toggled)
        root.addWidget(self._edit_panel)

        # ── 下部: スコアテーブル ──
        self._score_table = QTableWidget()
        self._score_table.setColumnCount(len(self._HEADERS))
        self._score_table.setHorizontalHeaderLabels(self._HEADERS)

        hdr = self._score_table.horizontalHeader()
        hdr.setSectionResizeMode(self._COL_TITLE, QHeaderView.Stretch)
        for col in [self._COL_LV, self._COL_DIFF, self._COL_GRADE,
                    self._COL_LAMP, self._COL_VF, self._COL_PLAYS,
                    self._COL_SCORE, self._COL_EX, self._COL_S_TIER, self._COL_P_TIER,
                    self._COL_RIVAL_SCORE, self._COL_RIVAL_LAMP, self._COL_SCORE_DIFF]:
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        for col in [self._COL_RIVAL_SCORE, self._COL_RIVAL_LAMP, self._COL_SCORE_DIFF]:
            self._score_table.setColumnHidden(col, True)

        self._score_table.setSortingEnabled(True)
        self._score_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._score_table.setSelectionMode(QTableWidget.SingleSelection)
        self._score_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._score_table.setAlternatingRowColors(True)
        self._score_table.itemSelectionChanged.connect(self._on_score_selected)
        self._score_table.horizontalHeader().sortIndicatorChanged.connect(self._on_sort_changed)

        root.addWidget(self._score_table, stretch=1)

        self.statusBar().showMessage("準備完了")

    def _make_filter_panel(self) -> QGroupBox:
        """左側: 検索・フィルターパネル"""
        box = QGroupBox("検索・フィルター")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        # 難易度チェックボックス
        layout.addWidget(QLabel("難易度:"))
        diff_row = QHBoxLayout()
        self._diff_checks: dict[difficulty, QCheckBox] = {}
        for diff in difficulty:
            cb = QCheckBox(str(diff))
            cb.setChecked(True)
            cb.stateChanged.connect(self._apply_filter)
            diff_row.addWidget(cb)
            self._diff_checks[diff] = cb
        diff_row.addStretch()
        layout.addLayout(diff_row)

        # レベルフィルタ（個別チェックボックス）
        lv_group = QGroupBox("レベル")
        lv_v = QVBoxLayout(lv_group)
        lv_v.setSpacing(3)
        lv_v.setContentsMargins(6, 4, 6, 4)

        self._lv_checks: dict[int, QCheckBox] = {}

        # ALL チェックボックス
        all_row = QHBoxLayout()
        all_row.setSpacing(4)
        self._lv_all_cb = QCheckBox("ALL")
        self._lv_all_cb.setChecked(True)
        self._lv_all_cb.stateChanged.connect(self._on_lv_all_changed)
        all_row.addWidget(self._lv_all_cb)
        all_row.addStretch()
        lv_v.addLayout(all_row)

        # Lv 1〜10
        row1 = QHBoxLayout()
        row1.setSpacing(2)
        for lv in range(1, 11):
            cb = QCheckBox(str(lv))
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_lv_check_changed)
            self._lv_checks[lv] = cb
            row1.addWidget(cb)
        row1.addStretch()
        lv_v.addLayout(row1)

        # Lv 11〜20
        row2 = QHBoxLayout()
        row2.setSpacing(2)
        for lv in range(11, 21):
            cb = QCheckBox(str(lv))
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_lv_check_changed)
            self._lv_checks[lv] = cb
            row2.addWidget(cb)
        row2.addStretch()
        lv_v.addLayout(row2)

        layout.addWidget(lv_group)

        # 検索ボックス
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("検索:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("タイトルを入力...")
        self._search_edit.textChanged.connect(self._apply_filter)
        search_row.addWidget(self._search_edit)
        layout.addLayout(search_row)

        # ライバル選択
        rival_row = QHBoxLayout()
        rival_row.addWidget(QLabel("ライバル:"))
        self._rival_combo = QComboBox()
        self._rival_combo.setMinimumWidth(130)
        self._rival_combo.addItem("(比較なし)")
        self._rival_combo.currentIndexChanged.connect(self._on_rival_changed)
        rival_row.addWidget(self._rival_combo)
        layout.addLayout(rival_row)

        # 勝敗バー
        self._win_loss_bar = _WinLossBar()
        layout.addWidget(self._win_loss_bar)

        # 編集モード
        self._edit_mode_cb = QCheckBox("編集モード")
        layout.addWidget(self._edit_mode_cb)

        # 更新ボタン
        refresh_btn = QPushButton("データ更新")
        refresh_btn.clicked.connect(self.refresh_data)
        layout.addWidget(refresh_btn)

        layout.addStretch()
        return box

    def _make_right_panel(self) -> QWidget:
        """右側: プレーログ＋ライバルパネル（横並び）"""
        widget = QWidget()
        h = QHBoxLayout(widget)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        # ── プレーログ ──
        log_box = QGroupBox("プレーログ")
        log_v = QVBoxLayout(log_box)
        log_v.setSpacing(4)

        self._hist_label = QLabel("下のテーブルで譜面を選択するとプレー履歴が表示されます")
        self._hist_label.setWordWrap(True)
        log_v.addWidget(self._hist_label)

        self._hist_table = QTableWidget()
        self._hist_table.setColumnCount(6)
        self._hist_table.setHorizontalHeaderLabels(
            ['日時', 'Score', 'Grade', 'EXScore', 'Lamp', 'VF'])
        self._hist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._hist_table.horizontalHeader().setStretchLastSection(True)
        self._hist_table.setSortingEnabled(True)
        self._hist_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._hist_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._hist_table.setAlternatingRowColors(True)
        self._hist_table.setMinimumHeight(140)
        self._hist_table.itemSelectionChanged.connect(
            lambda: self._del_btn.setEnabled(bool(self._hist_table.selectedItems()))
        )
        log_v.addWidget(self._hist_table)

        del_row = QHBoxLayout()
        del_row.addStretch()
        self._del_btn = QPushButton("選択プレーを削除")
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._delete_play)
        del_row.addWidget(self._del_btn)
        log_v.addLayout(del_row)

        h.addWidget(log_box, stretch=3)

        # ── portal送信済み ──
        h.addWidget(self._make_portal_panel(), stretch=2)

        # ── ライバル ──
        rival_box = QGroupBox("ライバル比較")
        rival_v = QVBoxLayout(rival_box)
        rival_v.setSpacing(4)

        self._rival_detail_label = QLabel("譜面を選択するとスコアを比較します")
        self._rival_detail_label.setWordWrap(True)
        rival_v.addWidget(self._rival_detail_label)

        self._rival_table = QTableWidget()
        self._rival_table.setColumnCount(5)
        self._rival_table.setHorizontalHeaderLabels(
            ['プレーヤー', 'Score', 'EXScore', 'Lamp', '差']
        )
        hdr = self._rival_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 5):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self._rival_table.setSortingEnabled(True)
        self._rival_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._rival_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._rival_table.setAlternatingRowColors(True)
        self._rival_table.setMinimumHeight(120)
        rival_v.addWidget(self._rival_table)

        h.addWidget(rival_box, stretch=2)

        return widget

    def _make_edit_panel(self) -> QGroupBox:
        """入力補助パネル（編集モード時に表示）"""
        box = QGroupBox("入力補助")
        h = QHBoxLayout(box)
        h.setSpacing(8)

        # ── 認識結果 ──
        rec_box = QGroupBox("認識結果")
        rec_v = QVBoxLayout(rec_box)
        rec_v.setSpacing(3)
        self._edit_title_label  = QLabel("—")
        self._edit_title_label.setWordWrap(True)
        self._edit_diff_label   = QLabel("—")
        self._edit_score_label  = QLabel("—")
        self._edit_exscore_label = QLabel("—")
        self._edit_lamp_label   = QLabel("—")
        for lbl, widget in [
            ("曲名:",     self._edit_title_label),
            ("難易度:",   self._edit_diff_label),
            ("スコア:",   self._edit_score_label),
            ("EXスコア:", self._edit_exscore_label),
            ("ランプ:",   self._edit_lamp_label),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(lbl))
            row.addWidget(widget, stretch=1)
            rec_v.addLayout(row)
        rec_v.addStretch()
        h.addWidget(rec_box, stretch=2)

        # ── 曲名選択 ──
        search_box = QGroupBox("曲名選択（認識ミス補正）")
        search_v = QVBoxLayout(search_box)
        self._edit_search_edit = QLineEdit()
        self._edit_search_edit.setPlaceholderText("曲名を検索... (空=認識タイトルを使用)")
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.timeout.connect(self._do_edit_search)
        self._edit_search_edit.textChanged.connect(
            lambda: self._search_debounce_timer.start(300)
        )
        search_v.addWidget(self._edit_search_edit)
        self._edit_candidate_list = QListWidget()
        self._edit_candidate_list.setMaximumHeight(120)
        search_v.addWidget(self._edit_candidate_list)
        h.addWidget(search_box, stretch=3)

        # ── 登録操作 ──
        op_box = QGroupBox("登録")
        op_v = QVBoxLayout(op_box)
        op_v.setSpacing(6)
        op_v.addWidget(QLabel("ランプ (補正):"))
        self._edit_lamp_combo = QComboBox()
        for lp in clear_lamp:
            self._edit_lamp_combo.addItem(str(lp), lp)
        op_v.addWidget(self._edit_lamp_combo)
        self._edit_autoregister_cb = QCheckBox("自動登録")
        op_v.addWidget(self._edit_autoregister_cb)
        self._edit_add_btn = QPushButton("追加")
        self._edit_add_btn.clicked.connect(self._on_edit_add_clicked)
        op_v.addWidget(self._edit_add_btn)
        op_v.addStretch()
        h.addWidget(op_box, stretch=1)

        return box

    def _make_portal_panel(self) -> QGroupBox:
        """portal送信済みスコアパネル"""
        box = QGroupBox("portal送信済み")
        v = QVBoxLayout(box)
        v.setSpacing(4)

        self._portal_label = QLabel("譜面を選択するとportal送信履歴が表示されます")
        self._portal_label.setWordWrap(True)
        v.addWidget(self._portal_label)

        self._portal_table = QTableWidget()
        self._portal_table.setColumnCount(5)
        self._portal_table.setHorizontalHeaderLabels(['Rev', '日時', 'Score', 'EXScore', 'Lamp'])
        hdr = self._portal_table.horizontalHeader()
        for col in range(4):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(True)
        self._portal_table.setSortingEnabled(True)
        self._portal_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._portal_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._portal_table.setAlternatingRowColors(True)
        self._portal_table.setMinimumHeight(120)
        self._portal_table.itemSelectionChanged.connect(
            lambda: self._portal_del_btn.setEnabled(bool(self._portal_table.selectedItems()))
        )
        v.addWidget(self._portal_table)

        del_row = QHBoxLayout()
        del_row.addStretch()
        self._portal_del_btn = QPushButton("選択を削除")
        self._portal_del_btn.setEnabled(False)
        self._portal_del_btn.clicked.connect(self._delete_portal_entry)
        del_row.addWidget(self._portal_del_btn)
        v.addLayout(del_row)

        return box

    # ── データ更新 ────────────────────────────────────────────────────────────

    def refresh_data(self):
        """DBからデータを再読み込みして表示を更新"""
        try:
            # portalマスタがあれば4th難易度名マップ・ティアマップを更新
            if self.portal_manager and self.portal_manager.master_db:
                self._4th_diff_map = self.portal_manager.get_4th_diff_map()
                self._tier_map     = self.portal_manager.get_tier_map()
            # 曲名リストを更新（songDBから全タイトル）
            self._all_titles = sorted(
                self.result_database.song_database._songs.keys()
            )
            self._bests = self.result_database.get_all_best_results()
            self._refresh_rival_combo()
            self._populate_score_table()
            total_vf = self.result_database.get_total_vf()
            self.statusBar().showMessage(
                f"総VF: {total_vf / 1000:.3f}  |  登録譜面数: {len(self._bests)}"
            )
        except Exception:
            logger.error(f"refresh_data エラー:\n{traceback.format_exc()}")

    def _refresh_rival_combo(self):
        """ライバルコンボボックスを最新状態に更新"""
        names = self.result_database.get_rival_names()
        current = self._rival_combo.currentText()
        self._rival_combo.blockSignals(True)
        self._rival_combo.clear()
        self._rival_combo.addItem("(比較なし)")
        self._rival_combo.addItems(names)
        idx = self._rival_combo.findText(current)
        self._rival_combo.setCurrentIndex(max(idx, 0))
        self._rival_combo.blockSignals(False)

    def _populate_score_table(self):
        """スコアテーブルにデータを投入"""
        self._score_table.setSortingEnabled(False)
        self._score_table.clearContents()
        self._score_table.setRowCount(len(self._bests))
        for row, best in enumerate(self._bests.values()):
            self._set_score_row(row, best)
        self._score_table.setSortingEnabled(True)
        self._score_table.sortByColumn(self._sort_col, self._sort_order)
        self._apply_filter()

    def _set_score_row(self, row: int, best: OneBestData):
        """スコアテーブルの1行をセット"""
        lv      = best.level or 0
        lamp    = best.best_lamp
        diff    = best.difficulty
        lamp_bg  = _LAMP_BG.get(lamp, QColor(185, 185, 185))
        row_bg   = _LAMP_ROW_BG.get(lamp, QColor(252, 252, 252))
        diff_fg  = _DIFF_FG.get(diff, QColor(50, 50, 50))

        def _mk(text, sort_val=None, align=Qt.AlignCenter) -> _SortItem:
            it = _SortItem(str(text))
            it.setTextAlignment(align)
            if sort_val is not None:
                it.setData(Qt.UserRole, sort_val)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            it.setBackground(QBrush(row_bg))
            it.setForeground(QBrush(QColor(30, 30, 30)))
            return it

        def _tier_sort(v: str):
            try:
                return float(v)
            except (ValueError, TypeError):
                return -1.0

        self._score_table.setItem(row, self._COL_LV, _mk(lv or '', lv))

        # S Tier / P Tier（portal マスタがあれば表示。数字のみ）
        s_tier, p_tier = self._tier_map.get((best.title, best.difficulty), ('', ''))
        self._score_table.setItem(row, self._COL_S_TIER, _mk(s_tier, _tier_sort(s_tier)))
        self._score_table.setItem(row, self._COL_P_TIER, _mk(p_tier, _tier_sort(p_tier)))

        self._score_table.setItem(row, self._COL_TITLE,
            _mk(best.title, align=Qt.AlignLeft | Qt.AlignVCenter))
        self._score_table.setItem(row, self._COL_SCORE, _mk(best.best_score, best.best_score))
        self._score_table.setItem(row, self._COL_GRADE, _mk(best.grade, _GRADE_ORDER.get(best.grade, -1)))
        ex = best.best_exscore if best.best_exscore is not None else ''
        self._score_table.setItem(row, self._COL_EX,    _mk(ex, best.best_exscore or 0))
        self._score_table.setItem(row, self._COL_VF,    _mk(f"{best.vf / 10:.1f}", best.vf))
        self._score_table.setItem(row, self._COL_DATE,  _mk(best.last_play_date))
        self._score_table.setItem(row, self._COL_PLAYS, _mk(best.play_count, best.play_count))

        # 難易度テキスト（4th枠はportalマスタの実際の名前を使用 MXM/INF/GRV/HVN/VVD/XCD）
        diff_label = (self._4th_diff_map.get(best.title, str(diff))
                      if diff == difficulty.maximum else str(diff))
        diff_item = _mk(diff_label)
        diff_item.setForeground(QBrush(diff_fg))
        self._score_table.setItem(row, self._COL_DIFF, diff_item)

        # ランプセル（彩度高い背景色）
        lum = (lamp_bg.red() * 299 + lamp_bg.green() * 587 + lamp_bg.blue() * 114) // 1000
        lamp_fg = QColor(20, 20, 20) if lum > 150 else QColor(255, 255, 255)
        lamp_item = _mk(str(lamp), lamp.value)
        lamp_item.setBackground(QBrush(lamp_bg))
        lamp_item.setForeground(QBrush(lamp_fg))
        self._score_table.setItem(row, self._COL_LAMP, lamp_item)

    def _on_sort_changed(self, col: int, order: Qt.SortOrder):
        """スコアテーブルのソート変更を記録する"""
        self._sort_col   = col
        self._sort_order = order

    # ── レベルフィルタ操作 ────────────────────────────────────────────────────

    def _on_lv_all_changed(self, state: int):
        """ALL チェックボックス操作 → 全レベルを一括切り替え"""
        checked = state == Qt.Checked
        for cb in self._lv_checks.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._apply_filter()

    def _on_lv_check_changed(self):
        """個別レベルチェックボックス操作 → ALL の状態を同期"""
        all_checked = all(cb.isChecked() for cb in self._lv_checks.values())
        self._lv_all_cb.blockSignals(True)
        self._lv_all_cb.setChecked(all_checked)
        self._lv_all_cb.blockSignals(False)
        self._apply_filter()

    # ── ライバル ────────────────────────────────────────────────────────────

    def _on_rival_changed(self, index: int):
        self._current_rival = self._rival_combo.currentText() if index > 0 else None
        self._update_rival_panel()
        self._apply_filter()

    def _on_rivals_loaded(self):
        """rival_manager の読み込み/フェッチ完了時に呼ばれる"""
        # 4th難易度名マップ・ティアマップを更新し、変化があった場合のみ列テキストを差し替える
        new_diff_map: dict[str, str] = {}
        new_tier_map: dict = {}
        if self.portal_manager and self.portal_manager.master_db:
            new_diff_map = self.portal_manager.get_4th_diff_map()
            new_tier_map = self.portal_manager.get_tier_map()
        if new_diff_map != self._4th_diff_map:
            self._4th_diff_map = new_diff_map
            self._update_diff_column()
        if new_tier_map != self._tier_map:
            self._tier_map = new_tier_map
            self._update_tier_columns()
        self._refresh_rival_combo()
        self._apply_filter()
        if self._selected_title:
            self._update_rival_panel(self._selected_title, self._selected_diff)

    def _update_diff_column(self):
        """4th難易度名マップ更新時にDiff列のテキストのみ差し替える（MXM枠対象）"""
        self._score_table.setSortingEnabled(False)
        try:
            for row in range(self._score_table.rowCount()):
                title_item = self._score_table.item(row, self._COL_TITLE)
                diff_item  = self._score_table.item(row, self._COL_DIFF)
                if not title_item or not diff_item:
                    continue
                diff_enum = convert_difficulty(diff_item.text())
                if diff_enum != difficulty.maximum:
                    continue  # NOV/ADV/EXH は変わらない
                new_label = self._4th_diff_map.get(title_item.text(), 'MXM')
                diff_item.setText(new_label)
        finally:
            self._score_table.setSortingEnabled(True)

    def _update_tier_columns(self):
        """ティアマップ更新時に S Tier / P Tier 列のテキストのみ差し替える"""
        def _tier_sort(v: str):
            try:
                return float(v)
            except (ValueError, TypeError):
                return -1.0
        self._score_table.setSortingEnabled(False)
        try:
            for row in range(self._score_table.rowCount()):
                title_item = self._score_table.item(row, self._COL_TITLE)
                diff_item  = self._score_table.item(row, self._COL_DIFF)
                s_item     = self._score_table.item(row, self._COL_S_TIER)
                p_item     = self._score_table.item(row, self._COL_P_TIER)
                if not (title_item and s_item and p_item and diff_item):
                    continue
                diff_enum = convert_difficulty(diff_item.text())
                s_tier, p_tier = self._tier_map.get((title_item.text(), diff_enum), ('', ''))
                s_item.setText(s_tier)
                s_item.setData(Qt.UserRole, _tier_sort(s_tier))
                p_item.setText(p_tier)
                p_item.setData(Qt.UserRole, _tier_sort(p_tier))
        finally:
            self._score_table.setSortingEnabled(True)

    def _update_rival_panel(self, title: str = None, diff_enum=None):
        """ライバルパネルを更新。選択曲がある場合は全プレーヤーのスコアを表示"""
        self._rival_table.setSortingEnabled(False)
        self._rival_table.setRowCount(0)

        if title is None:
            names = self.result_database.get_rival_names()
            self._rival_detail_label.setText(
                f"登録ライバル: {len(names)} 人  ―  譜面を選択するとスコアを比較します"
            )
            self._rival_table.setSortingEnabled(True)
            return

        diff_str = str(diff_enum) if diff_enum is not None else ''
        self._rival_detail_label.setText(f"比較: {title}  [{diff_str}]")

        # ── 自分のデータ取得 (_bests のキーは (title, difficulty) タプル) ──
        my_best    = self._bests.get((title, diff_enum)) if diff_enum else None
        my_score   = my_best.best_score   if my_best else 0
        my_exscore = my_best.best_exscore if my_best else None
        my_lamp    = my_best.best_lamp    if my_best else clear_lamp.noplay

        # ── エントリー収集: (name, score, exscore, lamp, is_self) ──
        # is_self=True の行は自分
        rows: list[tuple[str, int, int | None, clear_lamp, bool]] = []
        rows.append(('★自分', my_score, my_exscore, my_lamp, True))

        if self.rival_manager is not None and diff_str:
            fetched = self.rival_manager.get_all_scores(title, diff_str)
            fetched_names = {n for n, _ in fetched}
            for name, entry in fetched:
                rows.append((name, entry.score, entry.exscore, entry.lamp, False))
            for rd in self.rival_manager.rivals:
                if rd.name not in fetched_names:
                    rows.append((rd.name, 0, None, clear_lamp.noplay, False))
        else:
            for name in self.result_database.get_rival_names():
                s, _, lp = self.result_database.get_rival_best(
                    name=name, title=title, diff=diff_enum
                )
                rows.append((name, s or 0, None, lp, False))

        # ── テーブル描画 ──
        def _mk(text, sort_val=None) -> QTableWidgetItem:
            it = _SortItem(str(text))
            it.setTextAlignment(Qt.AlignCenter)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if sort_val is not None:
                it.setData(Qt.UserRole, sort_val)
            return it

        for name, score, exscore, lamp, is_self in rows:
            row = self._rival_table.rowCount()
            self._rival_table.insertRow(row)

            name_item = _mk(name)
            if is_self:
                name_item.setForeground(QBrush(QColor(0, 80, 200)))
            self._rival_table.setItem(row, 0, name_item)

            self._rival_table.setItem(row, 1, _mk(score, score))
            ex_text = exscore if exscore is not None else '―'
            self._rival_table.setItem(row, 2, _mk(ex_text, exscore if exscore is not None else -1))

            lamp_bg = _LAMP_BG.get(lamp, QColor(185, 185, 185))
            lum = (lamp_bg.red() * 299 + lamp_bg.green() * 587 + lamp_bg.blue() * 114) // 1000
            lamp_item = _mk(str(lamp), lamp.value)
            lamp_item.setBackground(QBrush(lamp_bg))
            lamp_item.setForeground(QBrush(
                QColor(20, 20, 20) if lum > 150 else QColor(255, 255, 255)
            ))
            self._rival_table.setItem(row, 3, lamp_item)

            if is_self:
                self._rival_table.setItem(row, 4, _mk('—', 0))
            else:
                diff_val  = my_score - score
                diff_text = f'+{diff_val}' if diff_val >= 0 else str(diff_val)
                diff_item = _mk(diff_text, diff_val)
                diff_item.setForeground(QBrush(
                    QColor(0, 150, 0) if diff_val >= 0 else QColor(190, 0, 0)
                ))
                self._rival_table.setItem(row, 4, diff_item)

        self._rival_table.setSortingEnabled(True)
        self._rival_table.sortByColumn(1, Qt.DescendingOrder)  # Score降順

    # ── フィルター ────────────────────────────────────────────────────────────

    def _apply_filter(self):
        """フィルター条件で行を表示/非表示"""
        enabled_diffs = {d for d, cb in self._diff_checks.items() if cb.isChecked()}
        enabled_lvs   = {lv for lv, cb in self._lv_checks.items() if cb.isChecked()}
        all_lv        = len(enabled_lvs) == len(self._lv_checks)
        search        = self._search_edit.text().lower()

        # ライバルフィルター: 自分が勝っている行を非表示にする
        rival_scores: dict = {}
        if self._current_rival and self.rival_manager:
            for rd in self.rival_manager.rivals:
                if rd.name == self._current_rival:
                    rival_scores = rd.scores
                    break

        visible = 0
        win_count = loss_count = draw_count = 0
        for row in range(self._score_table.rowCount()):
            diff_item  = self._score_table.item(row, self._COL_DIFF)
            lv_item    = self._score_table.item(row, self._COL_LV)
            title_item = self._score_table.item(row, self._COL_TITLE)
            if not (diff_item and lv_item and title_item):
                continue
            diff_str  = diff_item.text()
            # INF/GRV/HVN/VVD/XCD など4th枠の実名表示にも対応
            diff_enum = convert_difficulty(diff_str)
            lv        = lv_item.data(Qt.UserRole) or 0
            # lv==0 はレベル不明。全レベル選択時のみ表示する
            lv_hidden    = (lv == 0 and not all_lv) or (lv != 0 and lv not in enabled_lvs)
            search_hidden = bool(search) and search not in title_item.text().lower()
            # ライバルフィルター: 勝っている曲（自スコア > ライバルスコア）を非表示
            if rival_scores:
                s_item   = self._score_table.item(row, self._COL_SCORE)
                my_score = (s_item.data(Qt.UserRole) or 0) if s_item else 0
                # rival_scores のキーは "MXM" に正規化済みなので変換して照合
                norm_diff = str(diff_enum) if diff_enum else diff_str
                entry    = rival_scores.get((title_item.text(), norm_diff))
                r_score  = entry.score if entry else 0
                rival_hidden = my_score > r_score
                # diff/lv/search フィルターを通過した行のみ勝敗カウント
                if not (diff_enum not in enabled_diffs or lv_hidden or search_hidden):
                    if my_score > r_score:
                        win_count += 1
                    elif my_score < r_score:
                        loss_count += 1
                    else:
                        draw_count += 1
            else:
                rival_hidden = False
            hide = bool(diff_enum not in enabled_diffs or lv_hidden or search_hidden or rival_hidden)
            self._score_table.setRowHidden(row, hide)
            if not hide:
                visible += 1

        self._win_loss_bar.set_data(win_count, loss_count, draw_count)
        self.statusBar().showMessage(
            f"表示: {visible} 件  |  総VF: {self.result_database.get_total_vf() / 1000:.3f}"
        )

    # ── プレー履歴 ────────────────────────────────────────────────────────────

    def _on_score_selected(self):
        sel = self._score_table.selectedItems()
        if not sel:
            return
        row      = self._score_table.row(sel[0])
        t_item   = self._score_table.item(row, self._COL_TITLE)
        d_item   = self._score_table.item(row, self._COL_DIFF)
        s_item   = self._score_table.item(row, self._COL_SCORE)
        if not t_item or not d_item:
            return
        title     = t_item.text()
        diff_str  = d_item.text()
        diff_enum = convert_difficulty(diff_str)  # INF/GRV/HVN/VVD/XCD → difficulty.maximum
        my_score  = s_item.data(Qt.UserRole) if s_item else None

        self._selected_title = title
        self._selected_diff  = diff_enum
        self._selected_score = my_score
        self._hist_label.setText(f"プレー履歴: {title}  [{diff_str}]")
        self._show_history(title, diff_enum)
        self._show_portal_uploads(title, diff_enum)
        self._update_rival_panel(title, diff_enum)

    def _show_history(self, title: str, diff: Optional[difficulty]):
        """プレーログテーブルを更新"""
        results = self.result_database.search(title=title, diff=diff)
        target  = [r for r in results
                   if r.detect_mode not in (detect_mode.play, detect_mode.detect, detect_mode.init)]

        self._history_map.clear()
        self._hist_table.setSortingEnabled(False)
        self._hist_table.clearContents()
        self._hist_table.setRowCount(len(target))

        for row, r in enumerate(reversed(target)):
            self._history_map[row] = r
            ts      = datetime.datetime.fromtimestamp(r.timestamp).strftime('%Y-%m-%d %H:%M')
            lamp_bg = _LAMP_BG.get(r.lamp, QColor(185, 185, 185))
            lum     = (lamp_bg.red() * 299 + lamp_bg.green() * 587
                       + lamp_bg.blue() * 114) // 1000
            lamp_fg = QColor(20, 20, 20) if lum > 150 else QColor(255, 255, 255)

            def _mk(text, sort_val=None) -> _SortItem:
                it = _SortItem(str(text))
                it.setTextAlignment(Qt.AlignCenter)
                if sort_val is not None:
                    it.setData(Qt.UserRole, sort_val)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                return it

            self._hist_table.setItem(row, 0, _mk(ts, r.timestamp))
            self._hist_table.setItem(row, 1, _mk(r.score   or '', r.score   or 0))
            self._hist_table.setItem(row, 2, _mk(r.grade, _GRADE_ORDER.get(r.grade, -1)))
            self._hist_table.setItem(row, 3, _mk(r.exscore or '', r.exscore or 0))
            lamp_item = _mk(str(r.lamp), r.lamp.value)
            lamp_item.setBackground(QBrush(lamp_bg))
            lamp_item.setForeground(QBrush(lamp_fg))
            self._hist_table.setItem(row, 4, lamp_item)
            self._hist_table.setItem(row, 5, _mk(f"{r.vf / 10:.1f}", r.vf))

        self._hist_table.setSortingEnabled(True)
        self._hist_table.sortByColumn(1, Qt.DescendingOrder)  # Score降順
        self._del_btn.setEnabled(False)

    def _show_portal_uploads(self, title: str, diff_enum):
        """portal送信済みテーブルを更新"""
        self._portal_table.setSortingEnabled(False)
        self._portal_table.clearContents()
        self._portal_table.setRowCount(0)

        if not self.portal_manager or not self.portal_manager.master_db:
            self._portal_label.setText(
                'portal マスタ未受信のため表示できません' if self.portal_manager
                else 'portal連携が無効です'
            )
            return

        entries = self.portal_manager.get_uploaded_scores(title, diff_enum)
        diff_str = str(diff_enum) if diff_enum else ''
        self._portal_label.setText(
            f"portal送信履歴: {title}  [{diff_str}]  ({len(entries)} 件)"
        )

        def _mk(text, sort_val=None) -> _SortItem:
            it = _SortItem(str(text))
            it.setTextAlignment(Qt.AlignCenter)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if sort_val is not None:
                it.setData(Qt.UserRole, sort_val)
            return it

        for entry in entries:
            row = self._portal_table.rowCount()
            self._portal_table.insertRow(row)

            # Rev列 — エントリ参照を UserRole+1 に格納（ソート後も正しく参照できる）
            rev_item = _mk(entry.revision, entry.revision)
            rev_item.setData(Qt.UserRole + 1, entry)
            self._portal_table.setItem(row, 0, rev_item)

            uploaded_at = getattr(entry, 'uploaded_at', None)
            date_str  = uploaded_at.strftime('%Y-%m-%d %H:%M') if uploaded_at else '—'
            date_sort = uploaded_at.timestamp() if uploaded_at else 0
            self._portal_table.setItem(row, 1, _mk(date_str, date_sort))

            self._portal_table.setItem(row, 2, _mk(entry.score or '', entry.score or 0))
            ex = entry.exscore if entry.exscore is not None else '—'
            self._portal_table.setItem(row, 3, _mk(ex, entry.exscore if entry.exscore is not None else -1))

            lamp     = convert_lamp(entry.lamp or '')
            lamp_bg  = _LAMP_BG.get(lamp, QColor(185, 185, 185))
            lum      = (lamp_bg.red() * 299 + lamp_bg.green() * 587 + lamp_bg.blue() * 114) // 1000
            lamp_item = _mk(entry.lamp or '', lamp.value)
            lamp_item.setBackground(QBrush(lamp_bg))
            lamp_item.setForeground(QBrush(QColor(20, 20, 20) if lum > 150 else QColor(255, 255, 255)))
            self._portal_table.setItem(row, 4, lamp_item)

        self._portal_table.setSortingEnabled(True)
        self._portal_table.sortByColumn(0, Qt.DescendingOrder)  # Rev降順（最新が上）
        self._portal_del_btn.setEnabled(False)

    def _delete_portal_entry(self):
        """選択したportal送信済みエントリを削除（バックグラウンドスレッドで通信）"""
        sel = self._portal_table.selectedItems()
        if not sel:
            return
        row      = self._portal_table.row(sel[0])
        rev_item = self._portal_table.item(row, 0)
        entry    = rev_item.data(Qt.UserRole + 1) if rev_item else None
        if entry is None:
            return

        reply = QMessageBox.question(
            self, '確認',
            f'portal上のこのスコアを削除しますか？\n'
            f'Rev.{entry.revision}  {entry.music_id}  {entry.difficulty}\n'
            f'Score: {entry.score}  Lamp: {entry.lamp}',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # revision == -1 はリビジョン未記録のエントリ: API コールなしでローカルのみ削除
        if entry.revision == -1:
            mng = self.portal_manager._get_mng()
            mng.delete(entry.revision, entry.music_id, entry.difficulty)
            mng.save()
            self._show_portal_uploads(self._selected_title, self._selected_diff)
            return

        if not self.portal_manager or not self.portal_manager.token:
            QMessageBox.warning(self, 'エラー', 'portal トークンが未設定です')
            return

        # 通信中は削除ボタンを無効化してフリーズを防ぐ
        self._pending_delete_entry = entry
        self._portal_del_btn.setEnabled(False)
        self._portal_del_btn.setText("削除中...")

        # ワーカーを main thread に置いたまま Python スレッドで非同期実行
        self._delete_worker = _PortalDeleteWorker(self)
        self._delete_worker.done.connect(self._on_portal_delete_result)
        self._delete_worker.start(
            self.portal_manager, entry.revision, entry.music_id, entry.difficulty
        )

    def _on_portal_delete_result(self, res):
        """portal削除スレッド完了時のコールバック（メインスレッドで呼ばれる）"""
        self._delete_worker = None  # ワーカー参照解放
        self._portal_del_btn.setText("選択を削除")
        entry = self._pending_delete_entry
        self._pending_delete_entry = None

        # ローカルからは常に削除済みなのでテーブルを再描画
        self._show_portal_uploads(self._selected_title, self._selected_diff)

        if res is None:
            QMessageBox.warning(self, '警告',
                f'portal との通信に失敗しました。\nローカルの記録は削除しました。')
        elif res.status_code != 200:
            QMessageBox.warning(self, '警告',
                f'portal エラー: {res.status_code}\nローカルの記録は削除しました。\n{res.text[:200]}')
        # 選択状態に応じてボタン有効化
        self._portal_del_btn.setEnabled(bool(self._portal_table.selectedItems()))

    # ── 編集パネル ────────────────────────────────────────────────────────────

    def _on_edit_mode_toggled(self, state: int):
        self._edit_panel.setVisible(self._edit_mode_cb.isChecked())

    def update_select_data(
        self,
        title: str,
        diff: Optional[difficulty],
        score: Optional[int],
        exscore: Optional[int],
        lamp: Optional[clear_lamp],
    ):
        """メインウィンドウから選曲画面の認識データを受け取り、編集パネルを更新する。
        編集モードが OFF の場合は何もしない。
        """
        if not self._edit_mode_cb.isChecked():
            return

        new_data = {'title': title, 'diff': diff,
                    'score': score, 'exscore': exscore, 'lamp': lamp}
        if new_data == self._edit_data:
            return  # 変化なし: 10Hz 連呼による無駄な UI 更新を防ぐ

        prev_title = self._edit_data.get('title')
        self._edit_data = new_data

        # 認識結果ラベルを更新
        self._edit_title_label.setText(title or '(未認識)')
        self._edit_diff_label.setText(str(diff) if diff is not None else '—')
        self._edit_score_label.setText(str(score) if score is not None else '—')
        self._edit_exscore_label.setText(str(exscore) if exscore is not None else '—')
        self._edit_lamp_label.setText(str(lamp) if lamp is not None else '—')

        # 曲が変わった場合: 検索ボックスをリセットして新タイトルで自動補完
        # (ユーザーが手動入力した場合はリセットしない)
        if title:
            cur_search = self._edit_search_edit.text()
            if not cur_search or cur_search == self._edit_autofill_title:
                # 空または前回の自動補完テキストなら上書き
                self._edit_autofill_title = title
                self._edit_search_edit.setText(title)

        # ランプコンボを認識ランプに合わせる
        if lamp is not None:
            idx = self._edit_lamp_combo.findData(lamp)
            if idx >= 0:
                self._edit_lamp_combo.setCurrentIndex(idx)

        # 自動登録チェック
        if self._edit_autoregister_cb.isChecked():
            self._try_auto_register()

    def _do_edit_search(self):
        """曲名検索ボックスの内容で候補リストを絞り込む（デバウンス後に実行）"""
        text = self._edit_search_edit.text()
        self._edit_candidate_list.clear()
        if not text:
            return
        lower = text.lower()
        matches = [t for t in self._all_titles if lower in t.lower()]
        # 前方一致を上に
        matches.sort(key=lambda t: (0 if t.lower().startswith(lower) else 1, t))
        for t in matches[:60]:
            self._edit_candidate_list.addItem(t)

    def _get_effective_title(self) -> str:
        """選択リストで選ばれた曲名、なければ認識タイトルを返す"""
        sel = self._edit_candidate_list.selectedItems()
        if sel:
            return sel[0].text()
        return self._edit_data.get('title') or ''

    def _try_auto_register(self):
        """自動登録を試みる（同一データの重複登録は防ぐ）"""
        data  = self._edit_data
        title = self._get_effective_title()
        diff  = data.get('diff')
        score = data.get('score')
        lamp  = self._edit_lamp_combo.currentData()

        if not title or diff is None or score is None:
            return
        if lamp is None or lamp == clear_lamp.noplay:
            return

        key = (title, diff, score, lamp)
        if key == self._last_auto_registered:
            return

        added = self._do_register(title, diff, score, data.get('exscore'), lamp, auto=True)
        if added:
            self._last_auto_registered = key

    def _on_edit_add_clicked(self):
        """追加ボタンがクリックされたとき"""
        data  = self._edit_data
        title = self._get_effective_title()
        diff  = data.get('diff')
        score = data.get('score')
        exscore = data.get('exscore')
        lamp  = self._edit_lamp_combo.currentData()

        if not title:
            QMessageBox.warning(self, "エラー", "曲名が設定されていません")
            return
        if diff is None:
            QMessageBox.warning(self, "エラー", "難易度が認識されていません")
            return
        if score is None:
            QMessageBox.warning(self, "エラー", "スコアが認識されていません")
            return

        added = self._do_register(title, diff, score, exscore, lamp)
        if not added:
            QMessageBox.information(self, "情報",
                "スコアに更新がなかったため登録をスキップしました\n"
                "（現在の自己ベスト以下のスコア・ランプ）")

    def _do_register(
        self,
        title: str,
        diff: difficulty,
        score: int,
        exscore: Optional[int],
        lamp: clear_lamp,
        auto: bool = False,
    ) -> bool:
        """result_database に1件登録して保存・テーブル更新する。"""
        info  = self.result_database.song_database.get_song_info(title)
        level = info.get_level(diff) if info else None
        result = OneResult(
            title=title,
            difficulty=diff,
            lamp=lamp,
            score=score,
            exscore=exscore,
            level=level,
            detect_mode=detect_mode.select,
        )
        added = self.result_database.add(result)
        if added:
            self.result_database.save()
            self.refresh_data()
            prefix = "自動登録" if auto else "登録"
            self.statusBar().showMessage(
                f"{prefix}完了: {title} [{diff}] score:{score} lamp:{lamp}"
            )
        return added

    def _delete_play(self):
        """選択プレーを削除"""
        sel = self._hist_table.selectedItems()
        if not sel:
            return
        row    = self._hist_table.row(sel[0])
        result = self._history_map.get(row)
        if result is None:
            return
        reply = QMessageBox.question(
            self, "確認",
            f"このプレーを削除しますか？\n{result}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.result_database.results.remove(result)
                self.result_database.save()
                # 削除前に選択曲を保存しておき、refresh 後に復元する
                title_to_restore    = self._selected_title
                diff_to_restore     = self._selected_diff
                self.refresh_data()
                if title_to_restore is not None:
                    self._reselect_song(title_to_restore, diff_to_restore)
            except ValueError:
                QMessageBox.warning(self, "エラー", "削除に失敗しました")

    def _reselect_song(self, title: str, diff_enum):
        """refresh_data 後にスコアテーブルで同じ曲を再選択し履歴を再表示する"""
        for row in range(self._score_table.rowCount()):
            if self._score_table.isRowHidden(row):
                continue
            t = self._score_table.item(row, self._COL_TITLE)
            d = self._score_table.item(row, self._COL_DIFF)
            if t and d and t.text() == title and convert_difficulty(d.text()) == diff_enum:
                self._score_table.selectRow(row)
                # selectRow が itemSelectionChanged を発火するので履歴更新は自動的に行われる
                return
        # フィルタで非表示になった等で見つからない場合でも履歴だけ再表示
        self._show_history(title, diff_enum)

    # ── フィルター状態の保存・復元 ────────────────────────────────────────────

    def _save_filter_state(self):
        """難易度・レベルのチェック状態とソート状態を Config に書き込む"""
        self.config.score_viewer_diff_checks = [
            str(d) for d, cb in self._diff_checks.items() if cb.isChecked()
        ]
        self.config.score_viewer_lv_checks = [
            lv for lv, cb in self._lv_checks.items() if cb.isChecked()
        ]
        self.config.score_viewer_sort_column = self._sort_col
        self.config.score_viewer_sort_order  = self._sort_order.value

    def _restore_filter_state(self):
        """Config からチェック状態とソート状態を復元する（_init_ui() の後に呼ぶ）"""
        saved_diffs = self.config.score_viewer_diff_checks
        if saved_diffs:
            for d, cb in self._diff_checks.items():
                cb.blockSignals(True)
                cb.setChecked(str(d) in saved_diffs)
                cb.blockSignals(False)

        saved_lvs = set(self.config.score_viewer_lv_checks)
        if saved_lvs:
            for lv, cb in self._lv_checks.items():
                cb.blockSignals(True)
                cb.setChecked(lv in saved_lvs)
                cb.blockSignals(False)
            all_checked = all(cb.isChecked() for cb in self._lv_checks.values())
            self._lv_all_cb.blockSignals(True)
            self._lv_all_cb.setChecked(all_checked)
            self._lv_all_cb.blockSignals(False)

        # ソート状態を復元
        self._sort_col   = self.config.score_viewer_sort_column
        self._sort_order = Qt.SortOrder(self.config.score_viewer_sort_order)

    # ── ウィンドウ管理 ────────────────────────────────────────────────────────

    def _restore_geometry(self):
        import base64
        geom = getattr(self.config, 'score_viewer_geometry', None)
        if geom:
            try:
                self.restoreGeometry(QByteArray(base64.b64decode(geom)))
                return
            except Exception:
                pass
        self.setGeometry(150, 150, 1200, 720)

    def closeEvent(self, event):
        import base64
        self.config.score_viewer_geometry = base64.b64encode(
            self.saveGeometry().data()
        ).decode('ascii')
        self._save_filter_state()
        self.config.save_config()
        event.accept()
