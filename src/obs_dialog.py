"""
OBS制御設定ダイアログ(PySide6版・改良版)
既存のobs_websocket_manager.pyと完全互換
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                               QTableWidgetItem, QPushButton, QLabel, QComboBox,
                               QGroupBox, QHeaderView, QMessageBox, QFormLayout,
                               QLineEdit, QSpinBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from src.logger import get_logger
from src.funcs import load_ui_text

logger = get_logger(__name__)

# UIの型チェック用
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.ui_jp import UIText

class OBSControlDialog(QDialog):
    """OBS制御設定ダイアログ"""
    
    def __init__(self, config, obs_manager, parent=None):
        super().__init__(parent)
        self.config = config
        self.ui:UIText = load_ui_text(config)
        self.set_defines()
        self.obs_manager = obs_manager
        
        self.setWindowTitle(self.ui.window.obs_title)
        self.setMinimumSize(900, 700)
        
        self.init_ui()
        self.load_settings()
        
        # OBSのシーン一覧を取得
        self.update_scene_list()

    def set_defines(self):
        '''列で使う項目名をセットする'''
        # 実行タイミングの定義(既存コードと同じ)
        self.TIMINGS = [
            ("app_start"    , self.ui.obs_timing.app_start),
            ("app_end"      , self.ui.obs_timing.app_end),
            ("select_start" , self.ui.obs_timing.select_start),
            ("select_end"   , self.ui.obs_timing.select_end),
            ("detect_start" , self.ui.obs_timing.detect_start),
            ("detect_end"   , self.ui.obs_timing.detect_end),
            ("play_start"   , self.ui.obs_timing.play_start),
            ("play_end"     , self.ui.obs_timing.play_end),
            ("result_start" , self.ui.obs_timing.result_start),
            ("result_end"   , self.ui.obs_timing.result_end),
        ]
    
        # アクションの定義(既存コードと同じ)
        self.ACTIONS = [
            ("show_source",        self.ui.obs_action.show_source),
            ("hide_source",        self.ui.obs_action.hide_source),
            ("autosave_source",     self.ui.obs_action.autosave_source),
            ("switch_scene",       self.ui.obs_action.switch_scene),
            ("set_monitor_source", self.ui.obs_action.set_monitor_source),
        ]
    
        # 行の背景色定義
        self.ACTION_COLORS = {
            "show_source": QColor("#e8f5e9"),    # 薄い緑
            "hide_source": QColor("#ffebee"),    # 薄い赤
            "autosave_source": QColor("#fff2dd"),   # 薄い青
            "switch_scene": QColor("#e3f2fd"),   # 薄い青
        }
    
    def init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # WebSocket接続設定グループ
        websocket_group = QGroupBox(self.ui.obs.websocket_group)
        websocket_layout = QFormLayout()
        websocket_group.setLayout(websocket_layout)
        
        self.websocket_host_edit = QLineEdit()
        websocket_layout.addRow(self.ui.obs.websocket_host, self.websocket_host_edit)
        
        self.websocket_port_spin = QSpinBox()
        self.websocket_port_spin.setRange(1, 65535)
        self.websocket_port_spin.setValue(4444)
        websocket_layout.addRow(self.ui.obs.websocket_port, self.websocket_port_spin)
        
        self.websocket_password_edit = QLineEdit()
        self.websocket_password_edit.setEchoMode(QLineEdit.Password)
        websocket_layout.addRow(self.ui.obs.websocket_password, self.websocket_password_edit)
        
        layout.addWidget(websocket_group)

        # シーンコレクション設定グループ
        scene_collection_group = QGroupBox(self.ui.obs.scene_collection_group)
        scene_collection_layout = QFormLayout()
        scene_collection_group.setLayout(scene_collection_layout)

        self.scene_collection_combo = QComboBox()
        self.scene_collection_combo.currentIndexChanged.connect(self.on_scene_collection_changed)
        scene_collection_layout.addRow(self.ui.obs.scene_collection_label, self.scene_collection_combo)

        layout.addWidget(scene_collection_group)

        # 監視対象ソース表示
        monitor_group = QGroupBox(self.ui.obs.target_source_group)
        monitor_layout = QHBoxLayout()
        monitor_group.setLayout(monitor_layout)
        
        self.monitor_label = QLabel(self.ui.obs.target_source_not_set)
        self.monitor_label.setStyleSheet("font-weight: bold; color: blue;")
        monitor_layout.addWidget(QLabel(self.ui.obs.target_source_label))
        monitor_layout.addWidget(self.monitor_label)
        monitor_layout.addStretch()
        
        # クリアボタンを追加
        clear_monitor_button = QPushButton(self.ui.button.clear)
        clear_monitor_button.clicked.connect(self.clear_monitor_source)
        monitor_layout.addWidget(clear_monitor_button)
        
        layout.addWidget(monitor_group)
        
        # 新しい制御設定を追加するグループ
        add_group = QGroupBox(self.ui.obs.new_settings_group)
        add_layout = QFormLayout()
        add_group.setLayout(add_layout)
        
        # アクション
        self.action_combo = QComboBox()
        for action_id, action_name in self.ACTIONS:
            self.action_combo.addItem(action_name, action_id)
        self.action_combo.currentIndexChanged.connect(self.on_action_changed)
        add_layout.addRow(self.ui.obs.new_settings_action, self.action_combo)
        
        # 実行タイミング
        self.timing_combo = QComboBox()
        self.timing_combo.addItem("", None)  # 空白項目を追加
        for timing_id, timing_name in self.TIMINGS:
            self.timing_combo.addItem(timing_name, timing_id)
        add_layout.addRow(self.ui.obs.new_settings_timing, self.timing_combo)
        
        # 対象シーン
        self.target_scene_combo = QComboBox()
        self.target_scene_combo.currentIndexChanged.connect(self.on_target_scene_changed)
        add_layout.addRow(self.ui.obs.new_settings_target_scene, self.target_scene_combo)
        
        # 対象ソース
        self.target_source_combo = QComboBox()
        add_layout.addRow(self.ui.obs.new_settings_source, self.target_source_combo)
        
        # 切り替え先シーン
        self.switch_scene_combo = QComboBox()
        add_layout.addRow(self.ui.obs.new_settings_next_scene, self.switch_scene_combo)
        
        # 設定追加ボタン
        add_button_layout = QHBoxLayout()
        self.add_button = QPushButton(self.ui.button.add_setting)
        self.add_button.clicked.connect(self.add_setting)
        add_button_layout.addStretch()
        add_button_layout.addWidget(self.add_button)
        add_layout.addRow("", add_button_layout)
        
        layout.addWidget(add_group)
        
        # 初期状態のコンボボックス有効/無効を設定
        self.on_action_changed()
        
        # 登録済み制御設定一覧
        list_group = QGroupBox(self.ui.obs.registered_group)
        list_layout = QVBoxLayout()
        list_group.setLayout(list_layout)
        
        self.settings_table = QTableWidget()
        self.settings_table.setColumnCount(4)  # 対象シーンと対象ソースを分離
        self.settings_table.setHorizontalHeaderLabels([
            self.ui.obs.timing,
            self.ui.obs.action,
            self.ui.obs.scene,
            self.ui.obs.source
        ])
        
        # テーブルを編集不可に設定
        self.settings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        # 行全体を選択するように設定
        self.settings_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        # 列幅を自動調整
        header = self.settings_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.settings_table.setColumnWidth(0, 150)
        self.settings_table.setColumnWidth(1, 150)
        
        list_layout.addWidget(self.settings_table)
        
        # 一括削除ボタン
        delete_layout = QHBoxLayout()
        delete_layout.addStretch()
        
        self.delete_selected_button = QPushButton(self.ui.button.delete_selected_setting)
        self.delete_selected_button.clicked.connect(self.delete_selected)
        delete_layout.addWidget(self.delete_selected_button)
        
        self.delete_all_button = QPushButton(self.ui.button.delete_all_settings)
        self.delete_all_button.clicked.connect(self.delete_all)
        delete_layout.addWidget(self.delete_all_button)
        
        list_layout.addLayout(delete_layout)
        
        layout.addWidget(list_group)
        
        # 更新・再接続・OK/キャンセルボタン
        button_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton(self.ui.button.refresh)
        self.refresh_button.clicked.connect(self.update_scene_list)
        button_layout.addWidget(self.refresh_button)
        
        self.reconnect_button = QPushButton(self.ui.button.reconnect)
        self.reconnect_button.clicked.connect(self.reconnect_obs)
        button_layout.addWidget(self.reconnect_button)
        
        button_layout.addStretch()
        
        ok_button = QPushButton(self.ui.button.ok)
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        
        cancel_button = QPushButton(self.ui.button.cancel)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
    
    def update_scene_list(self):
        """OBSからシーン一覧を取得してコンボボックスを更新"""
        if not self.obs_manager.is_connected:
            logger.warning("OBSに接続されていません")
            return

        try:
            # OBSからシーン一覧を取得(List[Dict])
            scenes_data = self.obs_manager.get_scene_list()

            self.target_scene_combo.clear()
            self.switch_scene_combo.clear()

            # scenesデータからシーン名を抽出
            for scene_dict in scenes_data:
                scene_name = scene_dict.get('sceneName', '')
                if scene_name:
                    self.target_scene_combo.addItem(scene_name)
                    self.switch_scene_combo.addItem(scene_name)

            logger.info(f"シーンリストを更新しました: {len(scenes_data)}件")

        except Exception as e:
            logger.error(f"シーン一覧取得エラー: {e}")
            QMessageBox.warning(self, self.ui.message.error_title, f"シーンリストの取得に失敗しました:\n{e}")

        # シーンコレクション一覧を更新
        self._update_scene_collection_list()

    def _update_scene_collection_list(self):
        """OBSからシーンコレクション一覧を取得してコンボボックスを更新"""
        if not self.obs_manager.is_connected:
            return

        try:
            collections = self.obs_manager.get_scene_collection_list()
            if collections is None:
                return

            # シグナルを一時ブロックして誤動作を防ぐ
            self.scene_collection_combo.blockSignals(True)
            self.scene_collection_combo.clear()
            self.scene_collection_combo.addItem("", None)  # 未設定の空白項目
            for name in collections:
                self.scene_collection_combo.addItem(name, name)

            # 現在の設定値を選択
            current = self.config.obs_scene_collection
            if current:
                idx = self.scene_collection_combo.findData(current)
                if idx >= 0:
                    self.scene_collection_combo.setCurrentIndex(idx)
                else:
                    self.scene_collection_combo.setCurrentIndex(0)
            else:
                self.scene_collection_combo.setCurrentIndex(0)

            self.scene_collection_combo.blockSignals(False)
            logger.info(f"シーンコレクションリストを更新しました: {len(collections)}件")

        except Exception as e:
            logger.error(f"シーンコレクション一覧取得エラー: {e}")
    
    def on_scene_collection_changed(self):
        """シーンコレクション選択変更時にOBS側を切り替える"""
        name = self.scene_collection_combo.currentData()
        if not name or not self.obs_manager.is_connected:
            return
        try:
            self.obs_manager.set_scene_collection(name)
        except Exception as e:
            logger.error(f"シーンコレクション切り替えエラー: {e}")
            QMessageBox.warning(self, self.ui.message.error_title, f"シーンコレクションの切り替えに失敗しました:\n{e}")

    def on_target_scene_changed(self):
        """対象シーンが変更されたときにソース一覧を更新"""
        scene_name = self.target_scene_combo.currentText()
        if not scene_name or not self.obs_manager.is_connected:
            return
        
        try:
            # OBSから指定シーンのソース一覧を取得(List[str])
            sources = self.obs_manager.get_source_list(scene_name)
            
            self.target_source_combo.clear()
            for source in sources:
                self.target_source_combo.addItem(source)
            
            logger.debug(f"ソースリストを更新しました: {scene_name} ({len(sources)}件)")
        except Exception as e:
            logger.error(f"ソース一覧取得エラー: {e}")
    
    def on_action_changed(self):
        """アクション変更時に入力フィールドの有効/無効を切り替え"""
        action_id = self.action_combo.currentData()
        
        if action_id == "switch_scene":
            # シーン切り替え
            self.timing_combo.setEnabled(True)
            self.target_scene_combo.setEnabled(False)
            self.target_source_combo.setEnabled(False)
            self.switch_scene_combo.setEnabled(True)
        elif action_id in ("show_source", "hide_source", "autosave_source"):
            # ソース表示/非表示
            self.timing_combo.setEnabled(True)
            self.target_scene_combo.setEnabled(True)
            self.target_source_combo.setEnabled(True)
            self.switch_scene_combo.setEnabled(False)
        elif action_id == 'set_monitor_source':
            # 監視対象ソース指定
            self.timing_combo.setEnabled(False)
            self.target_scene_combo.setEnabled(True)
            self.target_source_combo.setEnabled(True)
            self.switch_scene_combo.setEnabled(False)
        else:
            # 未定義のアクション
            self.timing_combo.setEnabled(True)
            self.target_scene_combo.setEnabled(True)
            self.target_source_combo.setEnabled(True)
            self.switch_scene_combo.setEnabled(True)
    
    def add_setting(self):
        """設定を追加"""
        try:
            action_id = self.action_combo.currentData()
            action_name = self.action_combo.currentText()
            timing_id = self.timing_combo.currentData()
            timing_name = self.timing_combo.currentText()
            
            # 基本的な未入力チェック
            logger.debug(f"{action_id}, {action_name}, {timing_id}, {timing_name}")
            if action_id is None:
                QMessageBox.warning(self, self.ui.message.error_title, self.ui.message.select_action)
                return
            if action_id != "set_monitor_source" and not timing_id:
                QMessageBox.warning(self, self.ui.message.error_title, self.ui.message.select_timing)
                return
            
            setting = {
                "timing": timing_id,
                "action": action_id,
            }
            
            if action_id in ("show_source", "hide_source", "autosave_source"):
                # ソース表示・非表示
                target_scene = self.target_scene_combo.currentText()
                target_source = self.target_source_combo.currentText()
                
                if not target_scene or not target_source:
                    QMessageBox.warning(self, self.ui.message.error_title, self.ui.message.select_scene_and_source)
                    return
                
                setting["scene"] = target_scene
                setting["source"] = target_source
                
                scene_text = target_scene
                source_text = target_source
                
            elif action_id == "switch_scene":
                # シーン切り替え
                switch_scene = self.switch_scene_combo.currentText()
                
                if not switch_scene:
                    QMessageBox.warning(self, self.ui.message.error_title, self.ui.message.select_next_scene)
                    return
                
                setting["scene"] = switch_scene
                
                scene_text = switch_scene
                source_text = ""  # シーン切り替えの場合はソースは空
                
            elif action_id == "set_monitor_source":
                # 監視対象ソース設定
                target_scene = self.target_scene_combo.currentText()
                target_source = self.target_source_combo.currentText()
                
                if not target_scene or not target_source:
                    QMessageBox.warning(self, self.ui.message.error_title, self.ui.message.select_scene_and_source)
                    return
                
                # 既存の監視対象ソース設定を削除(1つのみ)
                self.config.obs_control_settings = [
                    s for s in self.config.obs_control_settings
                    if s.get("action") != "set_monitor_source"
                ]
                
                setting["scene"] = target_scene
                setting["source"] = target_source
                
                # 監視対象ソース名を更新
                self.config.monitor_source_name = target_source
                self.monitor_label.setText(target_source)
                
                # 設定を追加(ただしテーブルには追加しない)
                self.config.obs_control_settings.append(setting)
                
                logger.info(f"監視対象ソースを設定: {target_source} (シーン: {target_scene})")
                QMessageBox.information(self, self.ui.obs.setting_complete, self.ui.obs.source_configured.format(target_source))
                
                # フォームをリセット
                self.reset_form()
                
                # 早期リターン(テーブルに追加しない)
                return
            
            # 設定を追加
            self.config.obs_control_settings.append(setting)
            
            # テーブルに追加(引数の順序: timing, action, scene, source)
            self.add_table_row(timing_name, action_name, scene_text, source_text, setting)
            
            logger.info(f"OBS制御設定を追加: {setting}")
            
            # フォームをリセット
            self.reset_form()
            
        except Exception as e:
            logger.error(f"設定追加エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            QMessageBox.warning(self, self.ui.message.error_title, self.ui.message.failed_add_setting.format(e))
    
    def add_table_row(self, timing, action, scene, source, setting=None):
        """テーブルに行を追加"""
        row = self.settings_table.rowCount()
        self.settings_table.insertRow(row)
        
        # 各セルにアイテムを設定
        timing_item = QTableWidgetItem(timing)
        action_item = QTableWidgetItem(action)
        scene_item = QTableWidgetItem(scene)
        source_item = QTableWidgetItem(source)
        
        self.settings_table.setItem(row, 0, timing_item)
        self.settings_table.setItem(row, 1, action_item)
        self.settings_table.setItem(row, 2, scene_item)
        self.settings_table.setItem(row, 3, source_item)
        
        # 設定データを行に関連付け
        if setting:
            timing_item.setData(Qt.ItemDataRole.UserRole, setting)
            
            # アクションに応じて行の背景色を設定
            action_id = setting.get("action", "")
            if action_id in self.ACTION_COLORS:
                bg_color = self.ACTION_COLORS[action_id]
                timing_item.setBackground(bg_color)
                action_item.setBackground(bg_color)
                scene_item.setBackground(bg_color)
                source_item.setBackground(bg_color)
    
    def reset_form(self):
        """フォームをリセット"""
        # アクションは現在のまま保持（初期化しない）
        
        # 実行タイミングは空白項目（インデックス0）を選択
        self.timing_combo.setCurrentIndex(0)
        
        # シーンとソースのコンボボックスをクリア
        self.target_source_combo.clear()
        
        # 対象シーンと切り替え先シーンは最初の項目を選択（項目がある場合）
        if self.target_scene_combo.count() > 0:
            self.target_scene_combo.setCurrentIndex(0)
        if self.switch_scene_combo.count() > 0:
            self.switch_scene_combo.setCurrentIndex(0)
        
        # アクション変更に伴うフィールドの有効/無効を更新
        self.on_action_changed()
    
    def delete_selected(self):
        """選択された行を削除"""
        selected_rows = set()
        for item in self.settings_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.information(self, self.ui.message.info_title, self.ui.message.select_setting_to_remove)
            return
        
        # 後ろから削除
        for row in sorted(selected_rows, reverse=True):
            # テーブルの行から設定データを取得
            item = self.settings_table.item(row, 0)
            if item:
                setting = item.data(Qt.ItemDataRole.UserRole)
                if setting:
                    # config.obs_control_settingsから同じ設定を削除
                    try:
                        self.config.obs_control_settings.remove(setting)
                        logger.info(f"OBS制御設定を削除: {setting}")
                    except ValueError:
                        logger.warning(f"設定が見つかりません: {setting}")
            
            # テーブルから行を削除
            self.settings_table.removeRow(row)
    
    def delete_all(self):
        """すべての設定を削除"""
        reply = QMessageBox.question(
            self, self.ui.message.confirm_title,
            self.ui.message.ask_remove_all_settings,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 監視対象ソース設定は残して、それ以外を削除
            self.config.obs_control_settings = [
                s for s in self.config.obs_control_settings
                if s.get("action") == "set_monitor_source"
            ]
            
            # テーブルをクリア
            self.settings_table.setRowCount(0)
            
            logger.info("すべてのOBS制御設定を削除しました(監視対象ソースは除く)")
            QMessageBox.information(self, self.ui.message.completed_title, self.ui.message.removed_all_settings)
    
    def load_settings(self):
        """設定を読み込んでテーブルに表示"""
        self.settings_table.setRowCount(0)
        
        # WebSocket設定を読み込む
        self.websocket_host_edit.setText(self.config.websocket_host)
        self.websocket_port_spin.setValue(self.config.websocket_port)
        self.websocket_password_edit.setText(self.config.websocket_password)

        # シーンコレクション設定を読み込む（シグナルをブロックして誤動作を防ぐ）
        self.scene_collection_combo.blockSignals(True)
        self.scene_collection_combo.clear()
        self.scene_collection_combo.addItem("", None)
        saved_collection = self.config.obs_scene_collection
        if saved_collection:
            self.scene_collection_combo.addItem(saved_collection, saved_collection)
            self.scene_collection_combo.setCurrentIndex(1)
        self.scene_collection_combo.blockSignals(False)
        
        # 監視対象ソースを表示
        if self.config.monitor_source_name:
            self.monitor_label.setText(self.config.monitor_source_name)
        else:
            self.monitor_label.setText(self.ui.obs.target_source_not_set)
        
        # トリガーとアクションの逆引き辞書を作成
        timing_dict = {timing_id: name for timing_id, name in self.TIMINGS}
        action_dict = {action_id: name for action_id, name in self.ACTIONS}
        
        # 各設定をテーブルに追加(監視対象ソース設定は除外)
        for setting in self.config.obs_control_settings:
            timing_id = setting.get("timing", "")
            action_id = setting.get("action", "")
            
            # 監視対象ソース設定はスキップ(画面上部のラベルのみに表示)
            if action_id == "set_monitor_source":
                continue
            
            timing_name = timing_dict.get(timing_id, timing_id)
            action_name = action_dict.get(action_id, action_id)
            
            if action_id == "switch_scene":
                scene_text = setting.get("scene", "")
                source_text = ""  # シーン切り替えの場合はソースは空
            else:  # show_source or hide_source
                scene_text = setting.get("scene", "")
                source_text = setting.get("source", "")
            
            # 引数の順序: timing, action, scene, source
            self.add_table_row(timing_name, action_name, scene_text, source_text, setting)
    
    def reconnect_obs(self):
        """OBSに再接続"""
        try:
            self.obs_manager.disconnect()
            success = self.obs_manager.connect()
            if success:
                self.update_scene_list()
                QMessageBox.information(self, self.ui.message.success, self.ui.message.reconnected_to_obs)
            else:
                QMessageBox.warning(self, self.ui.message.error_title, self.ui.message.failed_reconnection_to_obs)
        except Exception as e:
            logger.error(f"OBS再接続エラー: {e}")
            QMessageBox.warning(self, self.ui.message.error_title, self.ui.message.failed_reconnection_to_obs_with_error.format(e))
    
    def clear_monitor_source(self):
        """監視対象ソースをクリア"""
        reply = QMessageBox.question(
            self, "確認",
            "監視対象ソースをクリアしますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 設定から監視対象ソース設定を削除
            self.config.obs_control_settings = [
                s for s in self.config.obs_control_settings
                if s.get("action") != "set_monitor_source"
            ]
            
            # 監視対象ソース名をクリア
            self.config.monitor_source_name = ""
            self.monitor_label.setText(self.ui.obs.target_source_not_set)
            
            logger.info("監視対象ソースをクリアしました")
            QMessageBox.information(self, self.ui.message.completed_title, self.ui.message.target_source_removed)
    
    def accept(self):
        """OKボタン"""
        # WebSocket設定を保存
        self.config.websocket_host = self.websocket_host_edit.text()
        self.config.websocket_port = self.websocket_port_spin.value()
        self.config.websocket_password = self.websocket_password_edit.text()

        # シーンコレクション設定を保存
        selected_collection = self.scene_collection_combo.currentData()
        self.config.obs_scene_collection = selected_collection if selected_collection else ""

        self.config.save_config()
        logger.info("OBS制御設定を保存しました")
        super().accept()
