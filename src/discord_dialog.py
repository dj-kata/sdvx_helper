"""Discord連携設定ダイアログ。"""

import traceback
import uuid
from copy import deepcopy
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QVBoxLayout,
)

from src.classes import clear_lamp, detect_mode, difficulty, screen_orientation
from src.discord_webhook import post_result_to_discord
from src.logger import get_logger
from src.result import OneResult
from src.result_image import expand_result_info_area
from src.screen_reader import ScreenReader
from src.songinfo import SongDatabase

logger = get_logger(__name__)

_LAMPS = ['PUC', 'UC', 'MAXXIVE', 'EXC-COMP', 'COMP', 'PLAYED']


class _DiscordTestSendWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, config, rule: dict | None = None, parent=None):
        super().__init__(parent)
        self.config = config
        self.rule = rule or {}

    def run(self):
        try:
            ok, detail = self._send_latest_or_dummy()
            self.finished.emit(ok, detail)
        except Exception as e:
            logger.error(f"Discordテスト送信エラー:\n{traceback.format_exc()}")
            self.finished.emit(False, str(e))

    def _send_latest_or_dummy(self) -> tuple[bool, str]:
        latest_path = self._find_latest_result_image()
        if latest_path is None:
            result = OneResult(
                title='TEST SONG',
                difficulty=difficulty.maximum,
                lamp=clear_lamp.exc,
                score=9_885_638,
                exscore=4864,
                level=18,
                detect_mode=detect_mode.result,
            )
            ok = post_result_to_discord(
                self.config,
                result,
                artist='TEST ARTIST',
                pre_score=9_837_730,
                pre_exscore=0,
                screen=None,
                extra_lines=['image: **None**'],
                show_delta=False,
                webhook_url=str(self.rule.get('webhook_url', '')).strip() or None,
            )
            return ok, 'dummy'

        with Image.open(latest_path) as img:
            screen = img.copy()

        result, artist = self._read_result_image(screen)
        ok = post_result_to_discord(
            self.config,
            result,
            artist=artist,
            screen=screen,
            show_delta=False,
            webhook_url=str(self.rule.get('webhook_url', '')).strip() or None,
        )
        return ok, str(latest_path)

    def _find_latest_result_image(self) -> Path | None:
        image_dir = Path(getattr(self.config, 'image_save_path', 'results') or 'results')
        if not image_dir.exists():
            return None
        candidates = [
            p
            for pattern in ('sdvx_*.png', 'sdvx_*.jpg', 'sdvx_*.jpeg')
            for p in image_dir.glob(pattern)
            if p.is_file()
        ]
        if not candidates:
            return None

        reader = self._make_reader()
        for path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with Image.open(path) as img:
                    reader.update_screen(expand_result_info_area(img))
                    if reader.detect_screen().is_result_screen():
                        return path
                    logger.debug(f"Discordテスト送信候補をスキップ(非リザルト): {path}")
            except Exception:
                logger.debug(f"Discordテスト送信候補をスキップ: {path}\n{traceback.format_exc()}")
        return None

    def _read_result_image(self, screen: Image.Image) -> tuple[OneResult, str]:
        song_db = SongDatabase()
        reader = self._make_reader(song_db)
        reader.update_screen(expand_result_info_area(screen))
        data = reader.read_from_result() or {}

        title = data.get('title') or 'UNKNOWN'
        diff = data.get('difficulty') or difficulty.maximum
        lamp = data.get('lamp') or clear_lamp.played
        score = data.get('score')
        exscore = data.get('exscore')

        info = song_db.get_song_info(title)
        level = info.get_level(diff) if info else None
        artist = info.artist if info else ''

        result = OneResult(
            title=title,
            difficulty=diff,
            lamp=lamp,
            score=score,
            exscore=exscore,
            level=level,
            detect_mode=data.get('detect_mode') or detect_mode.result,
        )
        return result, artist

    def _make_reader(self, song_db: SongDatabase | None = None) -> ScreenReader:
        return ScreenReader(
            song_db=song_db or SongDatabase(),
            orientation=self._parse_orientation(
                getattr(self.config, 'screen_orientation_override', None)
            ),
        )

    @staticmethod
    def _parse_orientation(value: str | None):
        return {
            'top_up': screen_orientation.top_up,
            'top_right': screen_orientation.top_right,
            'top_left': screen_orientation.top_left,
        }.get(value)


class DiscordConfigDialog(QDialog):
    """Discord Webhook URLと送信条件を複数ルールで設定するダイアログ。"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._rules: list[dict] = deepcopy(getattr(config, 'discord_rules', []) or [])
        self._level_checks: dict[int, QCheckBox] = {}
        self._lamp_checks: dict[str, QCheckBox] = {}
        self._syncing_all = False
        self._test_worker = None

        self.setWindowTitle("Discord連携設定")
        self.setMinimumWidth(860)
        self._init_ui()
        self._refresh_rule_table()
        if self._rules:
            self.rule_table.selectRow(0)
        else:
            self._clear_form()

    def _init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        main_row = QHBoxLayout()
        layout.addLayout(main_row)

        list_group = QGroupBox("登録済み通知ルール")
        list_layout = QVBoxLayout()
        list_group.setLayout(list_layout)
        self.rule_table = QTableWidget(0, 4)
        self.rule_table.setHorizontalHeaderLabels(["有効", "名前", "条件", "URL"])
        self.rule_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rule_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.rule_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rule_table.verticalHeader().setVisible(False)
        header = self.rule_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.rule_table.itemSelectionChanged.connect(self._on_rule_selected)
        list_layout.addWidget(self.rule_table)

        list_buttons = QHBoxLayout()
        self.new_rule_button = QPushButton("新規")
        self.new_rule_button.clicked.connect(self._clear_form)
        self.delete_rule_button = QPushButton("削除")
        self.delete_rule_button.clicked.connect(self._delete_rule)
        for button in (
            self.new_rule_button,
            self.delete_rule_button,
        ):
            list_buttons.addWidget(button)
        list_layout.addLayout(list_buttons)
        main_row.addWidget(list_group, 3)

        edit_group = QGroupBox("ルール編集")
        edit_layout = QVBoxLayout()
        edit_group.setLayout(edit_layout)
        main_row.addWidget(edit_group, 2)

        url_form = QFormLayout()
        edit_layout.addLayout(url_form)
        self.rule_name_edit = QLineEdit()
        self.rule_name_edit.setPlaceholderText("例: Lv18以上更新")
        url_form.addRow("名前:", self.rule_name_edit)
        self.webhook_url_edit = QLineEdit()
        self.webhook_url_edit.setPlaceholderText("https://discord.com/api/webhooks/...")
        url_form.addRow("Discord Webhook URL:", self.webhook_url_edit)
        self.enabled_check = QCheckBox("このルールを有効にする")
        edit_layout.addWidget(self.enabled_check)

        condition_group = QGroupBox("送信条件")
        condition_layout = QVBoxLayout()
        condition_group.setLayout(condition_layout)

        self.updated_only_check = QCheckBox("更新があったリザルトのみ送信")
        condition_layout.addWidget(self.updated_only_check)
        self.include_unrecognized_check = QCheckBox("曲名認識できない曲を含む")
        condition_layout.addWidget(self.include_unrecognized_check)

        score_row = QHBoxLayout()
        score_row.addWidget(QLabel("最低スコア"))
        self.min_score_spin = QSpinBox()
        self.min_score_spin.setRange(0, 10_000_000)
        self.min_score_spin.setSingleStep(100_000)
        self.min_score_spin.setSpecialValueText("指定なし")
        score_row.addWidget(self.min_score_spin)
        score_row.addStretch()
        condition_layout.addLayout(score_row)

        level_group = QGroupBox("レベルフィルタ")
        level_layout = QVBoxLayout()
        level_group.setLayout(level_layout)
        self.level_filter_enabled_check = QCheckBox("レベルフィルタを有効にする")
        self.level_filter_enabled_check.stateChanged.connect(
            self._update_filter_checkbox_states
        )
        level_layout.addWidget(self.level_filter_enabled_check)

        level_grid = QGridLayout()
        self.level_all_check = QCheckBox("ALL")
        self.level_all_check.stateChanged.connect(self._on_level_all_changed)
        level_grid.addWidget(self.level_all_check, 0, 0, alignment=Qt.AlignLeft)
        for lv in range(1, 21):
            cb = QCheckBox(str(lv))
            cb.stateChanged.connect(self._sync_level_all_check)
            self._level_checks[lv] = cb
            pos = lv
            level_grid.addWidget(cb, pos // 7, pos % 7, alignment=Qt.AlignLeft)
        level_layout.addLayout(level_grid)
        condition_layout.addWidget(level_group)

        lamp_group = QGroupBox("ランプフィルタ")
        lamp_layout = QVBoxLayout()
        lamp_group.setLayout(lamp_layout)
        self.lamp_filter_enabled_check = QCheckBox("ランプフィルタを有効にする")
        self.lamp_filter_enabled_check.stateChanged.connect(
            self._update_filter_checkbox_states
        )
        lamp_layout.addWidget(self.lamp_filter_enabled_check)

        lamp_row = QHBoxLayout()
        for lamp in _LAMPS:
            cb = QCheckBox(lamp)
            self._lamp_checks[lamp] = cb
            lamp_row.addWidget(cb)
        lamp_row.addStretch()
        lamp_layout.addLayout(lamp_row)
        condition_layout.addWidget(lamp_group)

        edit_layout.addWidget(condition_group)

        edit_buttons = QHBoxLayout()
        edit_buttons.addStretch()
        self.add_rule_button = QPushButton("追加")
        self.add_rule_button.clicked.connect(self._add_rule)
        self.update_rule_button = QPushButton("更新")
        self.update_rule_button.clicked.connect(self._update_rule)
        edit_buttons.addWidget(self.add_rule_button)
        edit_buttons.addWidget(self.update_rule_button)
        edit_layout.addLayout(edit_buttons)
        layout.addStretch()

        test_group = QGroupBox("テスト送信")
        test_layout = QHBoxLayout()
        test_group.setLayout(test_layout)
        self.test_send_button = QPushButton("選択中のルールへテスト送信")
        self.test_send_button.clicked.connect(self._on_test_send)
        test_layout.addWidget(self.test_send_button)
        self.test_status_label = QLabel("")
        test_layout.addWidget(self.test_status_label)
        test_layout.addStretch()
        layout.addWidget(test_group)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_rule_to_form(self, rule: dict):
        self.rule_name_edit.setText(str(rule.get('name', '')))
        self.webhook_url_edit.setText(str(rule.get('webhook_url', '')))
        self.enabled_check.setChecked(rule.get('enabled', True) is not False)
        self.updated_only_check.setChecked(bool(rule.get('updated_results_only', False)))
        self.include_unrecognized_check.setChecked(
            bool(rule.get('include_unrecognized_title', False))
        )
        self.min_score_spin.setValue(int(rule.get('min_score') or 0))
        self.level_filter_enabled_check.setChecked(bool(rule.get('level_filter_enabled', False)))
        levels = set(rule.get('levels', []) or range(1, 21))
        for lv, cb in self._level_checks.items():
            cb.setChecked(lv in levels)
        self._sync_level_all_check()

        self.lamp_filter_enabled_check.setChecked(bool(rule.get('lamp_filter_enabled', False)))
        lamps = set(rule.get('lamps', []) or _LAMPS)
        for lamp, cb in self._lamp_checks.items():
            cb.setChecked(lamp in lamps)
        self._update_filter_checkbox_states()

    def _clear_form(self):
        self.rule_table.clearSelection()
        self.rule_name_edit.setText("")
        self.webhook_url_edit.setText("")
        self.enabled_check.setChecked(True)
        self.updated_only_check.setChecked(False)
        self.include_unrecognized_check.setChecked(False)
        self.min_score_spin.setValue(0)
        self.level_filter_enabled_check.setChecked(False)
        for cb in self._level_checks.values():
            cb.setChecked(True)
        self._sync_level_all_check()
        self.lamp_filter_enabled_check.setChecked(False)
        for cb in self._lamp_checks.values():
            cb.setChecked(True)
        self._update_filter_checkbox_states()

    def _on_level_all_changed(self, *_args):
        if self._syncing_all:
            return
        checked = self.level_all_check.isChecked()
        self._syncing_all = True
        try:
            for cb in self._level_checks.values():
                cb.setChecked(checked)
        finally:
            self._syncing_all = False

    def _sync_level_all_check(self, *_args):
        if self._syncing_all:
            return
        all_checked = all(cb.isChecked() for cb in self._level_checks.values())
        self._syncing_all = True
        try:
            self.level_all_check.setChecked(all_checked)
        finally:
            self._syncing_all = False

    def _update_filter_checkbox_states(self, *_args):
        level_enabled = self.level_filter_enabled_check.isChecked()
        self.level_all_check.setEnabled(level_enabled)
        for cb in self._level_checks.values():
            cb.setEnabled(level_enabled)

        lamp_enabled = self.lamp_filter_enabled_check.isChecked()
        for cb in self._lamp_checks.values():
            cb.setEnabled(lamp_enabled)

    def _rule_from_form(self, existing_id: str | None = None) -> dict | None:
        name = self.rule_name_edit.text().strip()
        url = self.webhook_url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "警告", "Discord Webhook URLを入力してください")
            return None
        if not name:
            name = f"通知ルール{len(self._rules) + 1}"
        return {
            'id': existing_id or str(uuid.uuid4()),
            'name': name,
            'webhook_url': url,
            'enabled': self.enabled_check.isChecked(),
            'updated_results_only': self.updated_only_check.isChecked(),
            'include_unrecognized_title': self.include_unrecognized_check.isChecked(),
            'level_filter_enabled': self.level_filter_enabled_check.isChecked(),
            'levels': [
                lv for lv, cb in self._level_checks.items()
                if cb.isChecked()
            ],
            'lamp_filter_enabled': self.lamp_filter_enabled_check.isChecked(),
            'lamps': [
                lamp for lamp, cb in self._lamp_checks.items()
                if cb.isChecked()
            ],
            'min_score': self.min_score_spin.value(),
        }

    def _store_values(self, save: bool = False):
        self.config.discord_rules = deepcopy(self._rules)
        first_enabled = next(
            (rule for rule in self._rules if rule.get('enabled', True) is not False),
            self._rules[0] if self._rules else None,
        )
        if first_enabled:
            self.config.discord_webhook_url = str(first_enabled.get('webhook_url', ''))
            self.config.discord_updated_results_only = bool(first_enabled.get('updated_results_only', False))
            self.config.discord_level_filter_enabled = bool(first_enabled.get('level_filter_enabled', False))
            self.config.discord_levels = [
                int(v) for v in first_enabled.get('levels', []) or range(1, 21)
            ]
            self.config.discord_lamp_filter_enabled = bool(first_enabled.get('lamp_filter_enabled', False))
            self.config.discord_lamps = [
                str(v) for v in first_enabled.get('lamps', []) or _LAMPS
            ]
        else:
            self.config.discord_webhook_url = ''
            self.config.discord_updated_results_only = False
            self.config.discord_level_filter_enabled = False
            self.config.discord_levels = list(range(1, 21))
            self.config.discord_lamp_filter_enabled = False
            self.config.discord_lamps = list(_LAMPS)
        if save:
            self.config.save_config()

    def _selected_row(self) -> int:
        rows = self.rule_table.selectionModel().selectedRows()
        if not rows:
            return -1
        return rows[0].row()

    def _selected_rule(self) -> dict | None:
        row = self._selected_row()
        if 0 <= row < len(self._rules):
            return self._rules[row]
        return None

    def _refresh_rule_table(self):
        self.rule_table.setRowCount(len(self._rules))
        for row, rule in enumerate(self._rules):
            values = [
                "ON" if rule.get('enabled', True) is not False else "OFF",
                str(rule.get('name', '')),
                self._condition_summary(rule),
                self._mask_url(str(rule.get('webhook_url', ''))),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, rule.get('id'))
                self.rule_table.setItem(row, col, item)
        self.update_rule_button.setEnabled(bool(self._rules))
        self.delete_rule_button.setEnabled(bool(self._rules))
        self.test_send_button.setEnabled(bool(self._rules))

    def _on_rule_selected(self):
        rule = self._selected_rule()
        if rule:
            self._load_rule_to_form(rule)

    def _add_rule(self):
        rule = self._rule_from_form()
        if not rule:
            return
        self._rules.append(rule)
        self._refresh_rule_table()
        self.rule_table.selectRow(len(self._rules) - 1)

    def _update_rule(self):
        row = self._selected_row()
        if row < 0:
            QMessageBox.warning(self, "警告", "更新するルールを選択してください")
            return
        rule = self._rule_from_form(existing_id=str(self._rules[row].get('id', '')))
        if not rule:
            return
        self._rules[row] = rule
        self._refresh_rule_table()
        self.rule_table.selectRow(row)

    def _delete_rule(self):
        row = self._selected_row()
        if row < 0:
            QMessageBox.warning(self, "警告", "削除するルールを選択してください")
            return
        del self._rules[row]
        self._refresh_rule_table()
        if self._rules:
            self.rule_table.selectRow(min(row, len(self._rules) - 1))
        else:
            self._clear_form()

    @staticmethod
    def _condition_summary(rule: dict) -> str:
        parts = []
        if rule.get('updated_results_only', False):
            parts.append("更新のみ")
        if rule.get('include_unrecognized_title', False):
            parts.append("曲名未認識を含む")
        try:
            min_score = int(rule.get('min_score') or 0)
        except Exception:
            min_score = 0
        if min_score:
            parts.append(f"{min_score:,}点以上")
        if rule.get('level_filter_enabled', False):
            levels = [int(v) for v in rule.get('levels', []) or []]
            parts.append("Lv." + ",".join(str(v) for v in levels))
        if rule.get('lamp_filter_enabled', False):
            parts.append("/".join(str(v) for v in rule.get('lamps', []) or []))
        return " / ".join(parts) if parts else "すべて送信"

    @staticmethod
    def _mask_url(url: str) -> str:
        if len(url) <= 24:
            return url
        return f"{url[:24]}..."

    def _on_test_send(self):
        row = self._selected_row()
        if row < 0:
            QMessageBox.warning(self, "警告", "テスト送信するルールを選択してください")
            return
        rule = self._rule_from_form(existing_id=str(self._rules[row].get('id', '')))
        if not rule:
            return
        self._rules[row] = rule
        self._refresh_rule_table()
        self.rule_table.selectRow(row)

        image_dir = Path(getattr(self.config, 'image_save_path', 'results') or 'results')
        has_image = image_dir.exists() and any(
            p.is_file()
            for pattern in ('sdvx_*.png', 'sdvx_*.jpg', 'sdvx_*.jpeg')
            for p in image_dir.glob(pattern)
        )
        if not has_image:
            QMessageBox.warning(
                self,
                "警告",
                "保存済みのリザルト画像がありません。ダミーデータを送信します。",
            )

        self.test_send_button.setEnabled(False)
        self.test_status_label.setText("送信中...")
        self._test_worker = _DiscordTestSendWorker(self.config, rule, self)
        self._test_worker.finished.connect(self._on_test_send_finished)
        self._test_worker.start()

    def _on_test_send_finished(self, ok: bool, detail: str):
        self.test_send_button.setEnabled(True)
        self._test_worker = None
        if ok:
            self.test_status_label.setText("送信完了")
            logger.info(f"Discordテスト送信完了: {detail}")
        else:
            self.test_status_label.setText(f"送信失敗: {detail}")

    def accept(self):
        row = self._selected_row()
        if row >= 0:
            rule = self._rule_from_form(existing_id=str(self._rules[row].get('id', '')))
            if not rule:
                return
            self._rules[row] = rule
        self._store_values(save=True)
        logger.info("Discord連携設定を保存しました")
        super().accept()
