"""Discord連携設定ダイアログ。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
)

from src.logger import get_logger

logger = get_logger(__name__)

_LAMPS = ['PUC', 'MAXXIVE', 'EXC-COMP', 'COMP', 'PLAYED']


class DiscordConfigDialog(QDialog):
    """Discord Webhook URLと送信条件を設定するダイアログ。"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._level_checks: dict[int, QCheckBox] = {}
        self._lamp_checks: dict[str, QCheckBox] = {}
        self._syncing_all = False

        self.setWindowTitle("Discord連携設定")
        self.setMinimumWidth(560)
        self._init_ui()
        self._load_values()

    def _init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        url_group = QGroupBox("URL")
        url_form = QFormLayout()
        url_group.setLayout(url_form)
        self.webhook_url_edit = QLineEdit()
        self.webhook_url_edit.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.webhook_url_edit.setEchoMode(QLineEdit.Password)
        url_form.addRow("Discord Webhook URL:", self.webhook_url_edit)
        layout.addWidget(url_group)

        condition_group = QGroupBox("送信条件")
        condition_layout = QVBoxLayout()
        condition_group.setLayout(condition_layout)

        self.updated_only_check = QCheckBox("更新があったリザルトのみ送信")
        condition_layout.addWidget(self.updated_only_check)

        level_group = QGroupBox("レベルフィルタ")
        level_layout = QVBoxLayout()
        level_group.setLayout(level_layout)
        self.level_filter_enabled_check = QCheckBox("レベルフィルタを有効にする")
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
        lamp_layout.addWidget(self.lamp_filter_enabled_check)

        lamp_row = QHBoxLayout()
        for lamp in _LAMPS:
            cb = QCheckBox(lamp)
            self._lamp_checks[lamp] = cb
            lamp_row.addWidget(cb)
        lamp_row.addStretch()
        lamp_layout.addLayout(lamp_row)
        condition_layout.addWidget(lamp_group)

        layout.addWidget(condition_group)
        layout.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_values(self):
        self.webhook_url_edit.setText(getattr(self.config, 'discord_webhook_url', ''))
        self.updated_only_check.setChecked(
            getattr(self.config, 'discord_updated_results_only', False)
        )
        self.level_filter_enabled_check.setChecked(
            getattr(self.config, 'discord_level_filter_enabled', False)
        )
        levels = set(getattr(self.config, 'discord_levels', []) or range(1, 21))
        for lv, cb in self._level_checks.items():
            cb.setChecked(lv in levels)
        self._sync_level_all_check()

        self.lamp_filter_enabled_check.setChecked(
            getattr(self.config, 'discord_lamp_filter_enabled', False)
        )
        lamps = set(getattr(self.config, 'discord_lamps', []) or _LAMPS)
        for lamp, cb in self._lamp_checks.items():
            cb.setChecked(lamp in lamps)

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

    def accept(self):
        self.config.discord_webhook_url = self.webhook_url_edit.text().strip()
        self.config.discord_updated_results_only = self.updated_only_check.isChecked()
        self.config.discord_level_filter_enabled = (
            self.level_filter_enabled_check.isChecked()
        )
        self.config.discord_levels = [
            lv for lv, cb in self._level_checks.items()
            if cb.isChecked()
        ]
        self.config.discord_lamp_filter_enabled = (
            self.lamp_filter_enabled_check.isChecked()
        )
        self.config.discord_lamps = [
            lamp for lamp, cb in self._lamp_checks.items()
            if cb.isChecked()
        ]
        self.config.save_config()
        logger.info("Discord連携設定を保存しました")
        super().accept()
