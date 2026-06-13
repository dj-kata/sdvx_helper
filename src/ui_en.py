"""
English UI Definition
All UI strings defined as class member variables
IDE autocomplete friendly format
"""


class UIText:
    """UI text definition class"""

    class menu:
        """Menu bar"""
        file = '&File'
        tool = '&Tool'
        language = '&Language'
        help = '&Help'

        # File menu
        base_config = 'Configure(&C)...'
        obs_config = 'OBS Settings(&O)...'
        save_image = '&Save Image'
        exit = 'E&xit'

        # Tool menu
        score_viewer = 'Score &Viewer'

        # Language menu
        japanese = '日本語'
        english = 'English'

        # Help menu
        about = '&About'

    class window:
        """Window titles"""
        main_title = 'SDVX Helper'
        settings_title = 'Settings'
        obs_title = 'OBS Control Settings'
        about_title = 'About'

    class dialog:
        """Dialogs"""
        ok = 'OK'
        cancel = 'Cancel'
        apply = 'Apply'
        close = 'Close'
        yes = 'Yes'
        no = 'No'
        browse = 'Browse...'
        select_image_path = 'Select path for saving images'

    class tab:
        """Settings dialog tabs"""
        feature = 'Features'
        image_save = 'Image Saving'
        capture = 'Capture Settings'
        rival = 'Rival'
        import_data = 'Import Data'
        portal = 'Portal'

    class feature:
        """Feature settings tab"""
        other_group = 'Other'
        autoload_offset = 'Auto-load offset (hours):'
        websocket_port = 'Data display port:'
        obs_text_source = 'OBS Text Source Name:'
        keep_on_top = 'Always on Top'

    class image_save:
        """Image save settings tab"""
        path_group = 'Save Path'
        image_save_path = 'Image save path:'
        image_format = 'Image format:'
        image_format_png = 'PNG'
        image_format_jpg = 'JPG'
        autosave_image = 'Auto-save result screen'
        autosave_updated_score_only = 'Save only results with score updates'
        summary_updated_results_only = 'Receipt includes only updated results'
        csv_group = 'CSV Export'
        csv_export_path = 'CSV export path (empty=out/):'

    class capture:
        """Capture settings tab"""
        method_group = 'Capture Method'
        method_label = 'Method:'
        method_obs_websocket = 'OBS WebSocket'
        method_direct_window = 'Direct capture'
        orientation_group = 'Screen Orientation'
        orientation_auto = 'Auto-detect'
        orientation_top_up = 'Top up (top_up)'
        orientation_top_right = 'Top right (top_right)'
        orientation_top_left = 'Top left (top_left)'

    class rival:
        """Rival registration tab"""
        url_group = 'Rival Data (Google Drive)'
        url_label = 'Google Drive URL:'
        url_hint = 'e.g. https://drive.google.com/file/d/.../view'
        import_button = 'Import Data'
        import_success = 'Imported {count} rival records'
        import_failed = 'Failed to import rival data'

    class import_data:
        """Import data tab"""
        alllog_group = 'v1 Format Data (alllog.pkl)'
        alllog_label = 'alllog.pkl path:'
        alllog_button = 'Import'
        result_image_group = 'Result Image Folder'
        result_image_label = 'Folder path:'
        result_image_button = 'Import'
        import_success = 'Imported {count} records'
        import_failed = 'Failed to import data'

    class message:
        """Messages"""
        language_changed = 'Language changed. Restarting application...'
        config_saved = 'Settings saved'
        restart_required = 'Restart the application to apply settings'
        error_title = 'Error'
        warning_title = 'Warning'
        info_title = 'Info'
        confirm_title = 'Confirm'
        completed_title = 'Completed'
        success = 'Success'

    class status:
        """Status bar"""
        ready = 'Ready'
        processing = 'Processing...'
        saved = 'Saved'
        loading = 'Loading...'
        canceling = 'Canceling...'

    class button:
        """Buttons"""
        ok = 'OK'
        cancel = 'Cancel'
        clear = 'Clear'
        reconnect = 'Reconnect'
        refresh = 'Refresh'
        add_setting = 'Add'
        delete_selected_setting = 'Delete Selected'
        delete_all_settings = 'Delete All'

    class obs:
        '''OBS related messages'''
        connection_state = 'OBS Connection'
        status_connected = 'Connected'
        status_connection_failed = 'Connection failed'
        status_disconnected = 'Disconnected'
        status_lost = 'Connection lost'
        status_reconnect_failed = 'Reconnect failed'
        status_reconnecting = 'Reconnecting...'
        status_reconnected = 'Reconnected'
        not_configured = "Not configured"
        not_connected  = "Not connected"
        no_source = "Monitor source not set"
        connected = 'Connected'

        # OBS control dialog
        websocket_group = 'OBS WebSocket Settings'
        obs_control_enabled = 'Use OBS control with direct capture'
        websocket_host = 'Host:'
        websocket_port = 'Port:'
        websocket_password = 'Password:'
        scene_collection_group = 'Scene Collection'
        scene_collection_label = 'Scene Collection:'
        scene_collection_not_set = '(not set)'
        target_source_group = 'Monitor Source'
        target_source_not_set = 'Not set'
        target_source_label = 'Current monitor source:'
        new_settings_group = 'Add New Control Setting'
        new_settings_action = 'Action:'
        new_settings_timing = 'Timing:'
        new_settings_target_scene = 'Target scene:'
        new_settings_source = 'Target source:'
        new_settings_next_scene = 'Switch to scene:'
        registered_group = 'Registered Control Settings'
        timing = 'Timing'
        action = 'Action'
        scene = 'Target Scene'
        source = 'Target Source'
        setting_complete = 'Setting complete'
        source_configured = "Monitor source set to '{target_source}'"
        reconnected_to_obs = 'Reconnected to OBS'
        failed_reconnection_to_obs = 'Failed to reconnect to OBS'
        failed_reconnection_to_obs_with_error = 'Failed to reconnect to OBS:\n{error}'

    class obs_timing:
        '''OBS control timings'''
        app_start = "App start"
        app_end = "App end"
        select_start = "Song select start"
        select_end = "Song select end"
        detect_start = "Song info screen start"
        detect_end = "Song info screen end"
        play_start = "Play start"
        play_end = "Play end"
        result_start = "Result start"
        result_end = "Result end"

    class obs_action:
        '''OBS control actions'''
        show_source = "Show source"
        hide_source = "Hide source"
        switch_scene = "Switch scene"
        set_monitor_source = "Set monitor source"
        autosave_source = "Auto-save capture"

    class main:
        '''Main window'''
        other_info = 'Other Info'
        current_mode = 'Current mode:'
        ontime = 'Uptime:'
        play_count = 'Play count:'
        total_vf = 'Total VF:'
        last_saved_song = 'Last saved song:'
        save_image = 'Save Image (F6)'
        status_ready = 'Ready'

    class portal:
        """Portal integration tab"""
        url_group = 'Portal'
        url_label = 'URL:'
        open_button = 'Open Portal'
        token_group = 'Access Token'
        token_label = 'Token:'
        token_placeholder = 'Enter your token'
        player_name_label = 'Player name:'
        upload_group = 'Upload'
        upload_all_button = 'Send all play log to Portal'
        upload_status_idle = ''
        upload_status_running = 'Sending...'
        upload_status_ok = 'Upload complete'
        upload_status_error = 'Failed: {detail}'
        upload_no_master = 'Music master not loaded. Check your token.'
        upload_no_token = 'Token is not set.'

    class mode:
        '''Detect mode names'''
        init = '-'
        select = 'Song Select'
        detect = 'Song Info'
        play = 'Play'
        result = 'Result'
