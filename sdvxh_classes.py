from enum import Enum
from gen_summary import *
from manage_settings import *
import requests, re, csv
from bs4 import BeautifulSoup
import logging, logging.handlers
from functools import total_ordering
from collections import defaultdict
from scipy.stats import rankdata

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
    def __init__(self, title:str, cur_score:int, pre_score:int, lamp:str, difficulty:str, date:str):
        self.title = title
        self.cur_score = cur_score
        self.pre_score = pre_score
        self.lamp = lamp
        self.difficulty = difficulty
        self.date = date
        self.diff = cur_score - pre_score

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
        print(f"{self.title}({self.difficulty}), cur:{self.cur_score}, pre:{self.pre_score}({self.diff:+}), lamp:{self.lamp}, date:{self.date}")

class MusicInfo:
    """
    1譜面分の情報を管理する。  

    1エントリ=1曲のある1譜面。例えば冥のexhとinfは別々のインスタンスで表す。

    自己ベストもここで定義する。

    ソートはVF順に並ぶようにしている。
    """
    def __init__(self, title:str, artist:str, bpm:str, difficulty:str, lv, best_score:int, best_lamp:str):
        self.title = title
        self.artist = artist
        self.bpm = bpm
        self.difficulty = difficulty
        self.lv = lv
        self.best_score = best_score
        self.best_lamp = best_lamp
        self.rank = score_rank.novalue
        self.get_vf_single()

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
        self.lamp['hard'] = 0
        self.lamp['clear'] = 0
        self.lamp['failed'] = 0
        self.lamp['noplay'] = 0

        self.scores = {} # key:曲名___譜面 val:スコア(平均値計算用)
        self.average_score = 0

    def read(self, minfo:MusicInfo):
        self.rank[minfo.rank.name] += 1
        self.lamp[minfo.best_lamp] += 1
        self.scores[f"{minfo.title}___{minfo.difficulty}"] = minfo.best_score

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
    def __init__(self, player_name:str=''):
        self.date = datetime.datetime.now()
        self.gen_summary = GenSummary(self.date)
        self.stats       = Stats()
        self.best_allfumen = []
        self.pre_onselect_title = ''
        self.pre_onselect_difficulty = ''
        self.myname = ''
        self.total_vf = 0
        self.vf_pre = False
        self.player_name = player_name
        self.load_settings()
        self.load_alllog()
        self.titles = self.gen_summary.musiclist['titles']
        self.update_best_allfumen()
        self.update_total_vf()
        self.update_stats()

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
        except Exception:
            print(f"プレーログファイル(alllog.pkl)がありません。新規作成します。")
            self.alllog = []

    def get_rival_score(self, myname, names, ids):
        self.myname = myname
        self.rival_names = names
        ret = [] # MusicInfoの配列
        for id,name in zip(ids, names):
            URL = 'https://docs.google.com/uc?export=download'
            id = self.settings['rival_googledrive'][0]
            print(f"ライバルのスコアを取得中:{name}")

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
            with open('out/rival_tmp.csv', 'wb') as f:
                for chunk in response.iter_content(CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)

            tmp = []
            with open('out/rival_tmp.csv', encoding='utf-8') as f:
                csvr = csv.reader(f)
                for i,r in enumerate(csvr):
                    if i==0:
                        continue
                    difficulty = r[1]
                    if r[1] == '':
                        difficulty = 'APPEND'
                    if r[2] != '??':
                        lv = int(r[2])
                    else:
                        lv = r[2]
                    best_score = int(r[3])
                    best_lamp = r[4]
                    vf = int(r[5])
                    try:
                        info = MusicInfo(r[0], '', '', difficulty, lv, best_score, best_lamp)
                        info.vf = vf
                        tmp.append(info)
                    except Exception:
                        logger.debug(f'rival data error! (title:{r[0]}, difficulty:{difficulty}, best_score:{best_score}, best_lamp:{best_lamp})')
            ret.append(tmp)
        self.rival_score = ret
        print(f"ライバルのスコアを取得完了しました。")
        return ret

    def save_alllog(self):
        """プレーログを保存する。
        """
        with open(ALLLOG_FILE, 'wb') as f:
            pickle.dump(self.alllog, f)

    def push(self, title:str, cur_score:int, pre_score:int, lamp:str, difficulty:str, date:str):
        """
            新規データのpush
            その曲のプレーログ一覧を返す
        """
        tmp = OnePlayData(title=title, cur_score=cur_score, pre_score=pre_score, lamp=lamp, difficulty=difficulty, date=date)
        if tmp not in self.alllog:
            self.alllog.append(tmp)

        # 全譜面のbestを更新
        self.update_best_onesong(title, difficulty)
        # ここでHTML表示用XMLを作成
        self.gen_history_cursong(title, difficulty)
        # VF情報更新
        self.update_total_vf()
        # 統計情報も更新
        self.update_stats()
        # 選曲画面のためにリザルトしておく。この関数はリザルト画面で呼ばれる。
        self.pre_onselect_title = ''
        self.pre_onselect_difficulty = ''
        return tmp

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
            title = title.replace('&', '&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'",'&apos;')
            f.write(f"    <title>{title}</title>\n")
            f.write(f"    <difficulty>{difficulty}</difficulty>\n")

            if (logs != False) and (info != False):
                lv = info.lv
                f.write(f"    <lv>{lv}</lv>\n")
                f.write(f"    <best_score>{info.best_score}</best_score>\n")
                f.write(f"    <best_lamp>{info.best_lamp}</best_lamp>\n")
                vf_12 = int(info.vf/10)
                vf_3 = info.vf % 10
                f.write(f"    <vf>{vf_12}.{vf_3}</vf>\n")
                # このプレーの履歴とか、その他
                for p in logs:
                    f.write(f"    <Result>\n")
                    f.write(f"        <score>{p.cur_score}</score>\n")
                    f.write(f"        <lamp>{p.lamp}</lamp>\n")
                    mod_date = f"{p.date[:4]}-{p.date[4:6]}-{p.date[6:8]}"
                    f.write(f"        <date>{mod_date}</date>\n")
                    f.write(f"    </Result>\n")
            else: # invalid
                f.write(f"    <Result>\n")
                f.write(f"        <score></score>\n")
                f.write(f"        <lamp></lamp>\n")
                f.write(f"        <date></date>\n")
                f.write(f"    </Result>\n")
            f.write("</Items>\n")

    def gen_vf_onselect(self, title:str, difficulty:str):
        """曲名に対するVOLFORCE情報をXMLに出力する。
        選曲画面での利用を想定している。

        Args:
            title (str): 曲名
            difficulty (str): 譜面難易度
        """
        if (title != self.pre_onselect_title) or (difficulty != self.pre_onselect_difficulty): # 違う曲になったときだけ実行
            dat = []

            # 指定の曲名と同じ譜面情報を出力
            for d in self.best_allfumen:
                if (d.title == title) and (d.difficulty == difficulty):
                    #d.disp()
                    dat.append(d)

            with open('out/vf_onselect.xml', 'w', encoding='utf-8') as f:
                f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
                f.write("<Items>\n")
                for d in dat:
                    f.write("    <fumen>\n")
                    title = d.title.replace('&', '&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'",'&apos;')
                    f.write(f"        <title>{title}</title>\n")
                    f.write(f"        <difficulty>{d.difficulty.upper()}</difficulty>\n")
                    f.write(f"        <lv>{d.lv}</lv>\n")
                    f.write(f"        <best_score>{d.best_score}</best_score>\n")
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
            for d in self.best_allfumen:
                if (d.title == title) and (d.difficulty.lower() == difficulty.lower()):
                    d.player_name = self.myname
                    d.me = True
                    infos.append(d)
            for tmp,name in zip(self.rival_score, self.rival_names): # tmp: 1人分
                for s in tmp: # 1曲分
                    if (s.title == title) and (s.difficulty.lower() == difficulty.lower()):
                        s.player_name = name
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
                f.write(f"    <lv>{d.lv}</lv>\n")
                for i,(info,r) in enumerate(zip(infos_sorted, rank)):
                    f.write("    <rival>\n")
                    f.write(f"        <rank>{int(r)}</rank>\n")
                    f.write(f"        <name>{info.player_name}</name>\n")
                    if info.me:
                        f.write("        <me>1</me>\n")
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
        diff_table = ['nov', 'adv', 'exh', 'APPEND']
        lamp_table = ['', 'failed', 'clear', 'hard', 'uc', 'puc']
        logs = []
        best_score = 0
        best_lamp = ''
        for p in reversed(self.alllog):
            if (p.title == title) and (p.difficulty == difficulty):
                #p.disp()
                if p.lamp == 'class_clear': # TODO 段位抜けはノマゲ扱いにしておく
                    p.lamp = 'clear'
                best_lamp = p.lamp if lamp_table.index(p.lamp) > lamp_table.index(best_lamp) else best_lamp
                best_score = p.cur_score if (p.cur_score > best_score) and (p.cur_score <= 10000000) else best_score
                # 以前のbest情報の読み取り精度が悪いため、現在のスコアからの登録のみ
                #best_score = p.pre_score if (p.pre_score > best_score) and (p.pre_score <= 10000000) else best_score
                if p.cur_score > 7000000: # 最低スコアを設定 TODO
                    logs.append(p)
        try:
            tmp = self.titles[title]
            artist = tmp[1]
            bpm    = tmp[2]
            lv     = tmp[3+diff_table.index(difficulty)]
        except:
            logger.debug(traceback.format_exc())
            artist = ''
            bpm = ''
            lv = '??'
        info = MusicInfo(title, artist, bpm, difficulty, lv, best_score, best_lamp)
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
        # 譜面一覧を作成。ここで重複しないようにしている。
        for l in self.alllog:
            if [l.title, l.difficulty] not in fumenlist:
                fumenlist.append([l.title, l.difficulty])
        # 各譜面のbestを検索
        for title, diff in fumenlist:
            _, info = self.get_fumen_data(title, diff)
            if info != False:
                ret.append(info)
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

        with open('out/stats.xml', 'w', encoding='utf-8') as f:
            f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
            f.write("<stats>\n")
            f.write(f"    <date>{self.date.strftime('%Y/%m/%d')}</date>\n")
            f.write(f"    <player_name>{self.player_name}</player_name>\n")
            f.write(f"    <total_vf>{self.total_vf:.3f}</total_vf>\n")
            f.write(f"    <total_vf_pre>{self.vf_pre:.3f}</total_vf_pre>\n")
            f.write(f"    <total_vf_diff>{self.total_vf - self.vf_pre:.3f}</total_vf_diff>\n")
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
        with open('out/total_vf.xml', 'w', encoding='utf-8') as f:
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
                diff = self.gen_summary.difficulty
                lamp = self.gen_summary.lamp

                playdat = OnePlayData(ocr, cur, pre, lamp, diff, fmtnow)
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
                    lamp = p.best_lamp.replace('hard', 'exc').replace('clear', 'comp').upper()
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
                    lamp = p.lamp.replace('hard', 'exc').replace('clear', 'comp').upper()
                    date = f"{p.date[0:4]}/{p.date[4:6]}/{p.date[6:8]} {p.date[9:11]}:{p.date[11:13]}:{p.date[13:15]}"
                    writer.writerow([p.title, diff, lv, p.cur_score, lamp, vf, date])
                    #print(p.title, p.difficulty, lv, vf)
            return True

        except Exception:
            print(traceback.format_exc())
            logger.debug(traceback.format_exc())
            return False

    def analyze(self) -> str:
        """VF内訳を分析してlistで出力

        Returns:
            str: ツイート用文字列
        """
        #list: 分析結果(1要素:1Lv分のlist)
        #1要素は[num, puc, uc, hard, clear, failed, minscore, maxscore, avescore, min_vf, max_vf, ave_vf]
        list_lamp = ['puc', 'uc', 'hard', 'clear', 'failed']
        ret = [[0 for __ in range(12)] for _ in range(20)]
        for i in range(20):
            ret[i][6] = 10000000
            ret[i][9] = 1000.0
        for i,p in enumerate(self.best_allfumen):
            p.disp()
            idx = p.lv - 1
            # 曲数
            ret[idx][0] += 1
            # ランプ
            ret[idx][1+list_lamp.index(p.best_lamp)] += 1
            # min
            ret[idx][6] = min(ret[idx][6], p.best_score)
            ret[idx][9] = min(ret[idx][9], p.vf)
            # max
            ret[idx][7] = max(ret[idx][7], p.best_score)
            ret[idx][10] = max(ret[idx][10], p.vf)
            # ave用加算
            ret[idx][8] += p.best_score
            ret[idx][11] += p.vf
            if i >= 49:
                break
        # ave計算
        for lv in range(20):
            if ret[lv][0] > 0:
                ret[lv][8] /= ret[lv][0]
                ret[lv][11] /= ret[lv][0]
        # ツイート用文字列作成
        vfdiff = f' (+{self.total_vf - self.vf_pre:.3f})' if self.total_vf > self.vf_pre else ''
        msg = f'VF: {self.total_vf:.3f}{vfdiff}\n\n'
        for i,st in enumerate(ret):
            if st[0] > 0:
                lv = i+1
                msg += f"LV{lv} - "
                msg += f'{int(st[6]/10000)}-{int(st[7]/10000)}(ave:{int(st[8]/10000)}), '
                msg += f'{st[9]/10:.1f}-{st[10]/10:.1f}(ave:{st[11]/10:.1f}), '
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
    
if __name__ == '__main__':
    a = SDVXLogger(player_name='kata')
    for i,s in enumerate(a.best_allfumen):
        if i<50:
            s.disp()
    for i,s in enumerate(a.best_allfumen):
       if 'Gun Shooo' in s.title:
            s.disp()