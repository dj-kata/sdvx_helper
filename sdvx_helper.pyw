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
import json, datetime
from PIL import Image, ImageFilter
from gen_summary import *
import imagehash, keyboard
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
sg.theme('SystemDefault')

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

class SDVXSwitcher:
    def __init__(self):
        self.detect_mode = detect_mode.init
        self.gui_mode    = gui_mode.init
        self.stop_thread = False # 強制停止用
        self.window = False
        self.obs = False
        self.plays = 0
        self.imgpath = os.getcwd()+'/out/capture.png'
        keyboard.add_hotkey('F6', self.save_screenshot_general)

        self.load_settings()
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

    def load_settings(self):
        default_val = {
            'lx':0, 'ly':0,
            'host':'localhost', 'port':'4444', 'passwd':'',
            'autosave_dir':'','autosave_always':False,
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
            # others
            'ignore_rankD':True,
        }
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
        return ret

    def save_settings(self):
        with open(SETTING_FILE, 'w') as f:
            json.dump(self.settings, f, indent=2)

    def save_screenshot_general(self):
        ts = os.path.getmtime(self.imgpath)
        now = datetime.datetime.fromtimestamp(ts)
        fmtnow = format(now, "%Y%m%d_%H%M%S")
        dst = f"{self.settings['autosave_dir']}/sdvx_{fmtnow}.png"
        tmp = self.get_capture_after_rotate(self.imgpath)
        tmp.save(dst)
        self.gen_summary.generate() # ここでサマリも更新
        print(f"スクリーンショットを保存しました -> {dst}")

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
        ico=self.ico_path('icon.ico')
        self.window = sg.Window(f"SDVX switcher - OBS制御設定", layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=ico,location=(self.settings['lx'], self.settings['ly']))

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
        ]
        layout = [
            [sg.Frame('OBS設定', layout=layout_obs, title_color='#000044')],
            [sg.Frame('ゲームモード等の設定', layout=layout_gamemode, title_color='#000044')],
            [sg.Frame('リザルト自動保存設定', layout=layout_autosave, title_color='#000044')],
        ]
        self.window = sg.Window('SDVX switcher', layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=self.ico_path('icon.ico'),location=(self.settings['lx'], self.settings['ly']))

    def gui_main(self):
        self.gui_mode = gui_mode.main
        if self.window:
            self.window.close()
        menuitems = [['ファイル',['設定','OBS制御設定']]]
        layout = [
            [sg.Menubar(menuitems, key='menu')],
            [
                par_text('plays:'), par_text(str(self.plays), key='txt_plays')
                ,par_text('mode:'), par_text(self.detect_mode.name, key='txt_mode')
                ,par_text('warning! OBSに接続できません', key='txt_obswarning', text_color="#ff0000")],
            [par_btn('save', tooltip='画像を保存します', key='btn_savefig')],
            [par_text('', size=(40,1), key='txt_info')],
            [sg.Output(size=(63,8), key='output', font=(None, 9))],
        ]
        ico=self.ico_path('icon.ico')
        self.window = sg.Window('SDVX switcher', layout, grab_anywhere=True,return_keyboard_events=True,resizable=False,finalize=True,enable_close_attempted_event=True,icon=ico,location=(self.settings['lx'], self.settings['ly']))
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
                self.window['txt_obswarning'].update('warning! OBSに接続できません')
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
        img = self.get_capture_after_rotate().crop((0,1310,149,1609))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/onselect.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        return ret

    # 現在の画面がリザルト画面かどうか判定
    def is_onresult(self):
        img = self.get_capture_after_rotate()

        cr = img.crop((340,1600,539,1639))
        tmp = imagehash.average_hash(cr)
        img_j = Image.open('resources/onresult.png')
        hash_target = imagehash.average_hash(img_j)
        ret = abs(hash_target - tmp) <5 

        cr = img.crop((0,0,1079,149))
        tmp2 = imagehash.average_hash(cr)
        img_j = Image.open('resources/result_head.png')
        hash_target2 = imagehash.average_hash(img_j)
        ret2 = abs(hash_target2 - tmp2) < 5

        cr = img.crop((30,1390,239,1429))
        tmp = imagehash.average_hash(cr)
        img_j = Image.open('resources/onresult2.png')
        hash_target = imagehash.average_hash(img_j)
        ret3 = abs(hash_target - tmp) < 5

        return ret & ret2 & ret3

    # 現在の画面がプレー中かどうか判定
    def is_onplay(self):
        img = self.get_capture_after_rotate().crop((0,0,1080,200))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/onplay.png') #.crop((550,1,750,85))
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        return ret

    # 現在の画面が曲決定画面かどうか判定
    def is_ondetect(self):
        # cropは右下まで入るので注意。実際のサイズは170x130となる。
        img = self.get_capture_after_rotate().crop((240,1253,409,1382))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/ondetect.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        return ret
    
    # result, playの後の遷移画面(ゲームタイトルロゴ)かどうかを判定
    def is_onlogo(self):
        img = self.get_capture_after_rotate().crop((460,850,659,1049))
        tmp = imagehash.average_hash(img)
        img = Image.open('resources/logo.png')
        hash_target = imagehash.average_hash(img)
        ret = abs(hash_target - tmp) < 10
        return ret
    
    # 曲情報を切り出して保存
    def update_musicinfo(self):
        img = self.get_capture_after_rotate()
        jacket = img.crop((237,387, 843,993))
        jacket.save('out/select_jacket.png')
        title = img.crop((201,1091, 878,1212))
        title.save('out/select_title.png')
        lv = img.crop((908,1107, 998,1192))
        lv.save('out/select_level.png')
        bpm = img.crop((97,1127, 160,1172))
        bpm.save('out/select_bpm.png')
        ef = img.crop((313,1275, 803,1302))
        ef.save('out/select_effector.png')
        illust = img.crop((313,1333, 803,1360))
        illust.save('out/select_illustrator.png')
        self.obs.refresh_source('nowplaying')
        self.obs.refresh_source('nowplaying.html')

        img.save('out/select_whole.png')

    # メイン処理のループ
    # 速度を重視するため、認識処理は回転する前に行っておく
    def detect(self):
        # TODO 
        # 1. 曲決定画面での処理
        # 2. プレー画面での処理
        if self.obs == False:
            logger.debug('cannot connect to OBS -> exit')
            return False
        logger.debug(f'OBSver:{self.obs.ws.get_version().obs_version}, RPCver:{self.obs.ws.get_version().rpc_version}, OBSWSver:{self.obs.ws.get_version().obs_web_socket_version}')
        done_thissong = False # 曲決定画面の抽出が重いため1曲あたり一度しか行わないように制御
        while True:
            self.obs.save_screenshot()
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
            if self.detect_mode == detect_mode.select:
                if not self.is_onselect():
                    self.detect_mode = detect_mode.init
            if self.detect_mode == detect_mode.init:
                if not done_thissong:
                    if self.is_ondetect():
                        print(f"曲決定画面を検出")
                        time.sleep(2)
                        self.obs.save_screenshot()
                        self.update_musicinfo()
                        done_thissong = True
                if self.is_onplay() and done_thissong: # 曲決定画面を検出してから入る(曲終了時に何度も入らないように)
                    self.detect_mode = detect_mode.play

            # 状態遷移判定
            if pre_mode != self.detect_mode:
                if self.detect_mode == detect_mode.play:
                    self.control_obs_sources('play0')
                    self.plays += 1
                    self.window['txt_plays'].update(str(self.plays))
                    done_thissong = False # 曲が始まるタイミングでクリア
                if self.detect_mode == detect_mode.result:
                    self.control_obs_sources('result0')
                    if self.settings['autosave_always']:
                        self.save_screenshot_general()
                if self.detect_mode == detect_mode.select:
                    self.control_obs_sources('select0')

                if pre_mode == detect_mode.play:
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
        now_mod = now - datetime.timedelta(hours=2) # 多少の猶予をつける。2時間前までは遡る

        self.gen_summary = GenSummary(now_mod, self.settings['autosave_dir'], self.settings['ignore_rankD'])
        self.gen_summary.generate()
        self.gui_main()
        self.th = False
        self.control_obs_sources('boot')
        th = threading.Thread(target=self.detect, daemon=True)
        th.start()

        while True:
            ev, val = self.window.read()
            #logger.debug(f"ev:{ev}")
            self.update_settings(ev, val)
            if ev in (sg.WIN_CLOSED, 'Escape:27', '-WINDOW CLOSE ATTEMPTED-', 'btn_close_info', 'btn_close_setting'):
                if self.gui_mode == gui_mode.main:
                    self.save_settings()
                    self.control_obs_sources('quit')
                    break
                else:
                    try:
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


            elif ev in ('btn_setting', '設定'):
                self.stop()
                self.gui_setting()

if __name__ == '__main__':
    a = SDVXSwitcher()
    a.main()