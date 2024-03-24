default_val = {
    'lx':0, 'ly':0,
    'host':'localhost', 'port':'4444', 'passwd':'',
    'autosave_dir':'','autosave_always':False,'autosave_interval':60,'play0_interval':10,
    'autosave_prewait':'0.0', # リザルト画面を認識して撮影するまでの待ち時間(クルーに対する調整用)
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
    # VF表示用
    'obs_txt_vf_with_diff':'sdvx_helper_vf_with_diff', 'obs_txt_vf_header':'VF: ', 'obs_txt_vf_footer':'',
    # プレイ時間表示用
    'obs_txt_playtime':'sdvx_helper_playtime', 'obs_txt_playtime_header':'playtime: ', 'obs_txt_playtime_footer':'',
    # ブラスターゲージMAX時のリマインド用
    'obs_txt_blastermax':'sdvx_helper_blastermax','alert_blastermax':False,
    # sdvx_helperで使うシーンコレクション
    'obs_scene_collection':'',

    # カスタムwebhook用
    # それぞれ1エントリが1つの設定に対応。(全ての配列が同じ長さになる)
    'webhook_player_name':'', # webhook送信時のプレーヤ名(元のplayer_nameと独立させるために追加)
    'webhook_names':[], # 1entry: 説明文(str)
    'webhook_urls':[], # 1entry: url(str)
    'webhook_enable_pics':[], # 1entry:bool (画像を送信するかどうか)
    'webhook_enable_lvs':[], # 1entry:[False,False,...True]のような長さ20の配列(lv1-20)
    'webhook_enable_lamps':[], # 1entry:[True,True,False,False,False] puc,uc,hard,clear,failed

    # Googleドライブ連携用(自動保存及びライバル用)
    'get_rival_score':False,
    'my_googledrive':'',
    'rival_names':[],
    'rival_googledrive':[],

    # 選曲画面で自己べを取り込むための設定
    'import_from_select': False,
    'import_arcade_score': False, # AC自己べのものを許容するか

    # others
    'ignore_rankD':True, 'auto_update':True,
    'params_json':'resources/params.json',
    'logpic_offset_time':2, # ログ画像について、起動の何時間前以降を対象とするか
    'logpic_bg_alpha':255, # ログ画像について、背景の透明度(0-255, 0:完全に透過)
    'autoload_musiclist':True, # 曲リストを起動時にDLするかどうか。デバッグのためにオフにできるようにしている。
    'player_name':'', # 統計情報ビューに表示するプレイヤー名
    'save_on_capture':True, # 画面取得方式。True:旧方式、False:新方式(jpeg)
    'save_jacketimg':True, # OCR時にジャケット画像を保存する(保存先はjackets/内。VFビュー用。)
    'update_rival_on_result':False, # リザルト画面のたびにライバル関連データを更新するかどうか

    # debug
    'send_webhook':True, # OCR失敗時にwebhookで自動報告するかどうか
    'dbg_enable_output':True # GUIのoutput部分を表示するかどうか。Falseにすると標準出力される。
}
