from enum import Enum
from gen_summary import *
from manage_settings import *
import requests, re, csv
from bs4 import BeautifulSoup
import logging, logging.handlers
from functools import total_ordering
from collections import defaultdict
from scipy.stats import rankdata
from connect_maya2 import *
from params_secret import *
import datetime
import hashlib, hmac
import time
import socket

# IPv4を強制
import requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

SETTING_FILE = 'settings.json'
ALLLOG_FILE = 'alllog.pkl'
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


class gui_mode(Enum):
    init = 0
    main = 1
    setting = 2
    obs_control = 3
    webhook = 4
    googledrive = 5

class detect_mode(Enum):
    init = 0
    select = 1
    play = 2
    result = 3

class score_rank(Enum):
    novalue = 0
    s = 1
    aaa_plus = 2
    aaa = 3
    aa_plus = 4
    aa = 5
    a_plus = 6
    a = 7
    b = 8
    c = 9
    d = 10

@total_ordering
class OnePlayData:
    """
    1つのプレーデータを表すクラス。
    リストに入れてソートすると日付順になる。
    """
    def __init__(self, title:str, cur_score:int, cur_exscore:int, pre_score:int, pre_exscore:int, lamp:str, difficulty:str, date:str):
        self.title = title
        self.cur_score = cur_score
        self.cur_exscore = cur_exscore
        self.pre_score = pre_score
        self.pre_exscore = pre_exscore
        self.lamp = lamp
        self.difficulty = difficulty
        self.date = date
        self.diff = cur_score - pre_score

    def __setstate__(self, state):
        # pickleロード時にメンバが存在しない場合への対応
        self.__dict__.update(state)
        if 'cur_exscore' not in self.__dict__:
            self.cur_exscore = 0
        if 'pre_exscore' not in self.__dict__:
            self.pre_exscore = 0


    def get_vf_single(self, lv):
        """
        Note: 
            単曲VFを計算する。

        Args:
            lv (int): 曲のレベル。OnePlayDataで保持していないため、外から与える必要がある。

            '??'などの文字列だった場合は0を返す。

        Returns:
            int: 単曲VFの値。16PUCなら369のような整数なので注意。
        """
        score = self.cur_score
        lamp  = self.lamp
        if lamp == 'puc':
            coef_lamp = 1.1
        elif lamp == 'uc':
            coef_lamp = 1.05
        elif lamp == 'exh':
            coef_lamp = 1.04
        elif lamp == 'hard':
            coef_lamp = 1.02
        elif lamp == 'clear':
            coef_lamp = 1
        else:
            coef_lamp = 0.5

        if score >= 9900000: # S
            self.rank = score_rank.s
            coef_grade = 1.05
        elif score >= 9800000: # AAA+
            self.rank = score_rank.aaa_plus
            coef_grade = 1.02
        elif score >= 9700000: # AAA
            self.rank = score_rank.aaa
            coef_grade = 1
        elif score >= 9500000: # AA+
            self.rank = score_rank.aa_plus
            coef_grade = 0.97
        elif score >= 9300000: # AA
            self.rank = score_rank.aa
            coef_grade = 0.94
        elif score >= 9000000: # A+
            self.rank = score_rank.a_plus
            coef_grade = 0.91
        elif score >= 8700000: # A
            self.rank = score_rank.a
            coef_grade = 0.88
        elif score >= 7500000:
            self.rank = score_rank.b
            coef_grade = 0.85
        elif score >= 6500000:
            self.rank = score_rank.c
            coef_grade = 0.82
        else:
            self.rank = score_rank.d
            coef_grade = 0.8
        ret = 0
        if type(lv) == int:
            ret = int(lv*score*coef_grade*coef_lamp*20/10000000) # 42.0とかではなく420のように整数で出力
        self.vf = ret
        return ret

    def __eq__(self, other):
        if not isinstance(other, OnePlayData):
            return NotImplemented

        return (self.title == other.title) and (self.difficulty == other.difficulty) and (self.cur_score == other.cur_score) and (self.pre_score == other.pre_score) and (self.lamp == other.lamp) and (self.date == other.date)
    
    def __lt__(self, other):
        if not isinstance(other, OnePlayData):
            return NotImplemented
        return self.date < other.date

    def disp(self): # debug
        print(f"{self.title}({self.difficulty}), cur:{self.cur_score}, pre:{self.pre_score}({self.diff:+}), exscore:{self.pre_exscore}->{self.cur_exscore}, lamp:{self.lamp}, date:{self.date}")

class MusicInfo:
    """
    1譜面分の情報を管理する。  

    1エントリ=1曲のある1譜面。例えば冥のexhとinfは別々のインスタンスで表す。

    自己ベストもここで定義する。

    ソートはVF順に並ぶようにしている。
    """
    def __init__(self, title:str, artist:str, bpm:str, difficulty:str, lv, best_score:int, best_exscore:int, best_lamp:str, date:str='', s_tier:str='', p_tier:str=''):
        self.title = title
        self.artist = artist
        self.bpm = bpm
        self.difficulty = difficulty
        self.lv = lv
        self.best_score = best_score
        self.best_exscore = best_exscore
        self.best_lamp = best_lamp
        self.rank = score_rank.novalue
        self.date = date
        self.s_tier = s_tier
        self.p_tier = p_tier
        self.get_vf_single()

    def __setstate__(self, state):
        # pickleロード時にメンバが存在しない場合への対応
        self.__dict__.update(state)
        if 'best_exscore' not in self.__dict__:
            self.best_exscore = 0

    def disp(self):
        msg = f"{self.title}({self.difficulty}) Lv:{self.lv}"
        msg += f" {self.best_score:,}, {self.best_lamp}, VF:{self.vf}"

        print(msg)

    def get_vf_single(self):
        """
        Note: 
            単曲VFを計算する。
            例えば16PUCなら369のように整数を返す。36.9と表示するのは上位側でやる。
            スコアランク(self.rank)もここで更新する。
        """
        score = self.best_score
        lamp  = self.best_lamp
        lv    = self.lv
        if lamp == 'puc':
            coef_lamp = 1.1
        elif lamp == 'uc':
            coef_lamp = 1.05
        elif lamp == 'exh':
            coef_lamp = 1.04
        elif lamp == 'hard':
            coef_lamp = 1.02
        elif lamp == 'clear':
            coef_lamp = 1
        else:
            coef_lamp = 0.5

        if score >= 9900000: # S
            self.rank = score_rank.s
            coef_grade = 1.05
        elif score >= 9800000: # AAA+
            self.rank = score_rank.aaa_plus
            coef_grade = 1.02
        elif score >= 9700000: # AAA
            self.rank = score_rank.aaa
            coef_grade = 1
        elif score >= 9500000: # AA+
            self.rank = score_rank.aa_plus
            coef_grade = 0.97
        elif score >= 9300000: # AA
            self.rank = score_rank.aa
            coef_grade = 0.94
        elif score >= 9000000: # A+
            self.rank = score_rank.a_plus
            coef_grade = 0.91
        elif score >= 8700000: # A
            self.rank = score_rank.a
            coef_grade = 0.88
        elif score >= 7500000:
            self.rank = score_rank.b
            coef_grade = 0.85
        elif score >= 6500000:
            self.rank = score_rank.c
            coef_grade = 0.82
        else:
            self.rank = score_rank.d
            coef_grade = 0.8
        ret = 0
        if type(lv) == int:
            ret = int(lv*score*coef_grade*coef_lamp*20/10000000) # 42.0とかではなく420のように整数で出力
        self.vf = ret
        return ret

    # ソート用。VF順で並ぶようにする
    def __lt__(self, other):
        if not isinstance(other, MusicInfo):
            return NotImplemented
        return self.vf < other.vf

class OneLevelStat:
    """
    1つのレベルの統計情報を表すクラス。
    """
    def __init__(self, lv:int):
        """コンストラクタ

        Args:
            lv (int): どのレベルか
        """        
        self.lv:int = lv # 1～20
        self.reset()

    def disp(self):
        print(f"Lv{self.lv}")
        print(f"ave: {self.get_average_score():.0f}")
        print(f"rank: {self.rank}")
        print(f"lamp: {self.lamp}\n")

    def reset(self):
        self.rank = {}
        self.lamp = {}
        self.rank['s'] = 0
        self.rank['aaa_plus'] = 0
        self.rank['aaa'] = 0
        self.rank['aa_plus'] = 0
        self.rank['aa'] = 0
        self.rank['a_plus'] = 0
        self.rank['a'] = 0
        self.rank['b'] = 0
        self.rank['c'] = 0
        self.rank['d'] = 0
        self.lamp['puc'] = 0
        self.lamp['uc'] = 0
        self.lamp['exh'] = 0
        self.lamp['hard'] = 0
        self.lamp['clear'] = 0
        self.lamp['failed'] = 0
        self.lamp['noplay'] = 0

        self.scores = {} # key:曲名___譜面 val:スコア(平均値計算用)
        self.average_score = 0

    def read(self, minfo:MusicInfo):
        try:
            self.rank[minfo.rank.name] += 1
            self.lamp[minfo.best_lamp] += 1
            self.scores[f"{minfo.title}___{minfo.difficulty}"] = minfo.best_score
        except Exception:
            print(traceback.format_exc())

    def get_average_score(self):
        """平均スコアを計算して返す

        Returns:
            float: そのレベルの平均スコア
        """
        tmp = 0
        for sc in self.scores.values():
            tmp += sc
        if len(self.scores.values()) > 0:
            self.average_score = tmp / len(self.scores.values())
        else:
            self.average_score = 0
        return self.average_score

class Stats:
    """
        全統計情報を保持するクラス

        self.data[1-20]に各Lvの統計情報(OneLevelStat)を格納する。
    """
    def __init__(self):
        self.data = [OneLevelStat(i) for i in range(1,21)]

    def reset_all(self):
        """全レベルの統計情報をクリアする。再計算時に利用。
        """
        for s in self.data:
            s.reset()

    def read_all(self, minfo:MusicInfo):
        """1譜面のデータを受け取って統計情報を更新する

        Args:
            minfo (MusicInfo): ある譜面の自己べ情報
        """        
        if type(minfo.lv) == int:
            idx = minfo.lv - 1
            self.data[idx].read(minfo)

class SDVXLogger:
    def __init__(self, player_name:str='', rta_mode=False):
        self.date = datetime.datetime.now()
        self.gen_summary = GenSummary(self.date)
        self.stats       = Stats()
        self.best_allfumen = []
        self.pre_onselect_title = ''
        self.pre_onselect_difficulty = ''
        self.myname = ''
        self.rival_names = []
        self.rival_score = {}
        self.total_vf = 0
        self.vf_pre = False
        self.player_name = player_name
        self.load_settings()
        self.rta_mode = rta_mode
        self.filename_total_vf = 'out/total_vf.xml'
        self.filename_stats = 'out/stats.xml'
        self.rta_timer = ''
        if self.rta_mode:
            self.alllog = []
            self.filename_total_vf = 'out/rta_total_vf.xml'
            self.filename_stats = 'out/rta_stats.xml'
        if not self.rta_mode:
            self.load_alllog()
        self.todaylog = [] # その日のプレーログを格納、sdvx_battle向けに使う
        self.today_updates = [] # maya2連携で更新データだけ送るために使う
        self.titles = self.gen_summary.musiclist['titles']
        maya2_token = self.settings.get('maya2_token')
        self.maya2 = ManageMaya2(maya2_token) # サーバが生きていれば応答するコネクタ
        self.update_best_allfumen()
        self.update_total_vf()
        self.update_stats()
        logger.info('started')

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
        with open(self.settings['params_json'], 'r') as f:
            self.params = json.load(f)
        return ret

    def load_alllog(self):
        """プレーログを読み込む。alllog.pklがない場合は新規作成する。
        """
        try:
            with open(ALLLOG_FILE, 'rb') as f:
                self.alllog = pickle.load(f)
            self.alllog.sort()
            # 不正データがあれば自動で削除
            dellist = []
            for i,d in enumerate(self.alllog):
                if d.cur_score > 10000000:
                    dellist.append(i)
                    print(f'誤検出リザルトを自動削除しました。({d.title}, {d.difficulty}, {d.cur_score})')
            for i in reversed(dellist):
                tmp = self.alllog.pop(i)
        except Exception:
            print(f"プレーログファイル(alllog.pkl)がありません。新規作成します。")
            self.alllog = []

    def get_rival_score(self, myname, names, ids):
        """ライバルのスコアをGoogleドライブから取得

        Args:
            myname (str): 自分のプレーヤ名
            names (list): ライバルのプレーヤ名のリスト
            ids (list): ライバルのGoogleドライブのIDリスト

        Returns:
            dict[rival_name]: 各ライバルの自己べデータ
        """
        self.myname = myname
        self.rival_names = names
        ret = {} # key:name, keyごとにMusicInfoの配列. TODO そのうちkeyをidにしたいかも
        print(f"ライバルのスコアを取得中")
        for id,name in zip(ids, names):
            URL = 'https://docs.google.com/uc?export=download'

            session = requests.Session()
            response = session.get(URL, params = { 'id' : id }, stream = True)
            response.encoding = 'utf-8'

            token = None
            for key, value in response.cookies.items():
                if key.startswith('download_warning'):
                    token = value
                    break

            if token:
                params = { 'id' : id, 'confirm' : token }
                response = session.get(URL, params = params, stream = True)

            CHUNK_SIZE = 32*1024
            # google drive上のcsvを扱うために仕方なく一度ローカルに書き出している
            with open('out/rival_tmp.csv', 'wb') as f:
                for chunk in response.iter_content(CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)

            tmp = []
            # ローカルに書き出したcsvから読み込み
            with open('out/rival_tmp.csv', encoding='utf-8') as f:
                csvr = csv.reader(f)
                for i,r in enumerate(csvr):
                    if i==0:
                        continue
                    difficulty = r[1]
                    if r[1] == '':
                        difficulty = 'APPEND'
                    best_score = int(r[3])
                    exscore = 0
                    best_lamp = r[4]
                    vf = int(r[5])
                    try:
                        info = MusicInfo(r[0], '', '', difficulty, '??', best_score, exscore, best_lamp)
                        info.vf = vf
                        tmp.append(info)
                    except Exception:
                        logger.debug(f'rival data error! (title:{r[0]}, difficulty:{difficulty}, best_score:{best_score}, best_lamp:{best_lamp})')
            ret[name] = tmp
            vf = 0.0
            for s in ret[name][:50]:
                vf += s.vf
            print(f"{name}: {vf/1000:.3f}")
            logger.debug(f"{name}: {vf/1000:.3f}")
        self.rival_score = ret
        return ret

    def save_alllog(self):
        """プレーログを保存する。
        """
        with open(ALLLOG_FILE, 'wb') as f:
            pickle.dump(self.alllog, f)

    def push(self, title:str, cur_score:int, cur_exscore:int, pre_score:int, pre_exscore:int, lamp:str, difficulty:str, date:str):
        """
            新規データのpush
            その曲のプレーログ一覧を返す
        """
        tmp = OnePlayData(title=title, cur_score=cur_score, cur_exscore=cur_exscore, pre_score=pre_score, pre_exscore=pre_exscore, lamp=lamp, difficulty=difficulty, date=date)
        if tmp not in self.alllog:
            self.alllog.append(tmp)
        self.save_alllog()

        # 全譜面のbestを更新
        self.update_best_onesong(title, difficulty)
        # ここでHTML表示用XMLを作成
        if not self.rta_mode:
            self.gen_history_cursong(title, difficulty)
        # VF情報更新
        self.update_total_vf()
        # 統計情報も更新
        self.update_stats()
        # 選曲画面のためにリザルトしておく。この関数はリザルト画面で呼ばれる。
        self.pre_onselect_title = ''
        self.pre_onselect_difficulty = ''
        return tmp

    def pop_illegal_logs(self, title:str, difficulty:str, score:int, exscore:int, lamp:str):
        """1曲のログについて、指定されたスコア・ランプを超えるものを全て削除する

        Args:
            title (str): 曲名
            difficulty (str): 難易度
            score (int): 超えてはいけないスコア
            lamp (str): 超えてはいけないランプ

        Return:
            int: 削除した曲数
        """

        lamp_table = ['puc', 'uc', 'exh', 'hard', 'clear', 'failed']
        target = []
        for i,d in enumerate(self.alllog):
            if (d.title == title) and (d.difficulty.lower() == difficulty.lower()):
                if (d.cur_score > score) or (d.cur_exscore > exscore) or (lamp_table.index(d.lamp) < lamp_table.index(lamp)):
                    target.append(i)
                    print(f'不正データ?: {d.cur_score:,}, {d.lamp}, ({d.date})')
                    print(f"judge: {(d.cur_score > score)}, {d.cur_exscore > exscore}, {lamp_table.index(d.lamp) < lamp_table.index(lamp)}, {d.lamp}, {lamp}")
        for i in reversed(target): # 後ろからpopしていく
            self.alllog.pop(i)
        return len(target) # 削除した曲数

    def gen_history_cursong(self, title:str, difficulty:str):
        """その曲のプレー履歴情報のXMLを作成

        Args:
            title (str): 曲名
            difficulty (str): 譜面難易度
        """
        logs, info = self.get_fumen_data(title, difficulty)
        with open('out/history_cursong.xml', 'w', encoding='utf-8') as f:
            f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
            f.write("<Items>\n")
            title_esc = title.replace('&', '&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'",'&apos;')
            f.write(f"    <title>{title_esc}</title>\n")
            f.write(f"    <difficulty>{difficulty}</difficulty>\n")

            if (logs != False) and (info != False): # TODO ここのせいでプレー済み曲しか出ていない
                lv = info.lv
                f.write(f"    <lv>{lv}</lv>\n")
                if type(lv) == int:
                    maya2info = self.maya2.search_fumeninfo(title, difficulty)
                    if maya2info is not None: # maya2のマスタ上に楽曲情報が存在する場合
                        if maya2info['s_tier'] is not None:
                            f.write(f"    <gradeS_tier>{maya2info['s_tier'][5:]}</gradeS_tier>\n")
                        f.write(f"    <PUC_tier>{maya2info['p_tier']}</PUC_tier>\n")
                    elif min(19,lv) in (17,18,19): # 対象LvならS難易度表を取得
                        tmp = self.gen_summary.musiclist[f'gradeS_lv{min(19,lv)}'].get(title)
                        if tmp != None:
                            f.write(f"    <gradeS_tier>{tmp}</gradeS_tier>\n")
                f.write(f"    <best_score>{info.best_score}</best_score>\n")
                f.write(f"    <best_exscore>{info.best_exscore}</best_exscore>\n")
                f.write(f"    <best_lamp>{info.best_lamp}</best_lamp>\n")
                vf_12 = int(info.vf/10)
                vf_3 = info.vf % 10
                f.write(f"    <vf>{vf_12}.{vf_3}</vf>\n")
                # このプレーの履歴とか、その他
                for p in logs:
                    f.write(f"    <Result>\n")
                    f.write(f"        <score>{p.cur_score}</score>\n")
                    f.write(f"        <exscore>{p.cur_exscore}</exscore>\n")
                    f.write(f"        <lamp>{p.lamp}</lamp>\n")
                    mod_date = f"{p.date[:4]}-{p.date[4:6]}-{p.date[6:8]}"
                    f.write(f"        <date>{mod_date}</date>\n")
                    f.write(f"    </Result>\n")
            else: # invalid
                f.write(f"    <Result>\n")
                f.write(f"        <score></score>\n")
                f.write(f"        <exscore></exscore>\n")
                f.write(f"        <lamp></lamp>\n")
                f.write(f"        <date></date>\n")
                f.write(f"    </Result>\n")
            f.write("</Items>\n")

    def push_today_updates(self):
        """SDVXLogger.today_updatesを更新するために叩く。maya2連携における終了時のリザルト送信用。
        """
        if len(self.alllog) > 0 and self.alllog[-1] not in self.today_updates:
            lamp_table = ['', 'failed', 'clear', 'hard', 'exh', 'uc', 'puc']
            tmp = self.alllog[-1]
            pre_best = None
            for d in self.best_on_start:
                if (d.title == tmp.title) and (d.difficulty == tmp.difficulty):
                    pre_best = d
                    break
            push_ok = False
            if pre_best is None:
                push_ok = True
            elif (pre_best.best_score < tmp.cur_score) or (pre_best.best_exscore < tmp.cur_exscore) or (lamp_table.index(pre_best.best_lamp) < lamp_table.index(tmp.lamp)):
                push_ok = True

            tmp.disp()
            #print('maya2 send flg:', push_ok, pre_best.best_score < tmp.cur_score, pre_best.best_exscore < tmp.cur_exscore, lamp_table.index(pre_best.best_lamp) < lamp_table.index(tmp.lamp))
            print('maya2 send flg:', push_ok)
            if push_ok:
                logger.info(f"today_updates.append: {tmp.title}, {tmp.difficulty}, lamp:{tmp.lamp}, score:{tmp.cur_score}, ex:{tmp.cur_exscore}")
                duplicate = False
                for i,s in enumerate(self.today_updates): # 既に本日プレイ済みの曲ならマージする
                    if (s.title == tmp.title) and (s.difficulty == tmp.difficulty):
                        duplicate = True
                        self.today_updates[i].cur_score = max(self.today_updates[i].cur_score, tmp.cur_score)
                        self.today_updates[i].cur_exscore = max(self.today_updates[i].cur_exscore, tmp.cur_exscore)
                        self.today_updates[i].lamp = lamp_table[max(lamp_table.index(self.today_updates[i].lamp),lamp_table.index(tmp.lamp))]
                        logger.info(f"merged!, i={i}, title:{s.title}, difficulty:{s.difficulty}, score:{self.today_updates[i].cur_score}, exscore:{self.today_updates[i].cur_exscore}, lamp:{self.today_updates[i].lamp}")
                if not duplicate:
                    self.today_updates.append(tmp)

    def gen_sdvx_battle(self, update=True):
        """SDVX Battle向けのxmlを生成する。リザルト画面からしか呼ばれない。
        この中でlistの更新もする。

        Args:
            update (bool, optional): 最新のリザルトを取り込むかどうか。基本的には取り込むが、起動時のみ何もしない。
        """
        if update and len(self.alllog) > 0 and self.alllog[-1] not in self.todaylog:
            self.todaylog.append(self.alllog[-1])
        with open('out/sdvx_battle.xml', 'w', encoding='utf-8') as f:
            f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
            f.write("<Items>\n")
            for s in reversed(self.todaylog):
                logs, info = self.get_fumen_data(s.title, s.difficulty)
                f.write("    <song>\n")
                title_esc = s.title.replace('&', '&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'",'&apos;')
                f.write(f"        <title>{title_esc}</title>\n")
                f.write(f"        <difficulty>{s.difficulty}</difficulty>\n")
                maya2info = self.maya2.search_fumeninfo(s.title, s.difficulty)
                if maya2info is not None: # maya2のマスタ上に楽曲情報が存在する場合
                    if maya2info['s_tier'] is not None:
                        f.write(f"        <gradeS_tier>{maya2info['s_tier'][5:]}</gradeS_tier>\n")
                    f.write(f"        <PUC_tier>{maya2info['p_tier']}</PUC_tier>\n")
                    f.write(f"        <lv>{maya2info['level']}</lv>\n")
                else:
                    f.write(f"        <lv>{info.lv}</lv>\n")
                f.write(f"        <score>{s.cur_score}</score>\n")
                f.write(f"        <exscore>{s.cur_exscore}</exscore>\n")
                f.write(f"        <lamp>{s.lamp}</lamp>\n")
                f.write(f"        <date>{s.date}</date>\n")
                f.write(f"    </song>\n")
            f.write("</Items>\n")

    def gen_vf_onselect(self, title:str, difficulty:str):
        """曲名に対するVOLFORCE情報をXMLに出力する。
        選曲画面での利用を想定している。

        Args:
            title (str): 曲名
            difficulty (str): 譜面難易度
        """
        if (title != self.pre_onselect_title) or (difficulty != self.pre_onselect_difficulty): # 違う曲になったときだけ実行
            logs, info = self.get_fumen_data(title, difficulty)
            lv = info.lv
            dat = []

            # 指定の曲名と同じ譜面情報を出力
            for d in self.best_allfumen:
                if (d.title == title) and (d.difficulty == difficulty):
                    #d.disp()
                    dat.append(d)

            with open('out/vf_onselect.xml', 'w', encoding='utf-8') as f:
                f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
                f.write("<Items>\n")
                f.write("    <fumen>\n")
                title_esc = title.replace('&', '&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'",'&apos;')
                f.write(f"        <title>{title_esc}</title>\n")
                f.write(f"        <difficulty>{difficulty.upper()}</difficulty>\n")
                f.write(f"        <lv>{lv}</lv>\n")
                if type(lv) == int:
                    maya2info = self.maya2.search_fumeninfo(title, difficulty)
                    if maya2info is not None: # maya2のマスタ上に楽曲情報が存在する場合
                        if maya2info['s_tier'] is not None:
                            f.write(f"        <gradeS_tier>{maya2info['s_tier'][5:]}</gradeS_tier>\n")
                        f.write(f"        <PUC_tier>{maya2info['p_tier']}</PUC_tier>\n")
                    elif min(19,lv) in (17,18,19): # 対象LvならS難易度表を取得
                        tmp = self.gen_summary.musiclist[f'gradeS_lv{min(19,lv)}'].get(title)
                        if tmp != None:
                            f.write(f"        <gradeS_tier>{tmp}</gradeS_tier>\n")
                for d in dat:
                    f.write(f"        <best_score>{d.best_score}</best_score>\n")
                    f.write(f"        <best_exscore>{d.best_exscore}</best_exscore>\n")
                    f.write(f"        <best_lamp>{d.best_lamp}</best_lamp>\n")
                    vf_12 = int(d.vf/10)
                    vf_3 = d.vf % 10
                    f.write(f"        <vf>{vf_12}.{vf_3}</vf>\n")
                f.write("    </fumen>\n")
                f.write("</Items>\n")
        self.pre_onselect_title = title
        self.pre_onselect_difficulty = difficulty

    def update_rival_view(self, title:str, difficulty:str):
        """曲名認識結果を受けてライバル欄を更新する

        Args:
            title (str): 曲名
            difficulty (str): 難易度
        """
        if ((title != self.pre_onselect_title) or (difficulty != self.pre_onselect_difficulty)) and (len(self.rival_names)>0): # 違う曲になったときだけ実行
            infos = []

            # 指定の曲名と同じ譜面情報を出力
            lv = '??'
            for d in self.best_allfumen:
                if (d.title == title) and (d.difficulty.lower() == difficulty.lower()):
                    d.player_name = self.myname
                    d.is_maya2 = False
                    d.me = True
                    lv = d.lv
                    infos.append(d)
            for name in self.rival_names: # tmp: 1人分
                tmp = self.rival_score[name]
                for s in tmp: # 1曲分
                    if (s.title == title) and (s.difficulty.lower() == difficulty.lower()):
                        s.player_name = name
                        s.is_maya2 = False
                        s.me = False
                        infos.append(s)
            # maya2側
            for player in self.maya2.rival_scores.keys():
                for s in self.maya2.rival_scores[player]: # 1曲分
                    if (s.title == title) and (s.difficulty.lower() == difficulty.lower()):
                        s.player_name = player
                        s.is_maya2 = True
                        s.me = False
                        infos.append(s)
            
            # 順位付け
            infos_sorted = sorted(infos, key=lambda x:-x.best_score)
            tmp = [infos[i].best_score for i in range(len(infos))] # ソート対象
            rank = sorted(rankdata(-np.array(tmp)))

            with open('out/rival.xml', 'w', encoding='utf-8') as f:
                f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
                f.write("<Items>\n")
                title = title.replace('&', '&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'",'&apos;')
                f.write(f"    <title>{title}</title>\n")
                f.write(f"    <difficulty>{difficulty.upper()}</difficulty>\n")
                f.write(f"    <lv>{lv}</lv>\n")
                if type(lv) == int:
                    maya2info = self.maya2.search_fumeninfo(title, difficulty)
                    if maya2info is not None: # maya2のマスタ上に楽曲情報が存在する場合
                        if maya2info['s_tier'] is not None:
                            f.write(f"    <gradeS_tier>{maya2info['s_tier'][5:]}</gradeS_tier>\n")
                        f.write(f"    <PUC_tier>{maya2info['p_tier']}</PUC_tier>\n")
                    elif min(19,lv) in (17,18,19): # 対象LvならS難易度表を取得
                        tmp = self.gen_summary.musiclist[f'gradeS_lv{min(19,lv)}'].get(title)
                        if tmp != None:
                            f.write(f"        <gradeS_tier>{tmp}</gradeS_tier>\n")
                for i,(info,r) in enumerate(zip(infos_sorted, rank)):
                    f.write("    <rival>\n")
                    f.write(f"        <rank>{int(r)}</rank>\n")
                    f.write(f"        <name>{info.player_name}</name>\n")
                    if info.me:
                        f.write("        <me>1</me>\n")
                    if info.is_maya2:
                        f.write("        <is_maya2>1</is_maya2>\n")
                    f.write(f"        <best_score>{info.best_score}</best_score>\n")
                    f.write(f"        <best_lamp>{info.best_lamp.lower()}</best_lamp>\n")
                    f.write(f"        <vf>{info.vf}</vf>\n")
                    f.write("    </rival>\n")
                f.write("</Items>\n")

    def get_fumen_data(self, title:str, difficulty:str):
        """ある譜面のプレーログと曲情報(自己べ等)を取得する。
        自己ベストを取得する関係で1つにまとめている。

        Args:
            title (str): 曲名
            difficulty (str): 曲難易度

        Returns:
            list(OnePlayData), MusicInfo: プレー履歴のList、その曲のbest等の情報
        """
        diff_table = ['NOV', 'ADV', 'EXH', 'APPEND']
        lamp_table = ['', 'failed', 'clear', 'hard', 'exh', 'uc', 'puc']
        logs = []
        best_score = 0
        best_exscore = 0
        best_lamp = ''
        last_played_date = '0000/00/00'
        for p in reversed(self.alllog):
            if (p.title == title) and (p.difficulty == difficulty):
                last_played_date = p.date
                #p.disp()
                if p.lamp == 'class_clear': # TODO 段位抜けはノマゲ扱いにしておく
                    p.lamp = 'clear'
                if (p.lamp is None) or (best_lamp is None):
                    continue
                best_lamp = p.lamp if lamp_table.index(p.lamp) > lamp_table.index(best_lamp) else best_lamp
                best_score = p.cur_score if (p.cur_score > best_score) and (p.cur_score <= 10000000) else best_score
                best_exscore = p.cur_exscore if (p.cur_exscore > best_exscore) else best_exscore
                # 以前のbest情報の読み取り精度が悪いため、現在のスコアからの登録のみ
                #best_score = p.pre_score if (p.pre_score > best_score) and (p.pre_score <= 10000000) else best_score
                if p.cur_score > 7000000: # 最低スコアを設定 TODO
                    logs.append(p)
        try:
            tmp = self.titles[title]
            artist = tmp[1]
            bpm    = tmp[2]
            lv     = tmp[3+diff_table.index(difficulty.upper())]
        except:
            # logger.debug(traceback.format_exc())
            artist = ''
            bpm = ''
            lv = '??'
        info = MusicInfo(title, artist, bpm, difficulty, lv, best_score, best_exscore, best_lamp, last_played_date)
        return logs, info
    
    def update_best_onesong(self, title, diff):
        """
            単曲のbest情報を更新。リザルト画面で呼び出す想定。

            毎回update_best_allfumenを呼ばないようにする。
        """
        _, info = self.get_fumen_data(title, diff)
        is_found = False # best_allfumen内にあるかどうか、ない場合は追加
        for i,f in enumerate(self.best_allfumen):
            if (f.title == title) and (f.difficulty == diff):
                self.best_allfumen[i] = info
                is_found = True
                break
        if not is_found:
            self.best_allfumen.append(info)
        self.best_allfumen.sort(reverse=True)

    def update_best_allfumen(self):
        """
            self.alllogから全譜面のbest情報を作成

            alllogのエントリは同じ譜面を含む場合があるが、本関数は出力間で譜面を全て独立させる
        """
        fumenlist = []
        ret = []
        self.best_on_start = [] # 起動時のbestを格納、maya2で差分を取得するために用意
        # 譜面一覧を作成。ここで重複しないようにしている。
        for l in self.alllog:
            if [l.title, l.difficulty] not in fumenlist:
                fumenlist.append([l.title, l.difficulty])
        # 各譜面のbestを検索
        for title, diff in fumenlist:
            _, info = self.get_fumen_data(title, diff)
            if info != False:
                ret.append(info)
                self.best_on_start.append(info)
        # VF順にソート
        ret.sort(reverse=True)
        self.best_allfumen = ret
        return ret
    
    def update_stats(self):
        """
            最新のself.best_allfumenから統計情報を更新する。本関数の前にupdate_best_*を呼んでいること。

            xml出力もやる。
        """
        self.stats.reset_all()
        for f in self.best_allfumen:
            if type(f.lv) == int:
                self.stats.read_all(f)

        with open(self.filename_stats, 'w', encoding='utf-8') as f:
            f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
            f.write("<stats>\n")
            f.write(f"    <date>{self.date.strftime('%Y/%m/%d')}</date>\n")
            f.write(f"    <player_name>{self.player_name}</player_name>\n")
            f.write(f"    <total_vf>{self.total_vf:.3f}</total_vf>\n")
            f.write(f"    <total_vf_pre>{self.vf_pre:.3f}</total_vf_pre>\n")
            f.write(f"    <total_vf_diff>{self.total_vf - self.vf_pre:.3f}</total_vf_diff>\n")
            f.write(f"    <timer>{self.rta_timer}</timer>\n")
            for st in self.stats.data:
                f.write("    <lvs>\n")
                f.write(f"        <lv>{st.lv}</lv>\n")
                f.write(f"        <average>{int(st.get_average_score())}</average>\n")
                f.write("\n")
                for k in st.lamp.keys():
                    f.write(f"        <{k}>{st.lamp[k]}</{k}>\n")
                f.write("\n")
                for k in st.rank.keys():
                    f.write(f"        <{k}>{st.rank[k]}</{k}>\n")
                f.write("    </lvs>\n")
            f.write("</stats>\n")
    
    def update_total_vf(self):
        """
            全曲VFを計算して返す。self.total_vfにも書き込む。

            out/total_vf.xmlにも出力する。
        """
        ret = 0
        with open(self.filename_total_vf, 'w', encoding='utf-8') as f:
            f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
            f.write("<vfinfo>\n")
            for i,s in enumerate(self.best_allfumen):
                if i >= 50:
                    break
                ret += s.vf
                f.write(f"    <music>\n")
                hash = ''
                if s.title in self.gen_summary.musiclist['jacket'][s.difficulty].keys():
                    hash = self.gen_summary.musiclist['jacket'][s.difficulty][s.title]
                f.write(f"        <idx>{i+1}</idx>\n")
                f.write(f"        <lv>{s.lv}</lv>\n")
                title = s.title.replace('&', '&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'",'&apos;')

                f.write(f"        <title>{title}</title>\n")
                f.write(f"        <hash>{hash}</hash>\n")
                f.write(f"        <difficulty>{s.difficulty}</difficulty>\n")
                f.write(f"        <score>{s.best_score}</score>\n")
                f.write(f"        <lamp>{s.best_lamp}</lamp>\n")
                f.write(f"        <vf>{s.vf}</vf>\n")
                f.write(f"    </music>\n")
            self.total_vf = ret / 1000
            if self.vf_pre == False:
                self.vf_pre = self.total_vf
            f.write(f"    <total_vf>{self.total_vf:.3f}</total_vf>\n")
            f.write(f"    <total_vf_pre>{self.vf_pre:.3f}</total_vf_pre>\n")
            f.write(f"    <total_vf_diff>{self.total_vf - self.vf_pre:.3f}</total_vf_diff>\n")
            f.write("</vfinfo>\n")
        return self.total_vf

    def import_from_resultimg_core(self, f:str) -> OnePlayData:
        """リザルト画像置き場の画像からプレーログをインポートする。

        Args:
            f (str): ファイル名

        Returns:
            OnePlayData: 入力画像に対応するプレーデータ
        """
        img = Image.open(f)
        if self.gen_summary.is_result(img):
            self.gen_summary.cut_result_parts(img)
            ocr = self.gen_summary.ocr()
            if ocr != False:
                ts = os.path.getmtime(f)
                now = datetime.datetime.fromtimestamp(ts)
                fmtnow = format(now, "%Y%m%d_%H%M%S")

                cur,pre = self.gen_summary.get_score(img)
                cur_ex,pre_ex = self.gen_summary.get_exscore(img)
                diff = self.gen_summary.difficulty
                lamp = self.gen_summary.lamp

                playdat = OnePlayData(ocr, cur, cur_ex, pre, pre_ex, lamp, diff, fmtnow)
                playdat.disp()
                if playdat not in self.alllog:
                    self.alllog.append(playdat)
                    logger.debug(f"added! -> {playdat.title}({playdat.difficulty}) {playdat.cur_score} {playdat.lamp}")
            else:
                logger.debug(f"認識失敗！ {f}")
                print(f"認識失敗！ {f}")
        self.alllog.sort()
        print("リザルト画像の読み込みを完了しました。")

    def import_from_resultimg(self):
        """リザルト画像をプレーログに反映する。上位ループの処理。
        """
        print("リザルト画像をプレーログに反映します。")
        for f in self.gen_summary.get_result_files():
            self.import_from_resultimg_core(f)

    def gen_jacket_imgs(self):
        """リザルト画像置き場の画像からVFビュー用ジャケット画像を生成
        """
        print("リザルト画像からVFビュー用ジャケット画像を作成します。")
        for f in self.gen_summary.get_result_files():
            img = Image.open(f)
            if self.gen_summary.is_result(img):
                self.gen_summary.cut_result_parts(img)
                ocr = self.gen_summary.ocr()
                if ocr != False:
                    hash = str(self.gen_summary.hash_hit)
                    self.gen_summary.result_parts['jacket_org'].save(f'jackets/{hash}.png')

    def gen_best_csv(self, filename):
        try:
            with open(filename, 'w', encoding='utf-8', errors='ignore', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['title', 'difficulty', 'Lv', 'score', 'lamp', 'volforce'])
                for i,p in enumerate(self.best_allfumen):
                    diff = p.difficulty.replace('APPEND', '').upper()
                    lamp = p.best_lamp.replace('exh', 'maxxive').replace('hard', 'exc').replace('clear', 'comp').upper()
                    writer.writerow([p.title, diff, p.lv, p.best_score, lamp, p.vf])
            return True
        except Exception:
            logger.debug(traceback.format_exc())
            return False

    def gen_alllog_csv(self, filename):
        try:
            list_diff = ['nov', 'adv', 'exh', 'APPEND']
            with open(filename, 'w', encoding='shift_jis', errors='ignore', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['title', 'difficulty', 'Lv', 'score', 'lamp', 'volforce', 'date'])
                for i,p in enumerate(reversed(self.alllog)):
                    lv = '??'
                    if p.title in self.gen_summary.musiclist['titles'].keys():
                        lv = self.gen_summary.musiclist['titles'][p.title][3+list_diff.index(p.difficulty)]
                    vf = p.get_vf_single(lv)
                    diff = p.difficulty.replace('APPEND', '').upper()
                    lamp = p.lamp.replace('exh','maxxive').replace('hard', 'exc').replace('clear', 'comp').upper()
                    date = f"{p.date[0:4]}/{p.date[4:6]}/{p.date[6:8]} {p.date[9:11]}:{p.date[11:13]}:{p.date[13:15]}"
                    writer.writerow([p.title, diff, lv, p.cur_score, lamp, vf, date])
                    #print(p.title, p.difficulty, lv, vf)
            return True

        except Exception:
            print(traceback.format_exc())
            logger.debug(traceback.format_exc())
            return False
        
    def gen_playcount_csv(self, filename):
        try:
            with open(filename, 'w', encoding='utf-8', errors='ignore', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['date', 'playcount'])
                cnt = defaultdict(int)
                #for i,p in enumerate(reversed(self.alllog)): # 最新が一番上
                for i,p in enumerate(self.alllog):
                    date = p.date.split('_')[0]
                    date = f"{date[0:4]}/{date[4:6]}/{date[6:8]}"
                    cnt[date] += 1
                for k in cnt.keys():
                    writer.writerow([k, cnt[k]])
            return True
        except Exception:
            logger.debug(traceback.format_exc())
            return False

    def analyze(self) -> str:
        """VF内訳を分析してlistで出力

        Returns:
            str: ツイート用文字列
        """
        #list: 分析結果(1要素:1Lv分のlist)
        #1要素は[num, puc, uc, exh, hard, clear, failed, minscore, maxscore, avescore, min_vf, max_vf, ave_vf]
        list_lamp = ['puc', 'uc', 'exh', 'hard', 'clear', 'failed']
        ret = [[0 for __ in range(13)] for _ in range(20)]
        for i in range(20):
            ret[i][7] = 10000000
            ret[i][10] = 1000.0
        for i,p in enumerate(self.best_allfumen):
            p.disp()
            idx = p.lv - 1
            # 曲数
            ret[idx][0] += 1
            # ランプ
            ret[idx][1+list_lamp.index(p.best_lamp)] += 1
            # min
            ret[idx][7] = min(ret[idx][10], p.best_score)
            ret[idx][10] = min(ret[idx][10], p.vf)
            # max
            ret[idx][8] = max(ret[idx][8], p.best_score)
            ret[idx][11] = max(ret[idx][11], p.vf)
            # ave用加算
            ret[idx][9] += p.best_score
            ret[idx][12] += p.vf
            if i >= 49:
                break
        # ave計算
        for lv in range(20):
            if ret[lv][0] > 0:
                ret[lv][9] /= ret[lv][0]
                ret[lv][12] /= ret[lv][0]
        # ツイート用文字列作成
        vfdiff = f' (+{self.total_vf - self.vf_pre:.3f})' if self.total_vf > self.vf_pre else ''
        msg = f'VF: {self.total_vf:.3f}{vfdiff}\n\n'
        for i,st in enumerate(ret):
            if st[0] > 0:
                lv = i+1
                msg += f"LV{lv} - "
                msg += f'{int(st[7]/10000)}-{int(st[8]/10000)}(ave:{int(st[9]/10000)}), '
                msg += f'{st[10]/10:.1f}-{st[11]/10:.1f}(ave:{st[12]/10:.1f}), '
                #msg += f'ave:{int(st[8]/10000)} ({st[11]/10:.1f}),  '
                #msg += f'ave:{int(st[8]/10000)} '
                # lamp
                if st[1] > 0:
                    msg += f"PUC:{st[1]},"
                if st[2] > 0:
                    msg += f"UC:{st[2]},"
                if st[3] > 0:
                    msg += f"EXC:{st[3]},"
                if st[4] > 0:
                    msg += f"COMP:{st[4]},"
                if st[5] > 0:
                    msg += f"failed:{st[5]},"
                msg += ' '
                # score

                msg += '\n'
        msg += '#sdvx_helper'
        return msg

    def upload_best(self, player_name:str='NONAME', volforce:str='0.000', upload_all:bool=False, token:str=None)->bool:
        """maya2serverに自己ベcsvのアップロードを行う。

        Args:
            player_id (str, optional): _description_. Defaults to 'SV-XXXX-XXXX'.
            player_name (str, optional): _description_. Defaults to 'NONAME'.
            volforce (str, optional): _description_. Defaults to '0.000'.

        Returns:
            _type_: _description_
        """
        return self.maya2.upload_best(self, player_name, volforce, upload_all, token)

class OneUploadedScore:
    def __init__(self, revision:int=None, music_id:str=None, difficulty:str=None, score:int=None, exscore:int=None, lamp:str=None): 
        self.revision = revision
        self.music_id = music_id
        self.difficulty = difficulty
        self.score = score
        self.exscore = exscore
        self.lamp = lamp

    def disp(self):
        print(f"rev:{self.revision}, music_id:{self.music_id}, difficulty:{self.difficulty}, score:{self.score:,}, exscore:{self.exscore:,}, lamp:{self.lamp}")
class ManageUploadedScores:
    """maya2サーバへ送信済みのスコアを管理する
    """
    def __init__(self):
        self.load()

    def push(self, data:OneUploadedScore):
        self.scores.append(data)
        return len(self.scores)
    
    def delete(self, revision:int, music_id:str):
        for i,s in enumerate(self.scores):
            if s.music_id == music_id and s.revision == revision:
                self.scores.pop(i)
                logger.info(f"uploaded score deleted! (id:{s.music_id}, rev:{s.revision})")
                return True # 削除成功
        return False # 削除失敗

    def load(self):
        try:
            with open('out/uploaded_score.pkl', 'rb') as fp:
                self.scores = pickle.load(fp)
        except Exception:
            self.scores = []
    
    def save(self):
        with open('out/uploaded_score.pkl', 'wb') as fp:
            pickle.dump(self.scores, fp)

class Maya2TitleConverter:
    def __init__(self):
        self.load()

    def load(self):
        self.forward_table = {}
        self.backward_table = {}
        try:
            with open('resources/title_conv_table.pkl', 'rb') as f:
                self.forward_table = pickle.load(f)
            self.backward_table = dict(zip(self.forward_table.values(), self.forward_table.keys()))
        except Exception:
            logger.error(f"resources/title_conv_table.pkl読み込みエラー")

    def forward(self, key:str) -> str:
        """sdvx_helper側の曲名をmaya2側の曲名に変換する

        Args:
            key (str): sdvx_helper側曲名

        Returns:
            str: maya2側曲名
        """
        ret = key
        if key in self.forward_table.keys():
            ret = self.forward_table[key]
            logger.info(f"{key} をmaya2向けに変換しました。-> {ret}")
        return ret

    def backward(self, key:str) -> str:
        """maya2側の曲名をsdvx_helper側の曲名に変換する

        Args:
            key (str): maya2側曲名

        Returns:
            str: sdvx_helper側曲名
        """
        ret = key
        if key in self.backward_table.keys():
            ret = self.backward_table[key]
            # logger.info(f"{key} をsdvx_helper向けに変換しました。-> {ret}")
        return ret

class ManageMaya2:
    def __init__(self, token=None):
        self.update_token(token)
        self.master_db = []
        self.rival_scores = {}
        self.conv_table = Maya2TitleConverter()
        self.reload()
        logger.info('started')

    def reload(self, token=None):
        if token is not None:
            self.update_token(token)
        self.load_settings()
        start = time.time()
        logger.info(f'{time.time() - start:.2f}, settings loaded')
        self.get_musiclist()
        logger.info(f'{time.time() - start:.2f}, musiclist loaded')
        self.get_rival_scores()
        logger.info(f'{time.time() - start:.2f}, rival scores loaded')

    def update_token(self, token):
        self.token = token

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
        with open(self.settings['params_json'], 'r') as f:
            self.params = json.load(f)
        return ret

    def is_alive(self):
        """サーバ側が生きているかどうかを確認。トークン未設定時はアクセスしない。
        """
        payload = {}
        if self.token in ('', None):
            logger.info('トークン未設定のためスキップします。')
            return False
        try:
            if self.params.get('maya2_testing'):
                r = requests.get(self.params.get('maya2_url_testing')+'/', params=payload)
            else:
                r = requests.get(self.params.get('maya2_url_v1')+'/', params=payload)
        except Exception:
            logger.error(traceback.format_exc())
            logger.info('server: dead')
            return False
        if r.status_code == 200:
            logger.info('server: alive')
            return True
        else:
            logger.info('server: dead')
            return False

    def get_musiclist_test(self):
        """曲マスタを受信する。何も受信できなかった場合はNoneを返す。
        """
        if not self.is_alive():
            self.master_db = None
            logger.info('トークン未設定のためスキップします。')
            return False
        try:
            # APIのホスト名を取得（URLから抽出）
            from urllib.parse import urlparse
            parsed = urlparse(self.params.get('maya2_url_v1'))
            hostname = parsed.hostname

            print('=== DNS解決テスト ===')
            start = time.time()
            result = socket.getaddrinfo(hostname, 443, socket.AF_INET, socket.SOCK_STREAM)
            print(f'getaddrinfo: {time.time()-start:.1f}s')

            start = time.time()
            ip = socket.gethostbyname(hostname)
            print(f'gethostbyname: {time.time()-start:.1f}s, IP: {ip}')

            print('\n=== Session作成テスト ===')
            start = time.time()
            session = requests.Session()
            print(f'Session作成: {time.time()-start:.1f}s')

            start = time.time()
            session.trust_env = False
            print(f'trust_env設定: {time.time()-start:.1f}s')

            print('\n=== リクエスト送信テスト ===')
            header = {'X-Auth-Token': self.token}
            url = self.params.get('maya2_url_v1') + '/api/v1/export/musics'

            start = time.time()
            r = session.post(url, headers=header, timeout=10)
            print(f'POST完了: {time.time()-start:.1f}s')

            start = time.time()
            js = r.json()
            print(f'JSON解析: {time.time()-start:.1f}s')
        except Exception:
            print(traceback.format_exc())
            self.master_db = None
            return False
        return True

    def get_musiclist(self):
        """曲マスタを受信する。何も受信できなかった場合はNoneを返す。
        """
        if not self.is_alive():
            self.master_db = None
            logger.info('トークン未設定のためスキップします。')
            return False
        try:
            header = {'X-Auth-Token': self.token}
            if self.params.get('maya2_testing'):
                r = requests.post(self.params.get('maya2_url_testing')+'/api/testing/export/musics', headers=header)
            else:
                r = requests.post(self.params.get('maya2_url_v1')+'/api/v1/export/musics', headers=header)
            js = r.json()

            musics = js['musics']
            self.master_db = musics
        except Exception:
            print(traceback.format_exc())
            self.master_db = None
            return False
        return True

    def get_rival_scores(self):
        """ライバルのスコアをmaya2から取得する。

        self.rival_scores:dict, 
            key: name
            values: [MusicInfo(), MusicInfo(), ...]
        """
        if not self.is_alive():
            self.rival_scores = {}
            logger.info('トークン未設定のためスキップします。')
            return False
        ret = {}
        try:
            header = {'X-Auth-Token': self.token}
            if self.params.get('maya2_testing'):
                r = requests.post(self.params.get('maya2_url_testing')+'/api/testing/export/rival_scores', headers=header)
            else:
                r = requests.post(self.params.get('maya2_url_v1')+'/api/v1/export/rival_scores', headers=header)
            js = r.json()
            dict_lamp = {'COMP':'clear', 'MAX_COMP':'exh', 'EX_COMP':'hard', 'PLAYED':'failed', 'UC':'uc', 'PUC':'puc', 'MXM_COMP':'exh'}
            for rival in list(js.get('datas', {}).values()): # 1人分のライバルデータ
                tmp = []
                for s in rival.get('scores'):
                    # マスタからIDで検索
                    for m in self.master_db:
                        if m.get('music_id') == s.get('music_id'): # hit
                            best_score = s.get('score_value')
                            exscore = s.get('exscore_value')
                            lamp = dict_lamp[s.get('clear_type')]
                            difficulty = s.get('difficulty_type').lower()
                            if difficulty not in ('nov', 'adv', 'exh'):
                                difficulty = 'APPEND'
                            title = self.conv_table.backward(m.get('title'))
                            info = MusicInfo(title=title, difficulty=difficulty,
                                             best_score=best_score, best_exscore=exscore,
                                             best_lamp=lamp, artist='', bpm='', lv='??')
                            tmp.append(info)
                            break
                ret[rival['rival_name']] = tmp
                logger.info(f"{rival['rival_name']}: {len(tmp)}songs")
        except Exception:
            print(traceback.format_exc())
            # print(rival.keys())
            return False
        self.rival_scores = ret
        return True

    def search_fumeninfo(self, title, fumen='APPEND'):
        """楽曲dbから1譜面の情報を検索する
        """
        ret = None
        try:
            logger.debug(f"title:{title}, fumen:{fumen}")
            for m in self.master_db:
                if m.get('title') == title:
                    for c in m.get('charts'):
                        # 指定の名前が存在 or 最上位譜面でかつこのループが下位譜面でない
                        if ((fumen == 'APPEND') and (c['difficulty'] not in ('NOV', 'ADV', 'EXH'))) or (c['difficulty'] == fumen.upper()):
                            ret = c
                            break
        except Exception:
            return None
        return ret

    def search_musicinfo(self, title):
        """楽曲を検索する
        """
        ret = None
        for m in self.master_db:
            if m.get('title') == title:
                    ret = m
        return ret

    def upload_best(self, sdvx_logger:SDVXLogger, player_name:str='NONAME', volforce:str='0.000', upload_all:bool=False, token:str=None):
        if not self.is_alive():
            logger.error('トークン未設定のためスキップします。')
            return None
        fumen_list = ['nov', 'adv', 'exh', 'APPEND']
        if sdvx_logger is None:
            logger.error('sdvx_logger is None')
            return None
        target = sdvx_logger.best_allfumen if upload_all else sdvx_logger.today_updates
        if len(target) == 0:
            print('送信データがありません。')
            logger.error('送信データがありません。')
            return None
        
        cnt_ok = 0
        cnt_ng = 0
        filename = 'out/maya2_payload.csv'

        fp = open(filename, 'w', encoding='utf-8', newline='')
        writer = csv.writer(fp, lineterminator="\r\n") # \r\n\nになるので対策

        # header
        writer.writerow([player_name,volforce])

        lines = [f"{player_name},{volforce}"]

        # 一旦dictに必要な情報を登録
        tmp_maya2 = {}
        for song in target:
            key = song.title
            # 表記揺れ対応
            key = self.conv_table.forward(key)
            chart = self.search_fumeninfo(key, song.difficulty)
            if chart is not None:
                music = self.search_musicinfo(key)
                if upload_all:
                    lamp=song.best_lamp.upper()
                else:
                    lamp=song.lamp.upper()
                if lamp == 'EXH':
                    lamp = 'MAX_COMP'
                if lamp == 'HARD':
                    lamp = 'EX_COMP'
                if lamp == 'CLEAR':
                    lamp = 'COMP'
                if lamp == 'FAILED':
                    lamp = 'PLAYED'
                key = f"{music.get('music_id')}___{chart.get('difficulty')}"
                if key not in tmp_maya2.keys():
                    if upload_all:
                        tmp_maya2[key] = {'music_id':music.get('music_id'), 'difficulty':chart.get('difficulty'), 
                                            'best_score':song.best_score, 'exscore':song.best_exscore, 'lamp':lamp}
                    else:
                        tmp_maya2[key] = {'music_id':music.get('music_id'), 'difficulty':chart.get('difficulty'), 
                                            'best_score':song.cur_score, 'exscore':song.cur_exscore, 'lamp':lamp}
                else:
                    if upload_all:
                        tmp_maya2[key]['best_score'] = max(tmp_maya2[key]['best_score'], song.best_score)
                        tmp_maya2[key]['exscore'] = max(tmp_maya2[key]['exscore'], song.best_exscore)
                    else:
                        tmp_maya2[key]['best_score'] = max(tmp_maya2[key]['best_score'], song.cur_score)
                        tmp_maya2[key]['exscore'] = max(tmp_maya2[key]['exscore'], song.cur_exscore)

                    lamps = ['PLAYED', 'COMP', 'EX_COMP', 'UC', 'PUC']
                    print(lamp, tmp_maya2[key]['lamp'])
                    tmp_maya2[key]['lamp'] = lamps[max(lamps.index(lamp), lamps.index(tmp_maya2[key]['lamp']))]
                    print(f'duplicated data was updated -> key:{key}, data:{tmp_maya2[key]}')
            else:
                cnt_ng += 1
                print(f'not found in maya2 db!! title:{key}, diff:{song.difficulty}')
                logger.debug(f'not found in maya2 db!! title:{key}, diff:{song.difficulty}')

        for k in tmp_maya2.keys():
            cnt_ok += 1
            dat = tmp_maya2[k]
            line = f"{dat['music_id']},{dat['difficulty']},{dat['best_score']},{dat['exscore']},{dat['lamp']}"
            line_list = [dat['music_id'],dat['difficulty'],dat['best_score'],dat['exscore'],dat['lamp']]
            lines.append(line)
            writer.writerow(line.split(','))

        print(f"total result: OK:{cnt_ok}, NG:{cnt_ng}")
        logger.info(f"total result: OK:{cnt_ok}, NG:{cnt_ng}")

        # footer; calc checksum

        payload = '\r\n'.join(lines)
        secret = maya2_key.encode(encoding='utf-8')
        checksum = hmac.new(secret, payload.encode(encoding='utf-8'), hashlib.sha256).hexdigest()
        logger.debug(f"checksum = {checksum}")
        now = datetime.datetime.now().replace(microsecond=0)
        fp.close()
        with open(filename, 'a', encoding='utf-8', newline='') as fp:
            writer = csv.writer(fp, lineterminator="") # 最終行は改行しない
            writer.writerow([now,cnt_ok,checksum])

        # サーバへ送信
        header = {'X-Auth-Token': self.token}
        if self.params.get('maya2_testing'):
            url = self.params.get('maya2_url_testing')+'/api/testing/import/scores'
        else:
            url = self.params.get('maya2_url_v1')+'/api/v1/import/scores'
        file_binary = open(filename, 'rb').read()
        files = {'regist_score': (filename, file_binary)}
        res = requests.post(url, files=files, headers=header)
        logger.debug(f"status_code = {res.status_code}")
        print(res.json())

        # 送信済みリストを更新
        revision = res.json().get('revision', -1)
        print('rev:',revision)
        mng = ManageUploadedScores()
        for v in tmp_maya2.values():
            tmp = OneUploadedScore(
                revision=revision,
                music_id = v['music_id'],
                difficulty=v['difficulty'],
                score=v['best_score'],
                exscore=v['exscore'],
                lamp=v['lamp']
            )
            mng.push(tmp)
        mng.save()
        return res
    
    def delete_score(self, revision:str, music_id:str, difficulty:str):
        """maya2上のデータを削除

        Args:
            revision (str): 送信時のリビジョン番号
            music_id (str): 楽曲ID
            difficulty (str): 難易度(EXH, MXMなど)
        """
        filename = 'out/maya2_payload.csv'

        fp = open(filename, 'w', encoding='utf-8', newline='')
        writer = csv.writer(fp, lineterminator="\r\n") # \r\n\nになるので対策
        lines = []
        line = f'{revision}'
        lines.append(line)
        writer.writerow(line.split(','))

        # header
        line = f"{music_id},{difficulty},,,,1"
        lines.append(line)
        writer.writerow(line.split(','))

        payload = '\r\n'.join(lines)
        secret = maya2_key.encode(encoding='utf-8')
        checksum = hmac.new(secret, payload.encode(encoding='utf-8'), hashlib.sha256).hexdigest()
        logger.debug(f"checksum = {checksum}")
        now = datetime.datetime.now().replace(microsecond=0)
        fp.close()
        with open(filename, 'a', encoding='utf-8', newline='') as fp:
            writer = csv.writer(fp, lineterminator="") # 最終行は改行しない
            writer.writerow([now,1,checksum])

        # サーバへ送信
        header = {'X-Auth-Token': self.token}
        if self.params.get('maya2_testing'):
            url = self.params.get('maya2_url_testing')+'/api/testing/import/modify'
        else:
            url = self.params.get('maya2_url_v1')+'/api/v1/import/modify'
        file_binary = open(filename, 'rb').read()
        # files = {'file': ('modify.csv', file_binary)}
        files = {'modify': (filename, file_binary)}
        res = requests.post(url, files=files, headers=header)
        logger.debug(f"status_code = {res.status_code}")

        if res.status_code == 200:
            mng = ManageUploadedScores()
            mng.delete(revision, music_id)
            mng.save()
        return res

if __name__ == '__main__':
    a = SDVXLogger(player_name='kata')
    #a.get_rival_score(a.settings['player_name'], a.settings['rival_names'], a.settings['rival_googledrive'])
    #for i,s in enumerate(a.best_allfumen):
    #    if i<50:
    #        s.disp()
    #for i,s in enumerate(a.best_allfumen):
    #   if 'Gun Shooo' in s.title:
    #        s.disp()
    #print(f"自己べ: {a.best_allfumen[-27].best_score}")
    #print(f"rival 更新前:{b['自分'][-27].best_score} -> {a.rival_score['自分'][-27].best_score}") 
    print(a.maya2.is_alive())
    mng = ManageUploadedScores()
    if a.maya2.is_alive():
        res = a.maya2.upload_best(a, upload_all=True, player_name='かたお', volforce='19.149')
        # tmp = a.maya2.delete_score(24, '3kIgHPDRpyWYXg2wmuBNNg', 'EXH')
        # print(tmp)