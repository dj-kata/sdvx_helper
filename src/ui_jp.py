"""
日本語UI定義
すべてのUI文字列をクラスのメンバ変数として定義
VSCodeの補完が効く形式
"""


class UIText:
    """UI文字列定義クラス"""

    class menu:
        """メニューバー"""
        file = 'ファイル(&F)'
        tool = 'ツール(&E)'
        language = 'Language(&L)'
        help = 'ヘルプ(&H)'

        # ファイルメニュー
        base_config = '基本設定(&C)...'
        obs_config = 'OBS制御設定(&O)...'
        save_image = '画像保存(&S)'
        exit = '終了(&X)'

        # ツールメニュー
        score_viewer = 'スコアビューワ(&V)'

        # 言語メニュー
        japanese = '日本語'
        english = 'English'

        # ヘルプメニュー
        about = 'バージョン情報(&A)'

    class window:
        """ウィンドウタイトル"""
        main_title = 'SDVX Helper'
        settings_title = '基本設定'
        obs_title = 'OBS制御設定'
        about_title = 'バージョン情報'

    class dialog:
        """ダイアログ"""
        ok = 'OK'
        cancel = 'キャンセル'
        apply = '適用'
        close = '閉じる'
        yes = 'はい'
        no = 'いいえ'
        browse = '参照...'
        select_image_path = '画像保存先フォルダを選択'

    class tab:
        """設定ダイアログのタブ"""
        feature = '機能設定'
        image_save = '画像保存'
        capture = 'キャプチャ設定'
        rival = 'ライバル登録'
        import_data = 'データ取り込み'
        portal = 'Portal連携'

    class feature:
        """機能設定タブ"""
        other_group = 'その他'
        autoload_offset = '自動読み込みオフセット(時間):'
        websocket_port = 'データ表示用port:'
        obs_text_source = 'OBSテキストソース名:'
        keep_on_top = '常に最前面表示する'

    class image_save:
        """画像保存設定タブ"""
        path_group = '保存先'
        image_save_path = '画像保存先:'
        autosave_image = 'リザルト画面を自動保存する'
        autosave_updated_score_only = '更新があったスコアのみ保存'
        summary_updated_results_only = 'レシートにも更新されたリザルトのみ含む'
        csv_group = 'CSV出力'
        csv_export_path = 'CSV出力先(空=out/):'

    class capture:
        """キャプチャ設定タブ"""
        method_group = 'キャプチャ方式'
        method_label = '方式:'
        method_obs_websocket = 'OBS WebSocket'
        method_direct_window = '直接取得'
        orientation_group = '画面向き'
        orientation_auto = '自動検出'
        orientation_top_up = '上向き (top_up)'
        orientation_top_right = '右向き (top_right)'
        orientation_top_left = '左向き (top_left)'

    class rival:
        """ライバル登録タブ"""
        url_group = 'ライバルデータ (Google Drive)'
        url_label = 'Google Drive URL:'
        url_hint = '例: https://drive.google.com/file/d/.../view'
        import_button = 'データを取り込む'
        import_success = '{count} 件のライバルデータを取り込みました'
        import_failed = 'ライバルデータの取り込みに失敗しました'

    class import_data:
        """データ取り込みタブ"""
        alllog_group = 'v1形式データ (alllog.pkl)'
        alllog_label = 'alllog.pkl パス:'
        alllog_button = '取り込む'
        result_image_group = 'リザルト画像フォルダ'
        result_image_label = 'フォルダパス:'
        result_image_button = '取り込む'
        import_success = '{count} 件のデータを取り込みました'
        import_failed = 'データの取り込みに失敗しました'

    class message:
        """メッセージ"""
        language_changed = '言語を変更しました。アプリケーションを再起動します...'
        config_saved = '設定を保存しました'
        restart_required = '設定を反映するには、アプリケーションを再起動してください'
        error_title = 'エラー'
        warning_title = '警告'
        info_title = '情報'
        confirm_title = '確認'
        completed_title = '完了'
        success = '成功'

    class status:
        """ステータスバー"""
        ready = '準備完了'
        processing = '処理中...'
        saved = '保存しました'
        loading = '読み込み中...'
        canceling = 'キャンセル中...'

    class button:
        """ボタン"""
        ok = 'OK'
        cancel = 'キャンセル'
        clear = 'クリア'
        reconnect = '再接続'
        refresh = '更新'
        add_setting = '追加'
        delete_selected_setting = '選択削除'
        delete_all_settings = '全削除'

    class obs:
        '''OBS関連のメッセージ'''
        connection_state = 'OBS接続状態'
        status_connected = '接続中'
        status_connection_failed = '接続失敗'
        status_disconnected = '切断しました'
        status_lost = '切断されました'
        status_reconnect_failed = '再接続失敗'
        status_reconnecting = '再接続中...'
        status_reconnected = '再接続成功'
        not_configured = "設定が完了していません"
        not_connected  = "未接続"
        no_source = "監視対象ソース未設定"
        connected = '接続中'

        # 制御設定ダイアログ関連
        websocket_group = 'OBS WebSocket接続設定'
        obs_control_enabled = '直接取得でもOBS制御を使う'
        websocket_host = 'ホスト:'
        websocket_port = 'ポート:'
        websocket_password = 'パスワード:'
        scene_collection_group = 'シーンコレクション設定'
        scene_collection_label = 'シーンコレクション:'
        scene_collection_not_set = '(未設定)'
        target_source_group = '監視対象ソース'
        target_source_not_set = '未設定'
        target_source_label = '現在の監視対象:'
        new_settings_group = '新しい制御設定を追加'
        new_settings_action = 'アクション:'
        new_settings_timing = '実行タイミング:'
        new_settings_target_scene = '対象シーン:'
        new_settings_source = '対象ソース:'
        new_settings_next_scene = '切り替え先シーン:'
        registered_group = '登録済み制御設定'
        timing = '実行タイミング'
        action = 'アクション'
        scene = '対象シーン'
        source = '対象ソース'
        setting_complete = '設定完了'
        source_configured = "監視対象ソースを '{target_source}' に設定しました"
        reconnected_to_obs = 'OBSに再接続しました'
        failed_reconnection_to_obs = 'OBSへの再接続に失敗しました'
        failed_reconnection_to_obs_with_error = 'OBSへの再接続に失敗しました:\n{error}'


    class obs_timing:
        '''OBS制御設定におけるタイミング'''
        app_start = "アプリ起動時"
        app_end = "アプリ終了時"
        select_start = "選曲画面開始時"
        select_end = "選曲画面終了時"
        detect_start = "楽曲情報画面開始時"
        detect_end = "楽曲情報画面終了時"
        play_start = "プレー画面開始時"
        play_end = "プレー画面終了時"
        result_start = "リザルト画面開始時"
        result_end = "リザルト画面終了時"

    class obs_action:
        '''OBS制御設定におけるアクション'''
        show_source = "ソースを表示"
        hide_source = "ソースを非表示"
        switch_scene = "シーンを切り替え"
        set_monitor_source = "監視対象ソース指定"
        autosave_source = "キャプチャを自動保存"

    class main:
        '''main window'''
        other_info = 'その他の情報'
        current_mode = '現在のモード:'
        ontime = '起動時間:'
        play_count = 'プレイ数:'
        total_vf = '総VF:'
        last_saved_song = '最後に保存した曲:'
        save_image = '画像保存 (F6)'
        status_ready = '準備完了'

    class portal:
        """Portal連携タブ"""
        url_group = 'Portal'
        url_label = 'URL:'
        open_button = 'Portalを開く'
        token_group = 'アクセストークン'
        token_label = 'トークン:'
        token_placeholder = 'トークンを入力してください'
        player_name_label = 'プレイヤー名:'
        upload_group = 'データ送信'
        upload_all_button = '全プレーログをPortalに送信'
        upload_status_idle = ''
        upload_status_running = '送信中...'
        upload_status_ok = '送信完了'
        upload_status_error = '送信失敗: {detail}'
        upload_no_master = '楽曲マスタが未取得です。トークンを確認してください。'
        upload_no_token = 'トークンが設定されていません。'

    class mode:
        '''検出モード用'''
        init = '-'
        select = '選曲画面'
        detect = '楽曲情報画面'
        play = 'プレイ画面'
        result = 'リザルト画面'
