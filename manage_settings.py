default_val = {
    'lx':0, 'ly':0,
    'host':'localhost', 'port':'4444', 'passwd':'',
    'autosave_dir':'','autosave_always':False,'autosave_interval':60,'play0_interval':10,
    'detect_wait':3.5,
    'obs_source':'', 'top_is_right':False, # 回転している前提、画面上部が右ならTrueにする
    # スレッド起動時の設定
    'obs_enable_boot':[],'obs_disable_boot':[],'obs_scene_boot':'',
    # 0: シーン開始時
    'obs_enable_select0':[],'obs_disable_select0':[],'obs_scene_select':'',
    'obs_enable_play0':[],'obs_disable_play0':[],'obs_scene_play':'',
    'obs_enable_result0':[],'obs_disable_result0':[],'obs_scene_result':'',
    # 1: シーン終了時
    'obs_enable_select1':[],'obs_disable_select1':[],
    'obs_enable_play1':[],'obs_disable_play1':[],
    'obs_enable_result1':[],'obs_disable_result1':[],
    # スレッド終了時時の設定
    'obs_enable_quit':[],'obs_disable_quit':[],'obs_scene_quit':'',
    # プレイ回数設定関連
    'obs_txt_plays':'sdvx_helper_playcount', 'obs_txt_plays_header':'plays: ', 'obs_txt_plays_footer':'', 
    # ブラスターゲージMAX時のリマインド用
    'obs_txt_blastermax':'sdvx_helper_blastermax','alert_blastermax':False,
    # others
    'ignore_rankD':True, 'auto_update':True,
    'params_json':'resources/params.json',
    'logpic_offset_time':2, # ログ画像について、起動の何時間前以降を対象とするか
    'logpic_bg_alpha':255, # ログ画像について、背景の透明度(0-255, 0:完全に透過)
    'autoload_musiclist':True, # 曲リストを起動時にDLするかどうか。デバッグのためにオフにできるようにしている。
    'player_name':'', # 統計情報ビューに表示するプレイヤー名

    # debug
    'send_webhook':True, # OCR失敗時にwebhookで自動報告するかどうか
    'dbg_enable_output':True # GUIのoutput部分を表示するかどうか。Falseにすると標準出力される。
}