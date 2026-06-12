"""楽曲DBのポータルマスタ整合チェック＆変換ツール。

通常実行 (CLI):
    uv run python -m misc.manage_db

GUI実行:
    uv run python -m misc.manage_db --gui

対話モード（CLI処理後にREPLへ）:
    uv run python -m misc.manage_db --interactive
    uv run python -im misc.manage_db

対話モードで使える変数:
    portal_master    list[dict]  ポータルマスタ（title/music_id/charts）
    portal_titles    set[str]    ポータル収録曲名セット
    musiclist        dict        musiclist.pkl の内容そのまま
    musiclist_v2     dict        フィルタ済み（musiclistv2.sdvxh と同内容）
    matched_titles   list[str]   両方にある曲名
    unmatched_titles list[str]   pklにあってポータルにない曲名
"""
from __future__ import annotations

import argparse
import bz2
import code
import pickle
import sys
import unicodedata
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import Config
from src.portal_manager import PortalManager

_MUSICLIST_V1 = Path('resources') / 'musiclist.pkl'
_MUSICLIST_V2 = Path('resources') / 'musiclistv2.sdvxh'

# CLI対話モード用モジュールレベル変数
portal_master:    list = []
portal_titles:    set  = set()
musiclist:        dict = {}
musiclist_v2:     dict = {}
matched_titles:   list = []
unmatched_titles: list = []


# ── ファイルI/O ──────────────────────────────────────────────────────────────

def _load_pkl(path: Path) -> dict:
    with open(path, 'rb') as f:
        return pickle.load(f)


def _load_sdvxh(path: Path) -> dict:
    with bz2.open(path, 'rb') as f:
        return pickle.load(f)


def _save_sdvxh(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with bz2.open(path, 'wb') as f:
        pickle.dump(data, f)


def _filter_by_title(d: dict, title_set: set) -> dict:
    return {t: v for t, v in d.items() if t in title_set}


def _filter_diff_dict(d: dict, title_set: set) -> dict:
    return {diff: _filter_by_title(by_title, title_set) for diff, by_title in d.items()}


# ── DB操作 ───────────────────────────────────────────────────────────────────

def add_song_to_v2(old_title: str, new_title: str, v1: dict, v2: dict) -> None:
    """v1のold_title下のデータをv2のnew_title下に追加する（インプレース）。"""
    info = v1.get('titles', {}).get(old_title)
    if info:
        new_info = list(info)
        new_info[0] = new_title
        if old_title != new_title:
            if len(new_info) > 7:
                new_info[7] = old_title
            else:
                new_info.append(old_title)
        v2.setdefault('titles', {})[new_title] = new_info

    for section in ('jacket', 'info'):
        for diff_key in ('nov', 'adv', 'exh', 'APPEND'):
            h = v1.get(section, {}).get(diff_key, {}).get(old_title)
            if h:
                v2.setdefault(section, {}).setdefault(diff_key, {})[new_title] = h

    for key, val in v1.items():
        if key.startswith('gradeS_lv') and isinstance(val, dict):
            if old_title in val:
                v2.setdefault(key, {})[new_title] = val[old_title]


# ── GUI用ユーティリティ ──────────────────────────────────────────────────────

_DIFF_KEYS = [
    ('nov',    'NOV',    3),
    ('adv',    'ADV',    4),
    ('exh',    'EXH',    5),
    ('APPEND', 'APPEND', 6),
]

_DIFF_NAME_TO_KEY = {'NOV': 'nov', 'ADV': 'adv', 'EXH': 'exh', 'APPEND': 'APPEND'}


def _build_v2_hashes(v2: dict) -> set:
    """v2のjacketに登録済みの (diff_key, hash_hex) セットを返す。"""
    result = set()
    for diff_key, by_title in v2.get('jacket', {}).items():
        for h in by_title.values():
            if h:
                result.add((diff_key, h))
    return result


def _build_rows(ml: dict, exclude_set: set | None = None) -> list[tuple]:
    """musiclist dict から (title, diff_name, level, hash_hex) のリストを構築する。

    exclude_set: このセットに含まれるタイトルを除外する（unmatched表示用）。
    """
    rows = []
    titles_dict = ml.get('titles', {})
    jacket_dict = ml.get('jacket', {})

    for title, info in titles_dict.items():
        if exclude_set is not None and title in exclude_set:
            continue
        for db_key, diff_name, lv_idx in _DIFF_KEYS:
            level = info[lv_idx] if len(info) > lv_idx else 0
            if not level:
                continue
            hash_hex = jacket_dict.get(db_key, {}).get(title, '')
            rows.append((title, diff_name, level, hash_hex))
    return rows


def _chart_diff_keys(ml: dict, title: str) -> list[str]:
    """指定曲に存在する譜面のDBキー一覧を返す。"""
    info = ml.get('titles', {}).get(title)
    if not info:
        return []
    result = []
    for db_key, _diff_name, lv_idx in _DIFF_KEYS:
        level = info[lv_idx] if len(info) > lv_idx else 0
        if level:
            result.append(db_key)
    return result


def _existing_jacket_hashes(ml: dict, title: str) -> list[str]:
    """指定曲に登録済みのjacket hash一覧を返す。"""
    hashes = []
    jacket = ml.get('jacket', {})
    for db_key in _chart_diff_keys(ml, title):
        h = jacket.get(db_key, {}).get(title, '')
        if h:
            hashes.append(h)
    return hashes


def update_jacket_hash(v2: dict, title: str, diff_name: str, hash_hex: str) -> tuple[int, str]:
    """v2のjacket hashを更新する。

    その曲にhashが1つも無い場合は全譜面へコピーし、既にある場合は選択譜面のみ更新する。
    Returns:
        (更新した譜面数, 'all' | 'selected')
    """
    diff_key = _DIFF_NAME_TO_KEY.get(diff_name)
    if not diff_key:
        raise ValueError(f'未対応の難易度です: {diff_name}')

    target_keys = _chart_diff_keys(v2, title)
    if not target_keys:
        raise ValueError(f'譜面情報が見つかりません: {title}')

    scope = 'selected'
    if not _existing_jacket_hashes(v2, title):
        scope = 'all'
    else:
        target_keys = [diff_key]

    for target_key in target_keys:
        v2.setdefault('jacket', {}).setdefault(target_key, {})[title] = hash_hex
    return len(target_keys), scope


def _normalize_search_text(text: str) -> str:
    """検索用に半角カナ・全角カナ・ひらがなを寄せる。"""
    normalized = unicodedata.normalize('NFKC', str(text)).lower()
    chars = []
    for ch in normalized:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        else:
            chars.append(ch)
    return ''.join(chars)


# ── CLIモード ────────────────────────────────────────────────────────────────

def run() -> None:
    """データ取得・照合・保存をまとめて行い、結果をモジュール変数に書き込む。"""
    global portal_master, portal_titles, musiclist, musiclist_v2
    global matched_titles, unmatched_titles

    config = Config()
    if not config.portal_token:
        print('[ERROR] config.json に portal_token が設定されていません。')
        sys.exit(1)

    pm = PortalManager(token=config.portal_token)
    print('ポータルマスタを受信中...')
    ok = pm.get_musiclist()
    if not ok or not pm.master_db:
        print('[ERROR] ポータルマスタの受信に失敗しました。')
        sys.exit(1)

    portal_master = pm.master_db
    portal_titles = {m.get('title', '') for m in portal_master if m.get('title')}
    print(f'  ポータル収録曲数: {len(portal_titles)}')

    if not _MUSICLIST_V1.exists():
        print(f'[ERROR] {_MUSICLIST_V1} が見つかりません。')
        sys.exit(1)

    print(f'{_MUSICLIST_V1} を読み込み中...')
    musiclist = _load_pkl(_MUSICLIST_V1)
    all_titles = list(musiclist.get('titles', {}).keys())
    print(f'  musiclist.pkl 収録曲数: {len(all_titles)}')

    matched_titles   = [t for t in all_titles if t in portal_titles]
    unmatched_titles = [t for t in all_titles if t not in portal_titles]

    print(f'\n  ポータルマスタにあり  : {len(matched_titles)} 曲')
    print(f'  ポータルマスタになし  : {len(unmatched_titles)} 曲')

    if unmatched_titles:
        print('\n' + '=' * 60)
        print('【ポータルマスタに存在しない曲（musiclistv2.sdvxh に未登録）】')
        print('=' * 60)
        for i, title in enumerate(sorted(unmatched_titles), 1):
            info   = musiclist.get('titles', {}).get(title, [])
            artist = info[1] if len(info) > 1 else '?'
            print(f'  {i:4d}. {title}  [{artist}]')
        print('=' * 60)

    mset = set(matched_titles)
    dst: dict = {}
    dst['titles'] = _filter_by_title(musiclist.get('titles', {}), mset)
    for key in ('jacket', 'info'):
        if key in musiclist:
            dst[key] = _filter_diff_dict(musiclist[key], mset)
    for key, val in musiclist.items():
        if key.startswith('gradeS_lv') and isinstance(val, dict):
            dst[key] = _filter_by_title(val, mset)

    musiclist_v2 = dst
    print(f'\nmusiclistv2.sdvxh を保存中... ({len(musiclist_v2["titles"])} 曲)')
    _save_sdvxh(musiclist_v2, _MUSICLIST_V2)
    print(f'  → 保存完了: {_MUSICLIST_V2}')
    print('完了。')


# ── GUIモード ────────────────────────────────────────────────────────────────

def launch_gui() -> None:
    try:
        from PySide6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QSplitter,
            QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton, QCheckBox,
            QLineEdit, QLabel, QPushButton, QTableView,
            QHeaderView, QAbstractItemView, QMessageBox, QStatusBar, QInputDialog,
        )
        from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QThread, Signal, QSortFilterProxyModel
        from PySide6.QtGui import QColor
    except ImportError:
        print('[ERROR] PySide6 がインストールされていません。')
        sys.exit(1)

    # ── テーブルモデル ────────────────────────────────────────────────────────

    class SdvxTableModel(QAbstractTableModel):
        _HEADERS = ['曲名', '難易度', 'レベル', 'image_hash']

        _ALL_DIFFS = frozenset({'NOV', 'ADV', 'EXH', 'APPEND'})

        def __init__(self):
            super().__init__()
            self._rows: list[tuple] = []
            self._filtered: list[tuple] = []
            self._search = ''
            self._v2_hashes: set = set()
            self._diff_enabled: frozenset = self._ALL_DIFFS

        def set_diff_filter(self, enabled_diffs: set):
            self.beginResetModel()
            self._diff_enabled = frozenset(enabled_diffs)
            self._apply_filter()
            self.endResetModel()

        def set_v2_hashes(self, hashes: set):
            self._v2_hashes = hashes
            # 背景色変化のためビュー全体を再描画
            if self._filtered:
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(len(self._filtered) - 1, 3),
                    [Qt.BackgroundRole],
                )

        def set_rows(self, rows: list[tuple]):
            self.beginResetModel()
            self._rows = rows
            self._apply_filter()
            self.endResetModel()

        def set_search(self, text: str):
            self.beginResetModel()
            self._search = _normalize_search_text(text)
            self._apply_filter()
            self.endResetModel()

        def _apply_filter(self):
            rows = self._rows
            if self._diff_enabled != self._ALL_DIFFS:
                rows = [r for r in rows if r[1] in self._diff_enabled]
            if self._search:
                rows = [r for r in rows if self._search in _normalize_search_text(r[0])]
            self._filtered = rows

        def rowCount(self, parent=QModelIndex()):
            return len(self._filtered)

        def columnCount(self, parent=QModelIndex()):
            return 4

        def data(self, index, role=Qt.DisplayRole):
            if not index.isValid():
                return None
            row = self._filtered[index.row()]
            if role == Qt.DisplayRole:
                return str(row[index.column()])
            if role == Qt.BackgroundRole and self._v2_hashes:
                diff_key = _DIFF_NAME_TO_KEY.get(row[1], row[1].lower())
                if (diff_key, row[3]) in self._v2_hashes:
                    return QColor(200, 200, 200)
            return None

        def headerData(self, section, orientation, role=Qt.DisplayRole):
            if orientation == Qt.Horizontal and role == Qt.DisplayRole:
                return self._HEADERS[section]
            return None

        def get_row(self, row: int) -> tuple:
            return self._filtered[row]

    class PortalTableModel(QAbstractTableModel):
        _COLS    = ['title', 'title_ruby', 'artist', 'artist_ruby', 'music_id']
        _HEADERS = ['曲名', 'よみ', 'アーティスト', 'アーティストよみ', 'music_id']
        _SEARCH_FIELDS = ('title', 'title_ruby', 'artist', 'artist_ruby')

        def __init__(self):
            super().__init__()
            self._data: list[dict] = []
            self._filtered: list[dict] = []
            self._search = ''

        def set_data(self, data: list[dict]):
            self.beginResetModel()
            self._data = data
            self._apply_filter()
            self.endResetModel()

        def set_search(self, text: str):
            self.beginResetModel()
            self._search = _normalize_search_text(text)
            self._apply_filter()
            self.endResetModel()

        def _apply_filter(self):
            if not self._search:
                self._filtered = self._data[:]
            else:
                s = self._search
                self._filtered = [
                    m for m in self._data
                    if any(s in _normalize_search_text(m.get(f, '')) for f in self._SEARCH_FIELDS)
                ]

        def rowCount(self, parent=QModelIndex()):
            return len(self._filtered)

        def columnCount(self, parent=QModelIndex()):
            return len(self._COLS)

        def data(self, index, role=Qt.DisplayRole):
            if not index.isValid() or role != Qt.DisplayRole:
                return None
            return str(self._filtered[index.row()].get(self._COLS[index.column()], ''))

        def headerData(self, section, orientation, role=Qt.DisplayRole):
            if orientation == Qt.Horizontal and role == Qt.DisplayRole:
                return self._HEADERS[section]
            return None

        def get_row(self, row: int) -> dict:
            return self._filtered[row]

    # ── ポータル取得スレッド ──────────────────────────────────────────────────

    class FetchThread(QThread):
        done  = Signal(list)
        error = Signal(str)

        def __init__(self, token: str):
            super().__init__()
            self._token = token

        def run(self):
            pm = PortalManager(token=self._token)
            ok = pm.get_musiclist()
            if ok and pm.master_db:
                self.done.emit(pm.master_db)
            else:
                self.error.emit('ポータルマスタの取得に失敗しました')

    # ── ソートプロキシ ────────────────────────────────────────────────────────

    class SdvxSortProxy(QSortFilterProxyModel):
        def lessThan(self, left, right):
            # レベル列（2）は数値比較
            if left.column() == 2:
                try:
                    return int(left.data() or 0) < int(right.data() or 0)
                except (ValueError, TypeError):
                    pass
            return super().lessThan(left, right)

    # ── メインウィンドウ ──────────────────────────────────────────────────────

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('SDVX Helper DB管理')
            self.resize(1400, 900)

            self._v1: dict = {}
            self._v2: dict = {}
            self._portal_list: list = []
            self._portal_title_set: set = set()
            self._fetch_thread: FetchThread | None = None

            self._sdvx_model   = SdvxTableModel()
            self._sdvx_proxy   = SdvxSortProxy()
            self._sdvx_proxy.setSourceModel(self._sdvx_model)
            self._portal_model = PortalTableModel()

            self._setup_ui()
            self._load_local()
            self._start_fetch()

        # ── UI構築 ────────────────────────────────────────────────────────────

        def _setup_ui(self):
            central = QWidget()
            self.setCentralWidget(central)
            root = QVBoxLayout(central)
            root.setContentsMargins(6, 6, 6, 6)

            vsplit = QSplitter(Qt.Vertical)
            root.addWidget(vsplit)

            # ── 上部（左右分割） ──────────────────────────────────────────────
            upper_container = QWidget()
            upper_layout = QHBoxLayout(upper_container)
            upper_layout.setContentsMargins(0, 0, 0, 0)

            hsplit = QSplitter(Qt.Horizontal)
            upper_layout.addWidget(hsplit)

            # 左: 検索バー・フィルタ・ボタン群
            left = QWidget()
            left.setMinimumWidth(240)
            left.setMaximumWidth(360)
            ll = QVBoxLayout(left)
            ll.setSpacing(6)

            ll.addWidget(QLabel('SDVX DB 検索'))
            self._sdvx_search = QLineEdit()
            self._sdvx_search.setPlaceholderText('曲名で絞り込み（大文字小文字不問）')
            self._sdvx_search.textChanged.connect(self._on_sdvx_search)
            ll.addWidget(self._sdvx_search)

            filter_box = QGroupBox('表示対象')
            filter_layout = QVBoxLayout(filter_box)
            self._rb_v1        = QRadioButton('v1 (musiclist.pkl)')
            self._rb_v2        = QRadioButton('v2 (musiclistv2.sdvxh)')
            self._rb_unmatched = QRadioButton('v1にあってマスタにない曲')
            self._rb_v1.setChecked(True)
            for rb in (self._rb_v1, self._rb_v2, self._rb_unmatched):
                rb.toggled.connect(self._on_filter_changed)
                filter_layout.addWidget(rb)
            ll.addWidget(filter_box)

            diff_box = QGroupBox('難易度フィルタ')
            diff_layout = QHBoxLayout(diff_box)
            diff_layout.setSpacing(4)
            self._cb_nov    = QCheckBox('NOV')
            self._cb_adv    = QCheckBox('ADV')
            self._cb_exh    = QCheckBox('EXH')
            self._cb_append = QCheckBox('最上位\n(MXM/INF/...)')
            for cb in (self._cb_nov, self._cb_adv, self._cb_exh, self._cb_append):
                cb.setChecked(True)
                cb.stateChanged.connect(self._on_diff_filter_changed)
                diff_layout.addWidget(cb)
            ll.addWidget(diff_box)

            self._btn_fetch = QPushButton('ポータルマスタを再取得')
            self._btn_fetch.clicked.connect(self._start_fetch)
            ll.addWidget(self._btn_fetch)

            self._btn_add = QPushButton('選択曲をv2に追加\n（マスタ曲名でキー）')
            self._btn_add.setEnabled(False)
            self._btn_add.setToolTip(
                '「v1にあってマスタにない曲」表示中に\n'
                'SDVX DB行とポータルマスタ行を両方選択してクリック'
            )
            self._btn_add.clicked.connect(self._on_add_to_v2)
            ll.addWidget(self._btn_add)

            self._btn_edit_hash = QPushButton('選択hashを編集')
            self._btn_edit_hash.setEnabled(False)
            self._btn_edit_hash.setToolTip(
                'v2表示中にSDVX DB行を選択してクリック\n'
                '曲にhashが未登録なら全譜面へ、登録済みなら選択譜面だけ更新'
            )
            self._btn_edit_hash.clicked.connect(self._on_edit_hash)
            ll.addWidget(self._btn_edit_hash)

            ll.addStretch()
            hsplit.addWidget(left)

            # 右: ポータルマスタ検索 + テーブル
            right = QWidget()
            rl = QVBoxLayout(right)
            rl.setSpacing(4)
            rl.setContentsMargins(0, 0, 0, 0)

            portal_header = QHBoxLayout()
            portal_header.addWidget(QLabel('ポータルマスタ'))
            self._portal_count_label = QLabel('')
            portal_header.addWidget(self._portal_count_label)
            portal_header.addStretch()
            rl.addLayout(portal_header)

            self._portal_search = QLineEdit()
            self._portal_search.setPlaceholderText('曲名 / よみ / アーティスト / アーティストよみ で絞り込み')
            self._portal_search.textChanged.connect(self._on_portal_search)
            rl.addWidget(self._portal_search)

            self._portal_view = QTableView()
            self._portal_view.setModel(self._portal_model)
            self._portal_view.setSelectionBehavior(QAbstractItemView.SelectRows)
            self._portal_view.setSelectionMode(QAbstractItemView.SingleSelection)
            self._portal_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self._portal_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
            self._portal_view.verticalHeader().setDefaultSectionSize(22)
            self._portal_view.verticalHeader().setVisible(False)
            self._portal_view.selectionModel().selectionChanged.connect(self._update_add_button)
            rl.addWidget(self._portal_view)

            hsplit.addWidget(right)
            hsplit.setSizes([280, 900])

            vsplit.addWidget(upper_container)

            # ── 下部: SDVX DBテーブル ─────────────────────────────────────────
            lower = QWidget()
            low_l = QVBoxLayout(lower)
            low_l.setContentsMargins(0, 0, 0, 0)
            low_l.setSpacing(4)

            self._sdvx_label = QLabel('SDVX DB (v1)')
            low_l.addWidget(self._sdvx_label)

            self._sdvx_view = QTableView()
            self._sdvx_view.setModel(self._sdvx_proxy)
            self._sdvx_view.setSortingEnabled(True)
            self._sdvx_view.sortByColumn(0, Qt.AscendingOrder)
            self._sdvx_view.setSelectionBehavior(QAbstractItemView.SelectRows)
            self._sdvx_view.setSelectionMode(QAbstractItemView.SingleSelection)
            self._sdvx_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self._sdvx_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            self._sdvx_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            self._sdvx_view.verticalHeader().setDefaultSectionSize(22)
            self._sdvx_view.verticalHeader().setVisible(False)
            self._sdvx_view.selectionModel().selectionChanged.connect(self._update_add_button)
            low_l.addWidget(self._sdvx_view)

            vsplit.addWidget(lower)
            vsplit.setSizes([360, 540])

            self.setStatusBar(QStatusBar())

        # ── データ読み込み ────────────────────────────────────────────────────

        def _load_local(self):
            if _MUSICLIST_V1.exists():
                try:
                    self._v1 = _load_pkl(_MUSICLIST_V1)
                    self.statusBar().showMessage(
                        f'v1 読み込み完了: {len(self._v1.get("titles", {}))} 曲'
                    )
                except Exception as e:
                    QMessageBox.warning(self, 'エラー', f'v1 読み込み失敗:\n{e}')
            else:
                self.statusBar().showMessage(f'{_MUSICLIST_V1} が見つかりません')

            if _MUSICLIST_V2.exists():
                try:
                    self._v2 = _load_sdvxh(_MUSICLIST_V2)
                except Exception:
                    self._v2 = {}
            else:
                self._v2 = {}

            self._refresh_sdvx_table()

        def _start_fetch(self):
            config = Config()
            if not config.portal_token:
                self.statusBar().showMessage('portal_token が未設定です（config.json を確認）')
                return
            self._btn_fetch.setEnabled(False)
            self.statusBar().showMessage('ポータルマスタを取得中...')
            self._fetch_thread = FetchThread(config.portal_token)
            self._fetch_thread.done.connect(self._on_portal_fetched)
            self._fetch_thread.error.connect(self._on_portal_error)
            self._fetch_thread.start()

        def _on_portal_fetched(self, master_db: list):
            self._portal_list      = master_db
            self._portal_title_set = {m.get('title', '') for m in master_db if m.get('title')}
            self._portal_model.set_data(master_db)
            self._portal_count_label.setText(f'({len(master_db)} 曲)')
            self._btn_fetch.setEnabled(True)
            self.statusBar().showMessage(f'ポータルマスタ取得完了: {len(master_db)} 曲')
            self._refresh_sdvx_table()

        def _on_portal_error(self, msg: str):
            self._btn_fetch.setEnabled(True)
            self.statusBar().showMessage(f'エラー: {msg}')

        # ── テーブル更新 ──────────────────────────────────────────────────────

        def _refresh_sdvx_table(self):
            if self._rb_v2.isChecked():
                rows    = _build_rows(self._v2)
                n_songs = len(self._v2.get('titles', {}))
                label   = f'SDVX DB (v2) — {n_songs} 曲 / {len(rows)} 譜面'
                self._sdvx_model.set_rows(rows)
                self._sdvx_model.set_v2_hashes(set())
            elif self._rb_unmatched.isChecked():
                rows    = _build_rows(self._v1, exclude_set=self._portal_title_set)
                n_songs = len({r[0] for r in rows})
                label   = f'SDVX DB (v1のみ・マスタになし) — {n_songs} 曲 / {len(rows)} 譜面'
                self._sdvx_model.set_rows(rows)
                self._sdvx_model.set_v2_hashes(_build_v2_hashes(self._v2))
            else:
                rows    = _build_rows(self._v1)
                n_songs = len(self._v1.get('titles', {}))
                label   = f'SDVX DB (v1) — {n_songs} 曲 / {len(rows)} 譜面'
                self._sdvx_model.set_rows(rows)
                self._sdvx_model.set_v2_hashes(set())

            self._sdvx_label.setText(label)
            self._update_add_button()

        # ── イベントハンドラ ──────────────────────────────────────────────────

        def _on_sdvx_search(self, text: str):
            self._sdvx_model.set_search(text)

        def _on_portal_search(self, text: str):
            self._portal_model.set_search(text)

        def _on_filter_changed(self):
            self._sdvx_search.clear()
            self._refresh_sdvx_table()
            self._update_add_button()

        def _on_diff_filter_changed(self):
            enabled = set()
            if self._cb_nov.isChecked():    enabled.add('NOV')
            if self._cb_adv.isChecked():    enabled.add('ADV')
            if self._cb_exh.isChecked():    enabled.add('EXH')
            if self._cb_append.isChecked(): enabled.add('APPEND')
            self._sdvx_model.set_diff_filter(enabled)
            self._update_add_button()

        def _update_add_button(self):
            sdvx_sel   = self._sdvx_view.selectionModel().selectedRows()
            portal_sel = self._portal_view.selectionModel().selectedRows()
            can_add = (
                self._rb_unmatched.isChecked()
                and bool(sdvx_sel)
                and bool(portal_sel)
            )
            self._btn_add.setEnabled(can_add)
            self._btn_edit_hash.setEnabled(self._rb_v2.isChecked() and bool(sdvx_sel))

        def _on_add_to_v2(self):
            sdvx_rows   = self._sdvx_view.selectionModel().selectedRows()
            portal_rows = self._portal_view.selectionModel().selectedRows()
            if not sdvx_rows or not portal_rows:
                return

            src_idx      = self._sdvx_proxy.mapToSource(sdvx_rows[0])
            old_title    = self._sdvx_model.get_row(src_idx.row())[0]
            portal_entry = self._portal_model.get_row(portal_rows[0].row())
            new_title    = portal_entry.get('title', '')

            if not new_title:
                QMessageBox.warning(self, 'エラー', 'ポータルマスタの曲名が取得できません。')
                return

            reply = QMessageBox.question(
                self, '確認',
                f'以下の対応でv2に追加しますか?\n\n'
                f'  v1曲名 : {old_title}\n'
                f'  マスタ : {new_title}',
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            add_song_to_v2(old_title, new_title, self._v1, self._v2)
            try:
                _save_sdvxh(self._v2, _MUSICLIST_V2)
                self.statusBar().showMessage(f'追加・保存完了: {new_title}')
            except Exception as e:
                QMessageBox.critical(self, 'エラー', f'保存失敗:\n{e}')
                return

            self._refresh_sdvx_table()

        def _on_edit_hash(self):
            if not self._rb_v2.isChecked():
                QMessageBox.information(self, '情報', 'v2表示中のみhashを編集できます。')
                return

            sdvx_rows = self._sdvx_view.selectionModel().selectedRows()
            if not sdvx_rows:
                return

            src_idx = self._sdvx_proxy.mapToSource(sdvx_rows[0])
            title, diff_name, _level, current_hash = self._sdvx_model.get_row(src_idx.row())

            new_hash, ok = QInputDialog.getText(
                self,
                'hash編集',
                f'{title}\n{diff_name} の jacket hash:',
                QLineEdit.Normal,
                str(current_hash or ''),
            )
            if not ok:
                return

            new_hash = new_hash.strip().lower()
            if not new_hash:
                QMessageBox.warning(self, 'エラー', 'hashが空です。')
                return
            try:
                int(new_hash, 16)
            except ValueError:
                QMessageBox.warning(self, 'エラー', 'hashは16進数で入力してください。')
                return

            try:
                count, scope = update_jacket_hash(self._v2, title, diff_name, new_hash)
                _save_sdvxh(self._v2, _MUSICLIST_V2)
            except Exception as e:
                QMessageBox.critical(self, 'エラー', f'hash保存失敗:\n{e}')
                return

            self._refresh_sdvx_table()
            if scope == 'all':
                self.statusBar().showMessage(f'hash更新完了: {title} 全{count}譜面へコピー')
            else:
                self.statusBar().showMessage(f'hash更新完了: {title} {diff_name}')

    # ── 起動 ─────────────────────────────────────────────────────────────────

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


# ── エントリポイント ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description='楽曲DBポータルマスタ整合ツール')
    parser.add_argument('--gui', action='store_true', help='GUIを起動する')
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='CLI処理後に対話REPLを起動する',
    )
    args = parser.parse_args()

    if args.gui:
        launch_gui()
        return

    run()

    if args.interactive:
        banner = (
            '\n対話モードに入ります。利用可能な変数:\n'
            '  portal_master    - ポータルマスタ list[dict]\n'
            '  portal_titles    - ポータル曲名セット set[str]\n'
            '  musiclist        - musiclist.pkl の内容 dict\n'
            '  musiclist_v2     - フィルタ済みDB dict\n'
            '  matched_titles   - 一致した曲名リスト list[str]\n'
            '  unmatched_titles - 不一致の曲名リスト list[str]\n'
        )
        import misc.manage_db as _self
        code.interact(banner=banner, local=vars(_self))


if __name__ == '__main__':
    main()
