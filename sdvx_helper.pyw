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
from enum import Enum
from tkinter import filedialog
import json, datetime, winsound
from PIL import Image, ImageFilter
from gen_summary import *
import imagehash, keyboard
import subprocess
from bs4 import BeautifulSoup
import requests
from manage_settings import *
import urllib
# フラットウィンドウ、右下モード(左に上部側がくる)
# フルスクリーン、2560x1440に指定してもキャプは1920x1080で撮れてるっぽい

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
ALLLOG_FILE = 'alllog.pkl'
sg.theme('SystemDefault')
try:
    with open('version.txt', 'r') as f:
        SWVER = f.readline().strip()
except Exception:
    SWVER = "v?.?.?"

class gui_mode(Enum):
    init = 0
    main = 1
    setting = 2
    obs_control = 3
class detect_mode(Enum):
    init = 0
    select = 1
    play = 2
    result = 3

class OnePlayData:
    def __init__(self, title:str, cur_score:int, pre_score:int, lamp:str, difficulty:str, date:str):
        self.title = title
        self.cur_score = cur_score
        self.pre_score = pre_score
        self.lamp = lamp
        self.difficulty = difficulty
        self.date = date
        self.diff = cur_score - pre_score

    def __eq__(self, other):
        if not isinstance(other, OnePlayData):
            return NotImplemented

        return (self.title == other.title) and (self.difficulty == other.difficulty) and (self.cur_score == other.cur_score) and (self.pre_score == other.pre_score) and (self.lamp == other.lamp) and (self.date == other.date)
    
    def disp(self): # debug
        print(f"{self.title}({self.difficulty}), cur:{self.cur_score}, pre:{self.pre_score}({self.diff:+}), lamp:{self.lamp}, date:{self.date}")

class SDVXHelper:
    def __init__(self):
        self.ico=self.ico_path('icon.ico')
        self.detect_mode = detect_mode.init
        self.gui_mode    = gui_mode.init
        self.last_play0_time = datetime.datetime.now()
        self.last_autosave_time = datetime.datetime.now()
        self.img_rot = False # 正しい向きに直したImage形式の画像
        self.stop_thread = False # 強制停止用
        self.is_blastermax = False
        self.gen_first_vf = False
        self.window = False
        self.obs = False
        self.plays = 0
        self.imgpath = os.getcwd()+'/out/capture.png'
        keyboard.add_hotkey('F6', self.save_screenshot_general)

        self.load_settings()
        self.save_settings() # 値が追加された場合のために、一度保存
        self.load_alllog()
        self.update_musiclist()
        self.connect_obs()

        self.gen_summary = False
        logger.debug('created.')
        logger.debug(f'settings:{self.settings}')

    def ico_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
    
    # 曲リストを最新化
    def update_musiclist(self):
        if self.settings['autoload_musiclist']:
            urllib.request.urlretrieve(self.params['url_musiclist'], 'resources/musiclist.pkl')
        print('musiclist.pklを更新しました。')

    def get_latest_version(self):
        ret = None
        url = 'https://github.com/dj-kata/sdvx_helper/tags'
        r = requests.get(url)
        soup = BeautifulSoup(r.text,features="html.parser")
        for tag in soup.find_all('a'):
            if 'releases/tag/v.' in tag['href']:
                ret = tag['href'].split('/')[-1]
                break # 1番上が最新なので即break
        return ret
    
    def load_alllog(self):
        try:
            with open(ALLLOG_FILE, 'rb') as f:
                self.alllog = pickle.load(f)
        except Exception:
            print(f"プレーログファイル(alllog.pkl)がありません。新規作成します。")
            self.alllog = []

    def save_alllog(self):
        with open(ALLLOG_FILE, 'wb') as f:
            pickle.dump(self.alllog, f)

    def load_settings(self):
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
        with open(self.settings['params_json'], 'r') as f:
            self.params = json.load(f)
        return ret

    def save_settings(self):
        with open(SETTING_FILE, 'w') as f:
            json.dump(self.settings, f, indent=2)

    def save_screenshot_general(self):
        ts = os.path.getmtime(self.imgpath)
        now = datetime.datetime.fromtimestamp(ts)
        self.last_autosave_time = now
        fmtnow = format(now, "%Y%m%d_%H%M%S")
        dst = f"{self.settings['autosave_dir']}/sdvx_{fmtnow}.png"
        tmp = self.get_capture_after_rotate(self.imgpath)
        self.gen_summary.cut_result_parts(tmp)
        res_ocr = self.gen_summary.ocr()
        if res_ocr != False: # OCRで曲名認識に成功
            for ch in ('\\', '/', ':', '*', '?', '"', '<', '>', '|'):
                title = title.replace(ch, '')
            dst = f"{self.settings['autosave_dir']}/sdvx_{title[:120]}_{self.gen_summary.difficulty.upper()}_{self.gen_summary.lamp}_{str(cur)[:-4]}.png"
        tmp.save(dst)
        if res_ocr != False: # OCR通過時、ファイルのタイムスタンプを使うためにここで作成
            title = res_ocr
            ts = os.path.getmtime(dst)
            now = datetime.datetime.fromtimestamp(ts)
            fmtnow = format(now, "%Y%m%d_%H%M%S")
            cur,pre = self.gen_summary.get_score(tmp)
            onedata = OnePlayData(title=title, cur_score=cur, pre_score=pre, lamp=self.gen_summary.lamp, difficulty=self.gen_summary.difficulty, date=fmtnow)
            onedata.disp()
            self.alllog.append(onedata)
            
        self.gen_summary.generate() # ここでサマリも更新
        print(f"スクリーンショットを保存しました -> {dst}")

    def save_playerinfo(self):
        vf_cur = self.img_rot.crop(self.get_detect_points('vf'))
        if np.array(vf_cur).sum() > 1400000:
            vf_cur.save('out/vf_cur.png')
            class_cur = self.img_rot.crop(self.get_detect_points('class'))
            class_cur.save('out/class_cur.png')
            if not self.gen_first_vf: # 本日1プレー目に保存しておく
                vf_cur.save('out/vf_pre.png')
                class_cur.save('out/class_pre.png')
                self.gen_first_vf = True

    def get_capture_after_rotate(self, target=None):
        while True:
            try:
                if target==None:
                    img = Image.open(self.imgpath)
                else:
                    img = Image.open(target)
                if self.settings['top_is_right']:
                    ret = img.rotate(90, expand=True)
                else:
                    ret = img.rotate(270, expand=True)
                break
            except Exception:
                continue
        self.img_rot = ret
        return ret
    
    def update_settings(self, ev, val):
        if self.gui_mode == gui_mode.main:
            self.settings['lx'] = self.window.current_location()[0]
            self.settings['ly'] = self.window.current_location()[1]
        elif self.gui_mode == gui_mode.setting:
            self.settings['host'] = val['input_host']
            self.settings['port'] = val['input_port']
            self.settings['passwd'] = val['input_passwd']
            self.settings['top_is_right'] = val['top_is_right']
            self.settings['autosave_always'] = val['chk_always']
            self.settings['ignore_rankD'] = val['chk_ignore_rankD']
            self.settings['auto_update'] = val['chk_auto_update']
            #self.settings['obs_txt_plays'] = val['obs_txt_plays']
            self.settings['obs_txt_plays_header'] = val['obs_txt_plays_header']
            self.settings['obs_txt_plays_footer'] = val['obs_txt_plays_footer']
            self.settings['alert_blastermax'] = val['alert_blastermax']
            self.settings['logpic_bg_alpha'] = val['logpic_bg_alpha']

    def build_layout_one_scene(self, name, LR=None):
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

    def gui_obs_control(self):
        self.gui_mode = gui_mode.obs_control
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
        self.window = sg.Window(f"SDVX helper - OBS制御設定", layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=self.ico,location=(self.settings['lx'], self.settings['ly']))

    def gui_setting(self):
        self.gui_mode = gui_mode.setting
        if self.window:
            self.window.close()
        layout_obs = [
            [par_text('OBS host: '), sg.Input(self.settings['host'], font=FONT, key='input_host', size=(20,20))],
            [par_text('OBS websocket port: '), sg.Input(self.settings['port'], font=FONT, key='input_port', size=(10,20))],
            [par_text('OBS websocket password'), sg.Input(self.settings['passwd'], font=FONT, key='input_passwd', size=(20,20), password_char='*')],
        ]
        layout_gamemode = [
            [par_text('画面の向き(設定画面で選んでいるもの)'), sg.Radio('頭が右', group_id='topmode',default=self.settings['top_is_right'], key='top_is_right'), sg.Radio('頭が左', group_id='topmode', default=not self.settings['top_is_right'])],
        ]
        layout_autosave = [
            [par_text('リザルト自動保存先フォルダ'), par_btn('変更', key='btn_autosave_dir')],
            [sg.Text(self.settings['autosave_dir'], key='txt_autosave_dir')],
            [sg.Checkbox('更新に関係なく常時保存する',self.settings['autosave_always'],key='chk_always', enable_events=True)],
            [sg.Checkbox('サマリ画像生成時にrankDを無視する',self.settings['ignore_rankD'],key='chk_ignore_rankD', enable_events=True)],
            [sg.Text('プレイ曲数用テキストの設定', tooltip='OBSで指定した名前のテキストソースを作成しておくと、\n本日のプレイ曲数を表示することができます。')],
            [
                #par_text('テキストソース名'),sg.Input(self.settings['obs_txt_plays'], key='obs_txt_plays', size=(20,1)),
                sg.Text('ヘッダ', tooltip='"play: "や"本日の曲数:"など'),sg.Input(self.settings['obs_txt_plays_header'], key='obs_txt_plays_header', size=(10,1)),
                sg.Text('フッタ', tooltip='"plays", "曲"など'), sg.Input(self.settings['obs_txt_plays_footer'], key='obs_txt_plays_footer', size=(10,1)),
            ],
            [sg.Checkbox('BLASTER GAUGE最大時に音声でリマインドする',self.settings['alert_blastermax'],key='alert_blastermax', enable_events=True)],
            [par_text('ログ画像の背景の不透明度(0-255, 0:完全に透過)'), sg.Combo([i for i in range(256)],default_value=self.settings['logpic_bg_alpha'],key='logpic_bg_alpha', enable_events=True)],
            [sg.Checkbox('起動時にアップデートを確認する',self.settings['auto_update'],key='chk_auto_update', enable_events=True)],
        ]
        layout = [
            [sg.Frame('OBS設定', layout=layout_obs, title_color='#000044')],
            [sg.Frame('ゲームモード等の設定', layout=layout_gamemode, title_color='#000044')],
            [sg.Frame('その他設定', layout=layout_autosave, title_color='#000044')],
        ]
        self.window = sg.Window('SDVX helper', layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=self.ico,location=(self.settings['lx'], self.settings['ly']))

    def gui_main(self):
        self.gui_mode = gui_mode.main
        if self.window:
            self.window.close()
        menuitems = [['ファイル',['設定','OBS制御設定', 'アップデートを確認']]]
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
        self.window = sg.Window('SDVX helper', layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=self.ico,location=(self.settings['lx'], self.settings['ly']))
        if self.connect_obs():
            self.window['txt_obswarning'].update('')

    def start(self):
        self.stop_thread = False
        self.th = threading.Thread(target=self.detect, daemon=True)

    def stop(self):
        if self.th != False:
            self.stop_thread = True
            self.th.join()
            self.stop_thread = False
            self.th = False

    def play_wav(self, filename):
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

    # OBSソースの表示・非表示及びシーン切り替えを行う
    # nameで適切なシーン名を指定する必要がある。
    def control_obs_sources(self, name):
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
            self.obs.enable_source(tmps,tmpid)
            #print('enable', scene, s, tmps, tmpid)
        return True
    
    # 現在の画面が選曲画面かどうか判定
    def is_onselect(self):
        img = self.img_rot.crop(self.get_detect_points('onselect'))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/onselect.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        #logger.debug(f'onselect diff:{abs(hash_target-tmp)}')
        return ret

    # 現在の画面がリザルト画面かどうか判定
    def is_onresult(self):
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

    def get_detect_points(self, name):
        sx = self.params[f'{name}_sx']
        sy = self.params[f'{name}_sy']
        ex = self.params[f'{name}_sx']+self.params[f'{name}_w']-1
        ey = self.params[f'{name}_sy']+self.params[f'{name}_h']-1
        return (sx,sy,ex,ey)
    
    # 現在の画面がプレー中かどうか判定
    def is_onplay(self):
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

    # 現在の画面が曲決定画面かどうか判定
    def is_ondetect(self):
        img = self.img_rot.crop(self.get_detect_points('ondetect'))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/ondetect.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        return ret
    
    # result, playの後の遷移画面(ゲームタイトルロゴ)かどうかを判定
    def is_onlogo(self):
        img = self.img_rot.crop(self.get_detect_points('onlogo'))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/logo.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        return ret
    
    # blaster gaugeが最大かどうかを検出
    def chk_blastermax(self):
        img = self.img_rot.crop(self.get_detect_points('blastermax'))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/blastermax.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        self.is_blastermax = ret
        return ret
    
    # 曲情報を切り出して保存
    def update_musicinfo(self):
        jacket = self.img_rot.crop(self.get_detect_points('info_jacket'))
        jacket.save('out/select_jacket.png')
        title = self.img_rot.crop(self.get_detect_points('info_title'))
        title.save('out/select_title.png')
        lv = self.img_rot.crop(self.get_detect_points('info_lv'))
        lv.save('out/select_level.png')
        bpm = self.img_rot.crop(self.get_detect_points('info_bpm'))
        bpm.save('out/select_bpm.png')
        ef = self.img_rot.crop(self.get_detect_points('info_ef'))
        ef.save('out/select_effector.png')
        illust = self.img_rot.crop(self.get_detect_points('info_illust'))
        illust.save('out/select_illustrator.png')
        self.obs.refresh_source('nowplaying')
        self.obs.refresh_source('nowplaying.html')

        self.img_rot.save('out/select_whole.png')

    # メイン処理のループ
    # 速度を重視するため、認識処理は回転する前に行っておく
    def detect(self):
        if self.obs == False:
            logger.debug('cannot connect to OBS -> exit')
            return False
        if self.settings['obs_source'] == '':
            print("\nゲーム画面用ソースが設定されていません。\nメニュー->OBS制御設定からゲーム画面の指定を行ってください。")
            self.window['txt_obswarning'].update('error! ゲーム画面未設定')
            return False
        logger.debug(f'OBSver:{self.obs.ws.get_version().obs_version}, RPCver:{self.obs.ws.get_version().rpc_version}, OBSWSver:{self.obs.ws.get_version().obs_web_socket_version}')
        done_thissong = False # 曲決定画面の抽出が重いため1曲あたり一度しか行わないように制御
        while True:
            self.obs.save_screenshot()
            self.get_capture_after_rotate()
            pre_mode = self.detect_mode
            # 全モード共通の処理
            if self.is_onlogo():
                self.detect_mode = detect_mode.init
            elif self.is_onresult(): # 
                self.detect_mode = detect_mode.result
            elif self.is_onselect():
                self.detect_mode = detect_mode.select

            # モードごとの専用処理
            if self.detect_mode == detect_mode.play:
                if not self.is_onplay():
                    self.detect_mode = detect_mode.init
            if self.detect_mode == detect_mode.result:
                if self.is_onresult():
                    self.save_playerinfo()
            if self.detect_mode == detect_mode.select:
                if not self.is_onselect():
                    self.detect_mode = detect_mode.init
            if self.detect_mode == detect_mode.init:
                if not done_thissong:
                    if self.is_ondetect():
                        print(f"曲決定画面を検出")
                        time.sleep(self.settings['detect_wait'])
                        self.obs.save_screenshot()
                        self.get_capture_after_rotate()
                        self.update_musicinfo()
                        done_thissong = True
                #if self.is_onplay() and done_thissong: # 曲決定画面を検出してから入る(曲終了時に何度も入らないように)
                if self.is_onplay():
                    ts = os.path.getmtime(self.imgpath)
                    now = datetime.datetime.fromtimestamp(ts)
                    diff = (now - self.last_play0_time).total_seconds()
                    logger.debug(f'diff = {diff}s')
                    if diff > self.settings['play0_interval']: # 曲終わりのアニメーション後に再度入らないようにする
                        self.detect_mode = detect_mode.play

            # 状態遷移判定
            if pre_mode != self.detect_mode:
                if self.detect_mode == detect_mode.play:
                    self.control_obs_sources('play0')
                    self.plays += 1
                    self.window['txt_plays'].update(str(self.plays))
                    plays_str = f"{self.settings['obs_txt_plays_header']}{self.plays}{self.settings['obs_txt_plays_footer']}"
                    self.obs.change_text(self.settings['obs_txt_plays'], plays_str)
                    done_thissong = False # 曲が始まるタイミングでクリア
                if self.detect_mode == detect_mode.result:
                    self.control_obs_sources('result0')
                    if self.settings['autosave_always']:
                        ts = os.path.getmtime(self.imgpath)
                        now = datetime.datetime.fromtimestamp(ts)
                        diff = (now - self.last_autosave_time).total_seconds()
                        logger.debug(f'diff = {diff}s')
                        if diff > self.settings['autosave_interval']: # VF演出の前後で繰り返さないようにする
                            self.save_screenshot_general()
                if self.detect_mode == detect_mode.select:
                    self.control_obs_sources('select0')
                    if self.chk_blastermax():
                        self.obs.change_text(self.settings['obs_txt_blastermax'],'BLASTER GAUGEが最大です!!　　　　　　　　　　　　')
                        if self.settings['alert_blastermax']:
                            self.play_wav('resources/blastermax.wav')
                    else:
                        self.obs.change_text(self.settings['obs_txt_blastermax'],'')

                if pre_mode == detect_mode.play:
                    self.last_play0_time = datetime.datetime.now()
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
        now = datetime.datetime.now()
        now_mod = now - datetime.timedelta(hours=self.settings['logpic_offset_time']) # 多少の猶予をつける。2時間前までは遡る

        self.gen_summary = GenSummary(now_mod)
        self.gen_summary.generate()
        self.starttime = now
        self.gui_main()
        self.th = False
        self.control_obs_sources('boot')
        plays_str = f"{self.settings['obs_txt_plays_header']}{self.plays}{self.settings['obs_txt_plays_footer']}"
        if self.obs != False:
            self.obs.change_text(self.settings['obs_txt_plays'], plays_str)
        th = threading.Thread(target=self.detect, daemon=True)
        th.start()

        if self.settings['auto_update']:
            self.window.write_event_value('アップデートを確認', " ")

        while True:
            ev, val = self.window.read()
            #logger.debug(f"ev:{ev}")
            self.update_settings(ev, val)
            if ev in (sg.WIN_CLOSED, 'Escape:27', '-WINDOW CLOSE ATTEMPTED-', 'btn_close_info', 'btn_close_setting'):
                if self.gui_mode == gui_mode.main:
                    self.save_settings()
                    self.control_obs_sources('quit')
                    summary_filename = f"{self.settings['autosave_dir']}/{self.starttime.strftime('%Y%m%d')}_summary.png"
                    print(f"本日の成果一覧を保存中...\n==> {summary_filename}")
                    self.gen_summary.generate_today_all(summary_filename)
                    self.save_alllog()
                    print(f"プレーログを保存しました。")
                    break
                else:
                    try:
                        plays_str = f"{self.settings['obs_txt_plays_header']}{self.plays}{self.settings['obs_txt_plays_footer']}"
                        if self.obs != False:
                            self.obs.change_text(self.settings['obs_txt_plays'], plays_str)
                        self.gui_main()
                    except Exception as e:
                        print(traceback.format_exc())
            
            elif ev == 'OBS制御設定':
                if self.connect_obs():
                    self.gui_obs_control()
                else:
                    sg.popup_error('OBSに接続できません')
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
            elif ev == 'btn_autosave_dir':
                tmp = filedialog.askdirectory()
                if tmp != '':
                    self.settings['autosave_dir'] = tmp
                    self.window['txt_autosave_dir'].update(tmp)

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
                self.stop()
                self.gui_setting()

if __name__ == '__main__':
    a = SDVXHelper()
    a.main()