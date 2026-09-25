"""SDVX musiclist editor.

resources/musiclist.pkl と resources/musiclistv2.sdvxh を編集するための GUI ツール。

起動:
    uv run -m misc.database_editor
"""
from __future__ import annotations

import bz2
import pickle
import sys
import unicodedata
from copy import deepcopy
from pathlib import Path

import imagehash
from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.classes import detect_mode
from src.config import Config
from src.define import RECT_INFO_JACKET, RECT_RESULT_JACKET, RECT_SELECT_JACKET
from src.portal_manager import PortalManager
from src.result_image import RESULT_INFO_CROP_SIZE, expand_result_info_area
from src.screen_reader import ScreenReader


MUSICLIST_V1 = Path("resources") / "musiclist.pkl"
MUSICLIST_V2 = Path("resources") / "musiclistv2.sdvxh"

DIFFS = [
    ("nov", "NOV", 3),
    ("adv", "ADV", 4),
    ("exh", "EXH", 5),
    ("APPEND", "APPEND", 6),
]
DIFF_BY_DB_KEY = {db_key: label for db_key, label, _idx in DIFFS}
GRADE_LEVELS = (17, 18, 19)


class _HashImportSongDb:
    def identify_jacket(self, _jacket_img, _diff):
        return None


class SaveWorker(QThread):
    finished_with_results = Signal(list)

    def __init__(self, jobs: list[tuple[str, Path, dict, int]], parent=None):
        super().__init__(parent)
        self._jobs = jobs

    def run(self):
        results = []
        for key, path, data, revision in self._jobs:
            error = ""
            try:
                save_musiclist(data, path)
            except Exception as exc:
                error = str(exc)
            results.append((key, str(path), error, revision))
        self.finished_with_results.emit(results)


def normalize_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text)).lower()
    chars = []
    for ch in normalized:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        else:
            chars.append(ch)
    return "".join(chars)


def load_pkl(path: Path) -> dict:
    with open(path, "rb") as f:
        return pickle.load(f)


def save_pkl(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "wb") as f:
        pickle.dump(data, f)
    tmp_path.replace(path)


def load_sdvxh(path: Path) -> dict:
    with bz2.open(path, "rb") as f:
        return pickle.load(f)


def save_sdvxh(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with bz2.open(tmp_path, "wb") as f:
        pickle.dump(data, f)
    tmp_path.replace(path)


def load_musiclist(path: Path) -> dict:
    if path.suffix == ".sdvxh":
        return load_sdvxh(path)
    return load_pkl(path)


def save_musiclist(data: dict, path: Path) -> None:
    if path.suffix == ".sdvxh":
        save_sdvxh(data, path)
    else:
        save_pkl(data, path)


def ensure_title_row(row: list) -> list:
    row = list(row)
    while len(row) < 7:
        row.append(0 if len(row) >= 3 else "")
    return row


def row_level(row: list, idx: int) -> int:
    try:
        return int(row[idx] or 0)
    except (TypeError, ValueError):
        return 0


def grade_value(data: dict, level: int, title: str) -> str:
    return str(data.get(f"gradeS_lv{level}", {}).get(title, ""))


def set_grade_value(data: dict, level: int, title: str, enabled: bool) -> None:
    key = f"gradeS_lv{level}"
    grades = data.setdefault(key, {})
    if enabled:
        grades[title] = "1"
    else:
        grades.pop(title, None)


def portal_chart_levels(portal_entry: dict) -> dict[str, int]:
    levels = {"nov": 0, "adv": 0, "exh": 0, "APPEND": 0}
    for chart in portal_entry.get("charts", []) or []:
        diff_name = str(chart.get("difficulty") or "")
        db_key = {"NOV": "nov", "ADV": "adv", "EXH": "exh"}.get(diff_name, "APPEND")
        try:
            level = int(chart.get("level") or 0)
        except (TypeError, ValueError):
            level = 0
        if level:
            levels[db_key] = max(levels[db_key], level)
    return levels


def portal_entry_to_title_row(portal_entry: dict) -> list:
    title = str(portal_entry.get("title") or "")
    levels = portal_chart_levels(portal_entry)
    return [
        title,
        str(portal_entry.get("artist") or ""),
        "",
        levels["nov"],
        levels["adv"],
        levels["exh"],
        levels["APPEND"],
    ]


class FilterPanel(QGroupBox):
    filter_changed = Signal()

    def __init__(self, parent=None):
        super().__init__("フィルタ", parent)
        layout = QVBoxLayout(self)

        self.rb_v2 = QRadioButton("v2 (musiclistv2.sdvxh)")
        self.rb_v1 = QRadioButton("v1 (musiclist.pkl)")
        self.rb_v2.setChecked(True)
        layout.addWidget(self.rb_v2)
        layout.addWidget(self.rb_v1)

        self.cb_diff = QComboBox()
        self.cb_diff.addItem("ALL")
        for _key, label, _idx in DIFFS:
            self.cb_diff.addItem(label)
        layout.addWidget(QLabel("難易度"))
        layout.addWidget(self.cb_diff)

        self.cb_level = QComboBox()
        self.cb_level.addItem("ALL")
        for lv in range(1, 21):
            self.cb_level.addItem(str(lv))
        layout.addWidget(QLabel("レベル"))
        layout.addWidget(self.cb_level)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("曲名 / アーティストで検索")
        layout.addWidget(QLabel("検索"))
        layout.addWidget(self.search_edit)

        layout.addStretch()

        self.rb_v1.toggled.connect(self.filter_changed)
        self.rb_v2.toggled.connect(self.filter_changed)
        self.cb_diff.currentIndexChanged.connect(self.filter_changed)
        self.cb_level.currentIndexChanged.connect(self.filter_changed)
        self.search_edit.textChanged.connect(self.filter_changed)

    def target_key(self) -> str:
        return "v2" if self.rb_v2.isChecked() else "v1"

    def diff_filter(self) -> str | None:
        text = self.cb_diff.currentText()
        return None if text == "ALL" else text

    def level_filter(self) -> int | None:
        text = self.cb_level.currentText()
        return None if text == "ALL" else int(text)

    def search_text(self) -> str:
        return normalize_search_text(self.search_edit.text().strip())


class SongEditPanel(QGroupBox):
    saved = Signal(str)

    def __init__(self, parent=None):
        super().__init__("編集", parent)
        self._data: dict | None = None
        self._title: str | None = None
        self._loading = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.title_label = QLabel("(未選択)")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.title_label)

        form_box = QGroupBox("基本情報")
        form = QFormLayout(form_box)
        self.title_edit = QLineEdit()
        self.artist_edit = QLineEdit()
        self.bpm_edit = QLineEdit()
        self.title_v1_edit = QLineEdit()
        form.addRow("曲名:", self.title_edit)
        form.addRow("アーティスト:", self.artist_edit)
        form.addRow("BPM:", self.bpm_edit)
        form.addRow("v1曲名:", self.title_v1_edit)
        layout.addWidget(form_box)

        levels_box = QGroupBox("レベル")
        levels = QGridLayout(levels_box)
        self.level_spins: dict[str, QSpinBox] = {}
        for col, (db_key, label, _idx) in enumerate(DIFFS):
            levels.addWidget(QLabel(label), 0, col)
            spin = QSpinBox()
            spin.setRange(0, 20)
            spin.setSpecialValueText("-")
            self.level_spins[db_key] = spin
            levels.addWidget(spin, 1, col)
        layout.addWidget(levels_box)

        hash_box = QGroupBox("hash")
        hash_grid = QGridLayout(hash_box)
        hash_grid.addWidget(QLabel("難易度"), 0, 0)
        hash_grid.addWidget(QLabel("jacket"), 0, 1)
        hash_grid.addWidget(QLabel("info"), 0, 2)
        self.jacket_edits: dict[str, QLineEdit] = {}
        self.info_edits: dict[str, QLineEdit] = {}
        for row, (db_key, label, _idx) in enumerate(DIFFS, start=1):
            hash_grid.addWidget(QLabel(label), row, 0)
            jacket = QLineEdit()
            info = QLineEdit()
            self.jacket_edits[db_key] = jacket
            self.info_edits[db_key] = info
            hash_grid.addWidget(jacket, row, 1)
            hash_grid.addWidget(info, row, 2)

        import_row = len(DIFFS) + 1
        self.hash_target_combo = QComboBox()
        self.hash_target_combo.addItem("自動判定", "auto")
        for db_key, label, _idx in DIFFS:
            self.hash_target_combo.addItem(label, db_key)
        self.import_hash_btn = QPushButton("画像からjacket hashを取得")
        self.import_hash_btn.clicked.connect(self._import_jacket_hash_from_image)
        self.hash_import_status = QLabel("")
        self.hash_import_status.setWordWrap(True)
        hash_grid.addWidget(QLabel("取込先"), import_row, 0)
        hash_grid.addWidget(self.hash_target_combo, import_row, 1)
        hash_grid.addWidget(self.import_hash_btn, import_row, 2)
        hash_grid.addWidget(self.hash_import_status, import_row + 1, 0, 1, 3)
        layout.addWidget(hash_box)

        grade_box = QGroupBox("Grade S 対象")
        grade_layout = QHBoxLayout(grade_box)
        self.grade_checks: dict[int, QCheckBox] = {}
        for lv in GRADE_LEVELS:
            cb = QCheckBox(f"Lv{lv}")
            self.grade_checks[lv] = cb
            grade_layout.addWidget(cb)
        grade_layout.addStretch()
        layout.addWidget(grade_box)

        buttons = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.reload_btn = QPushButton("再読み込み")
        self.save_btn.clicked.connect(self._save)
        self.reload_btn.clicked.connect(self._reload_current)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.reload_btn)
        layout.addLayout(buttons)
        layout.addStretch()

        self._set_enabled(False)

    def _set_enabled(self, enabled: bool):
        for widget in (
            self.title_edit,
            self.artist_edit,
            self.bpm_edit,
            self.title_v1_edit,
            self.save_btn,
            self.reload_btn,
            self.hash_target_combo,
            self.import_hash_btn,
        ):
            widget.setEnabled(enabled)
        for widget in list(self.level_spins.values()) + list(self.jacket_edits.values()) + list(self.info_edits.values()):
            widget.setEnabled(enabled)
        for widget in self.grade_checks.values():
            widget.setEnabled(enabled)

    def set_database(self, data: dict):
        self._data = data
        self.set_title(self._title)

    def set_title(self, title: str | None):
        self._title = title
        self._load_title()

    def _load_title(self):
        self._loading = True
        try:
            if not self._data or not self._title:
                self.title_label.setText("(未選択)")
                self._clear()
                self._set_enabled(False)
                return

            row = self._data.get("titles", {}).get(self._title)
            if not row:
                self.title_label.setText("(未選択)")
                self._clear()
                self._set_enabled(False)
                return

            row = ensure_title_row(row)
            self.title_label.setText(self._title)
            self.title_edit.setText(str(row[0] or self._title))
            self.artist_edit.setText(str(row[1] or ""))
            self.bpm_edit.setText(str(row[2] or ""))
            self.title_v1_edit.setText(str(row[7] or "") if len(row) > 7 else "")

            for db_key, _label, idx in DIFFS:
                self.level_spins[db_key].setValue(row_level(row, idx))
                self.jacket_edits[db_key].setText(str(self._data.get("jacket", {}).get(db_key, {}).get(self._title, "") or ""))
                self.info_edits[db_key].setText(str(self._data.get("info", {}).get(db_key, {}).get(self._title, "") or ""))

            for lv, cb in self.grade_checks.items():
                cb.setChecked(grade_value(self._data, lv, self._title) == "1")
            self._set_enabled(True)
        finally:
            self._loading = False

    def _clear(self):
        for edit in (self.title_edit, self.artist_edit, self.bpm_edit, self.title_v1_edit):
            edit.clear()
        for spin in self.level_spins.values():
            spin.setValue(0)
        for edit in list(self.jacket_edits.values()) + list(self.info_edits.values()):
            edit.clear()
        for cb in self.grade_checks.values():
            cb.setChecked(False)

    def _reload_current(self):
        self._load_title()

    def _import_jacket_hash_from_image(self):
        if not self._data or not self._title:
            return

        path, _filter = QFileDialog.getOpenFileName(
            self,
            "jacket hashを取得する画像を選択",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not path:
            return

        try:
            hash_hex, db_key, scene_label = self._calculate_jacket_hash_from_image(Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "画像取込失敗", str(exc))
            return

        self.jacket_edits[db_key].setText(hash_hex)
        diff_label = DIFF_BY_DB_KEY.get(db_key, db_key)
        self.hash_import_status.setText(
            f"{scene_label}: {diff_label} jacket hash = {hash_hex}"
        )

    def _calculate_jacket_hash_from_image(self, path: Path) -> tuple[str, str, str]:
        with Image.open(path) as loaded:
            img = loaded.copy()

        if img.size == RESULT_INFO_CROP_SIZE:
            img = expand_result_info_area(img)

        reader = ScreenReader(_HashImportSongDb())
        reader.update_screen(img)
        mode = reader.detect_screen()
        screen = reader.corrected_screen
        if screen is None:
            raise ValueError("画像の補正に失敗しました。")

        if mode == detect_mode.select:
            diff = reader._read_difficulty_from_select(screen)
            jacket_img = screen.crop(RECT_SELECT_JACKET)
            scene_label = "選曲画面"
        elif mode == detect_mode.detect:
            diff = reader._read_difficulty_from_detect(screen)
            jacket_img = screen.crop(RECT_INFO_JACKET)
            scene_label = "楽曲情報画面"
        elif mode.is_result_screen():
            diff = reader._read_difficulty_from_result(screen)
            jacket_img = screen.crop(RECT_RESULT_JACKET)
            scene_label = "リザルト画面"
        else:
            raise ValueError("選曲画面・楽曲情報画面・リザルト画面として判定できませんでした。")

        target_key = self.hash_target_combo.currentData()
        if target_key == "auto":
            if diff is None:
                raise ValueError("譜面を自動判定できませんでした。取込先を手動で選んでください。")
            target_key = diff.to_db_key()

        if target_key not in self.jacket_edits:
            raise ValueError(f"取込先譜面が不正です: {target_key}")

        hash_hex = str(imagehash.average_hash(jacket_img))
        return hash_hex, target_key, scene_label

    def _save(self):
        if not self._data or not self._title:
            return

        old_title = self._title
        new_title = self.title_edit.text().strip()
        if not new_title:
            QMessageBox.warning(self, "保存できません", "曲名は空にできません。")
            return
        if new_title != old_title and new_title in self._data.get("titles", {}):
            QMessageBox.warning(self, "保存できません", f"既に同名の曲があります:\n{new_title}")
            return

        titles = self._data.setdefault("titles", {})
        row = ensure_title_row(titles.get(old_title, [old_title, "", "", 0, 0, 0, 0]))
        row[0] = new_title
        row[1] = self.artist_edit.text().strip()
        row[2] = self.bpm_edit.text().strip()
        for db_key, _label, idx in DIFFS:
            row[idx] = int(self.level_spins[db_key].value())

        title_v1 = self.title_v1_edit.text().strip()
        if title_v1:
            while len(row) <= 7:
                row.append("")
            row[7] = title_v1
        elif len(row) > 7:
            row[7] = ""

        if new_title != old_title:
            titles.pop(old_title, None)
        titles[new_title] = row

        self._rename_nested_title(old_title, new_title)
        self._write_hashes(new_title)
        for lv, cb in self.grade_checks.items():
            if old_title != new_title:
                self._data.setdefault(f"gradeS_lv{lv}", {}).pop(old_title, None)
            set_grade_value(self._data, lv, new_title, cb.isChecked())

        self._title = new_title
        self.title_label.setText(new_title)
        self.saved.emit(new_title)

    def _rename_nested_title(self, old_title: str, new_title: str):
        if old_title == new_title or not self._data:
            return
        for section in ("jacket", "info"):
            for by_title in self._data.get(section, {}).values():
                if isinstance(by_title, dict) and old_title in by_title:
                    by_title[new_title] = by_title.pop(old_title)
        for key, value in self._data.items():
            if key.startswith("gradeS_lv") and isinstance(value, dict) and old_title in value:
                value[new_title] = value.pop(old_title)

    def _write_hashes(self, title: str):
        if not self._data:
            return
        for section, edits in (("jacket", self.jacket_edits), ("info", self.info_edits)):
            section_data = self._data.setdefault(section, {})
            for db_key, edit in edits.items():
                value = edit.text().strip().lower()
                by_title = section_data.setdefault(db_key, {})
                if value:
                    by_title[title] = value
                else:
                    by_title.pop(title, None)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SDVX musiclist editor")
        self.resize(1280, 820)
        self._db: dict[str, dict] = {}
        self._paths = {"v1": MUSICLIST_V1, "v2": MUSICLIST_V2}
        self._dirty = {"v1": False, "v2": False}
        self._dirty_revision = {"v1": 0, "v2": 0}
        self._save_worker: SaveWorker | None = None
        self._portal_manager = PortalManager()
        self._portal_master: list[dict] = []
        self._setup_ui()
        self._load_all()
        self._apply_filter()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.filter_panel = FilterPanel()
        self.filter_panel.filter_changed.connect(self._on_filter_changed)
        left_layout.addWidget(self.filter_panel)

        left_splitter = QSplitter(Qt.Vertical)
        left_layout.addWidget(left_splitter)

        local_box = QGroupBox("ローカルDB")
        local_layout = QVBoxLayout(local_box)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["曲名", "Artist", "NOV", "ADV", "EXH", "APPEND", "v1曲名"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(2, 6):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        local_layout.addWidget(self.table)
        left_splitter.addWidget(local_box)

        portal_box = QGroupBox("ポータルマスタ")
        portal_layout = QVBoxLayout(portal_box)
        portal_search_row = QHBoxLayout()
        self.portal_search_edit = QLineEdit()
        self.portal_search_edit.setPlaceholderText("曲名 / よみ / アーティストで検索")
        self.portal_search_edit.textChanged.connect(self._apply_portal_filter)
        self.portal_missing_only_check = QCheckBox("未登録のみ")
        self.portal_missing_only_check.stateChanged.connect(self._apply_portal_filter)
        self.portal_refresh_btn = QPushButton("再取得")
        self.portal_refresh_btn.clicked.connect(self._refresh_portal_master)
        portal_search_row.addWidget(self.portal_search_edit)
        portal_search_row.addWidget(self.portal_missing_only_check)
        portal_search_row.addWidget(self.portal_refresh_btn)
        portal_layout.addLayout(portal_search_row)

        self.portal_table = QTableWidget()
        self.portal_table.setColumnCount(8)
        self.portal_table.setHorizontalHeaderLabels(["状態", "曲名", "Artist", "NOV", "ADV", "EXH", "APPEND", "music_id"])
        self.portal_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.portal_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.portal_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for col in range(3, 7):
            self.portal_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.portal_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.portal_table.verticalHeader().setDefaultSectionSize(22)
        self.portal_table.verticalHeader().setVisible(False)
        self.portal_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.portal_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.portal_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.portal_table.setSortingEnabled(True)
        self.portal_table.itemSelectionChanged.connect(self._update_portal_buttons)
        self.portal_table.itemDoubleClicked.connect(self._on_portal_double_clicked)
        portal_layout.addWidget(self.portal_table)

        portal_button_row = QHBoxLayout()
        self.portal_select_btn = QPushButton("登録済み曲を選択")
        self.portal_select_btn.clicked.connect(self._select_registered_portal_song)
        self.portal_add_btn = QPushButton("表示中DBへ追加")
        self.portal_add_btn.clicked.connect(self._add_selected_portal_song)
        portal_button_row.addWidget(self.portal_select_btn)
        portal_button_row.addWidget(self.portal_add_btn)
        portal_layout.addLayout(portal_button_row)
        self.portal_status_label = QLabel("")
        self.portal_status_label.setWordWrap(True)
        portal_layout.addWidget(self.portal_status_label)
        left_splitter.addWidget(portal_box)
        left_splitter.setSizes([520, 300])

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.edit_panel = SongEditPanel()
        self.edit_panel.saved.connect(self._on_song_saved)
        right_layout.addWidget(self.edit_panel)

        db_buttons = QGroupBox("DB")
        db_layout = QVBoxLayout(db_buttons)
        self.save_current_btn = QPushButton("表示中DBをファイルへ保存")
        self.save_all_btn = QPushButton("両方保存")
        self.copy_v1_to_v2_btn = QPushButton("同名曲を v1 -> v2 に反映")
        self.reload_btn = QPushButton("ファイルから再読み込み")
        self.save_current_btn.clicked.connect(self._save_current)
        self.save_all_btn.clicked.connect(self._save_all)
        self.copy_v1_to_v2_btn.clicked.connect(self._copy_selected_v1_to_v2)
        self.reload_btn.clicked.connect(self._reload_all)
        db_layout.addWidget(self.save_current_btn)
        db_layout.addWidget(self.save_all_btn)
        db_layout.addWidget(self.copy_v1_to_v2_btn)
        db_layout.addWidget(self.reload_btn)
        right_layout.addWidget(db_buttons)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)
        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([820, 460])

    def _load_all(self):
        self._db = {}
        errors = []
        for key, path in self._paths.items():
            try:
                self._db[key] = load_musiclist(path)
                self._dirty[key] = False
                self._dirty_revision[key] = 0
            except Exception as exc:
                self._db[key] = {"titles": {}, "jacket": {}, "info": {}}
                errors.append(f"{path}: {exc}")
        self._refresh_editor_db()
        self._load_portal_cache()
        if errors:
            QMessageBox.warning(self, "読み込みエラー", "\n".join(errors))
        self._set_status("読み込み完了")

    def _current_key(self) -> str:
        return self.filter_panel.target_key()

    def _current_db(self) -> dict:
        return self._db[self._current_key()]

    def _refresh_editor_db(self):
        self.edit_panel.set_database(self._current_db())

    def _on_filter_changed(self):
        self._refresh_editor_db()
        self._apply_filter()
        self._apply_portal_filter()

    def _load_portal_cache(self):
        self._portal_manager.load_cache()
        self._portal_master = list(self._portal_manager.master_db or [])
        self._apply_portal_filter()

    def _refresh_portal_master(self):
        config = Config()
        if not config.portal_token:
            QMessageBox.information(self, "ポータルマスタ", "config.json に portal_token が設定されていません。")
            return

        self.portal_refresh_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            manager = PortalManager(token=config.portal_token)
            if not manager.get_musiclist():
                QMessageBox.warning(self, "ポータルマスタ", "ポータルマスタの取得に失敗しました。")
                return
            self._portal_manager = manager
            self._portal_master = list(manager.master_db or [])
            self._apply_portal_filter()
            self.portal_status_label.setText(f"ポータルマスタ取得完了: {len(self._portal_master)} 曲")
        finally:
            QApplication.restoreOverrideCursor()
            self.portal_refresh_btn.setEnabled(True)

    def _portal_entry_registered(self, entry: dict) -> bool:
        title = str(entry.get("title") or "")
        return bool(title and title in self._current_db().get("titles", {}))

    def _portal_search_haystack(self, entry: dict) -> str:
        return normalize_search_text(
            " ".join(
                str(entry.get(key) or "")
                for key in ("title", "title_ruby", "artist", "artist_ruby", "music_id")
            )
        )

    def _apply_portal_filter(self):
        if not hasattr(self, "portal_table"):
            return

        search = normalize_search_text(self.portal_search_edit.text().strip())
        missing_only = self.portal_missing_only_check.isChecked()
        rows = []
        for entry in self._portal_master:
            title = str(entry.get("title") or "")
            if not title:
                continue
            registered = self._portal_entry_registered(entry)
            if missing_only and registered:
                continue
            if search and search not in self._portal_search_haystack(entry):
                continue
            rows.append((entry, registered))

        rows.sort(key=lambda item: normalize_search_text(str(item[0].get("title") or "")))
        self.portal_table.setSortingEnabled(False)
        self.portal_table.setRowCount(len(rows))
        registered_brush = QBrush(QColor(226, 246, 229))
        missing_brush = QBrush(QColor(255, 233, 233))

        for table_row, (entry, registered) in enumerate(rows):
            levels = portal_chart_levels(entry)
            values = [
                "登録済" if registered else "未登録",
                str(entry.get("title") or ""),
                str(entry.get("artist") or ""),
                str(levels["nov"] or ""),
                str(levels["adv"] or ""),
                str(levels["exh"] or ""),
                str(levels["APPEND"] or ""),
                str(entry.get("music_id") or ""),
            ]
            brush = registered_brush if registered else missing_brush
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setBackground(brush)
                item.setData(Qt.UserRole, entry)
                if col in (3, 4, 5, 6):
                    item.setData(Qt.UserRole + 1, int(value or 0))
                    item.setTextAlignment(Qt.AlignCenter)
                self.portal_table.setItem(table_row, col, item)

        self.portal_table.setSortingEnabled(True)
        self.portal_status_label.setText(f"表示: {len(rows)} / ポータルマスタ: {len(self._portal_master)} 曲")
        self._update_portal_buttons()

    def _selected_portal_entry(self) -> dict | None:
        row = self.portal_table.currentRow()
        if row < 0:
            return None
        item = self.portal_table.item(row, 0)
        entry = item.data(Qt.UserRole) if item else None
        return entry if isinstance(entry, dict) else None

    def _update_portal_buttons(self):
        if not hasattr(self, "portal_add_btn"):
            return
        entry = self._selected_portal_entry()
        registered = self._portal_entry_registered(entry) if entry else False
        self.portal_select_btn.setEnabled(bool(entry and registered))
        self.portal_add_btn.setEnabled(bool(entry and not registered))

    def _select_registered_portal_song(self):
        entry = self._selected_portal_entry()
        if not entry:
            return
        title = str(entry.get("title") or "")
        if title not in self._current_db().get("titles", {}):
            return
        self._select_title(title)

    def _add_selected_portal_song(self):
        entry = self._selected_portal_entry()
        if not entry:
            return
        title = str(entry.get("title") or "")
        if not title:
            return

        data = self._current_db()
        if title in data.get("titles", {}):
            self._select_title(title)
            self._apply_portal_filter()
            return

        data.setdefault("titles", {})[title] = portal_entry_to_title_row(entry)
        self._mark_dirty(self._current_key())
        self._apply_filter()
        self._select_title(title)
        self._apply_portal_filter()
        self._set_status(f"ポータルマスタから追加しました: {title}（ファイル保存はまだです）")

    def _on_portal_double_clicked(self, _item: QTableWidgetItem):
        entry = self._selected_portal_entry()
        if not entry:
            return
        if self._portal_entry_registered(entry):
            self._select_registered_portal_song()
        else:
            self._add_selected_portal_song()

    def _apply_filter(self):
        selected_title = self._selected_title()
        data = self._current_db()
        search = self.filter_panel.search_text()
        diff = self.filter_panel.diff_filter()
        level = self.filter_panel.level_filter()

        rows = []
        for title, raw_row in data.get("titles", {}).items():
            row = ensure_title_row(raw_row)
            haystack = normalize_search_text(f"{title} {row[0]} {row[1]}")
            if search and search not in haystack:
                continue
            if diff or level is not None:
                matched = False
                for _db_key, label, idx in DIFFS:
                    lv = row_level(row, idx)
                    if diff and label != diff:
                        continue
                    if level is not None and lv != level:
                        continue
                    if lv:
                        matched = True
                        break
                if not matched:
                    continue
            rows.append((title, row))

        rows.sort(key=lambda item: normalize_search_text(item[0]))

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for table_row, (title, row) in enumerate(rows):
            values = [
                title,
                str(row[1] or ""),
                str(row_level(row, 3) or ""),
                str(row_level(row, 4) or ""),
                str(row_level(row, 5) or ""),
                str(row_level(row, 6) or ""),
                str(row[7] or "") if len(row) > 7 else "",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (2, 3, 4, 5):
                    item.setData(Qt.UserRole, int(value or 0))
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(table_row, col, item)
        self.table.setSortingEnabled(True)

        if selected_title:
            self._select_title(selected_title)
        elif self.table.rowCount():
            self.table.selectRow(0)
        else:
            self.edit_panel.set_title(None)

        self._update_window_title()

    def _selected_title(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _select_title(self, title: str):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() == title:
                self.table.selectRow(row)
                return

    def _on_selection_changed(self):
        self.edit_panel.set_title(self._selected_title())

    def _on_song_saved(self, title: str):
        key = self._current_key()
        self._mark_dirty(key)
        self._apply_filter()
        self._select_title(title)
        self._apply_portal_filter()
        self._set_status(f"未保存の変更あり: {self._paths[key]}")

    def _copy_selected_v1_to_v2(self):
        title = self._selected_title()
        if not title:
            return
        v1 = self._db["v1"]
        v2 = self._db["v2"]
        if title not in v1.get("titles", {}):
            QMessageBox.information(self, "反映できません", "同名曲が v1 にありません。")
            return

        reply = QMessageBox.question(
            self,
            "確認",
            f"v1 の同名曲データを v2 へ反映しますか?\n\n{title}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        v2.setdefault("titles", {})[title] = deepcopy(v1["titles"][title])
        for section in ("jacket", "info"):
            for db_key, _label, _idx in DIFFS:
                src = v1.get(section, {}).get(db_key, {})
                dst = v2.setdefault(section, {}).setdefault(db_key, {})
                if title in src:
                    dst[title] = src[title]
                else:
                    dst.pop(title, None)
        for lv in GRADE_LEVELS:
            set_grade_value(v2, lv, title, grade_value(v1, lv, title) == "1")

        self._mark_dirty("v2")
        self.filter_panel.rb_v2.setChecked(True)
        self._apply_filter()
        self._select_title(title)
        self._set_status("v1 から v2 へ反映しました。ファイル保存はまだです。")

    def _mark_dirty(self, key: str):
        self._dirty[key] = True
        self._dirty_revision[key] += 1

    def _save_current(self):
        self._start_save([self._current_key()])

    def _save_all(self):
        self._start_save(["v1", "v2"])

    def _start_save(self, keys: list[str]):
        if self._save_worker is not None and self._save_worker.isRunning():
            QMessageBox.information(self, "保存中", "現在の保存が完了してから再度実行してください。")
            return

        jobs = [
            (key, self._paths[key], deepcopy(self._db[key]), self._dirty_revision[key])
            for key in keys
        ]
        self._set_save_controls_enabled(False)
        self._set_status("保存中...")
        self._save_worker = SaveWorker(jobs, self)
        self._save_worker.finished_with_results.connect(self._on_save_finished)
        self._save_worker.start()

    def _set_save_controls_enabled(self, enabled: bool):
        self.save_current_btn.setEnabled(enabled)
        self.save_all_btn.setEnabled(enabled)
        self.reload_btn.setEnabled(enabled)

    def _on_save_finished(self, results: list):
        self._set_save_controls_enabled(True)
        errors = []
        saved = []
        stale = []
        for key, path, error, revision in results:
            if error:
                errors.append(f"{path}\n{error}")
                continue
            saved.append(path)
            if self._dirty_revision.get(key) == revision:
                self._dirty[key] = False
            else:
                stale.append(key)

        worker = self._save_worker
        self._save_worker = None
        if worker is not None:
            worker.deleteLater()

        self._update_window_title()
        if errors:
            QMessageBox.critical(self, "保存失敗", "\n\n".join(errors))
            self._set_status("保存に失敗しました")
        elif stale:
            self._set_status(f"保存しましたが、新しい変更が残っています: {', '.join(stale)}")
        else:
            self._set_status(f"保存しました: {', '.join(saved)}")

    def _reload_all(self):
        if any(self._dirty.values()):
            reply = QMessageBox.question(
                self,
                "確認",
                "未保存の変更を破棄して再読み込みしますか?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._load_all()
        self._apply_filter()

    def _set_status(self, text: str):
        dirty = [key for key, value in self._dirty.items() if value]
        suffix = f" / 未保存: {', '.join(dirty)}" if dirty else ""
        self.status_label.setText(text + suffix)
        self._update_window_title()

    def _update_window_title(self):
        dirty_mark = "*" if any(self._dirty.values()) else ""
        current = self._current_key()
        self.setWindowTitle(f"SDVX musiclist editor{dirty_mark} - {current}")

    def closeEvent(self, event):
        if any(self._dirty.values()):
            reply = QMessageBox.question(
                self,
                "確認",
                "未保存の変更があります。終了しますか?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
        super().closeEvent(event)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SDVX musiclist editor")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
