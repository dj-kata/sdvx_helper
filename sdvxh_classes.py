from enum import Enum
from gen_summary import *
from manage_settings import *
import requests
from bs4 import BeautifulSoup
import logging, logging.handlers

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

# 1曲分の情報。自己ベストも保持する。

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
        self.vf = self.get_vf_single(best_score, best_lamp, lv) if (best_lamp!='') and (type(lv)==int) else 0

    def disp(self):
        msg = f"{self.title}({self.difficulty}) Lv:{self.lv}"
        msg += f" {self.best_score:,}, {self.best_lamp}, VF:{self.vf}"

        print(msg)

    # 単曲のVFを計算
    # 例えば16PUCなら369を返す。36.9と表示するのは上位側でやる。
    # ついでにここでスコアランクを入れておく
    def get_vf_single(self, score, lamp, lv):
        """
        Note: 
            単曲VFを計算する。
            例えば16PUCなら369のように整数を返す。36.9と表示するのは上位側でやる。
            スコアランク(self.rank)もここで更新する。
        Attributes
            score: スコア
            lamp: クリアランプ
            lv: 譜面のレベル

        """
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
        ret = int(lv*score*coef_grade*coef_lamp*20/10000000) # 42.0とかではなく420のように整数で出力
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
    def __init__(self):
        self.gen_summary = GenSummary(datetime.datetime.now())
        self.stats       = Stats()
        self.best_allfumen = []
        self.pre_onselect_title = ''
        self.total_vf = 0
        self.load_settings()
        self.load_alllog()
        self.read_bemaniwiki()
        self.update_best_allfumen()
        self.update_stats()

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

    def load_alllog(self):
        try:
            with open(ALLLOG_FILE, 'rb') as f:
                self.alllog = pickle.load(f)
            self.alllog.sort()
        except Exception:
            print(f"プレーログファイル(alllog.pkl)がありません。新規作成します。")
            self.alllog = []

    def save_alllog(self):
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
        self.gen_history_cursong(title, cur_score, lamp, difficulty)
        # 統計情報も更新
        self.update_stats()
        # VF情報更新
        self.update_total_vf()
        # 選曲画面のためにリザルトしておく。この関数はリザルト画面で呼ばれる。
        self.pre_onselect_title = ''

    # その曲のプレー履歴情報のHTMLを作成
    def gen_history_cursong(self, title:str, cur_score:int, lamp:str, difficulty:str):
        logs, info = self.get_fumen_data(title, difficulty)
        with open('out/history_cursong.xml', 'w', encoding='utf-8') as f:
            f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
            f.write("<Items>\n")
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
            else:
                pass # invalid的なデータを書き込みたい
            f.write("</Items>\n")

    # 曲名に対するVF情報をXML出力
    # 選曲画面からの利用を想定
    def gen_vf_onselect(self, title):
        if title != self.pre_onselect_title: # 違う曲になったときだけ実行
            dat = []
            # 指定の曲名と同じ譜面情報を全て出力
            for d in self.best_allfumen:
                if d.title == title:
                    #d.disp()
                    dat.append(d)

            with open('out/vf_onselect.xml', 'w', encoding='utf-8') as f:
                f.write(f'<?xml version="1.0" encoding="utf-8"?>\n')
                f.write("<Items>\n")
                for d in dat:
                    f.write("    <fumen>\n")
                    f.write(f"        <title>{d.title}</title>\n")
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

    # ある譜面のログと曲情報を取得。自己べを取得する関係で1つにまとめている。
    def get_fumen_data(self, title:str, difficulty:str):
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
        for i,f in enumerate(self.best_allfumen):
            if (f.title == title) and (f.difficulty == diff):
                self.best_allfumen[i] = info
                break
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
    
    # self.best_allfumenから各レベルの統計情報を更新
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
                f.write(f"        <idx>{i+1}</idx>\n")
                f.write(f"        <lv>{s.lv}</lv>\n")
                f.write(f"        <title>{s.title}</title>\n")
                f.write(f"        <difficulty>{s.difficulty}</difficulty>\n")
                f.write(f"        <score>{s.best_score}</score>\n")
                f.write(f"        <lamp>{s.best_lamp}</lamp>\n")
                f.write(f"        <vf>{s.vf}</vf>\n")
                f.write(f"    </music>\n")
            self.total_vf = ret / 1000
            f.write(f"    <total_vf>{self.total_vf:.3f}</total_vf>\n")
            f.write("</vfinfo>\n")
        print(f"VOLFORCE: {self.total_vf}")
        return self.total_vf

    # bemaniwikiから曲、Lvの一覧を取得.将来的にはAPPENDの譜面名も取得したい(TODO)
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

    # リザルト画像置き場の画像からプレーログをインポート
    def import_from_resultimg(self):
        for f in self.gen_summary.get_result_files():
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
                        playdat.disp()
                else:
                    print(f"認識失敗！ {f}")
        self.alllog.sort()

if __name__ == '__main__':
    a = SDVXLogger()
    a.update_best_allfumen()
    a.update_total_vf()
    a.update_stats()

    #for i in range(15,20):
    #    a.stats.data[i].disp()

    #for f in a.best_allfumen:
    #    if f.lv == 19:
    #        f.disp()