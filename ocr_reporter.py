# OCR未検出結果の報告用GUI
# 曲一覧を持っておき、各hash値に曲名情報を入れてpickleに追加する
# pickleをwebhookで送信する

# bemaniwikiから全曲情報を取得
# 自動保存フォルダの画像を確認し、認識できないものを一通り抽出
# リストビュー+選択したファイルについてジャケット、曲名を出すビュー
# 
import PySimpleGUI as sg
from bs4 import BeautifulSoup
import sys
import requests
import pickle
import threading
from collections import defaultdict
from gen_summary import *
from manage_settings import *
import traceback
import urllib
import logging, logging.handlers
from tkinter import filedialog

SETTING_FILE = 'settings.json'
sg.theme('SystemDefault')
diff_table = ['nov', 'adv', 'exh', 'APPEND']

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

class Reporter:
    def __init__(self):
        start = datetime.datetime(year=2023,month=10,day=12,hour=0)
        self.load_settings()
        self.update_musiclist()
        self.gen_summary = GenSummary(start)
        self.load_musiclist()
        self.read_bemaniwiki()
        self.ico=self.ico_path('icon.ico')
        self.num_added_fumen = 0 # 登録した譜面数
        self.flg_registered = {} # key:ファイル名、値:登録済みならTrue.do_coloringの結果保存用。
        self.gui()
        self.main()

    def ico_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    # 曲リストを最新化
    def update_musiclist(self):
        try:
            with urllib.request.urlopen(self.params['url_musiclist']) as wf:
                with open('resources/musiclist.pkl', 'wb') as f:
                    f.write(wf.read())
            logger.debug('musiclist.pklを更新しました。')
        except Exception:
            logger.debug(traceback.format_exc())

    def load_settings(self):
        ret = {}
        try:
            with open(SETTING_FILE) as f:
                ret = json.load(f)
                logger.debug(f"設定をロードしました。\n")
        except Exception as e:
            logger.debug(traceback.format_exc())
            logger.debug(f"有効な設定ファイルなし。デフォルト値を使います。")

        ### 後から追加した値がない場合にもここでケア
        for k in default_val.keys():
            if not k in ret.keys():
                logger.debug(f"{k}が設定ファイル内に存在しません。デフォルト値({default_val[k]}を登録します。)")
                ret[k] = default_val[k]
        self.settings = ret
        with open(self.settings['params_json'], 'r') as f:
            self.params = json.load(f)
        return ret

    def load_musiclist(self):
        try:
            with open('resources/musiclist.pkl', 'rb') as f:
                self.musiclist = pickle.load(f)
        except:
            logger.debug('musiclist読み込み時エラー。新規作成します。')
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

    def merge_musiclist(self):
        filename = filedialog.askopenfilename()
        try:
            with open(filename, 'rb') as f:
                tmp = pickle.load(f)
            pre_len = len(self.musiclist['jacket']['exh'].keys())
            for pos in ('jacket', 'info'):
                for diff in ('nov', 'adv', 'exh', 'APPEND'):
                    for s in tmp[pos][diff].keys(): # 曲名のリスト
                        if s not in self.musiclist[pos][diff].keys():
                            self.musiclist[pos][diff][s] = tmp[pos][diff][s]
                            logger.debug(f'added! {s}({diff},{pos}): {tmp[pos][diff][s]}')
                        elif self.musiclist[pos][diff][s] != tmp[pos][diff][s]:
                            logger.debug(f'merged! {s}({diff},{pos}): {tmp[pos][diff][s]} (before:{self.musiclist[pos][diff][s]})')
                            self.musiclist[pos][diff][s] = tmp[pos][diff][s]
            cur_len = len(self.musiclist['jacket']['exh'].keys())
            logger.debug(f'マージ完了。{pre_len:,} -> {cur_len:,}')
            print(f'マージ完了。{pre_len:,} -> {cur_len:,}')
        except Exception:
            logger.debug(traceback.format_exc())

    def save(self):
        with open('resources/musiclist.pkl', 'wb') as f:
            pickle.dump(self.musiclist, f)

    def read_bemaniwiki(self):
        req = requests.get('https://bemaniwiki.com/index.php?%A5%B3%A5%CA%A5%B9%A5%C6/SOUND+VOLTEX+EXCEED+GEAR/%B3%DA%B6%CA%A5%EA%A5%B9%A5%C8')

        soup = BeautifulSoup(req.text, 'html.parser')
        songs = []
        titles = {}
        for tr in soup.find_all('tr'):
            tds = tr.find_all('td')
            numtd = len(tds)
            if numtd in (7,8):
                if tds[2].text != 'BPM':
                    tmp = [tds[0].text, tds[1].text, tds[2].text]
                    tmp.append(int(tds[3].text))
                    tmp.append(int(tds[4].text))
                    tmp.append(int(tds[5].text))
                    if tds[6].text not in ('', '-'):
                        tmp.append(int(tds[6].text))
                    else:
                        tmp.append(None)
                    songs.append(tmp)
                    titles[tds[0].text] = tmp

        self.songs = songs
        self.titles = titles
        print(f"read_bemaniwiki end. (total {len(titles):,} songs)")

    def send_webhook(self, title, difficulty, hash_jacket, hash_info):
        try:
            webhook = DiscordWebhook(url=self.params['url_webhook_reg'], username="unknown title info")
            msg = f"**{title}**\n"
            msg += f" - **{hash_jacket}**"
            if hash_info != "":
                msg += f" - **{hash_info}**"
            if self.gen_summary.result_parts != False:
                img_bytes = io.BytesIO()
                self.gen_summary.result_parts['info'].crop((0,0,260,65)).save(img_bytes, format='PNG')
                webhook.add_file(file=img_bytes.getvalue(), filename=f'info.png')
                img_bytes = io.BytesIO()
                self.gen_summary.result_parts['difficulty'].save(img_bytes, format='PNG')
                webhook.add_file(file=img_bytes.getvalue(), filename=f'difficulty.png')
            msg += f"(difficulty: **{difficulty.upper()}**)"
            webhook.content=msg
            res = webhook.execute()
        except Exception:
            print(traceback.format_exc())

    def send_pkl(self):
        webhook = DiscordWebhook(url=self.params['url_webhook_reg'], username="unknown title info")
        with open('resources/musiclist.pkl', 'rb') as f:
            webhook.add_file(file=f.read(), filename='musiclist.pkl')
        webhook.content = f"追加した譜面数: {self.num_added_fumen}, total: {len(self.musiclist['jacket']['APPEND'])+len(self.musiclist['jacket']['nov'])+len(self.musiclist['jacket']['adv'])+len(self.musiclist['jacket']['exh'])}"
        webhook.content += f", 曲数:{len(self.musiclist['jacket']['APPEND'])}"
        res = webhook.execute()
    
    ##############################################
    ##########          GUIの設定
    ##############################################
    def gui(self):
        header = ['title', 'artist', 'bpm', 'nov', 'adv', 'exh', '(APPEND)']
        layout_info = [
            [sg.Image(None, size=(137,29), key='difficulty')],
            [sg.Image(None, size=(526,64), key='info')],
        ]
        layout_tables = [
            [sg.Table(
                []
                ,headings=header
                ,auto_size_columns=False
                ,col_widths=[40,40,7,3,3,3,3]
                ,alternating_row_color='#eeeeee'
                ,justification='left'
                ,key='musics'
                ,size=(120,10)
                ,enable_events=True
                ,font=(None, 16)
                )
            ],
            [sg.Table(
                []
                ,headings=['saved files']
                ,auto_size_columns=False
                ,col_widths=[90]
                ,alternating_row_color='#eeeeee'
                ,justification='left'
                ,key='files'
                ,size=(90,10)
                ,enable_events=True
                ,font=(None, 16)
                )
            ],
        ]
        layout_db = [
            [
                sg.Text('difficulty:'), sg.Combo(['', 'nov', 'adv', 'exh', 'APPEND'], key='combo_diff_db', font=(None,16), enable_events=True)
                ,sg.Button('外部pklのマージ', key='merge')
                ,sg.Text('0', key='num_hash'), sg.Text('曲')
            ],
            [
                sg.Table(
                    []
                    ,headings=['title', 'hash']
                    ,auto_size_columns=False
                    ,col_widths=[40, 20]
                    ,alternating_row_color='#eeeeee'
                    ,justification='left'
                    ,key='db'
                    ,size=(90,10)
                    ,enable_events=True
                    ,font=(None, 16)
                )
            ],
        ]
        layout = [
            [
                sg.Text('search:', font=(None,16)), sg.Input('', size=(40,1), key='filter', font=(None,16), enable_events=True), sg.Button('clear', font=(None,16)), sg.Text('(登録済: ', font=(None,16)), sg.Text('0', key='num_added_fumen', font=(None,16)), sg.Text('譜面)', font=(None,16))
            ],
            [
                sg.Text('title:', font=(None,16)), sg.Input('', key='txt_title', font=(None,16), size=(50,1))
            ],
            [
                sg.Text('hash_jacket:'), sg.Input('', key='hash_jacket', size=(20,1)), sg.Text('hash_info:'), sg.Input('', key='hash_info', size=(20,1))
                ,sg.Text('難易度:', font=(None,16)), sg.Combo(['', 'nov', 'adv', 'exh', 'APPEND'], key='combo_difficulty', font=(None,16))
            ],
            [sg.Button('曲登録', key='register'), sg.Button('ファイル一覧に色付け(重いです)', key='coloring')],
            [sg.Column(layout_tables, key='column_table'), sg.Column(layout_db, key='column_db')],
            [sg.Text('', text_color="#ff0000", key='state')],
            [sg.Image(None, size=(100,100), key='jacket'), sg.Column(layout_info)]
        ]
        self.window = sg.Window(f"SDVX helper - OCR未検出曲報告ツール", layout, resizable=True, grab_anywhere=True,return_keyboard_events=True,finalize=True,enable_close_attempted_event=True,icon=self.ico,location=(self.settings['lx'], self.settings['ly']), size=(900,780))
        self.window['musics'].expand(expand_x=True, expand_y=True)
        self.window['files'].expand(expand_x=True, expand_y=True)
        self.window['column_table'].expand(expand_x=True, expand_y=True)
        self.window['db'].expand(expand_x=True, expand_y=True)
        self.window['column_db'].expand(expand_x=True, expand_y=True)
        self.window['musics'].update(self.get_musiclist())
        filelist, bgcs = self.get_filelist()
        self.window['files'].update(filelist, row_colors=bgcs)

    # bemaniwikiから取得した曲一覧を返す
    def get_musiclist(self):
        ret = []
        for s in self.songs:
            to_push = True
            if self.window['filter'].get().strip() != '':
                for search_word in self.window['filter'].get().strip().split(' '):
                    if (search_word.lower() not in s[0].lower()) and (search_word.lower() not in s[1].lower()):
                        to_push = False
            if to_push: # 表示するデータを追加
                ret.append(s)
        self.musiclist_gui = ret # 現在GUIに表示している曲一覧を記憶しておく
        return ret

    def get_filelist(self):
        ret = []
        bgcs = []
        for i,f in enumerate(self.gen_summary.get_result_files()):
            ret.append(f)
            if i%2 == 0:
                bgcs.append([len(bgcs), '#000000', '#ffffff'])
            else:
                bgcs.append([len(bgcs), '#000000', '#eeeeee'])
            # is_resultチェックを全画像に対してやるのは遅いのでボツ
            #tmp = Image.open(f)
            #if self.gen_summary.is_result(tmp):
            #    ret.append(f)
        self.filelist_bgcolor = bgcs
        return ret, bgcs
    
    # ファイル一覧に対し、OCR結果に応じた色を付ける
    def do_coloring(self):
        self.gen_summary.load_hashes()
        for i,f in enumerate(list(self.gen_summary.get_result_files())):
            try:
                img = Image.open(f)
            except Exception:
                print(f'ファイルが見つかりません。スキップします。({f})')
                continue
            if self.gen_summary.is_result(img):
                self.gen_summary.cut_result_parts(img)
                res = self.gen_summary.ocr()
                if res != False:
                    self.filelist_bgcolor[i][1] = '#dddddd'
                    self.filelist_bgcolor[i][2] = '#333333'
                    title = res
                    cur,pre = self.gen_summary.get_score(img)
                    ts = os.path.getmtime(f)
                    now = datetime.datetime.fromtimestamp(ts)
                    fmtnow = format(now, "%Y%m%d_%H%M%S")
                    for ch in ('\\', '/', ':', '*', '?', '"', '<', '>', '|'):
                        title = title.replace(ch, '')
                    for ch in (' ', '　'):
                        title = title.replace(ch, '_')
                    dst = f"{self.settings['autosave_dir']}/sdvx_{title[:120]}_{self.gen_summary.difficulty.upper()}_{self.gen_summary.lamp}_{str(cur)[:-4]}_{fmtnow}.png"
                    try:
                        os.rename(f, dst)
                    except Exception:
                        print(f'既に存在するファイル名なのでskip。({dst})')
            else:
                self.filelist_bgcolor[i][1] = '#dddddd'
                self.filelist_bgcolor[i][2] = '#333333'
        self.window['files'].update(list(self.gen_summary.get_result_files()),row_colors=self.filelist_bgcolor)
        self.window['state'].update('色付けを完了しました。', text_color='#000000')

    def main(self):
        while True:
            ev, val = self.window.read()
            if ev in (sg.WIN_CLOSED, 'Escape:27', '-WINDOW CLOSE ATTEMPTED-', 'btn_close_info', 'btn_close_setting'):
                self.save()
                if self.num_added_fumen > 0:
                    self.send_pkl()
                break
            elif ev == 'files': # ファイル選択時
                if len(val[ev]) > 0:
                    f = self.window['files'].get()[val[ev][0]]
                    try:
                        img = Image.open(f)
                        if self.gen_summary.is_result(img):
                            parts = self.gen_summary.cut_result_parts(Image.open(f))
                            parts['jacket_org'].resize((100,100)).save('out/tmp_jacket.png')
                            parts['info'].save('out/tmp_info.png')
                            parts['difficulty_org'].save('out/tmp_difficulty.png')
                            self.window['jacket'].update('out/tmp_jacket.png')
                            self.window['info'].update('out/tmp_info.png')
                            self.window['difficulty'].update('out/tmp_difficulty.png')
                            self.window['state'].update('')
                            self.window['hash_jacket'].update(str(imagehash.average_hash(parts['jacket_org'])))
                            self.window['hash_info'].update(str(imagehash.average_hash(parts['info'])))
                            res_ocr = self.gen_summary.ocr()
                            if self.gen_summary.difficulty != False:
                                self.window['combo_difficulty'].update(self.gen_summary.difficulty)
                            else:
                                self.window['combo_difficulty'].update('')
                            print(res_ocr)
                            if res_ocr == False:
                                self.window['state'].update('曲名DBに登録されていません。曲を選択してから曲登録を押してもらえると喜びます。', text_color='#ff0000')
                            else:
                                self.window['state'].update('')
                            #diff = parts['difficulty_org'].crop((0,0,70,30))
                            #rsum = np.array(diff)[:,:,0].sum()
                            #gsum = np.array(diff)[:,:,1].sum()
                            #bsum = np.array(diff)[:,:,2].sum()
                            #self.window['state'].update(f"sum (r,g,b)=({rsum}, {gsum}, {bsum})", text_color='#000000')
                        else:
                            self.window['jacket'].update(None)
                            self.window['info'].update(None)
                            self.window['difficulty'].update(None)
                            self.window['state'].update('(リザルト画像ではないファイル)', text_color='#ff0000')
                    except Exception:
                        self.window['state'].update('error! ファイル見つかりません', text_color='#ff0000')
                        print(traceback.format_exc())
            elif ev == 'musics':
                if len(val['musics']) > 0:
                    self.window['txt_title'].update(self.get_musiclist()[val['musics'][0]][0])
            elif ev == 'filter':
                self.window['musics'].update(self.get_musiclist())
            elif ev == 'clear':
                self.window['filter'].update('')
                self.window['musics'].update(self.get_musiclist())
            elif ev == 'coloring':
                self.th_coloring = threading.Thread(target=self.do_coloring, daemon=True)
                self.th_coloring.start()
                self.window['state'].update('ファイル一覧をOCR結果に応じて色付け中。しばらくお待ちください。', text_color='#000000')
            elif ev == 'register':
                music = self.window['txt_title'].get()
                if music != '':
                    hash_jacket = self.window['hash_jacket'].get()
                    hash_info = self.window['hash_info'].get()
                    difficulty = val['combo_difficulty']
                    print(difficulty, hash_jacket, hash_info)
                    if (difficulty != '') and (hash_jacket != ''):
                        # TODO ジャケットなしの曲はinfoを登録する
                        self.send_webhook(music, difficulty, hash_jacket, hash_info)
                        if music not in self.musiclist['jacket'][difficulty].keys():
                            self.window['state'].update(f'曲が未登録。全譜面の情報を登録します。({music} / {hash_jacket})', text_color='#000000')
                            print('登録されていません。全譜面の情報を登録します。')
                            for i,diff in enumerate(diff_table):
                                self.num_added_fumen += 1
                                self.musiclist['jacket'][diff][music] = str(hash_jacket)
                                if hash_info != '':
                                    self.musiclist['info'][diff][music] = str(hash_info)
                            if len(val['files']) > 0:
                                self.filelist_bgcolor[val['files'][0]][-2] = '#dddddd'
                                self.filelist_bgcolor[val['files'][0]][-1] = '#333399'
                                self.window['files'].update(row_colors=self.filelist_bgcolor)
                        else:
                            self.num_added_fumen += 1
                            self.window['state'].update(f'曲自体は登録済み。{difficulty}のhashを修正しました。({music} / {hash_jacket})', text_color='#000000')
                            print(f'曲自体の登録はされています。この譜面({difficulty})のみhashを修正します。')
                            self.musiclist['jacket'][difficulty][music] = str(hash_jacket)
                            if hash_info != '':
                                self.musiclist['info'][difficulty][music] = str(hash_info)
                            if len(val['files']) > 0:
                                self.filelist_bgcolor[val['files'][0]][-2] = '#dddddd'
                                self.filelist_bgcolor[val['files'][0]][-1] = '#333399'
                                self.window['files'].update(row_colors=self.filelist_bgcolor)
                        self.window['num_added_fumen'].update(self.num_added_fumen)
                        self.save()
                        self.window['hash_jacket'].update('')
                        self.window['hash_info'].update('')
                        self.window['txt_title'].update('')
                    else:
                        print('難易度が取得できません')
            elif ev == 'combo_diff_db': # hash値リスト側の難易度設定を変えた時に入る
                if val[ev] != '':
                    titles = [k for k in self.musiclist['jacket'][val[ev]].keys()]
                    titles = sorted(titles, key=str.lower)
                    dat = [ (k, self.musiclist['jacket'][val[ev]][k]) for k in titles ]
                    self.window['db'].update(dat)
                    self.window['num_hash'].update(len(titles))
            elif ev == 'merge': # pklのマージボタン
                self.merge_musiclist()

if __name__ == '__main__':
    a = Reporter()