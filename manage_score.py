import sys, os
import PySimpleGUI as sg
import numpy as np
import logging, logging.handlers
import traceback
import pickle, json
from gen_summary import *
from manage_settings import *
from sdvxh_classes import *
from functools import partial
import urllib
import socket, ssl, urllib.parse
# IPv4を強制
import requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

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
lamp_table = ['FAILED', 'COMP', 'EXC', 'MAXXIVE', 'UC', 'PUC']

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
        self.modflg = False # 内部データを弄ったかどうか覚えておく
        self.num_del = 0 # 削除したデータ数
        self.mng = ManageUploadedScores()
        self.load_rivallog()

    def load_rivallog(self):
        """前回起動時に保存していたライバルの自己べ情報を読み込む
        """
        try:
            with open('out/rival_log.pkl', 'rb') as f:
                self.rival_log = pickle.load(f)
        except:
            self.rival_log = {}
        logger.debug(f'rival_logに保存されたkey: {self.rival_log.keys()}')
        logger.debug(f'ライバル:{self.settings["rival_names"]}')

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
        """曲リスト(musiclist.pkl)を最新化する
        """
        if self.settings['autoload_musiclist']:
            try:
                url = self.params['url_musiclist']
                url = 'https://raw.githubusercontent.com/dj-kata/sdvx_helper/main/resources/musiclist.pkl'
                parsed = urllib.parse.urlparse(url)
                hostname = parsed.hostname
                port = 443

                # TCP接続
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                ip = socket.gethostbyname(hostname)
                sock.connect((ip, port))

                # SSL Handshake
                context = ssl.create_default_context()
                ssock = context.wrap_socket(sock, server_hostname=hostname)

                # HTTPリクエスト
                request = f'GET {parsed.path} HTTP/1.1\r\nHost: {hostname}\r\nConnection: close\r\n\r\n'
                ssock.send(request.encode())

                # レスポンス受信
                response = b''
                while True:
                    data = ssock.recv(4096)
                    if not data:
                        break
                    response += data

                ssock.close()

                # ヘッダーとボディを分離
                header_end = response.find(b'\r\n\r\n')
                body = response[header_end+4:]

                with open('resources/musiclist.pkl', 'wb') as f:
                    f.write(body)

                print('musiclist.pklを更新しました。')
            except Exception as e:
                print(f'musiclist.pklの更新に失敗: {e}')


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
                sg.Radio('Tier', group_id='sort_key', enable_events=True, key='sort_tier'),
                sg.Radio('曲名', group_id='sort_key', enable_events=True, key='sort_title'),
            ],
            [
                sg.Radio('スコア', group_id='sort_key', enable_events=True, key='sort_score'),
                sg.Radio('ランプ', group_id='sort_key', enable_events=True, key='sort_lamp'),
                sg.Radio('最終プレー日', group_id='sort_key', enable_events=True, key='sort_date'),
            ],
        ]
        layout_edit = [
            [sg.Text('', key='edit_title')],
            [sg.Listbox([], size=(50,4), key='edit_list', enable_events=True)],
            [sg.Button('削除', key='edit_delete', enable_events=True),],
        ]
        layout_maya2 = [
            [sg.Listbox([], size=(50,4), key='maya2_list', enable_events=True)],
            [sg.Button('削除', key='maya2_delete', enable_events=True),],
        ]
        layout_rival = [
            [
                sg.Table(
                    []
                    ,size=(40,7)
                    ,key='table_rival'
                    ,headings=['name', 'score', 'lamp']
                    ,vertical_scroll_only = True
                    ,auto_size_columns=False
                    #,cols_justification='cclrccc' # 4.61.0.21以降
                    ,justification='left'
                    ,select_mode = sg.TABLE_SELECT_MODE_BROWSE
                    ,col_widths=[10,7,7]
                    ,background_color='#ffffff'
                    ,enable_events=True
                )
            ]
        ]
        header = ['lv', 'Tier', 'title', 'diff', 'score', 'lamp', 'VF', 'last played']
        layout = [
            [sg.Frame(title='Filter', layout=layout_filter),
             sg.Frame(title='Sort', layout=layout_sort),
             sg.Frame(title='Rival', layout=layout_rival),
             sg.Frame(title='Edit (helper)', layout=layout_edit),
             sg.Frame(title='Edit (maya2)', layout=layout_maya2)],
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
                    ,enable_events=True
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
            if (type(s.lv) == str) or (s.lv == None):
                lv = 0
                if not self.window[f'lv1'].get(): # レベル未設定(検索失敗)のやつは1フォルダで代用(TBD)
                    continue
            elif not self.window[f'lv{lv}'].get():
                continue
            lamp = s.best_lamp.upper().replace('CLEAR', 'COMP').replace('HARD','EXC').replace('EXH','MAXXIVE')
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
            elif self.window['sort_tier'].get(): # S-Tier sort
                sort_row = 1
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
            elif self.window['sort_lv'].get() or self.window['sort_score'].get() or self.window['sort_lamp'].get() or self.window['sort_tier'].get(): # intソート
                tmp = []
                for i,y in enumerate(out):
                    if sort_row == 4:
                        tmp.append([i,  int(out[i][sort_row].replace(',',''))])
                    elif sort_row == 1:
                        if out[i][sort_row] in ('N/A', ''):
                            tmp.append([i,  0.0])
                        elif out[i][sort_row] == '0-':
                            tmp.append([i,  0.1])
                        elif out[i][sort_row] == '0+':
                            tmp.append([i,  -0.1])
                        else:
                            tmp.append([i,  float(out[i][sort_row])])
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
            elif lamp == 'MAXXIVE':
                bgc = '#dddddd'
            elif lamp == 'EXC':
                bgc = '#ffccff'
            elif lamp == 'COMP':
                bgc = '#77ff77'
            elif lamp == 'FAILED':
                bgc = '#aaaaaa'
            row_colors.append([len(row_colors), '#000000', bgc])
            if out[i][0] == '0':
                out[i][0] = ''
        self.data = out
        self.window['table'].update(out)
        self.window['table'].update(row_colors=row_colors)

    def update_edit_list(self, val):
        """編集画面に選択された曲の全ログを表示。曲を選択した時に実行する。

        Args:
            val (dict): window.read()のvalueをそのまま渡す
        """
        try:
            tmp = self.data[val['table'][0]]
            title = tmp[2]
            diff  = 'APPEND' if tmp[3] == '' else tmp[3]
            logs  = []
            for i,d in enumerate(self.sdvx_logger.alllog):
                if (d.title == title) and (d.difficulty.lower() == diff.lower()):
                    logs.append(f"{i} - {d.cur_score:,}, {d.lamp}, ({d.date})")
            logs = list(reversed(logs))
            self.window['edit_list'].update(values=logs)
            self.window['edit_title'].update(f"{title} ({diff})")
            self.logs = logs

            # maya2側
            if self.sdvx_logger.maya2.is_alive():
                # 曲ID取得
                key = self.sdvx_logger.maya2.conv_table.forward(title)
                chart = self.sdvx_logger.maya2.search_fumeninfo(key, diff)
                diff = chart['difficulty']
                if chart is not None:
                    music = self.sdvx_logger.maya2.search_musicinfo(key)
                    music_id = music.get('music_id')
                    maya2_logs = []
                    for i,d in enumerate(self.mng.scores):
                        if d.music_id == music_id and d.difficulty == diff:
                            maya2_logs.append(f"{i}, {d.revision}, {d.score}, {d.exscore}, {d.lamp}")
                    maya2_logs = list(reversed(maya2_logs))
                    self.window['maya2_list'].update(values=maya2_logs)
                    self.maya2_logs = maya2_logs
                    self.maya2_music_id = music_id
                    self.maya2_difficulty = chart.get('difficulty')
        except Exception: # 切り替わり時など、雑に回避しておく
            pass

    def update_rival_list(self, val):
        try:
            tmp = self.data[val['table'][0]]
            title = tmp[2]
            diff  = 'APPEND' if tmp[3] == '' else tmp[3]

            rivals  = []
            for i,p in enumerate(self.settings['rival_names']):
                if p in self.rival_log.keys():
                    for s in self.rival_log[p]:
                        if s.title == title and s.difficulty == diff:
                            rivals.append([p, s.best_score, s.best_lamp])
                            break

            # 自己べも入れる
            for s in self.sdvx_logger.best_allfumen:
                if s.title == title and s.difficulty == diff:
                    lamp = s.best_lamp.replace('clear','COMP').replace('hard','exc').replace('exh', 'maxxive').upper()
                    rivals.append([self.settings['player_name'], s.best_score, lamp])
                    break

            # スコア順にソート
            rivals = sorted(rivals, reverse=True, key=lambda x: x[1])

            self.window['table_rival'].update(values=rivals)
            row_colors = []
            # 色付けのためソート後の配列を確認
            for i in range(len(rivals)):
                bgc='#ffffff'
                lamp = rivals[i][2]
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
            self.window['table_rival'].update(row_colors=row_colors)
            self.rivals = rivals
        except Exception: # 切り替わり時など、雑に回避しておく
            pass

    def main(self):
        self.gui()

        while True:
            ev, val = self.window.read()
            if ev in (sg.WIN_CLOSED, 'Escape:27', '-WINDOW CLOSE ATTEMPTED-'): # 終了処理
                if self.modflg: # 削除されている
                    ans = sg.popup_yes_no(f'プレーデータが{self.num_del}件削除されています。\nプレーデータを保存しますか？', icon=self.ico_path('icon.ico'))
                    if ans == 'Yes':
                        with open('alllog.pkl', 'wb') as f:
                            pickle.dump(self.sdvx_logger.alllog, f)
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
            elif ev == 'table': # 曲を選択した際にedit欄を更新
                self.update_edit_list(val)
                self.update_rival_list(val)
            elif ev == 'edit_delete':
                try:
                    idx_in_editlist = self.window['edit_list'].get_indexes()
                    dataidx = int(self.logs[idx_in_editlist[0]].split(' - ')[0])
                    tmp = self.sdvx_logger.alllog.pop(dataidx)
                    logger.debug(f"removed: idx:{dataidx} - {tmp.title}({tmp.difficulty}, {tmp.cur_score:,}(ex:{tmp.cur_exscore:,}) {tmp.lamp})")
                    tmp.disp()
                    # maya2向け削除処理
                    
                    self.modflg = True
                    self.num_del += 1
                    self.update_edit_list(val)
                except Exception:
                    print(traceback.format_exc())
            elif ev == 'maya2_delete':
                try:
                    idx_in_editlist = self.window['maya2_list'].get_indexes()
                    data = [d.strip() for d in self.maya2_logs[idx_in_editlist[0]].split(',')]
                    revision = int(data[1])
                    music_id = self.maya2_music_id
                    difficulty = self.maya2_difficulty
                    res = self.sdvx_logger.maya2.delete_score(revision, music_id, difficulty)
                    # if res.status_code == 200: # 不正なデータを消せるようにするためにレスポンスは見ないでおく?
                    self.mng.delete(revision, music_id)
                    self.mng.save()
                    self.update_edit_list(val)
                except Exception:
                    print(traceback.format_exc())
    
if __name__ == '__main__':
    #b = SDVXLogger()
    a = ScoreViewer()
    a.main()