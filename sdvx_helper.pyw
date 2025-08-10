import pyautogui as pgui
import PySimpleGUI as sg
import numpy as np
import os, sys, re
import time
import threading
from obssocket import OBSSocket
import logging, logging.handlers
import traceback
from functools import partial
from tkinter import filedialog
import json, datetime, winsound
from PIL import Image, ImageFilter
from gen_summary import *
import imagehash, keyboard
import subprocess
from bs4 import BeautifulSoup
import requests
from manage_settings import *
from sdvxh_classes import *
import urllib
import webbrowser
from decimal import Decimal
# フラットウィンドウ、右下モード(左に上部側がくる)
# フルスクリーン、2560x1440に指定してもキャプは1920x1080で撮れてるっぽい

os.makedirs('jackets', exist_ok=True)
os.makedirs('log', exist_ok=True)
os.makedirs('out', exist_ok=True)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
hdl = logging.handlers.RotatingFileHandler(
    f'log/{os.path.basename(__file__).split(".")[0]}.log',
    encoding='utf-8',
    maxBytes=1024*1024*2,
    backupCount=1,
)
hdl.setLevel(logging.DEBUG)
hdl_formatter = logging.Formatter('%(asctime)s %(filename)s:%(lineno)5d %(funcName)s() [%(levelname)s] %(message)s')
hdl.setFormatter(hdl_formatter)
logger.addHandler(hdl)

### 固定値
FONT = ('Meiryo',12)
FONTs = ('Meiryo',8)
par_text = partial(sg.Text, font=FONT)
par_btn = partial(sg.Button, pad=(3,0), font=FONT, enable_events=True, border_width=0)
SETTING_FILE = 'settings.json'
sg.theme('SystemDefault')
try:
    with open('version.txt', 'r') as f:
        SWVER = f.readline().strip()
except Exception:
    SWVER = "v?.?.?"

class SDVXHelper:
    def __init__(self):
        self.ico=self.ico_path('icon.ico')
        self.detect_mode = detect_mode.init
        self.gui_mode    = gui_mode.init
        self.last_play0_time = datetime.datetime.now()
        self.last_play1_time = datetime.datetime.now()
        self.last_autosave_time = datetime.datetime.now()
        self.img_rot = False # 正しい向きに直したImage形式の画像
        self.stop_thread = False # 強制停止用
        self.is_blastermax = False
        self.gen_first_vf = False
        self.window = False
        self.obs = False
        # RTA関連
        self.rta_mode = False
        self.rta_finished = False
        self.rta_starttime = datetime.datetime.now()
        self.rta_endtime = datetime.datetime.now()
        self.rta_target_vf = Decimal('20.0')

        self.plays = 0
        self.playtime = datetime.timedelta(seconds=0) # 楽曲プレイ時間の合計
        self.imgpath = os.getcwd()+'/out/capture.png'

        keyboard.add_hotkey('F6', self.save_screenshot_general)
        keyboard.add_hotkey('F7', self.import_score_on_select_with_dialog)
        keyboard.add_hotkey('F8', self.update_rival)
        keyboard.add_hotkey('F3', self.start_rta_mode)

        self.load_settings()
        self.save_settings() # 値が追加された場合のために、一度保存
        self.update_musiclist()
        self.sdvx_logger = SDVXLogger(player_name=self.settings['player_name'])
        self.sdvx_logger.gen_sdvx_battle(False)
        self.vf_pre = self.sdvx_logger.total_vf # アプリ起動時のVF
        self.vf_cur = self.sdvx_logger.total_vf # 最新のVF
        self.connect_obs()
        vf_str = f"{self.settings['obs_txt_vf_header']}{self.vf_cur:.3f} ({self.vf_cur-self.vf_pre:+.3f}){self.settings['obs_txt_vf_footer']}"
        if self.obs != False:
            self.obs.change_text(self.settings['obs_txt_vf_with_diff'], vf_str)

        self.gen_summary = False
        logger.debug('created.')
        logger.debug(f'settings:{self.settings}')

    def ico_path(self, relative_path:str):
        """アイコン表示用

        Args:
            relative_path (str): アイコンファイル名

        Returns:
            str: アイコンファイルの絶対パス
        """
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
    
    def update_musiclist(self):
        """曲リスト(musiclist.pkl)を最新化する
        """
        try:
            if self.settings['autoload_musiclist']:
                with urllib.request.urlopen(self.params['url_musiclist']) as wf:
                    with open('resources/musiclist.pkl', 'wb') as f:
                        f.write(wf.read())
                print('musiclist.pklを更新しました。')
        except Exception:
            print(traceback.format_exc())

    def get_latest_version(self):
        """GitHubから最新版のバージョンを取得する。

        Returns:
            str: バージョン番号
        """
        ret = None
        url = 'https://github.com/dj-kata/sdvx_helper/tags'
        r = requests.get(url)
        soup = BeautifulSoup(r.text,features="html.parser")
        for tag in soup.find_all('a'):
            if 'releases/tag/v.' in tag['href']:
                ret = tag['href'].split('/')[-1]
                break # 1番上が最新なので即break
        return ret
    
    def load_settings(self):
        """ユーザ設定(self.settings)をロードしてself.settingsにセットする。一応返り値にもする。

        Returns:
            dict: ユーザ設定
        """
        ret = {}
        try:
            with open(SETTING_FILE) as f:
                ret = json.load(f)
                print(f"設定をロードしました。\n")
        except Exception as e:
            logger.debug(traceback.format_exc())
            print(f"有効な設定ファイルなし。デフォルト値を使います。")

        ### 後から追加した値がない場合にもここでケア
        for k in default_val.keys():
            if not k in ret.keys():
                print(f"{k}が設定ファイル内に存在しません。デフォルト値({default_val[k]}を登録します。)")
                ret[k] = default_val[k]
        self.settings = ret
        self.check_legacy_settings()
        with open(self.settings['params_json'], 'r') as f:
            self.params = json.load(f)
        return ret

    def save_settings(self):
        """ユーザ設定(self.settings)を保存する。
        """
        with open(SETTING_FILE, 'w') as f:
            json.dump(self.settings, f, indent=2)

    def check_legacy_settings(self):
        """古くなった設定からの移行時に呼び出す関数。古いパラメータがある際に一度だけ呼び出す想定。
        """
        if 'top_is_right' in self.settings.keys(): # 1.0.29, 画面回転モードの判定
            if self.settings['top_is_right']:
                self.settings['orientation_top'] = 'right'
            else:
                self.settings['orientation_top'] = 'left'
            self.settings.pop('top_is_right')
            print('old parameter is updated.\n(top_is_right -> orientation_top)')

    def save_screenshot_general(self):
        """ゲーム画面のスクショを保存する。ホットキーで呼び出す用。
        """
        title = False
        now = datetime.datetime.now()
        self.last_autosave_time = now
        fmtnow = format(now, "%Y%m%d_%H%M%S")
        dst = f"{self.settings['autosave_dir']}/sdvx_{fmtnow}.png"
        tmp = self.get_capture_after_rotate()
        self.gen_summary.cut_result_parts(tmp)
        cur,pre = self.gen_summary.get_score(tmp)
        res_ocr = self.gen_summary.ocr(notify=True)
        if res_ocr != False and self.detect_mode == detect_mode.result: # OCRで曲名認識に成功
            title = res_ocr
            for ch in ('\\', '/', ':', '*', '?', '"', '<', '>', '|'):
                title = title.replace(ch, '')
            dst = f"{self.settings['autosave_dir']}/sdvx_{title[:120]}_{self.gen_summary.difficulty.upper()}_{self.gen_summary.lamp}_{str(cur)[:-4]}_{fmtnow}.png"
        tmp.save(dst)
        lamp = ''
        difficulty = ''
        try:
            lamp = self.gen_summary.lamp
            difficulty = self.gen_summary.difficulty
        except:
            #print(traceback.format_exc())
            pass
        tmp_playdata = OnePlayData(title='???', cur_score=cur, pre_score=pre, lamp=lamp, difficulty=difficulty, date=fmtnow)
        if res_ocr != False: # OCR通過時、ファイルのタイムスタンプを使うためにここで作成
            ts = os.path.getmtime(dst)
            now = datetime.datetime.fromtimestamp(ts)
            tmp_playdata = self.sdvx_logger.push(res_ocr, cur, pre, self.gen_summary.lamp, self.gen_summary.difficulty, fmtnow)
            # RTA用
            if self.rta_mode:
                self.rta_logger.push(res_ocr, cur, pre, self.gen_summary.lamp, self.gen_summary.difficulty, fmtnow)
                self.rta_vf_cur = self.rta_logger.total_vf
                if Decimal(str(self.rta_vf_cur))>=Decimal(self.settings['rta_target_vf']):
                    self.rta_finished = True
                    current = self.rta_endtime if self.rta_finished else datetime.datetime.now()
                    self.rta_endtime = datetime.datetime.now()
                    rta_time = (self.rta_endtime - self.rta_starttime)
                    self.obs.change_text('sdvx_helper_rta_timer', str(rta_time).split('.')[0])
                    print(f"Timer stop! ({str(rta_time).split('.')[0]}), vf:{self.rta_vf_cur}")
                    self.rta_logger.rta_timer = str(rta_time).split('.')[0]
                    self.rta_logger.update_stats()
                rta_vf_str = f"{self.settings['obs_txt_vf_header']}{self.rta_vf_cur:.3f}{self.settings['obs_txt_vf_footer']}"
                self.obs.change_text('sdvx_helper_rta_vf', rta_vf_str)
                tmp_playdata.disp()
            self.vf_cur = self.sdvx_logger.total_vf # アプリ起動時のVF
            vf_str = f"{self.settings['obs_txt_vf_header']}{self.vf_cur:.3f} ({self.vf_cur-self.vf_pre:+.3f}){self.settings['obs_txt_vf_footer']}"
            self.obs.change_text(self.settings['obs_txt_vf_with_diff'], vf_str)
        self.th_webhook = threading.Thread(target=self.send_custom_webhook, args=(tmp_playdata,), daemon=True)
        self.th_webhook.start()
            
        self.gen_summary.generate() # ここでサマリも更新
        print(f"スクリーンショットを保存しました -> {dst}")

        # ライバル欄更新
        if type(title) == str:
            self.sdvx_logger.update_rival_view(title, self.gen_summary.difficulty.upper())
        
        self.update_mybest()

    def update_mybest(self):
        """自己べ情報をcsv出力する
        """
        try:
            if self.settings['my_googledrive'] != '':
                self.sdvx_logger.gen_best_csv(self.settings['my_googledrive']+'/sdvx_helper_best.csv')
        except Exception:
            logger.debug(traceback.format_exc())

    def load_rivallog(self):
        """前回起動時に保存していたライバルの自己べ情報を読み込む
        """
        try:
            with open('out/rival_log.pkl', 'rb') as f:
                self.rival_log = pickle.load(f)
        except:
            self.rival_log = {}
        logger.debug(f'rival_logに保存されたkey: {self.rival_log.keys()}')
        logger.debug(f'rival_scoreのkey: {self.sdvx_logger.rival_score.keys()}')
        for i,p in enumerate(self.sdvx_logger.rival_names): # rival_log['名前']=MusicInfoのリスト
            if p not in self.rival_log.keys():
                self.rival_log[p] = []
            logger.debug(f"rival: {p} - {len(self.sdvx_logger.rival_score[p])}件")

    def save_rivallog(self):
        """ライバルの自己べ情報を保存する
        """
        for i,p in enumerate(self.sdvx_logger.rival_names):
            self.rival_log[p] = self.sdvx_logger.rival_score[p]
        with open('out/rival_log.pkl', 'wb') as f:
            pickle.dump(self.rival_log, f)

    def check_rival_update(self):
        """ライバル挑戦状用の処理。ライバルの更新有無を確認し、更新された曲一覧をdictで返す。

        Returns:
            dict: 各ライバルの更新データ。key:ライバル名(str)
        """
        out = {}
        logger.debug(f"rival_names:{self.sdvx_logger.rival_names}")
        logger.debug(f"rival_log.keys():{self.rival_log.keys()}")
        for i,p in enumerate(self.sdvx_logger.rival_names):
            if p in self.rival_log.keys():
                out[p] = []

                # pklに保存していたライバルデータに対して逆引き用dict作成
                tmp = {}
                for s in self.rival_log[p]:
                    tmp[(s.title,s.difficulty)] = s

                # 検索
                for s in self.sdvx_logger.rival_score[p]:
                    new = None
                    # 既にスコアがついてた曲の更新時
                    if (s.title, s.difficulty) in tmp.keys():
                        if s.best_score > tmp[(s.title, s.difficulty)].best_score:
                            new = [s.title, s.difficulty, s.best_score, s.best_score-tmp[(s.title, s.difficulty)].best_score]
                    else: # 新規プレイ時
                        new = [s.title, s.difficulty, s.best_score, s.best_score]
                    # 自己べよりも高い場合は出力。自分が未プレーの場合は出力されない。
                    if new != None:
                        for i,my in enumerate(self.sdvx_logger.best_allfumen):
                            if (s.title==my.title) and (s.difficulty == my.difficulty.upper()): # TODO 自己べ情報のフォーマットを揃えたい
                                if s.best_score > my.best_score:
                                    new.append(my.best_score)
                                    out[p].append(new) # title, diff, score, diffだけ保持
                                    logger.debug(f'added! {new}')
                if len(out[p]) > 0:
                    print(f'ライバル:{p}から挑戦状が{len(out[p])}件届いています。')
                logger.debug(f'ライバル:{p}から挑戦状が{len(out[p])}件届いています。')
            #self.rival_log[p] = self.sdvx_logger.rival_score[i] # ライバルの一時スコアを保存する場合はこれ

        with open('out/rival_updates.xml', 'w', encoding='utf-8') as f:
            f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
            f.write(f'<Updates>\n')
            for p in out.keys(): # ライバルID
                for s in out[p]: # 曲
                    f.write("<Item>\n")
                    title_esc   = s[0].replace('&', '&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'",'&apos;')
                    difficulty  = s[1]
                    score       = s[2]
                    diff        = s[3]
                    myscore     = s[4]
                    _, info = self.sdvx_logger.get_fumen_data(s[0], difficulty)
                    lv = info.lv
                    f.write(f"    <rival>{p}</rival>\n")
                    f.write(f"    <lv>{lv}</lv>\n")
                    f.write(f"    <title>{title_esc}</title>\n")
                    f.write(f"    <difficulty>{difficulty}</difficulty>\n")
                    f.write(f"    <score>{score:,}</score>\n")
                    f.write(f"    <myscore>{myscore:,}</myscore>\n")
                    f.write(f"    <score_10k>{int(score/10000):,}</score_10k>\n")
                    f.write(f"    <myscore_10k>{int(myscore/10000):,}</myscore_10k>\n")
                    f.write(f"    <behind>{score - myscore}</behind>\n")
                    f.write(f"    <behind_fmt>{score - myscore:+,}</behind_fmt>\n")
                    f.write(f"    <behind_10k>{int((score - myscore)/10000)}</behind_10k>\n")
                    f.write(f"    <behind_fmt_10k>{int((score - myscore)/10000):+,}</behind_fmt_10k>\n")
                    f.write("</Item>\n")
            f.write(f'</Updates>\n')
        return out

    def update_rival(self):
        try:
            self.update_mybest()
            self.sdvx_logger.get_rival_score(self.settings['player_name'], self.settings['rival_names'], self.settings['rival_googledrive'])
            print(f"ライバルのスコアを取得完了しました。")
            self.check_rival_update()
        except Exception:
            logger.debug(traceback.format_exc())
            print('ライバルのログ取得に失敗しました。') # ネットワーク接続やURL設定を見直す必要がある

    def save_playerinfo(self):
        """プレイヤー情報(VF,段位)を切り出して画像として保存する。
        """
        vf_cur = self.img_rot.crop(self.get_detect_points('vf'))
        threshold = 1400000 if self.settings['save_on_capture'] else 700000
        if np.array(vf_cur).sum() > threshold:
            vf_cur.save('out/vf_cur.png')
            class_cur = self.img_rot.crop(self.get_detect_points('class'))
            class_cur.save('out/class_cur.png')
            if not self.gen_first_vf: # 本日1プレー目に保存しておく
                vf_cur.save('out/vf_pre.png')
                class_cur.save('out/class_pre.png')
                self.gen_first_vf = True

    def start_rta_mode(self):
        """RTA開始処理。変数の初期化などを行う。
        """
        self.rta_mode = True
        self.rta_finished = False
        self.rta_starttime = datetime.datetime.now()
        self.rta_logger = SDVXLogger(player_name=self.settings['player_name'], rta_mode=True)
        self.rta_target_vf = Decimal(self.settings['rta_target_vf'])
        rta_vf_str = f"{self.settings['obs_txt_vf_header']}0.000{self.settings['obs_txt_vf_footer']}"
        self.obs.change_text('sdvx_helper_rta_vf', rta_vf_str)
        print(f'RTAモードを開始します。\ntarget VF = {self.rta_target_vf}')

    def get_capture_after_rotate(self):
        """ゲーム画面のキャプチャを取得し、正しい向きに直す。self.img_rotにも格納する。

        Returns:
            PIL.Image: 取得したゲーム画面
        """
        while True:
            try:
                if self.settings['save_on_capture']:
                    self.obs.save_screenshot()
                    img = Image.open(self.imgpath)
                else:
                    img = self.obs.get_screenshot()
                if self.settings['orientation_top'] == 'right':
                    ret = img.rotate(90, expand=True)
                elif self.settings['orientation_top'] == 'left':
                    ret = img.rotate(270, expand=True)
                else:
                    ret = img.resize((1080,1920))
                break
            except Exception:
                continue
        self.img_rot = ret
        return ret
    
    def update_settings(self, ev, val):
        """GUIから値を取得し、設定の更新を行う。

        Args:
            ev (str): sgのイベント
            val (dict): sgの各GUIの値
        """
        if self.gui_mode == gui_mode.main:
            if self.settings['clip_lxly']:
                self.settings['lx'] = max(0, self.window.current_location()[0])
                self.settings['ly'] = max(0, self.window.current_location()[1])
            else:
                self.settings['lx'] = self.window.current_location()[0]
                self.settings['ly'] = self.window.current_location()[1]
        elif self.gui_mode == gui_mode.webhook:
            self.settings['webhook_player_name'] = val['player_name2']
        elif self.gui_mode == gui_mode.googledrive:
            self.settings['get_rival_score'] = val['get_rival_score']
            self.settings['update_rival_on_result'] = val['update_rival_on_result']
            self.settings['player_name'] = val['player_name3']
        elif self.gui_mode == gui_mode.setting:
            self.settings['clip_lxly'] = val['clip_lxly']
            self.settings['host'] = val['input_host']
            self.settings['port'] = val['input_port']
            self.settings['passwd'] = val['input_passwd']
            if val['orientation_top_right']:
                self.settings['orientation_top'] = 'right'
            elif val['orientation_top_top']:
                self.settings['orientation_top'] = 'top'
            elif val['orientation_top_left']:
                self.settings['orientation_top'] = 'left'
            self.settings['autosave_always'] = val['chk_always']
            self.settings['ignore_rankD'] = val['chk_ignore_rankD']
            self.settings['auto_update'] = val['chk_auto_update']
            #self.settings['obs_txt_plays'] = val['obs_txt_plays']
            self.settings['obs_txt_plays_header'] = val['obs_txt_plays_header']
            self.settings['obs_txt_plays_footer'] = val['obs_txt_plays_footer']
            self.settings['alert_blastermax'] = val['alert_blastermax']
            self.settings['logpic_bg_alpha'] = val['logpic_bg_alpha']
            self.settings['rta_target_vf'] = val['rta_target_vf']
            self.settings['player_name'] = val['player_name']
            self.sdvx_logger.player_name = val['player_name']
            self.settings['save_on_capture'] = val['save_on_capture']
            self.settings['save_jacketimg'] = val['save_jacketimg']
            self.settings['import_from_select'] = val['import_from_select']
            self.settings['import_arcade_score'] = val['import_arcade_score']
            self.settings['autosave_prewait'] = val['autosave_prewait']

    def build_layout_one_scene(self, name, LR=None):
        """OBS制御設定画面におけるシーン1つ分のGUIを出力する。

        Args:
            name (str): シーン名
            LR (bool, optional): 開始、終了があるシーンかどうかを指定。 Defaults to None.

        Returns:
            list: pysimpleguiで使うレイアウトを格納した配列。
        """
        if LR == None:
            sc = [
                    sg.Column([[par_text('表示する')],[sg.Listbox(self.settings[f'obs_enable_{name}'], key=f'obs_enable_{name}', size=(20,4))], [par_btn('add', key=f'add_enable_{name}'),par_btn('del', key=f'del_enable_{name}')]]),
                    sg.Column([[par_text('消す')],[sg.Listbox(self.settings[f'obs_disable_{name}'], key=f'obs_disable_{name}', size=(20,4))], [par_btn('add', key=f'add_disable_{name}'),par_btn('del', key=f'del_disable_{name}')]]),
                ]
        else:
            scL = [[
                    sg.Column([[par_text('表示する')],[sg.Listbox(self.settings[f'obs_enable_{name}0'], key=f'obs_enable_{name}0', size=(20,4))], [par_btn('add', key=f'add_enable_{name}0'),par_btn('del', key=f'del_enable_{name}0')]]),
                    sg.Column([[par_text('消す')],[sg.Listbox(self.settings[f'obs_disable_{name}0'], key=f'obs_disable_{name}0', size=(20,4))], [par_btn('add', key=f'add_disable_{name}0'),par_btn('del', key=f'del_disable_{name}0')]]),
                ]]
            scR = [[
                    sg.Column([[par_text('表示する')],[sg.Listbox(self.settings[f'obs_enable_{name}1'], key=f'obs_enable_{name}1', size=(20,4))], [par_btn('add', key=f'add_enable_{name}1'),par_btn('del', key=f'del_enable_{name}1')]]),
                    sg.Column([[par_text('消す')],[sg.Listbox(self.settings[f'obs_disable_{name}1'], key=f'obs_disable_{name}1', size=(20,4))], [par_btn('add', key=f'add_disable_{name}1'),par_btn('del', key=f'del_disable_{name}1')]]),
                ]]
            sc = [
                sg.Frame('開始時', scL, title_color='#440000'),sg.Frame('終了時', scR, title_color='#440000')
            ]
        ret = [
            [
                par_text('シーン:')
                ,par_text(self.settings[f'obs_scene_{name}'], size=(20, 1), key=f'obs_scene_{name}')
                ,par_btn('set', key=f'set_scene_{name}')
            ],
            sc
        ]
        return ret

    def gui_webhook(self):
        """カスタムWebhook設定画面のGUIを起動する。
        """
        self.gui_mode = gui_mode.init
        if self.window:
            self.window.close()

        layout_lvs = [
            [sg.Checkbox('all', key='webhook_enable_alllv', enable_events=True)]+[sg.Checkbox(f'{lv}', key=f'webhook_enable_lv{lv}') for lv in range(1,11)],
            [sg.Checkbox(f'{lv}', key=f'webhook_enable_lv{lv}') for lv in range(11,14)]+[sg.Checkbox(f'{lv}', key=f'webhook_enable_lv{lv}', default=True) for lv in range(14,21)]
        ]
        layout_lamps = [
            [
                sg.Checkbox('all', key='webhook_enable_alllamp', enable_events=True),
                sg.Checkbox('PUC', key='webhook_enable_puc', default=True),
                sg.Checkbox('UC', key='webhook_enable_uc',default=True),
                sg.Checkbox('EXC', key='webhook_enable_hard', default=True),
                sg.Checkbox('COMP', key='webhook_enable_clear', default=True),
                sg.Checkbox('Failed', key='webhook_enable_failed'),
            ]
        ]
        layout = [
            [sg.Text('プレーヤー名'), sg.Input(self.settings['webhook_player_name'], key='player_name2')],
            [sg.Listbox(self.settings['webhook_names'], size=(50, 5), key='list_webhook', enable_events=True), sg.Button('追加', key='webhook_add', tooltip='同じ名前の場合は上書きされます。'), sg.Button('削除', key='webhook_del')],
            [sg.Text('設定名'), sg.Input('', key='webhook_names', size=(63,1))],
            [sg.Text('Webhook URL(Discord)'), sg.Input('', key='webhook_urls', size=(50,1))],
            [sg.Checkbox('画像を送信する', key='webhook_enable_pics', default=True)],
            [sg.Frame('送信対象Lv', layout=layout_lvs, title_color='#000044')],
            [sg.Frame('送信対象ランプ', layout=layout_lamps, title_color='#000044')],
        ]

        self.gui_mode = gui_mode.webhook
        self.window = sg.Window(f"SDVX helper - カスタムWebhook設定", layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=self.ico,location=(self.settings['lx'], self.settings['ly']))

    def gui_googledrive(self):
        """Googleドライブ連携設定用のGUIを起動する。
        """
        self.gui_mode = gui_mode.init
        if self.window:
            self.window.close()
        layout_list = [
            [sg.Table([[self.settings['rival_names'][i], self.settings['rival_googledrive'][i]] for i in range(len(self.settings['rival_names']))], key='rival_names', auto_size_columns=False, headings=['name', 'gdrive_id'], size=(30,7), col_widths=[15, 30], justification='left', enable_events=True)],
        ]
        layout_btn = [
            [par_btn('追加', key='add_rival')],
            [par_btn('削除', key='del_rival')],
            [par_btn('URLを開く', key='open_rival')],
            #[par_btn('上書き', key='mod_rival')],
        ]
        layout = [
            [sg.Text('自分のプレーヤー名'), sg.Input(self.settings['player_name'], key='player_name3')],
            [par_text('自分のプレーデータ用自動保存先'), par_btn('変更', key='btn_my_googledrive')],
            [par_text(self.settings['my_googledrive'], key='txt_my_googledrive')],
            [sg.Checkbox('起動時にライバルのスコアを取得する',self.settings['get_rival_score'],key='get_rival_score', enable_events=True)],
            [sg.Checkbox('リザルト画面の度にライバル関連データを更新する',self.settings['update_rival_on_result'],key='update_rival_on_result', enable_events=True)],
            [par_text('ライバル名'), sg.Input('', key='rival_name', size=(30,1))],
            [par_text('ライバル用URL'), sg.Input('', key='rival_googledrive')],
            [sg.Column(layout_list), sg.Column(layout_btn)]
        ]
        self.gui_mode = gui_mode.googledrive
        self.window = sg.Window(f"SDVX helper - Googleドライブ設定", layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=self.ico,location=(self.settings['lx'], self.settings['ly']))

    def gui_obs_control(self):
        """OBS制御設定画面のGUIを起動する。
        """
        self.gui_mode = gui_mode.init
        if self.window:
            self.window.close()
        obs_scenes = []
        obs_sources = []
        if self.obs != False:
            tmp = self.obs.get_scenes()
            tmp.reverse()
            for s in tmp:
                obs_scenes.append(s['sceneName'])
        layout_select = self.build_layout_one_scene('select', 0)
        layout_play = self.build_layout_one_scene('play', 0)
        layout_result = self.build_layout_one_scene('result', 0)
        layout_boot = self.build_layout_one_scene('boot')
        layout_quit = self.build_layout_one_scene('quit')
        layout_obs2 = [
            [par_text('シーンコレクション(起動時に切り替え):'), sg.Combo(self.obs.get_scene_collection_list(), key='scene_collection', size=(40,1), enable_events=True)],
            [par_text('シーン:'), sg.Combo(obs_scenes, key='combo_scene', size=(40,1), enable_events=True)],
            [par_text('ソース:'),sg.Combo(obs_sources, key='combo_source', size=(40,1))],
            [par_text('ゲーム画面:'), par_text(self.settings['obs_source'], size=(20,1), key='obs_source'), par_btn('set', key='set_obs_source')],
            [sg.Frame('選曲画面',layout=layout_select, title_color='#000044')],
            [sg.Frame('プレー中',layout=layout_play, title_color='#000044')],
            [sg.Frame('リザルト画面',layout=layout_result, title_color='#000044')],
        ]
        layout_r = [
            [sg.Frame('打鍵カウンタ起動時', layout=layout_boot, title_color='#000044')],
            [sg.Frame('打鍵カウンタ終了時', layout=layout_quit, title_color='#000044')],
        ]

        col_l = sg.Column(layout_r)
        col_r = sg.Column(layout_obs2)

        layout = [
            [col_l, col_r],
            [sg.Text('', key='info', font=(None,9))]
        ]
        self.gui_mode = gui_mode.obs_control
        self.window = sg.Window(f"SDVX helper - OBS制御設定", layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=self.ico,location=(self.settings['lx'], self.settings['ly']))
        if self.settings['obs_scene_collection'] != '':
            self.window['scene_collection'].update(value=self.settings['obs_scene_collection'])

    def gui_setting(self):
        """設定画面のGUIを起動する。
        """
        self.gui_mode = detect_mode.init
        if self.window:
            self.window.close()
        layout_obs = [
            [par_text('OBS host: '), sg.Input(self.settings['host'], font=FONT, key='input_host', size=(20,20))],
            [par_text('OBS websocket port: '), sg.Input(self.settings['port'], font=FONT, key='input_port', size=(10,20))],
            [par_text('OBS websocket password'), sg.Input(self.settings['passwd'], font=FONT, key='input_passwd', size=(20,20), password_char='*')],
        ]
        layout_gamemode = [
            [par_text('画面の向き(設定画面で選んでいるもの)'),
             sg.Radio('頭が右', group_id='topmode',default=self.settings['orientation_top']=='right', enable_events=True, key='orientation_top_right'),
             sg.Radio('回転なし', group_id='topmode', default=self.settings['orientation_top']=='top', enable_events=True, key='orientation_top_top'),
             sg.Radio('頭が左', group_id='topmode', default=self.settings['orientation_top']=='left', enable_events=True, key='orientation_top_left'),
            ],
        ]
        list_vf = [f"{i}.000" for i in range(1,17)]
        list_vf += [z for sublist in [[x, y] for x, y in zip([f'{i}.000' for i in range(17,23)], [f'{i}.500' for i in range(17,23)])] for z in sublist]
        layout_etc = [
            [sg.Checkbox('画面取得時にファイル保存を行う(旧方式)', self.settings['save_on_capture'], key='save_on_capture', enable_events=True, tooltip='有効(旧方式): out/capture.pngに保存される\n無効(新方式): メモリ上で処理(ディスク負荷小)\n本ツールによってカクつきが発生する場合は有効にしてみてください。')],
            [par_text('リザルト自動保存先フォルダ'), par_btn('変更', key='btn_autosave_dir')],
            [sg.Text(self.settings['autosave_dir'], key='txt_autosave_dir')],
            [sg.Checkbox('更新に関係なく常時保存する',self.settings['autosave_always'],key='chk_always', enable_events=True), par_text('リザルト撮影前のwait', font=(None,10), tooltip=f'リザルト画面を認識してから自動保存するまでの待ち時間(デフォルト:0.0)\nネメシスクルーによって変なタイミングになってしまう場合への対策'),sg.Spin([f"{i/10:.1f}" for i in range(100)], self.settings['autosave_prewait'], readonly=True, key='autosave_prewait', size=(4,1))],
            [sg.Checkbox('サマリ画像生成時にrankDを無視する',self.settings['ignore_rankD'],key='chk_ignore_rankD', enable_events=True)],
            [sg.Button('保存したリザルト画像をプレーログに反映(重いです)', key='read_from_result')],
            [sg.Button('保存したリザルト画像からVFビュー用ジャケット画像を一括生成', key='gen_jacket_imgs')], 
            [sg.Checkbox('リザルト画面でジャケット画像を自動保存(VF表示ビュー用)', self.settings['save_jacketimg'], key='save_jacketimg')],
            [
                sg.Text('プレイ曲数用テキストの設定', tooltip=f'OBSで{self.settings["obs_txt_plays"]}という名前のテキストソースを作成しておくと、\n本日のプレイ曲数を表示することができます。'),
                sg.Text('ヘッダ', tooltip='"play: "や"本日の曲数:"など'),sg.Input(self.settings['obs_txt_plays_header'], key='obs_txt_plays_header', size=(10,1)),
                sg.Text('フッタ', tooltip='"plays", "曲"など'), sg.Input(self.settings['obs_txt_plays_footer'], key='obs_txt_plays_footer', size=(10,1)),
            ],
            [
                sg.Text('プレイ時間用テキストの設定', tooltip=f'OBSで{self.settings["obs_txt_playtime"]}という名前のテキストソースを作成しておくと、\n本日の総プレイ時間を表示することができます。'),
                sg.Text('ヘッダ', tooltip='"playtime: "や"本日のプレー時間:"など'),sg.Input(self.settings['obs_txt_playtime_header'], key='obs_txt_playtime_header', size=(10,1)),
                #sg.Text('フッタ', tooltip='"plays", "曲"など'), sg.Input(self.settings['obs_txt_plays_footer'], key='obs_txt_plays_footer', size=(10,1)),
            ],
            [
                par_text('RTA用設定'), par_text('target VF'), sg.Combo(list_vf, key='rta_target_vf', default_value=self.settings['rta_target_vf'], enable_events=True)
            ],
            [sg.Checkbox('BLASTER GAUGE最大時に音声でリマインドする',self.settings['alert_blastermax'],key='alert_blastermax', enable_events=True)],
            [sg.Text('ログ画像の背景の不透明度(0-255, 0:完全に透過)'), sg.Combo([i for i in range(256)],default_value=self.settings['logpic_bg_alpha'],key='logpic_bg_alpha', enable_events=True)],
            [sg.Checkbox('起動時にアップデートを確認する',self.settings['auto_update'],key='chk_auto_update', enable_events=True)],
            [sg.Text('sdvx_stats.htmlに表示するプレーヤー名'),sg.Input(self.settings['player_name'], key='player_name', size=(30,1))],
            [sg.Checkbox('選曲画面からスコアを取り込む',self.settings['import_from_select'],key='import_from_select', enable_events=True),sg.Checkbox('AC版の自己べも取り込む',self.settings['import_arcade_score'],key='import_arcade_score', enable_events=True)],
            [sg.Checkbox('ウィンドウの座標を0以上に補正する',self.settings['clip_lxly'],key='clip_lxly', enable_events=True, tooltip='設定ファイルに保存されるsdvx_helperウィンドウの座標がマイナスにならないようにします。(60p/120pを切り替える人向け)\n基本的には外しておいてOKです。')],
        ]
        layout = [
            [sg.Frame('OBS設定', layout=layout_obs, title_color='#000044')],
            [sg.Frame('ゲームモード等の設定', layout=layout_gamemode, title_color='#000044')],
            [sg.Frame('その他設定', layout=layout_etc, title_color='#000044')],
        ]
        self.gui_mode = gui_mode.setting
        self.window = sg.Window('SDVX helper', layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=self.ico,location=(self.settings['lx'], self.settings['ly']))

    def gui_main(self):
        """メイン画面のGUIを起動する。
        """
        self.gui_mode = detect_mode.init
        self.detect_mode = detect_mode.init
        if self.window:
            self.window.close()
        menuitems = [
            ['ファイル',['設定','OBS制御設定', 'カスタムWebhook設定', 'アップデートを確認']],
            ['ライバル関連',['Googleドライブ設定(ライバル関連)', 'ライバルのスコアを取得']],
            ['RTA',['RTA開始']],
            ['分析',['VF内訳をツイート', '全プレーログをCSV出力', '自己ベストをCSV出力']]
        ]
        layout = [
            [sg.Menubar(menuitems, key='menu')],
            [
                par_text('plays:'), par_text(str(self.plays), key='txt_plays')
                ,par_text('mode:'), par_text(self.detect_mode.name, key='txt_mode')
                ,par_text('error! OBS接続不可', key='txt_obswarning', text_color="#ff0000")],
            [par_btn('save', tooltip='画像を保存します', key='btn_savefig')],
            [par_text('', size=(40,1), key='txt_info')],
        ]
        if self.settings['dbg_enable_output']:
            layout.append([sg.Output(size=(63,8), key='output', font=(None, 9))])
        self.gui_mode = gui_mode.main
        self.window = sg.Window('SDVX helper', layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=self.ico,location=(self.settings['lx'], self.settings['ly']))
        if self.connect_obs():
            self.window['txt_obswarning'].update('')

    def start_detect(self):
        """認識スレッドを開始する。
        """
        logger.debug('starting detect thread')
        self.stop_thread = False
        self.th = threading.Thread(target=self.detect, daemon=True)
        self.th.start()

    def stop_detect(self):
        """認識スレッドを停止する。
        """
        logger.debug('stopping detect thread')
        if self.th != False:
            self.stop_thread = True
            self.th.join()
            self.stop_thread = False
            self.th = False

    def play_wav(self, filename:str):
        """指定した音声ファイルを再生する。

        Args:
            filename (str): 再生したいファイル名(フルパス)
        """
        try:
            winsound.PlaySound(filename, winsound.SND_FILENAME)
        except:
            logger.debug(traceback.format_exc())

    def connect_obs(self):
        if self.obs != False:
            self.obs.close()
            self.obs = False
        try:
            self.obs = OBSSocket(self.settings['host'], self.settings['port'], self.settings['passwd'], self.settings['obs_source'], self.imgpath)
            if self.gui_mode == gui_mode.main:
                self.window['txt_obswarning'].update('')
                print('OBSに接続しました')
            return True
        except:
            logger.debug(traceback.format_exc())
            self.obs = False
            print('obs socket error!')
            if self.gui_mode == gui_mode.main:
                self.window['txt_obswarning'].update('error! OBS接続不可')
                print('Error!! OBSとの接続に失敗しました。')
            return False

    def control_obs_sources(self, name:str):
        """OBSソースの表示・非表示及びシーン切り替えを行う。
        nameで適切なシーン名を指定する必要がある。

        Args:
            name (str): シーン名(boot,exit,play{0,1},select{0,1},result{0,1})

        Returns:
            bool: 正常終了していればTrue
        """
        if self.gui_mode == gui_mode.main:
            self.window['txt_mode'].update(self.detect_mode.name)
        if self.obs == False:
            logger.debug('cannot connect to OBS -> exit')
            return False
        logger.debug(f"name={name} (detect_mode={self.detect_mode.name})")
        name_common = name
        if name[-1] in ('0','1'):
            name_common = name[:-1]
        scene = self.settings[f'obs_scene_{name_common}']
        # TODO 前のシーンと同じなら変えないようにしたい
        if scene != '':
            self.obs.change_scene(scene)
        # 非表示の制御
        for s in self.settings[f"obs_disable_{name}"]:
            tmps, tmpid = self.obs.search_itemid(scene, s)
            self.obs.disable_source(tmps,tmpid)
            #print('disable', scene, s, tmps, tmpid)
        # 表示の制御
        for s in self.settings[f"obs_enable_{name}"]:
            tmps, tmpid = self.obs.search_itemid(scene, s)
            #self.obs.refresh_source(s)
            self.obs.enable_source(tmps,tmpid)
            #print('enable', scene, s, tmps, tmpid)
        return True
    
    def is_onselect(self):
        """現在の画面が選曲画面かどうか判定し、結果を返す

        Returns:
            bool: 選曲画面かどうか
        """
        img = self.img_rot.crop(self.get_detect_points('onselect'))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/onselect.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 5
        #logger.debug(f'onselect diff:{abs(hash_target-tmp)}')
        return ret

    def is_onresult(self):
        """現在の画面がリザルト画面かどうか判定し、結果を返す

        Returns:
            bool: リザルト画面かどうか
        """
        cr = self.img_rot.crop(self.get_detect_points('onresult_val0'))
        tmp = imagehash.average_hash(cr)
        img_j = Image.open('resources/onresult.png')
        hash_target = imagehash.average_hash(img_j)
        val0 = abs(hash_target - tmp) <5 

        cr = self.img_rot.crop(self.get_detect_points('onresult_val1'))
        tmp = imagehash.average_hash(cr)
        img_j = Image.open('resources/onresult2.png')
        hash_target = imagehash.average_hash(img_j)
        val1 = abs(hash_target - tmp) < 5

        ret = val0 & val1
        if self.params['onresult_enable_head']:
            cr = self.img_rot.crop(self.get_detect_points('onresult_head'))
            tmp = imagehash.average_hash(cr)
            img_j = Image.open('resources/result_head.png')
            hash_target2 = imagehash.average_hash(img_j)
            val2 = abs(hash_target2 - tmp) < 5
            ret &= val2

        return ret

    def is_onplay(self):
        """現在の画面がプレー画面かどうか判定し、結果を返す

        Returns:
            bool: プレー画面かどうか
        """
        img = self.img_rot.crop(self.get_detect_points('onplay_val1'))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/onplay1.png')
        hash_target = imagehash.average_hash(img)
        ret1 = abs(hash_target - tmp) < 10
        img = self.img_rot.crop(self.get_detect_points('onplay_val2'))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/onplay2.png')
        hash_target = imagehash.average_hash(img)
        ret2 = abs(hash_target - tmp) < 10
        return ret1&ret2

    def is_ondetect(self):
        """現在の画面が曲決定画面かどうか判定し、結果を返す

        Returns:
            bool: 曲決定画面かどうか
        """
        img = self.img_rot.crop(self.get_detect_points('ondetect'))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/ondetect.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        return ret
    
    def is_onlogo(self):
        """現在の画面が遷移画面(ゲームタイトルロゴ)画面かどうか判定し、結果を返す

        Returns:
            bool: 遷移画面(ゲームタイトルロゴ)画面かどうか
        """
        img = self.img_rot.crop(self.get_detect_points('onlogo'))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/logo.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        return ret
    
    def get_detect_points(self, name:str):
        """self.paramsのパラメータ名を受け取り、四隅の座標を算出して返す

        Args:
            name (str): パラメータ名。params.jsonのパラメータ名のうち、_sxなどを含まない部分を指定すること。

        Returns:
            (int,int,int,int): sx,sy,ex,eyの4座標
        """
        sx = self.params[f'{name}_sx']
        sy = self.params[f'{name}_sy']
        ex = self.params[f'{name}_sx']+self.params[f'{name}_w']-1
        ey = self.params[f'{name}_sy']+self.params[f'{name}_h']-1
        return (sx,sy,ex,ey)
    
    def chk_blastermax(self) -> bool:
        """Blaster Gaugeが最大かどうかを検出する。

        Returns:
            bool: 最大ならTrue
        """
        img = self.img_rot.crop(self.get_detect_points('blastermax'))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/blastermax.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        self.is_blastermax = ret
        return ret
    
    def webhook_add(self, val:dict):
        """カスタムwebhookを登録する

        Args:
            val (dict): pysimpleguiのwindow.read()で貰えるval
        """
        if self.window['webhook_names'] == '':
            sg.popup_ok('設定名を入力してください。')
        else:
            if self.window['webhook_urls'] == '':
                sg.popup_ok('WebhookのURLを入力してください。')
            else: # 登録実行
                if val['webhook_names'] in self.settings['webhook_names']: # 上書きの場合
                    idx = self.settings['webhook_names'].index(val['webhook_names'])
                    self.settings['webhook_names'][idx] = val['webhook_names']
                    self.settings['webhook_urls'][idx] = val['webhook_urls']
                    self.settings['webhook_enable_pics'][idx] = val['webhook_enable_pics']
                    self.settings['webhook_enable_lvs'][idx] = [val[f'webhook_enable_lv{lv}'] for lv in range(1,21)]
                    self.settings['webhook_enable_lamps'][idx] = [val[f'webhook_enable_{l}'] for l in ('puc', 'uc', 'hard', 'clear', 'failed')]
                else:
                    self.settings['webhook_names'].append(val['webhook_names'])
                    self.settings['webhook_urls'].append(val['webhook_urls'])
                    self.settings['webhook_enable_pics'].append(val['webhook_enable_pics'])
                    self.settings['webhook_enable_lvs'].append([val[f'webhook_enable_lv{lv}'] for lv in range(1,21)])
                    self.settings['webhook_enable_lamps'].append([val[f'webhook_enable_{l}'] for l in ('puc', 'uc', 'hard', 'clear', 'failed')])
                self.set_webhook_ui_default()

    def webhook_del(self, val:dict):
        """登録されたカスタムwebhook情報を削除する。

        Args:
            val (dict): pysimpleguiのwindow.read()で貰えるval
        """
        if len(val['list_webhook']) > 0:
            idx = self.settings['webhook_names'].index(val['list_webhook'][0])
            self.settings['webhook_names'].pop(idx)
            self.settings['webhook_urls'].pop(idx)
            self.settings['webhook_enable_pics'].pop(idx)
            self.settings['webhook_enable_lvs'].pop(idx)
            self.settings['webhook_enable_lamps'].pop(idx)
            self.set_webhook_ui_default()

    def webhook_read(self, val:dict):
        """登録済みのカスタムwebhook情報を読み出してGUIに反映する。

        Args:
            val (dict): pysimpleguiのwindow.read()で貰えるval
        """
        if len(val['list_webhook']) > 0:
            key = val['list_webhook'][0]
            idx = self.settings['webhook_names'].index(key)
            self.window['webhook_names'].update(key)
            self.window['webhook_urls'].update(self.settings['webhook_urls'][idx])
            self.window['webhook_enable_pics'].update(self.settings['webhook_enable_pics'][idx])
            for i in range(1,21):
                self.window[f'webhook_enable_lv{i}'].update(self.settings['webhook_enable_lvs'][idx][i-1])
            for i,l in enumerate(('puc', 'uc', 'hard', 'clear', 'failed')):
                self.window[f'webhook_enable_{l}'].update(self.settings['webhook_enable_lamps'][idx][i])

    def set_webhook_ui_default(self):
        self.window['list_webhook'].update(self.settings['webhook_names'])
        self.window['webhook_names'].update('')
        self.window['webhook_urls'].update('')
        self.window['webhook_enable_pics'].update(True)
        for i in range(1,14):
            self.window[f'webhook_enable_lv{i}'].update(False)
        for i in range(14,21):
            self.window[f'webhook_enable_lv{i}'].update(True)
        for l in ('puc', 'uc', 'hard', 'clear'):
            self.window[f'webhook_enable_{l}'].update(True)
        self.window[f'webhook_enable_failed'].update(False)

    def send_custom_webhook(self, playdata:OnePlayData):
        """カスタムWebhookへの送出を行う

        Args:
            playdata (OnePlayData): 送るリザルトのデータ
        """
        diff_table = ['nov', 'adv', 'exh', 'APPEND']
        lamp_table = ['puc', 'uc', 'hard', 'clear', 'failed', '']
        lamp_idx = lamp_table.index(playdata.lamp)
        lv = '??'
        if playdata.title in self.sdvx_logger.titles.keys():
            lv     = self.sdvx_logger.titles[playdata.title][3+diff_table.index(playdata.difficulty)]
        img_bytes = io.BytesIO()
        self.img_rot.save(img_bytes, format='PNG')
        for i in range(len(self.settings['webhook_names'])):
            # 送出判定
            sendflg = True
            ## lv
            if type(lv) == int: # レベル単位の送出フラグを見る
                sendflg &= self.settings[f'webhook_enable_lvs'][i][lv-1]
            ## ランプ
            sendflg &= self.settings[f"webhook_enable_lamps"][i][lamp_idx]

            if not sendflg: # 送出条件を満たしていなければ飛ばす
                continue
            
            webhook = DiscordWebhook(url=self.settings['webhook_urls'][i], username=f"{self.settings['webhook_player_name']}")
            # 画像送信有効時のみ添付する
            if self.settings['webhook_enable_pics'][i]:
                webhook.add_file(file=img_bytes.getvalue(), filename=f'{playdata.date}.png')
            msg = f'**{playdata.title}** ({playdata.difficulty}, Lv{lv}),   '
            msg += f'{playdata.cur_score:,},   '
            msg += f'{playdata.lamp},   '
            webhook.content=msg
            try:
                res = webhook.execute()
            except Exception:
                print('webhook送出エラー(URLがおかしい？)')
                logger.debug(traceback.format_exc())

    def import_score_on_select_with_dialog(self):
        """ボタンを押したときだけ選曲画面から自己べを取り込む。合ってるかどうかの確認もやる。
        """
        self.window.write_event_value('-import_score_on_select-', " ")

    def detect(self):
        """認識処理を行う。無限ループになっており、メインスレッドから別スレッドで起動される。

        Returns:
            bool: エラー時にFalse
        """
        if self.obs == False:
            logger.debug('cannot connect to OBS -> exit')
            return False
        if self.settings['obs_source'] == '':
            print("\nゲーム画面用ソースが設定されていません。\nメニュー->OBS制御設定からゲーム画面の指定を行ってください。")
            self.window['txt_obswarning'].update('error! ゲーム画面未設定')
            return False
        obsv = self.obs.ws.get_version()
        if obsv != None:
            logger.debug(f'OBSver:{obsv.obs_version}, RPCver:{obsv.rpc_version}, OBSWSver:{obsv.obs_web_socket_version}')
        done_thissong = False # 曲決定画面の抽出が重いため1曲あたり一度しか行わないように制御
        self.obs.change_text(self.settings['obs_txt_playtime'], self.settings['obs_txt_playtime_header']+str(self.playtime).split('.')[0])
        while True:
            self.get_capture_after_rotate()
            pre_mode = self.detect_mode
            if self.rta_mode:
                current = self.rta_endtime if self.rta_finished else datetime.datetime.now()
                rta_time = (current - self.rta_starttime)
                self.obs.change_text('sdvx_helper_rta_timer', str(rta_time).split('.')[0])
            # 全モード共通の処理
            if self.is_onlogo():
                self.detect_mode = detect_mode.init
            elif self.is_onresult(): # 
                self.detect_mode = detect_mode.result
            elif self.is_onselect():
                self.detect_mode = detect_mode.select

            # モードごとの専用処理
            if self.detect_mode == detect_mode.play:
                playtime = self.playtime + (datetime.datetime.now() - self.last_play0_time)
                self.obs.change_text(self.settings['obs_txt_playtime'], self.settings['obs_txt_playtime_header']+str(playtime).split('.')[0])
                if not self.is_onplay():
                    self.detect_mode = detect_mode.init
            if self.detect_mode == detect_mode.result:
                if self.is_onresult():
                    self.save_playerinfo()
            if self.detect_mode == detect_mode.select:
                title, diff_hash, diff = self.gen_summary.ocr_only_jacket(
                    self.img_rot.crop(self.get_detect_points('select_jacket')),
                    self.img_rot.crop(self.get_detect_points('select_nov')),
                    self.img_rot.crop(self.get_detect_points('select_adv')),
                    self.img_rot.crop(self.get_detect_points('select_exh')),
                    self.img_rot.crop(self.get_detect_points('select_APPEND')),
                )
                # 選曲画面から自己べを取り込む
                if self.settings['import_from_select']:
                    sc,lamp,is_arcade = self.gen_summary.get_score_on_select(self.img_rot)
                    import_ok = True
                    if is_arcade and (not self.settings['import_arcade_score']):
                        import_ok = False
                    if import_ok:
                        now = datetime.datetime.now()
                        self.last_autosave_time = now
                        fmtnow = format(now, "%Y%m%d_%H%M%S")
                        best_sc = 0
                        best_lamp = 'failed'
                        lamp_table = ['puc', 'uc', 'hard', 'clear', 'failed']
                        for d in self.sdvx_logger.best_allfumen:
                            if (d.title == title) and (d.difficulty.lower() == diff.lower()):
                                best_sc = d.best_score
                                best_lamp = d.best_lamp
                        # 本ツール内のbestと合っていない場合(取り込み漏れorエラー動作)は選曲画面のスコアを登録
                        #if (sc!=best_sc) or (lamp_table.index(lamp) != lamp_table.index(best_lamp)):
                        if sc <= 10000000:
                            if (sc>best_sc) or (lamp_table.index(lamp) < lamp_table.index(best_lamp)):
                                print(f"選曲画面から自己ベストを登録しました。\n-> {title}({diff.upper()}): {sc:,}, {lamp}")
                                self.sdvx_logger.push(title, sc, 0, lamp, diff, fmtnow)
                                if self.rta_mode:
                                    self.rta_logger.push(title, sc, 0, lamp, diff, fmtnow)
                                self.check_rival_update() # お手紙ビューを更新
                if diff_hash < 8:
                    self.sdvx_logger.update_rival_view(title, diff)
                    self.sdvx_logger.gen_vf_onselect(title, diff)
                    self.sdvx_logger.gen_history_cursong(title, diff)
                if not self.is_onselect():
                    self.detect_mode = detect_mode.init
            if self.detect_mode == detect_mode.init:
                if not done_thissong:
                    if self.is_ondetect():
                        print(f"曲決定画面を検出")
                        time.sleep(self.params['detect_wait'])
                        self.get_capture_after_rotate()
                        self.gen_summary.update_musicinfo(self.img_rot)
                        self.obs.refresh_source('nowplaying.html')
                        self.obs.refresh_source('nowplaying')
                        # ライバル欄更新のため、曲決定画面からもOCRを動かしておく
                        title, diff_hash, diff = self.gen_summary.ocr_from_detect()
                        self.sdvx_logger.update_rival_view(title, diff)
                        self.sdvx_logger.gen_vf_onselect(title, diff)
                        self.sdvx_logger.gen_history_cursong(title, diff)
                        done_thissong = True
                #if self.is_onplay() and done_thissong: # 曲決定画面を検出してから入る(曲終了時に何度も入らないように)
                if self.is_onplay():
                    now = datetime.datetime.now()
                    time_delta = (now - self.last_play1_time).total_seconds()
                    #logger.debug(f'diff = {diff}s')
                    if time_delta > self.settings['play0_interval']: # 曲終わりのアニメーション後に再度入らないようにする
                        self.detect_mode = detect_mode.play

            # 状態遷移判定
            if pre_mode != self.detect_mode:
                if self.detect_mode == detect_mode.play:
                    self.last_play0_time = datetime.datetime.now()
                    self.control_obs_sources('play0')
                    self.plays += 1
                    self.window['txt_plays'].update(str(self.plays))
                    plays_str = f"{self.settings['obs_txt_plays_header']}{self.plays}{self.settings['obs_txt_plays_footer']}"
                    self.obs.change_text(self.settings['obs_txt_plays'], plays_str)
                    done_thissong = False # 曲が始まるタイミングでクリア
                if self.detect_mode == detect_mode.result:
                    self.control_obs_sources('result0')
                    time.sleep(float(self.settings['autosave_prewait']))
                    if self.settings['autosave_always']:
                        now = datetime.datetime.now()
                        diff = (now - self.last_autosave_time).total_seconds()
                        logger.debug(f'diff = {diff}s')
                        if diff > self.settings['autosave_interval']: # VF演出の前後で繰り返さないようにする
                            self.save_screenshot_general()
                            self.sdvx_logger.gen_sdvx_battle()
                if self.detect_mode == detect_mode.select:
                    self.control_obs_sources('select0')
                    if self.chk_blastermax():
                        self.obs.change_text(self.settings['obs_txt_blastermax'],'BLASTER GAUGEが最大です!!　　　　　　　　　　　　')
                        if self.settings['alert_blastermax']:
                            self.play_wav('resources/blastermax.wav')
                    else:
                        self.obs.change_text(self.settings['obs_txt_blastermax'],'')

                if pre_mode == detect_mode.play:
                    self.last_play1_time = datetime.datetime.now()
                    self.playtime += (self.last_play1_time - self.last_play0_time)
                    self.obs.change_text(self.settings['obs_txt_playtime'], self.settings['obs_txt_playtime_header']+str(self.playtime).split('.')[0])
                    self.control_obs_sources('play1')
                if pre_mode == detect_mode.result:
                    self.control_obs_sources('result1')
                if pre_mode == detect_mode.select:
                    self.control_obs_sources('select1')

            if self.stop_thread:
                break
            time.sleep(0.1)
        logger.debug(f'detect end!')

    def main(self):
        """メイン処理。PySimpleGUIのイベント処理など。
        """
        logger.debug('started')
        now = datetime.datetime.now()
        now_mod = now - datetime.timedelta(hours=self.settings['logpic_offset_time']) # 多少の猶予をつける。2時間前までは遡る

        self.gen_summary = GenSummary(now_mod)
        self.gen_summary.generate()
        self.starttime = now
        self.gui_main()
        if self.settings['get_rival_score']:
            try:
                self.sdvx_logger.get_rival_score(self.settings['player_name'], self.settings['rival_names'], self.settings['rival_googledrive'])
                print(f"ライバルのスコアを取得完了しました。")
            except Exception: # 関数全体が落ちる=Googleドライブへのアクセスでコケたときの対策
                logger.debug(traceback.format_exc())
                print('ライバルのログ取得に失敗しました。') # ネットワーク接続やURL設定を見直す必要がある
        self.load_rivallog()
        self.check_rival_update()
        self.th = False
        if type(self.obs) == OBSSocket:
            self.obs.set_scene_collection(self.settings['obs_scene_collection'])
        self.control_obs_sources('boot')
        plays_str = f"{self.settings['obs_txt_plays_header']}{self.plays}{self.settings['obs_txt_plays_footer']}"
        if self.obs != False:
            self.obs.change_text(self.settings['obs_txt_plays'], plays_str)
        self.start_detect()

        if self.settings['auto_update']:
            self.window.write_event_value('アップデートを確認', " ")

        while True:
            ev, val = self.window.read()
            #logger.debug(f"ev:{ev}")
            self.update_settings(ev, val)
            if ev in (sg.WIN_CLOSED, 'Escape:27', '-WINDOW CLOSE ATTEMPTED-', 'btn_close_info', 'btn_close_setting'):
                if self.gui_mode == gui_mode.main: # メインウィンドウを閉じた場合
                    self.save_settings()
                    # maya2serverへのアップロード
                    self.sdvx_logger.upload_best(volforce=self.vf_cur)
                    self.control_obs_sources('quit')
                    summary_filename = f"{self.settings['autosave_dir']}/{self.starttime.strftime('%Y%m%d')}_summary.png"
                    print(f"本日の成果一覧を保存中...\n==> {summary_filename}")
                    self.gen_summary.generate_today_all(summary_filename)
                    self.sdvx_logger.save_alllog()
                    self.sdvx_logger.gen_playcount_csv(self.settings['my_googledrive']+'/playcount.csv')
                    self.update_mybest()
                    self.save_rivallog()
                    print(f"プレーログを保存しました。")
                    vf_filename = f"{self.settings['autosave_dir']}/{self.starttime.strftime('%Y%m%d')}_total_vf.png"
                    #print(f"VF対象一覧を保存中 (OBSに設定していれば保存されます) ...\n==> {vf_filename}")
                    try:
                        tmps, tmpid = self.obs.search_itemid(self.settings[f'obs_scene_select'], 'sdvx_stats.html')
                        if self.obs.enable_source(tmps, tmpid):
                            time.sleep(2)
                            self.obs.ws.save_source_screenshot('sdvx_stats.html', 'png', vf_filename, 3000, 2300, 100)
                            print(f"VF対象一覧を保存しました。")
                            self.obs.disable_source(tmps, tmpid)
                    except Exception:
                        pass
                    try:
                        tmps, tmpid = self.obs.search_itemid(self.settings[f'obs_scene_select'], 'sdvx_stats_v2.html')
                        if self.obs.enable_source(tmps, tmpid):
                            time.sleep(2)
                            self.obs.ws.save_source_screenshot('sdvx_stats_v2.html', 'png', vf_filename, 3500, 2700, 100)
                            print(f"VF対象一覧を保存しました。")
                            self.obs.disable_source(tmps, tmpid)
                    except Exception:
                        pass
                    if self.rta_mode:
                        try:
                            tmps, tmpid = self.obs.search_itemid(self.settings[f'obs_scene_select'], 'rta_sdvx_stats_v2.html')
                            if self.obs.enable_source(tmps, tmpid):
                                time.sleep(2)
                                rta_filename = f"{self.settings['autosave_dir']}/{self.starttime.strftime('%Y%m%d')}_rta_result.png"
                                self.obs.ws.save_source_screenshot('rta_sdvx_stats_v2.html', 'png', rta_filename, 3500, 2700, 100)
                                print(f"RTAのリザルトを保存しました。")
                                self.obs.disable_source(tmps, tmpid)
                        except Exception:
                            pass
                    break
                else: # メイン以外のGUIを閉じた場合
                    self.start_detect()
                    try:
                        plays_str = f"{self.settings['obs_txt_plays_header']}{self.plays}{self.settings['obs_txt_plays_footer']}"
                        if self.obs != False:
                            self.obs.change_text(self.settings['obs_txt_plays'], plays_str)
                        self.gui_main()
                    except Exception as e:
                        print(traceback.format_exc())
            
            elif ev == 'OBS制御設定':
                self.stop_detect()
                if self.connect_obs():
                    self.gui_obs_control()
                else:
                    sg.popup_error('OBSに接続できません')
            elif ev == 'RTA開始':
                self.start_rta_mode()
            elif ev == 'btn_savefig':
                self.save_screenshot_general()

            elif ev == 'combo_scene': # シーン選択時にソース一覧を更新
                if self.obs != False:
                    sources = self.obs.get_sources(val['combo_scene'])
                    self.window['combo_source'].update(values=sources)
            elif ev == 'set_obs_source':
                tmp = val['combo_source'].strip()
                if tmp != "":
                    self.settings['obs_source'] = tmp
                    self.window['obs_source'].update(tmp)
            elif ev.startswith('set_scene_'): # 各画面のシーンsetボタン押下時
                tmp = val['combo_scene'].strip()
                self.settings[ev.replace('set_scene', 'obs_scene')] = tmp
                self.window[ev.replace('set_scene', 'obs_scene')].update(tmp)
            elif ev.startswith('add_enable_') or ev.startswith('add_disable_'):
                tmp = val['combo_source'].strip()
                key = ev.replace('add', 'obs')
                if tmp != "":
                    if tmp not in self.settings[key]:
                        self.settings[key].append(tmp)
                        self.window[key].update(self.settings[key])
            elif ev.startswith('del_enable_') or ev.startswith('del_disable_'):
                key = ev.replace('del', 'obs')
                if len(val[key]) > 0:
                    tmp = val[key][0]
                    if tmp != "":
                        if tmp in self.settings[key]:
                            self.settings[key].pop(self.settings[key].index(tmp))
                            self.window[key].update(self.settings[key])
            elif ev == 'scene_collection': # シーンコレクションを選択
                self.settings['obs_scene_collection'] = val[ev]
                self.obs.set_scene_collection(val[ev]) # そのシーンコレクションに切り替え
                time.sleep(3)
                obs_scenes = []
                tmp = self.obs.get_scenes()
                tmp.reverse()
                for s in tmp:
                    obs_scenes.append(s['sceneName'])
                self.window['combo_scene'].update(values=obs_scenes) # シーン一覧を更新
            elif ev == 'btn_autosave_dir':
                tmp = filedialog.askdirectory()
                if tmp != '':
                    self.settings['autosave_dir'] = tmp
                    self.window['txt_autosave_dir'].update(tmp)
            elif ev == 'btn_my_googledrive':
                tmp = filedialog.askdirectory()
                if tmp != '':
                    self.settings['my_googledrive'] = tmp
                    self.window['txt_my_googledrive'].update(tmp)

            elif ev == 'アップデートを確認':
                ver = self.get_latest_version()
                if ver != SWVER:
                    print(f'現在のバージョン: {SWVER}, 最新版:{ver}')
                    ans = sg.popup_yes_no(f'アップデートが見つかりました。\n\n{SWVER} -> {ver}\n\nアプリを終了して更新します。', icon=self.ico)
                    if ans == "Yes":
                        self.save_settings()
                        self.control_obs_sources('quit')
                        if os.path.exists('update.exe'):
                            logger.info('アップデート確認のため終了します')
                            res = subprocess.Popen('update.exe')
                            break
                        else:
                            sg.popup_error('update.exeがありません', icon=self.ico)
                else:
                    print(f'お使いのバージョンは最新です({SWVER})')

            elif ev in ('btn_setting', '設定'):
                self.stop_detect()
                self.gui_setting()
            elif ev == 'read_from_result':
                self.sdvx_logger.import_from_resultimg()
            elif ev == 'gen_jacket_imgs':
                self.sdvx_logger.gen_jacket_imgs()
            ### webhook関連
            elif ev == 'カスタムWebhook設定':
                self.stop_detect()
                self.gui_webhook()
            elif ev == 'Googleドライブ設定(ライバル関連)':
                self.stop_detect()
                self.gui_googledrive()
            elif ev == 'ライバルのスコアを取得':
                self.update_rival()
            elif ev == 'webhook_add':
                self.webhook_add(val)
            elif ev == 'webhook_del':
                self.webhook_del(val)
            elif ev == 'list_webhook':
                self.webhook_read(val)
            elif ev == 'webhook_enable_alllv':
                for i in range(1,21):
                    self.window[f"webhook_enable_lv{i}"].update(val[ev])
            elif ev == 'webhook_enable_alllamp':
                for l in ('puc', 'uc', 'hard', 'clear', 'failed'):
                    self.window[f"webhook_enable_{l}"].update(val[ev])

            ### Googleドライブ関連
            elif ev == 'add_rival':
                name = val['rival_name']
                url  = val['rival_googledrive']
                url_split = url.split('/')
                # https://drive.google.com/open?id=1VWSUs7DRBWBiKK2zmIyTknQiUugC6sVK&usp=drive_fs 
                # https://drive.google.com/file/d/10EeiBpPZCHBDTkeLfyZSB7rE_2ALIwBm/view
                if (len(url_split) == 7) and (len(url_split[6]) == 33) and (url_split[2]=='drive.google.com'):
                    url = url_split[6]
                elif (len(url_split) == 4): # エクスプローラでコピーした場合のURL
                    url = url_split[-1].split('=')[1].split('&')[0]
                logger.debug(f"name={name}, url={url}")
                if name != '' and url != '' and len(url) == 33:
                    self.settings['rival_names'].append(name)
                    self.settings['rival_googledrive'].append(url)
                    self.window['rival_name'].update('')
                    self.window['rival_googledrive'].update('')
                self.window['rival_names'].update([[self.settings['rival_names'][i], self.settings['rival_googledrive'][i]] for i in range(len(self.settings['rival_names']))])
            elif ev == 'del_rival':
                for idx in val['rival_names']:
                    self.settings['rival_names'].pop(idx)
                    self.settings['rival_googledrive'].pop(idx)
                self.window['rival_names'].update([[self.settings['rival_names'][i], self.settings['rival_googledrive'][i]] for i in range(len(self.settings['rival_names']))])
            elif ev == 'open_rival':
                for idx in val['rival_names']:
                    id = self.settings['rival_googledrive'][idx]
                    webbrowser.open(f"https://drive.google.com/file/d/{id}/view")

            ### ツイート機能
            elif ev == 'VF内訳をツイート':
                msg = self.sdvx_logger.analyze()
                encoded_msg = urllib.parse.quote(f"{msg}")
                webbrowser.open(f"https://twitter.com/intent/tweet?text={encoded_msg}")
            elif ev == '全プレーログをCSV出力':
                tmp = filedialog.asksaveasfilename(defaultextension='csv', filetypes=[("csv file", "*.csv")], initialdir='./', initialfile='sdvx_helper_alllog.csv')
                if tmp != '':
                    ret = self.sdvx_logger.gen_alllog_csv(tmp)
                    if ret:
                        sg.popup_ok(f'CSV出力完了\n\n(-> {tmp})')
                    else:
                        sg.popup_error(f'CSV出力失敗')
            elif ev == '自己ベストをCSV出力':
                tmp = filedialog.asksaveasfilename(defaultextension='csv', filetypes=[("csv file", "*.csv")], initialdir='./', initialfile='sdvx_helper_best.csv')
                if tmp != '':
                    ret = self.sdvx_logger.gen_best_csv(tmp)
                    if ret:
                        sg.popup_ok(f'CSV出力完了\n\n(-> {tmp})')
                    else:
                        sg.popup_error(f'CSV出力失敗')
            elif ev == '-import_score_on_select-':
                if self.detect_mode == detect_mode.select:
                    title, diff_hash, diff = self.gen_summary.ocr_only_jacket(
                        self.img_rot.crop(self.get_detect_points('select_jacket')),
                        self.img_rot.crop(self.get_detect_points('select_nov')),
                        self.img_rot.crop(self.get_detect_points('select_adv')),
                        self.img_rot.crop(self.get_detect_points('select_exh')),
                        self.img_rot.crop(self.get_detect_points('select_APPEND')),
                    )
                    sc,lamp,is_arcade = self.gen_summary.get_score_on_select(self.img_rot)
                    now = datetime.datetime.now()
                    self.last_autosave_time = now
                    fmtnow = format(now, "%Y%m%d_%H%M%S")
                    if sc <= 10000000:
                        ans = sg.popup_yes_no(f'以下の自己ベストを登録しますか？\ntitle:{title} ({diff})\nscore:{sc}, lamp:{lamp}, ACのスコアか?:{is_arcade}', icon=self.ico)
                        if ans == "Yes":
                            print(f"選曲画面から自己ベストを登録しました。\n-> {title}({diff.upper()}): {sc:,}, {lamp}")
                            self.sdvx_logger.push(title, sc, 0, lamp, diff, fmtnow)
                            if self.rta_mode:
                                self.rta_logger.push(title, sc, 0, lamp, diff, fmtnow)
                            self.check_rival_update() # お手紙ビューを更新
                    else:
                        print(f'取得失敗。スキップします。({title},{diff},{sc},{lamp})')
                else:
                    print(f'選曲画面ではないのでスキップします。')

if __name__ == '__main__':
    a = SDVXHelper()
    a.main()
