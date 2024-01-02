import sys, os
from PIL import Image
import pyautogui as pgui
import PySimpleGUI as sg
import numpy as np
import logging, logging.handlers
import traceback
import urllib, requests
from bs4 import BeautifulSoup
import pickle, json
from gen_summary import *
from manage_settings import *
from sdvxh_classes import *
from functools import partial
import datetime

os.makedirs('log', exist_ok=True)
os.makedirs('out', exist_ok=True)
os.makedirs('jackets', exist_ok=True)
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
lamp_table = ['FAILED', 'COMP', 'EXC', 'UC', 'PUC']

# TODO
## Lv一覧の作成
## 全譜面の自己べ情報抽出


class ScoreViewer:
    def __init__(self):
        self.load_settings()
        self.update_musiclist()
        self.load_musiclist()
        self.sdvx_logger = SDVXLogger()
        self.window = None

    def load_musiclist(self):
        try:
            with open('resources/musiclist.pkl', 'rb') as f:
                self.musiclist = pickle.load(f)
        except:
            print('musiclist読み込み時エラー。新規作成します。')
            self.musiclist = {}
            self.musiclist['jacket'] = {}
            self.musiclist['jacket']['nov'] = {}
            self.musiclist['jacket']['adv'] = {}
            self.musiclist['jacket']['exh'] = {}
            self.musiclist['jacket']['APPEND'] = {}
            self.musiclist['info'] = {}
            self.musiclist['info']['nov'] = {}
            self.musiclist['info']['adv'] = {}
            self.musiclist['info']['exh'] = {}
            self.musiclist['info']['APPEND'] = {}

    # 曲リストを最新化
    def update_musiclist(self):
        try:
            if self.settings['autoload_musiclist']:
                with urllib.request.urlopen(self.params['url_musiclist']) as wf:
                    with open('resources/musiclist.pkl', 'wb') as f:
                        f.write(wf.read())
                print('musiclist.pklを更新しました。')
        except Exception:
            print(traceback.format_exc())

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

    def ico_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
    
    def gui(self):
        layout_filter = [
            [sg.Checkbox('all', key='alllv', default=True, enable_events=True)],
            [sg.Checkbox(f"{lv:02d}", key=f'lv{lv}', default=True, enable_events=True) for lv in range(1,11)],
            [sg.Checkbox(lv, key=f'lv{lv}', default=True, enable_events=True) for lv in range(11,21)],
            [par_text('search'), sg.Input('', key='txt_filter', enable_events=True), par_btn('clear', key='btn_clear')]
        ]
        layout_sort = [
            [
                sg.Radio('降順', key='order_descend', group_id='order', default=True, enable_events=True),
                sg.Radio('昇順', group_id='order', key='order_ascend', enable_events=True),
            ],
            [par_text('ソート対象')],
            [
                sg.Radio('VF', group_id='sort_key', enable_events=True, key='sort_vf', default=True),
                sg.Radio('Lv', group_id='sort_key', enable_events=True, key='sort_lv'),
                sg.Radio('曲名', group_id='sort_key', enable_events=True, key='sort_title'),
                sg.Radio('スコア', group_id='sort_key', enable_events=True, key='sort_score'),
                sg.Radio('ランプ', group_id='sort_key', enable_events=True, key='sort_lamp'),
                sg.Radio('最終プレー日', group_id='sort_key', enable_events=True, key='sort_date'),
            ]
        ]
        header = ['lv', 'Tier', 'title', 'diff', 'score', 'lamp', 'VF', 'last played']
        layout = [
            [sg.Frame(title='filter', layout=layout_filter), sg.Frame(title='sort', layout=layout_sort)],
            [
                sg.Table(
                    []
                    ,key='table'
                    ,font=(None, 16)
                    ,headings=header
                    ,vertical_scroll_only = False
                    ,auto_size_columns=False
                    #,cols_justification='cclrccc' # 4.61.0.21以降
                    ,justification='left'
                    ,select_mode = sg.TABLE_SELECT_MODE_BROWSE
                    ,col_widths=[4,4,40,10,10,5,5,14]
                    ,background_color='#ffffff'
                )
            ]
        ]
        ico = self.ico_path('icon.ico')
        self.window = sg.Window("sdvx_helper score viewer", layout, resizable=True, return_keyboard_events=True, finalize=True, enable_close_attempted_event=True, icon=ico, size=(800,600))
        self.window['table'].expand(expand_x=True, expand_y=True)
        self.update_table()

    def update_table(self):
        out = []
        row_colors = []
        for s in self.sdvx_logger.best_allfumen:
            s_diff = ''
            if type(s.lv) == int:
                if min(19,s.lv) in (17,18,19): # 対象LvならS難易度表を取得
                    tmp = self.sdvx_logger.gen_summary.musiclist[f'gradeS_lv{min(19,s.lv)}'].get(s.title)
                    if tmp != None:
                        s_diff = tmp
            lv = s.lv
            if type(s.lv) == str:
                lv = 0
                if not self.window[f'lv1'].get(): # レベル未設定(検索失敗)のやつは1フォルダで代用(TBD)
                    continue
            elif not self.window[f'lv{lv}'].get():
                continue
            lamp = s.best_lamp.upper().replace('CLEAR', 'COMP').replace('HARD','EXC')
            difficulty = s.difficulty.upper().replace('APPEND', '')
            tmp = s.date.split('_')[0]
            #date = f"{s.date[:4]}/{s.date[4:6]}/{s.date[6:8]} {s.date[9:11]}:{s.date[11:13]}:{s.date[13:15]}"
            date = f"{s.date[:4]}/{s.date[4:6]}/{s.date[6:8]}"
            # フィルタ処理
            to_push = True
            if self.window['txt_filter'].get().strip() != '':
                for search_word in self.window['txt_filter'].get().strip().split(' '):
                    if search_word.lower() not in s.title.lower():
                        to_push = False
            if not to_push: # フィルタで弾かれた場合はskip
                continue
            out.append([
                lv
                ,s_diff
                ,s.title
                ,difficulty
                ,f'{s.best_score:,}'
                ,lamp_table.index(lamp)
                ,'%.1f'%(s.vf/10)
                ,date
            ])
        # sort
        if len(out) > 0:
            sort_row = 6
            if self.window['sort_title'].get(): # title sort
                sort_row = 2
            elif self.window['sort_lv'].get(): # lv sort
                sort_row = 0
            elif self.window['sort_score'].get(): # score sort
                sort_row = 4
            elif self.window['sort_lamp'].get(): # lamp sort
                sort_row = 5
            elif self.window['sort_date'].get(): # lamp date
                sort_row = 7
            dat_np = np.array(out)

            if self.window['sort_vf'].get(): # floatソート
                tmp = []
                for i,y in enumerate(out):
                    tmp.append([float(i),  float(out[i][sort_row])])
                tmp = np.array(tmp)
                tmp = tmp[tmp[:,1].argsort()] # IDX, srateだけのfloat型のnp.arrayを作ってソート
                idxlist = [int(tmp[i][0]) for i in range(tmp.shape[0])]
                dat_np = dat_np[idxlist, :]
            elif self.window['sort_lv'].get() or self.window['sort_score'].get() or self.window['sort_lamp'].get(): # intソート
                tmp = []
                for i,y in enumerate(out):
                    if type(out[i][sort_row]) == str:
                        tmp.append([i,  int(out[i][sort_row].replace(',',''))])
                    else:
                        tmp.append([i,  int(out[i][sort_row])])
                tmp = np.array(tmp)
                tmp = tmp[tmp[:,1].argsort()] # IDX, srateだけのint型のnp.arrayを作ってソート
                idxlist = [int(tmp[i][0]) for i in range(tmp.shape[0])]
                dat_np = dat_np[idxlist, :]
            elif self.window['sort_title'].get() or self.window['sort_date'].get():
                dat_np = dat_np[dat_np[:,sort_row].argsort()]

            # 降順なら逆にする
            if self.window['order_descend'].get():
                dat_np = dat_np[::-1]

            out = dat_np.tolist()
        row_colors = []
        # 色付けのためソート後の配列を確認
        for i in range(len(out)):
            bgc='#ffffff'
            out[i][5] = lamp_table[int(out[i][5])]
            lamp = out[i][5]
            if lamp == 'PUC':
                bgc = '#ffff66'
            elif lamp == 'UC':
                bgc = '#ffaaaa'
            elif lamp == 'EXC':
                bgc = '#ffccff'
            elif lamp == 'COMP':
                bgc = '#77ff77'
            elif lamp == 'FAILED':
                bgc = '#aaaaaa'
            row_colors.append([len(row_colors), '#000000', bgc])
            if out[i][0] == '0':
                out[i][0] = ''

        self.window['table'].update(out)
        self.window['table'].update(row_colors=row_colors)

    def main(self):
        self.gui()

        while True:
            ev, val = self.window.read()
            # prinv(ev, val)
            if ev in (sg.WIN_CLOSED, 'Escape:27', '-WINDOW CLOSE ATTEMPTED-'): # 終了処理
                break
            if ev == 'txt_filter':
                self.update_table()
            elif ev == 'btn_clear':
                self.window['txt_filter'].update('')
                self.update_table()
            elif ev.startswith('sort_') or ev.startswith('order_') or ev.startswith('lv'):
                self.update_table()
            elif ev == 'alllv':
                for i in range(1,21):
                    self.window[f'lv{i}'].update(val['alllv'])
                self.update_table()
    
if __name__ == '__main__':
    #b = SDVXLogger()
    a = ScoreViewer()
    a.main()