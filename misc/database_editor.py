"""
misc/database_editor.py
songinfo.infdc を編集するための GUI ツール

起動: uv run -m misc.database_editor
"""

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QLineEdit, QPushButton, QGroupBox, QGridLayout,
    QComboBox, QRadioButton, QButtonGroup, QScrollArea,
    QDialog, QFormLayout, QDoubleSpinBox, QSpinBox,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.classes import play_style, difficulty, music_pack, unofficial_difficulty
from src.songinfo import SongDatabase, OneSongInfo
from src.funcs import calc_chart_id

# =========================================================
#  定数
# =========================================================

VERSION_NAMES: dict[int, str] = {
    1:        '1st&substream',
    2:        '2nd style',
    3:        '3rd style',
    4:        '4th style',
    5:        '5th style',
    6:        '6th style',
    7:        '7th style',
    8:        '8th style',
    9:        '9th style',
    10:       '10th style',
    11:       'IIDX RED',
    12:       'HAPPY SKY',
    13:       'DistorteD',
    14:       'GOLD',
    15:       'DJ TROOPERS',
    16:       'EMPRESS',
    17:       'SIRIUS',
    18:       'Resort Anthem',
    19:       'Lincle',
    20:       'tricoro',
    21:       'SPADA',
    22:       'PENDUAL',
    23:       'copula',
    24:       'SINOBUZ',
    25:       'CANNON BALLERS',
    26:       'Rootage',
    27:       'HEROIC VERSE',
    28:       'BISTROVER',
    29:       'CastHour',
    30:       'RESIDENT',
    31:       'EPOLIS',
    32:       'Pinky Crush',
    33:       'Sparkle Shower',
    99999999: 'INFINITAS',
}
VERSION_NAME_TO_NUM: dict[str, int] = {v: k for k, v in VERSION_NAMES.items()}

# 難易度ラベルと Enum のペア (表示順)
DIFF_LABELS = [
    ('B', difficulty.beginner),
    ('N', difficulty.normal),
    ('H', difficulty.hyper),
    ('A', difficulty.another),
    ('L', difficulty.leggendaria),
]

# unofficial_difficulty の表示名リスト (先頭が空欄 = None)
UNOFF_NAMES = [''] + [str(ud) for ud in unofficial_difficulty]
UNOFF_NAME_TO_ENUM: dict[str, unofficial_difficulty] = {
    str(ud): ud for ud in unofficial_difficulty
}


# =========================================================
#  ヘルパー関数
# =========================================================

def version_str(version: Optional[int]) -> str:
    if version is None:
        return ''
    return VERSION_NAMES.get(version, str(version))


def pack_str(pack) -> str:
    if pack is None:
        return ''
    if isinstance(pack, music_pack):
        return pack.name
    return str(pack)


def level_str(level: Optional[int]) -> str:
    return str(level) if level is not None else '-'


# =========================================================
#  EditDialog – モードレス編集ダイアログ
# =========================================================

class EditDialog(QDialog):
    """曲情報を編集するモードレスダイアログ。
    メインウィンドウの選択が変わるたびに set_title() が呼ばれる。
    """

    saved = Signal()  # 保存完了時に emit

    def __init__(self, db: SongDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_title: Optional[str] = None
        self.setWindowTitle('曲情報編集')
        self.setMinimumWidth(420)
        self.resize(480, 700)
        self._setup_ui()

    # =========================================================
    #  UI 構築
    # =========================================================

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # ---- タイトル表示 ----
        self.title_label = QLabel('(未選択)')
        self.title_label.setStyleSheet('font-weight: bold; font-size: 14px;')
        root.addWidget(self.title_label)

        # ---- SP/DP ラジオ ----
        ps_box = QGroupBox('プレースタイル')
        ps_layout = QHBoxLayout(ps_box)
        self.rb_sp = QRadioButton('SP')
        self.rb_dp = QRadioButton('DP')
        self.rb_sp.setChecked(True)
        self._ps_group = QButtonGroup(self)
        self._ps_group.addButton(self.rb_sp, 0)
        self._ps_group.addButton(self.rb_dp, 1)
        ps_layout.addWidget(self.rb_sp)
        ps_layout.addWidget(self.rb_dp)
        root.addWidget(ps_box)

        # ---- 難易度ラジオ ----
        diff_box = QGroupBox('難易度')
        diff_layout = QHBoxLayout(diff_box)
        self.rb_diffs: dict[difficulty, QRadioButton] = {}
        self._diff_group = QButtonGroup(self)
        for i, (label, d) in enumerate(DIFF_LABELS):
            rb = QRadioButton(label)
            self.rb_diffs[d] = rb
            self._diff_group.addButton(rb, i)
            diff_layout.addWidget(rb)
        self.rb_diffs[difficulty.another].setChecked(True)
        root.addWidget(diff_box)

        # ---- チャート存在ラベル ----
        self.chart_status_label = QLabel('')
        root.addWidget(self.chart_status_label)

        # ---- スクロールエリア (フォーム本体) ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # == 基本情報 ==
        self._section(form, '基本情報')

        self.cb_version = QComboBox()
        self.cb_version.addItem('')
        for name in VERSION_NAMES.values():
            self.cb_version.addItem(name)
        form.addRow('収録バージョン:', self.cb_version)

        self.cb_pack = QComboBox()
        self.cb_pack.addItem('')
        for mp in music_pack:
            self.cb_pack.addItem(mp.name)
        form.addRow('楽曲パック:', self.cb_pack)

        bpm_row = QWidget()
        bpm_rl = QHBoxLayout(bpm_row)
        bpm_rl.setContentsMargins(0, 0, 0, 0)
        self.sb_min_bpm = self._spinbox(0, 9999)
        self.sb_max_bpm = self._spinbox(0, 9999)
        bpm_rl.addWidget(QLabel('min:'))
        bpm_rl.addWidget(self.sb_min_bpm)
        bpm_rl.addWidget(QLabel('max:'))
        bpm_rl.addWidget(self.sb_max_bpm)
        bpm_rl.addStretch()
        form.addRow('BPM:', bpm_row)

        # == 譜面情報 ==
        self._section(form, '譜面情報')

        self.sb_notes = self._spinbox(0, 99999)
        form.addRow('ノーツ数:', self.sb_notes)

        self.cb_level = QComboBox()
        self.cb_level.addItem('')
        for i in range(1, 13):
            self.cb_level.addItem(str(i))
        form.addRow('レベル (1–12):', self.cb_level)

        # == ノーツレーダー ==
        self._section(form, 'ノーツレーダー')

        self.dsb_rader_notes   = self._dspinbox()
        self.dsb_rader_peak    = self._dspinbox()
        self.dsb_rader_scratch = self._dspinbox()
        self.dsb_rader_soflan  = self._dspinbox()
        self.dsb_rader_charge  = self._dspinbox()
        self.dsb_rader_chord   = self._dspinbox()
        form.addRow('Notes:',   self.dsb_rader_notes)
        form.addRow('Peak:',    self.dsb_rader_peak)
        form.addRow('Scratch:', self.dsb_rader_scratch)
        form.addRow('Soflan:',  self.dsb_rader_soflan)
        form.addRow('Charge:',  self.dsb_rader_charge)
        form.addRow('Chord:',   self.dsb_rader_chord)

        # == SP 非公式難易度 ==
        self._section(form, 'SP 非公式難易度')

        self.cb_sp12_hard  = self._unoff_combo()
        self.cb_sp12_clear = self._unoff_combo()
        self.le_sp12_title = QLineEdit()
        self.cb_sp11_hard  = self._unoff_combo()
        self.cb_sp11_clear = self._unoff_combo()
        form.addRow('SP12 Hard:',  self.cb_sp12_hard)
        form.addRow('SP12 Clear:', self.cb_sp12_clear)
        form.addRow('SP12 Title:', self.le_sp12_title)
        form.addRow('SP11 Hard:',  self.cb_sp11_hard)
        form.addRow('SP11 Clear:', self.cb_sp11_clear)

        # == CPI ==
        self._section(form, 'CPI')

        self.dsb_cpi_easy  = self._dspinbox()
        self.dsb_cpi_clear = self._dspinbox()
        self.dsb_cpi_hard  = self._dspinbox()
        self.dsb_cpi_exh   = self._dspinbox()
        self.dsb_cpi_fc    = self._dspinbox()
        form.addRow('Easy:',  self.dsb_cpi_easy)
        form.addRow('Clear:', self.dsb_cpi_clear)
        form.addRow('Hard:',  self.dsb_cpi_hard)
        form.addRow('EXH:',   self.dsb_cpi_exh)
        form.addRow('FC:',    self.dsb_cpi_fc)

        # == 片手難易度 ==
        self._section(form, '片手難易度')

        self.sb_katate_12 = self._spinbox(-1, 99)
        self.sb_katate_11 = self._spinbox(-1, 99)
        form.addRow('Katate 12:', self.sb_katate_12)
        form.addRow('Katate 11:', self.sb_katate_11)

        # == BPI ==
        self._section(form, 'BPI')

        self.sb_bpi_ave   = self._spinbox(-1, 99999)
        self.sb_bpi_top   = self._spinbox(-1, 99999)
        self.dsb_bpi_coef = self._dspinbox(lo=-999.0, hi=999.0)
        self.le_bpi_title = QLineEdit()
        form.addRow('Ave:',       self.sb_bpi_ave)
        form.addRow('Top:',       self.sb_bpi_top)
        form.addRow('Coef:',      self.dsb_bpi_coef)
        form.addRow('BPI Title:', self.le_bpi_title)

        # == DP 非公式難易度 ==
        self._section(form, 'DP 非公式難易度')

        self.dsb_dp_unofficial  = self._dspinbox(lo=-1.0, hi=30.0)
        self.dsb_dp_ereter_easy = self._dspinbox()
        self.dsb_dp_ereter_hard = self._dspinbox()
        self.dsb_dp_ereter_exh  = self._dspinbox()
        form.addRow('DP 非公式:',   self.dsb_dp_unofficial)
        form.addRow('ereter Easy:', self.dsb_dp_ereter_easy)
        form.addRow('ereter Hard:', self.dsb_dp_ereter_hard)
        form.addRow('ereter EXH:',  self.dsb_dp_ereter_exh)

        scroll.setWidget(inner)
        root.addWidget(scroll)

        # ---- ボタン行 ----
        btn_layout = QHBoxLayout()
        self.btn_save   = QPushButton('保存')
        self.btn_cancel = QPushButton('キャンセル')
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        root.addLayout(btn_layout)

        # ---- シグナル接続 ----
        self._ps_group.buttonClicked.connect(self._on_chart_changed)
        self._diff_group.buttonClicked.connect(self._on_chart_changed)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel.clicked.connect(self._on_cancel)

    # ---- ウィジェットファクトリ ----

    def _spinbox(self, lo: int = -1, hi: int = 9999) -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(lo, hi)
        if lo == -1:
            sb.setSpecialValueText('-')
        return sb

    def _dspinbox(self, lo: float = -1.0, hi: float = 9999.0) -> QDoubleSpinBox:
        dsb = QDoubleSpinBox()
        dsb.setRange(lo, hi)
        dsb.setDecimals(2)
        if lo == -1.0:
            dsb.setSpecialValueText('-')
        return dsb

    def _unoff_combo(self) -> QComboBox:
        cb = QComboBox()
        for name in UNOFF_NAMES:
            cb.addItem(name)
        return cb

    def _section(self, form: QFormLayout, title: str):
        lbl = QLabel(f'── {title} ──')
        lbl.setStyleSheet('color: gray; margin-top: 6px;')
        form.addRow(lbl)

    # =========================================================
    #  公開メソッド
    # =========================================================

    def set_title(self, title: Optional[str]):
        """メインウィンドウの選択が変わったときに呼ぶ。"""
        self.current_title = title
        self.title_label.setText(title if title else '(未選択)')
        self._load_chart()

    # =========================================================
    #  内部処理
    # =========================================================

    def _current_ps_diff(self) -> tuple[play_style, difficulty]:
        ps = play_style.sp if self.rb_sp.isChecked() else play_style.dp
        for d, rb in self.rb_diffs.items():
            if rb.isChecked():
                return ps, d
        return play_style.sp, difficulty.another

    def _on_chart_changed(self):
        self._load_chart()

    def _load_chart(self):
        if not self.current_title:
            self._clear_fields()
            self.chart_status_label.setText('')
            return
        ps, diff = self._current_ps_diff()
        chart = self.db.search(title=self.current_title, play_style=ps, difficulty=diff)
        if chart:
            self.chart_status_label.setText('')
            self._fill_fields(chart)
        else:
            self.chart_status_label.setText(
                '※ このチャートは DB に未登録です (保存すると新規作成)'
            )
            self.chart_status_label.setStyleSheet('color: orange;')
            self._clear_fields()

    # ---- フィールドクリア ----

    def _clear_fields(self):
        self.cb_version.setCurrentIndex(0)
        self.cb_pack.setCurrentIndex(0)
        self.sb_min_bpm.setValue(0)
        self.sb_max_bpm.setValue(0)
        self.sb_notes.setValue(0)
        self.cb_level.setCurrentIndex(0)
        for dsb in (
            self.dsb_rader_notes, self.dsb_rader_peak, self.dsb_rader_scratch,
            self.dsb_rader_soflan, self.dsb_rader_charge, self.dsb_rader_chord,
        ):
            dsb.setValue(dsb.minimum())
        for cb in (self.cb_sp12_hard, self.cb_sp12_clear, self.cb_sp11_hard, self.cb_sp11_clear):
            cb.setCurrentIndex(0)
        self.le_sp12_title.clear()
        for dsb in (
            self.dsb_cpi_easy, self.dsb_cpi_clear, self.dsb_cpi_hard,
            self.dsb_cpi_exh, self.dsb_cpi_fc,
        ):
            dsb.setValue(dsb.minimum())
        self.sb_katate_12.setValue(-1)
        self.sb_katate_11.setValue(-1)
        self.sb_bpi_ave.setValue(-1)
        self.sb_bpi_top.setValue(-1)
        self.dsb_bpi_coef.setValue(self.dsb_bpi_coef.minimum())
        self.le_bpi_title.clear()
        self.dsb_dp_unofficial.setValue(self.dsb_dp_unofficial.minimum())
        for dsb in (self.dsb_dp_ereter_easy, self.dsb_dp_ereter_hard, self.dsb_dp_ereter_exh):
            dsb.setValue(dsb.minimum())

    # ---- フィールド入力 ----

    def _fill_fields(self, c: OneSongInfo):
        # バージョン
        vname = version_str(c.version)
        idx = self.cb_version.findText(vname)
        self.cb_version.setCurrentIndex(idx if idx >= 0 else 0)

        # パック
        pname = pack_str(c.music_pack)
        idx = self.cb_pack.findText(pname)
        self.cb_pack.setCurrentIndex(idx if idx >= 0 else 0)

        # BPM
        self.sb_min_bpm.setValue(c.min_bpm or 0)
        self.sb_max_bpm.setValue(c.max_bpm or 0)

        # ノーツ数
        self.sb_notes.setValue(c.notes or 0)

        # レベル
        if c.level is not None:
            idx = self.cb_level.findText(str(c.level))
            self.cb_level.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self.cb_level.setCurrentIndex(0)

        # ノーツレーダー
        def fv(v): return v if v is not None else -1.0
        self.dsb_rader_notes.setValue(fv(c.rader_notes))
        self.dsb_rader_peak.setValue(fv(c.rader_peak))
        self.dsb_rader_scratch.setValue(fv(c.rader_scratch))
        self.dsb_rader_soflan.setValue(fv(c.rader_soflan))
        self.dsb_rader_charge.setValue(fv(c.rader_charge))
        self.dsb_rader_chord.setValue(fv(c.rader_chord))

        # SP 非公式難易度
        def set_unoff(cb, val):
            name = str(val) if val is not None else ''
            idx = cb.findText(name)
            cb.setCurrentIndex(idx if idx >= 0 else 0)

        set_unoff(self.cb_sp12_hard,  c.sp12_hard)
        set_unoff(self.cb_sp12_clear, c.sp12_clear)
        set_unoff(self.cb_sp11_hard,  c.sp11_hard)
        set_unoff(self.cb_sp11_clear, c.sp11_clear)
        self.le_sp12_title.setText(c.sp12_title or '')

        # CPI
        self.dsb_cpi_easy.setValue(fv(c.cpi_easy))
        self.dsb_cpi_clear.setValue(fv(c.cpi_clear))
        self.dsb_cpi_hard.setValue(fv(c.cpi_hard))
        self.dsb_cpi_exh.setValue(fv(c.cpi_exh))
        self.dsb_cpi_fc.setValue(fv(c.cpi_fc))

        # 片手難易度
        self.sb_katate_12.setValue(c.katate_12 if c.katate_12 is not None else -1)
        self.sb_katate_11.setValue(c.katate_11 if c.katate_11 is not None else -1)

        # BPI
        self.sb_bpi_ave.setValue(c.bpi_ave if c.bpi_ave is not None else -1)
        self.sb_bpi_top.setValue(c.bpi_top if c.bpi_top is not None else -1)
        self.dsb_bpi_coef.setValue(fv(c.bpi_coef))
        self.le_bpi_title.setText(c.bpi_title or '')

        # DP 非公式難易度
        # dp_unofficial はDBでは float として格納されている
        dp_unoff = c.dp_unofficial
        if dp_unoff is not None:
            try:
                self.dsb_dp_unofficial.setValue(float(dp_unoff))
            except (ValueError, TypeError):
                self.dsb_dp_unofficial.setValue(-1.0)
        else:
            self.dsb_dp_unofficial.setValue(-1.0)

        self.dsb_dp_ereter_easy.setValue(fv(c.dp_ereter_easy))
        self.dsb_dp_ereter_hard.setValue(fv(c.dp_ereter_hard))
        self.dsb_dp_ereter_exh.setValue(fv(c.dp_ereter_exh))

    # ---- 保存 ----

    def _on_save(self):
        if not self.current_title:
            return
        ps, diff = self._current_ps_diff()
        chart = self.db.search(title=self.current_title, play_style=ps, difficulty=diff)
        if chart is None:
            lt = self.cb_level.currentText()
            chart = OneSongInfo(
                title=self.current_title,
                play_style=ps,
                difficulty=diff,
                level=int(lt) if lt else None,
            )

        # バージョン
        vname = self.cb_version.currentText()
        chart.version = VERSION_NAME_TO_NUM.get(vname) if vname else None

        # パック
        pack_name = self.cb_pack.currentText()
        if pack_name:
            try:
                chart.music_pack = music_pack[pack_name]
            except KeyError:
                chart.music_pack = None
        else:
            chart.music_pack = None

        # BPM
        chart.min_bpm = self.sb_min_bpm.value() or None
        chart.max_bpm = self.sb_max_bpm.value() or None

        # ノーツ数
        chart.notes = self.sb_notes.value() or None

        # レベル
        lt = self.cb_level.currentText()
        chart.level = int(lt) if lt else chart.level

        # ノーツレーダー
        def gf(dsb: QDoubleSpinBox):
            v = dsb.value()
            return None if v <= dsb.minimum() + 0.001 else v

        def gi(sb: QSpinBox):
            v = sb.value()
            return None if v == -1 else v

        chart.rader_notes   = gf(self.dsb_rader_notes)
        chart.rader_peak    = gf(self.dsb_rader_peak)
        chart.rader_scratch = gf(self.dsb_rader_scratch)
        chart.rader_soflan  = gf(self.dsb_rader_soflan)
        chart.rader_charge  = gf(self.dsb_rader_charge)
        chart.rader_chord   = gf(self.dsb_rader_chord)

        # SP 非公式難易度
        def get_unoff(cb: QComboBox):
            name = cb.currentText()
            return UNOFF_NAME_TO_ENUM.get(name) if name else None

        chart.sp12_hard  = get_unoff(self.cb_sp12_hard)
        chart.sp12_clear = get_unoff(self.cb_sp12_clear)
        chart.sp11_hard  = get_unoff(self.cb_sp11_hard)
        chart.sp11_clear = get_unoff(self.cb_sp11_clear)
        chart.sp12_title = self.le_sp12_title.text() or None

        # CPI
        chart.cpi_easy  = gf(self.dsb_cpi_easy)
        chart.cpi_clear = gf(self.dsb_cpi_clear)
        chart.cpi_hard  = gf(self.dsb_cpi_hard)
        chart.cpi_exh   = gf(self.dsb_cpi_exh)
        chart.cpi_fc    = gf(self.dsb_cpi_fc)

        # 片手難易度
        chart.katate_12 = gi(self.sb_katate_12)
        chart.katate_11 = gi(self.sb_katate_11)

        # BPI
        chart.bpi_ave   = gi(self.sb_bpi_ave)
        chart.bpi_top   = gi(self.sb_bpi_top)
        chart.bpi_coef  = gf(self.dsb_bpi_coef)
        chart.bpi_title = self.le_bpi_title.text() or None

        # DP 非公式難易度
        chart.dp_unofficial  = gf(self.dsb_dp_unofficial)
        chart.dp_ereter_easy = gf(self.dsb_dp_ereter_easy)
        chart.dp_ereter_hard = gf(self.dsb_dp_ereter_hard)
        chart.dp_ereter_exh  = gf(self.dsb_dp_ereter_exh)

        self.db.add(chart)
        self.db.save()

        self.chart_status_label.setText(
            f'保存しました: {ps.name.upper()} {diff.name.upper()}'
        )
        self.chart_status_label.setStyleSheet('color: green;')
        self.saved.emit()

    # ---- キャンセル ----

    def _on_cancel(self):
        """変更を破棄してリロード。"""
        self._load_chart()
        self.chart_status_label.setText('変更を破棄しました')
        self.chart_status_label.setStyleSheet('color: gray;')


# =========================================================
#  PropertiesPanel – 右上のプロパティ表示
# =========================================================

class PropertiesPanel(QGroupBox):
    """選択中の曲の概要を表示し、編集ボタンを持つパネル。"""

    edit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__('プロパティ', parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        grid = QGridLayout()

        def lbl(bold=False) -> QLabel:
            l = QLabel('-')
            if bold:
                l.setStyleSheet('font-weight: bold;')
            l.setWordWrap(True)
            return l

        self.lbl_title   = lbl(bold=True)
        self.lbl_sp      = lbl()
        self.lbl_dp      = lbl()
        self.lbl_version = lbl()
        self.lbl_pack    = lbl()

        grid.addWidget(QLabel('曲名:'),   0, 0, Qt.AlignTop)
        grid.addWidget(self.lbl_title,   0, 1)
        grid.addWidget(QLabel('SP:'),     1, 0, Qt.AlignTop)
        grid.addWidget(self.lbl_sp,      1, 1)
        grid.addWidget(QLabel('DP:'),     2, 0, Qt.AlignTop)
        grid.addWidget(self.lbl_dp,      2, 1)
        grid.addWidget(QLabel('Version:'),3, 0, Qt.AlignTop)
        grid.addWidget(self.lbl_version, 3, 1)
        grid.addWidget(QLabel('Pack:'),   4, 0, Qt.AlignTop)
        grid.addWidget(self.lbl_pack,    4, 1)
        grid.setColumnStretch(1, 1)

        layout.addLayout(grid)

        self.btn_edit = QPushButton('編集...')
        self.btn_edit.clicked.connect(self.edit_requested)
        self.btn_edit.setEnabled(False)
        layout.addWidget(self.btn_edit)
        layout.addStretch()

    def update_song(self, title: Optional[str], charts: dict):
        """
        charts: {(play_style, difficulty): OneSongInfo}
        """
        if title is None:
            self.lbl_title.setText('-')
            self.lbl_sp.setText('-')
            self.lbl_dp.setText('-')
            self.lbl_version.setText('-')
            self.lbl_pack.setText('-')
            self.btn_edit.setEnabled(False)
            return

        self.lbl_title.setText(title)

        # SP レベル表示 (B N H A L)
        sp_parts = []
        for label, d in DIFF_LABELS:
            c = charts.get((play_style.sp, d))
            if c:
                sp_parts.append(f'{label}:{level_str(c.level)}')
        self.lbl_sp.setText('  '.join(sp_parts) if sp_parts else '-')

        # DP レベル表示 (N H A L, Beginner はなし)
        dp_parts = []
        for label, d in DIFF_LABELS[1:]:
            c = charts.get((play_style.dp, d))
            if c:
                dp_parts.append(f'{label}:{level_str(c.level)}')
        self.lbl_dp.setText('  '.join(dp_parts) if dp_parts else '-')

        # バージョン (最初の非 None)
        ver = next((c.version for c in charts.values() if c.version is not None), None)
        self.lbl_version.setText(version_str(ver) or '-')

        # パック (最初の非 None)
        pk = next((c.music_pack for c in charts.values() if c.music_pack is not None), None)
        self.lbl_pack.setText(pack_str(pk) or '-')

        self.btn_edit.setEnabled(True)


# =========================================================
#  FilterPanel – 左上のフィルタ・検索パネル
# =========================================================

class FilterPanel(QGroupBox):
    """プレースタイル・レベル・曲名検索でリストを絞り込むパネル。"""

    filter_changed = Signal()

    def __init__(self, parent=None):
        super().__init__('フィルタ', parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # プレースタイル
        ps_layout = QHBoxLayout()
        self.rb_all = QRadioButton('ALL')
        self.rb_sp  = QRadioButton('SP')
        self.rb_dp  = QRadioButton('DP')
        self.rb_all.setChecked(True)
        self._ps_group = QButtonGroup(self)
        for i, rb in enumerate([self.rb_all, self.rb_sp, self.rb_dp]):
            self._ps_group.addButton(rb, i)
            ps_layout.addWidget(rb)
        layout.addLayout(ps_layout)

        # レベル
        lv_layout = QHBoxLayout()
        lv_layout.addWidget(QLabel('Level:'))
        self.cb_level = QComboBox()
        self.cb_level.addItem('ALL')
        for i in range(1, 13):
            self.cb_level.addItem(str(i))
        lv_layout.addWidget(self.cb_level)
        lv_layout.addStretch()
        layout.addLayout(lv_layout)

        # 曲名検索
        layout.addWidget(QLabel('検索:'))
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText('曲名で検索...')
        layout.addWidget(self.le_search)

        layout.addStretch()

        self._ps_group.buttonClicked.connect(self.filter_changed)
        self.cb_level.currentIndexChanged.connect(self.filter_changed)
        self.le_search.textChanged.connect(self.filter_changed)

    def ps_filter(self) -> Optional[play_style]:
        id_ = self._ps_group.checkedId()
        if id_ == 1:
            return play_style.sp
        if id_ == 2:
            return play_style.dp
        return None

    def level_filter(self) -> Optional[int]:
        txt = self.cb_level.currentText()
        return None if txt == 'ALL' else int(txt)

    def search_text(self) -> str:
        return self.le_search.text().strip()


# =========================================================
#  MainWindow
# =========================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Database Editor – songinfo.infdc')
        self.resize(1100, 750)

        print('Loading database...')
        self.db = SongDatabase()
        self._build_title_data()
        self._setup_ui()
        self._apply_filter()

    # ---- データ構築 ----

    def _build_title_data(self):
        """曲名をキーとして全チャートを集約する。"""
        self.title_data: dict[str, dict] = {}
        for chart in self.db.songs.values():
            t = chart.title
            if t not in self.title_data:
                self.title_data[t] = {'charts': {}}
            self.title_data[t]['charts'][(chart.play_style, chart.difficulty)] = chart

    # ---- UI 構築 ----

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 上部: フィルタ(左) + プロパティ(右)
        top_splitter = QSplitter(Qt.Horizontal)

        self.filter_panel = FilterPanel()
        self.filter_panel.setMaximumWidth(260)
        self.filter_panel.filter_changed.connect(self._apply_filter)
        top_splitter.addWidget(self.filter_panel)

        self.props_panel = PropertiesPanel()
        self.props_panel.edit_requested.connect(self._on_edit_requested)
        top_splitter.addWidget(self.props_panel)
        top_splitter.setStretchFactor(1, 1)

        # 下部: リストビュー
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(['曲名', 'Version', 'Music Pack'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        # 垂直スプリッタ (上部 / リスト)
        vsplit = QSplitter(Qt.Vertical)
        vsplit.addWidget(top_splitter)
        vsplit.addWidget(self.table)
        vsplit.setStretchFactor(1, 1)
        vsplit.setSizes([240, 510])

        main_layout.addWidget(vsplit)

        # モードレス編集ダイアログ
        self.edit_dialog = EditDialog(self.db, self)
        self.edit_dialog.saved.connect(self._on_db_saved)

    # =========================================================
    #  フィルタ & テーブル更新
    # =========================================================

    def _apply_filter(self):
        ps_f  = self.filter_panel.ps_filter()
        lv_f  = self.filter_panel.level_filter()
        srch  = self.filter_panel.search_text().lower()

        # 現在の選択を保持
        selected_title = self._selected_title()

        # フィルタ適用
        filtered: list[str] = []
        for title, data in self.title_data.items():
            if srch and srch not in title.lower():
                continue
            if ps_f is not None or lv_f is not None:
                ok = any(
                    (ps_f is None or ps == ps_f)
                    and (lv_f is None or (c.level is not None and c.level == lv_f))
                    for (ps, _), c in data['charts'].items()
                )
                if not ok:
                    continue
            filtered.append(title)

        filtered.sort()

        # テーブル更新 (ソートを一時停止)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(filtered))
        for row, title in enumerate(filtered):
            charts = self.title_data[title]['charts']
            ver = next((c.version for c in charts.values() if c.version is not None), None)
            pk  = next((c.music_pack for c in charts.values() if c.music_pack is not None), None)
            self.table.setItem(row, 0, QTableWidgetItem(title))
            self.table.setItem(row, 1, QTableWidgetItem(version_str(ver)))
            self.table.setItem(row, 2, QTableWidgetItem(pack_str(pk)))
        self.table.setSortingEnabled(True)

        # 選択を復元
        if selected_title:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item and item.text() == selected_title:
                    self.table.selectRow(row)
                    break

    # =========================================================
    #  選択変更ハンドラ
    # =========================================================

    def _selected_title(self) -> Optional[str]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _on_selection_changed(self):
        title = self._selected_title()
        if title is None:
            self.props_panel.update_song(None, {})
            self.edit_dialog.set_title(None)
            return
        data = self.title_data.get(title, {'charts': {}})
        self.props_panel.update_song(title, data['charts'])
        self.edit_dialog.set_title(title)

    # =========================================================
    #  編集ダイアログ
    # =========================================================

    def _on_edit_requested(self):
        self.edit_dialog.show()
        self.edit_dialog.raise_()
        self.edit_dialog.activateWindow()

    def _on_db_saved(self):
        """EditDialog が保存したあとに呼ばれる。title_data を再構築してリストを更新。"""
        self._build_title_data()
        self._apply_filter()
        # プロパティパネルも更新
        title = self._selected_title()
        if title:
            data = self.title_data.get(title, {'charts': {}})
            self.props_panel.update_song(title, data['charts'])


# =========================================================
#  エントリーポイント
# =========================================================

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('DB Editor')
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
