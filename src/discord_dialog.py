"""Discord連携設定ダイアログ。"""

import traceback
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

_LAMPS = ['PUC', 'MAXXIVE', 'EXC-COMP', 'COMP', 'PLAYED']


class _DiscordTestSendWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config

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
    """Discord Webhook URLと送信条件を設定するダイアログ。"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._level_checks: dict[int, QCheckBox] = {}
        self._lamp_checks: dict[str, QCheckBox] = {}
        self._syncing_all = False
        self._test_worker = None

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
        url_form.addRow("Discord Webhook URL:", self.webhook_url_edit)
        layout.addWidget(url_group)

        test_group = QGroupBox("テスト送信")
        test_layout = QHBoxLayout()
        test_group.setLayout(test_layout)
        self.test_send_button = QPushButton("テスト送信")
        self.test_send_button.clicked.connect(self._on_test_send)
        test_layout.addWidget(self.test_send_button)
        self.test_status_label = QLabel("")
        test_layout.addWidget(self.test_status_label)
        test_layout.addStretch()
        layout.addWidget(test_group)

        condition_group = QGroupBox("送信条件")
        condition_layout = QVBoxLayout()
        condition_group.setLayout(condition_layout)

        self.updated_only_check = QCheckBox("更新があったリザルトのみ送信")
        condition_layout.addWidget(self.updated_only_check)

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

    def _store_values(self, save: bool = False):
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
        if save:
            self.config.save_config()

    def _on_test_send(self):
        self._store_values(save=True)
        if not self.config.discord_webhook_url:
            QMessageBox.warning(
                self,
                "警告",
                "Discord Webhook URLを入力してください",
            )
            return

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
        self._test_worker = _DiscordTestSendWorker(self.config, self)
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
        self._store_values(save=True)
        logger.info("Discord連携設定を保存しました")
        super().accept()
