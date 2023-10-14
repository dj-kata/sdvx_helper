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

SETTING_FILE = 'settings.json'
sg.theme('SystemDefault')
diff_table = ['nov', 'adv', 'exh', 'APPEND']

class Reporter:
    def __init__(self):
        start = datetime.datetime(year=2023,month=10,day=12,hour=0)
        self.gen_summary = GenSummary(start)
        self.load_settings()
        self.load_musiclist()
        self.read_bemaniwiki()
        self.ico=self.ico_path('icon.ico')
        self.num_added_music = 0 # 登録した曲数
        self.num_added_fumen = 0 # 登録した譜面数(>=num_added_music)
        self.flg_registered = {} # key:ファイル名、値:登録済みならTrue.do_coloringの結果保存用。
        self.gui()
        self.main()

    def ico_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

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

    def send_webhook(self, title, difficulty):
        if self.gen_summary.result_parts != False:
            webhook = DiscordWebhook(url=self.params['url_webhook_reg'], username="unknown title info")
            msg = f"**{title}**\n"
            for i in ('jacket_org', 'info'):
                msg += f"- **{imagehash.average_hash(self.gen_summary.result_parts[i])}**\n"
            img_bytes = io.BytesIO()
            self.gen_summary.result_parts['info'].save(img_bytes, format='PNG')
            webhook.add_file(file=img_bytes.getvalue(), filename=f'{i}.png')
            msg += f"(difficulty: **{difficulty.upper()}**)"

            webhook.content=msg

        res = webhook.execute()

    def send_pkl(self):
        webhook = DiscordWebhook(url=self.params['url_webhook_reg'], username="unknown title info")
        with open('resources/musiclist.pkl', 'rb') as f:
            webhook.add_file(file=f.read(), filename='musiclist.pkl')
        webhook.content = f"追加した譜面数: {self.num_added_fumen}, total: {len(self.musiclist['jacket']['exh'])}"
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
        layout = [
            [
                sg.Text('search:'), sg.Input('', size=(40,1), key='filter', enable_events=True), sg.Button('clear'), sg.Text('(登録済: '), sg.Text("0", key='num_added_music'), sg.Text('曲, '), sg.Text('0', key='num_added_fumen'), sg.Text('譜面)')
                ,sg.Text('                      title:'), sg.Input('', key='txt_title'), sg.Text('hash_jacket:'), sg.Input('', key='hash_jacket', size=(20,1)), sg.Text('hash_info:'), sg.Input('', key='hash_info', size=(20,1))
                ,sg.Text('難易度:'), sg.Combo(['', 'nov', 'adv', 'exh', 'APPEND'], key='combo_difficulty')
            ],
            [sg.Button('曲登録', key='register'), sg.Button('ファイル一覧に色付け(重いです)', key='coloring')],
            [sg.Table(
                []
                ,headings=header
                ,auto_size_columns=False
                ,col_widths=[50,40,7,3,3,3,3]
                ,alternating_row_color='#eeeeee'
                ,justification='left'
                ,key='musics'
                ,size=(120,10)
                ,enable_events=True
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
                )
            ],
            [sg.Text('', text_color="#ff0000", key='state')],
            [sg.Image(None, size=(100,100), key='jacket'), sg.Column(layout_info)]
        ]
        self.window = sg.Window(f"SDVX helper - OCR未検出曲報告ツール", layout, resizable=True, grab_anywhere=True,return_keyboard_events=True,finalize=True,enable_close_attempted_event=True,icon=self.ico,location=(self.settings['lx'], self.settings['ly']), size=(700,600))
        self.window['musics'].expand(expand_x=True, expand_y=True)
        self.window['files'].expand(expand_x=True, expand_y=True)
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
        for i,f in enumerate(list(self.gen_summary.get_result_files())):
            img = Image.open(f)
            if self.gen_summary.is_result(img):
                self.gen_summary.cut_result_parts(img)
                res = self.gen_summary.ocr()
                if res != False:
                    self.filelist_bgcolor[i][1] = '#dddddd'
                    self.filelist_bgcolor[i][2] = '#333399'
            else:
                self.filelist_bgcolor[i][1] = '#dddddd'
                self.filelist_bgcolor[i][2] = '#333333'
        self.window['files'].update(row_colors=self.filelist_bgcolor)

    def main(self):
        while True:
            ev, val = self.window.read()
            if ev in (sg.WIN_CLOSED, 'Escape:27', '-WINDOW CLOSE ATTEMPTED-', 'btn_close_info', 'btn_close_setting'):
                self.save()
                if self.num_added_fumen > 0:
                    self.send_pkl()
                break
            elif ev == 'files': # ファイル選択時
                f = self.window['files'].get()[val[ev][0]]
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
                else:
                    self.window['jacket'].update(None)
                    self.window['info'].update(None)
                    self.window['difficulty'].update(None)
                    self.window['state'].update('(リザルト画像ではないファイル)', text_color='#ff0000')
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
                        self.send_webhook(music, difficulty)
                        self.window['state'].update('登録しました！', text_color='#000000')
                        if music not in self.musiclist['info'][difficulty].keys():
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
                            print(f'曲自体の登録はされています。この譜面({difficulty})のみhashを修正します。')
                            self.musiclist['jacket'][difficulty][music] = str(hash_jacket)
                            if hash_info != '':
                                self.musiclist['info'][diff][music] = str(hash_info)
                            if len(val['files']) > 0:
                                self.filelist_bgcolor[val['files'][0]][-2] = '#dddddd'
                                self.filelist_bgcolor[val['files'][0]][-1] = '#333399'
                                self.window['files'].update(row_colors=self.filelist_bgcolor)
                        self.window['num_added_fumen'].update(self.num_added_fumen)
                    else:
                        print('難易度が取得できません')

if __name__ == '__main__':
    a = Reporter()