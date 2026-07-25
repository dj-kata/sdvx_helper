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

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
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


MUSICLIST_V1 = Path("resources") / "musiclist.pkl"
MUSICLIST_V2 = Path("resources") / "musiclistv2.sdvxh"

DIFFS = [
    ("nov", "NOV", 3),
    ("adv", "ADV", 4),
    ("exh", "EXH", 5),
    ("APPEND", "APPEND", 6),
]
GRADE_LEVELS = (17, 18, 19)


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
        left_layout.addWidget(self.table)

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
            except Exception as exc:
                self._db[key] = {"titles": {}, "jacket": {}, "info": {}}
                errors.append(f"{path}: {exc}")
        self._refresh_editor_db()
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
        self._dirty[key] = True
        self._apply_filter()
        self._select_title(title)
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

        self._dirty["v2"] = True
        self.filter_panel.rb_v2.setChecked(True)
        self._apply_filter()
        self._select_title(title)
        self._set_status("v1 から v2 へ反映しました。ファイル保存はまだです。")

    def _save_current(self):
        self._save_one(self._current_key())

    def _save_all(self):
        self._save_one("v1")
        self._save_one("v2")

    def _save_one(self, key: str):
        try:
            save_musiclist(self._db[key], self._paths[key])
        except Exception as exc:
            QMessageBox.critical(self, "保存失敗", f"{self._paths[key]}\n{exc}")
            return
        self._dirty[key] = False
        self._update_window_title()
        self._set_status(f"保存しました: {self._paths[key]}")

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
