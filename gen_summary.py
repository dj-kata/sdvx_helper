#!/usr/bin/python3
import glob, os, io, pickle
from PIL import Image
import imagehash
import datetime, json
import logging, logging.handlers, traceback
import numpy as np
from discord_webhook import DiscordWebhook

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

try:
    with open('version.txt', 'r') as f:
        SWVER = f.readline().strip()
except Exception:
    SWVER = "v?.?.?"

class GenSummary:
    def __init__(self, now):
        self.start = now
        self.result_parts = False
        self.difficulty = False
        self.load_settings()
        self.load_hashes()
        self.savedir = self.settings['autosave_dir']
        self.ignore_rankD = self.settings['ignore_rankD']
        self.alpha = self.settings['logpic_bg_alpha']
        self.max_num = self.params['log_maxnum']
        print(now, self.savedir)

    def load_settings(self):
        try:
            with open('settings.json') as f:
                self.settings = json.load(f)
            with open(self.settings['params_json'], 'r') as f:
                self.params = json.load(f)
            logger.debug(f"params={self.params}")
        except Exception as e:
            logger.debug(traceback.format_exc())
            with open('resources/params.json', 'r') as f:
                self.params = json.load(f)

    # スコアの数字及び、曲名情報のハッシュを読む
    def load_hashes(self):
        self.score_hash_small = []
        self.score_hash_large = []
        self.bestscore_hash   = []
        for i in range(10):
            self.score_hash_small.append(imagehash.average_hash(Image.open(f'resources/result_score_s{i}.png')))
            self.score_hash_large.append(imagehash.average_hash(Image.open(f'resources/result_score_l{i}.png')))
            self.bestscore_hash.append(imagehash.average_hash(Image.open(f'resources/result_bestscore_{i}.png')))

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
        
        if not 'titles' in self.musiclist.keys():
            print('各曲のレベル情報がないので新規作成します。')
            self.musiclist['titles'] = {}

        # 譜面毎のハッシュ一覧を作っておく(検索用)
        # keyはハッシュ値、右辺は曲名
        self.musiclist_hash = {}
        self.musiclist_hash['jacket'] = {}
        self.musiclist_hash['jacket']['nov'] = {}
        self.musiclist_hash['jacket']['adv'] = {}
        self.musiclist_hash['jacket']['exh'] = {}
        self.musiclist_hash['jacket']['APPEND'] = {}
        self.musiclist_hash['info'] = {}
        self.musiclist_hash['info']['nov'] = {}
        self.musiclist_hash['info']['adv'] = {}
        self.musiclist_hash['info']['exh'] = {}
        self.musiclist_hash['info']['APPEND'] = {}
        for pos in ('jacket', 'info'):
            for diff in ('nov', 'adv', 'exh', 'APPEND'):
                for s in self.musiclist[pos][diff].keys():
                    self.musiclist_hash[pos][diff][self.musiclist[pos][diff][s]] = s

    def get_detect_points(self, name):
        sx = self.params[f'{name}_sx']
        sy = self.params[f'{name}_sy']
        ex = self.params[f'{name}_sx']+self.params[f'{name}_w']-1
        ey = self.params[f'{name}_sy']+self.params[f'{name}_h']-1
        return (sx,sy,ex,ey)

    # スコアの抽出
    # PIL.Imageを受け取ってintのスコアを返す
    # resources/result_score_{l,s}{0-9}.pngはグレースケールなので注意    
    def get_score(self, img):
        img_gray = img.convert('L')
        tmp = []
        tmp.append(img_gray.crop(self.get_detect_points('result_score_large_0')))
        tmp.append(img_gray.crop(self.get_detect_points('result_score_large_1')))
        tmp.append(img_gray.crop(self.get_detect_points('result_score_large_2')))
        tmp.append(img_gray.crop(self.get_detect_points('result_score_large_3')))
        tmp.append(img_gray.crop(self.get_detect_points('result_score_small_4')))
        tmp.append(img_gray.crop(self.get_detect_points('result_score_small_5')))
        tmp.append(img_gray.crop(self.get_detect_points('result_score_small_6')))
        tmp.append(img_gray.crop(self.get_detect_points('result_score_small_7')))
        out = []
        for j,t in enumerate(tmp):
            hash = imagehash.average_hash(t)
            minid = -1
            minval = 999999
            if j < 4:
                for i,h in enumerate(self.score_hash_large):
                    val = abs(h - hash)
                    minid = i if val<minval else minid
                    minval = val if val<minval else minval
            else:
                for i,h in enumerate(self.score_hash_small):
                    val = abs(h - hash)
                    minid = i if val<minval else minid
                    minval = val if val<minval else minval
            out.append(minid)
        cur_score = int(''.join(map(str, out)))

        # bestスコアの処理
        tmp = []
        out = []
        tmp.append(img_gray.crop(self.get_detect_points('result_bestscore_0')))
        tmp.append(img_gray.crop(self.get_detect_points('result_bestscore_1')))
        tmp.append(img_gray.crop(self.get_detect_points('result_bestscore_2')))
        tmp.append(img_gray.crop(self.get_detect_points('result_bestscore_3')))
        tmp.append(img_gray.crop(self.get_detect_points('result_bestscore_4')))
        tmp.append(img_gray.crop(self.get_detect_points('result_bestscore_5')))
        tmp.append(img_gray.crop(self.get_detect_points('result_bestscore_6')))
        tmp.append(img_gray.crop(self.get_detect_points('result_bestscore_7')))
        #for j,t in enumerate(tmp):
        #    hash = imagehash.average_hash(t)
        #    t.save(f"result_bestscore_{hash}.png")
        for j,t in enumerate(tmp):
            hash = imagehash.average_hash(t)
            minid = -1
            minval = 999999
            for i,h in enumerate(self.bestscore_hash):
                val = abs(h - hash)
                minid = i if val<minval else minid
                minval = val if val<minval else minval
            if minid in (9,8): # 8,9の判定を間違えやすいので、左下の色を見て判別
                if np.array(t)[10][1] < 100:
                    minid = 9
                else:
                    minid = 8
            out.append(minid)
        pre_score = int(''.join(map(str, out)))

        return cur_score, pre_score

    def comp_images(self, img1, img2, threshold=10):
        val1 = imagehash.average_hash(img1)
        val2 = imagehash.average_hash(img2)
        return abs(val2-val1) < threshold
    
    def send_webhook(self):
        try:
            if (self.result_parts != False) and self.settings['send_webhook']:
                url = self.params['url_webhook_unknown']
                if self.difficulty == 'exh':
                    url = self.params['url_webhook_unknown_exh']
                elif self.difficulty == 'adv':
                    url = self.params['url_webhook_unknown_adv']
                elif self.difficulty == 'nov':
                    url = self.params['url_webhook_unknown_nov']
                webhook = DiscordWebhook(url=url, username="unknown title info")
                msg = ''
                for i in ('jacket_org', 'info'):
                    msg += f"- **{imagehash.average_hash(self.result_parts[i])}**\n"
                # 添付ファイル
                img_bytes = io.BytesIO()
                self.result_parts['info'].crop((0,0,260,65)).save(img_bytes, format='PNG')
                webhook.add_file(file=img_bytes.getvalue(), filename=f'info.png')
                img_bytes = io.BytesIO()
                self.result_parts['difficulty'].save(img_bytes, format='PNG')
                webhook.add_file(file=img_bytes.getvalue(), filename=f'difficulty.png')
                msg += f"(difficulty: **{self.difficulty.upper()}**, sdvx_helper:{SWVER})"

                webhook.content=msg

            res = webhook.execute()
        except Exception:
            logger.debug(traceback.format_exc())
    
    def is_result(self,img):
        cr = img.crop(self.get_detect_points('onresult_val0'))
        img_j = Image.open('resources/onresult.png')
        val0 = self.comp_images(cr, img_j, 5)

        cr = img.crop(self.get_detect_points('onresult_val1'))
        img_j = Image.open('resources/onresult2.png')
        val1 = self.comp_images(cr, img_j, 5)

        ret = val0 & val1
        if self.params['onresult_enable_head']:
            cr = img.crop(self.get_detect_points('onresult_head'))
            img_j = Image.open('resources/result_head.png')
            val2 = self.comp_images(cr, img_j, 5)
            ret &= val2
        return ret

    def cut_result_parts(self, img):
        parts = {}
        parts['rank'] = img.crop(self.get_detect_points('log_crop_rank'))

        # 各パーツの切り取り
        for i in ('title', 'title_small', 'difficulty', 'rate', 'score', 'jacket', 'info'):
            parts[i] = img.crop(self.get_detect_points('log_crop_'+i))

        # クリアランプの抽出
        lamp = ''
        if self.comp_images(img.crop(self.get_detect_points('lamp')), Image.open('resources/lamp_puc.png')):
            lamp = 'puc'
        elif self.comp_images(img.crop(self.get_detect_points('lamp')), Image.open('resources/lamp_uc.png')):
            lamp = 'uc'
        elif self.comp_images(img.crop(self.get_detect_points('lamp')), Image.open('resources/lamp_clear.png')):
            rsum = np.array(img.crop(self.get_detect_points('gauge')))[:,:,0].sum()
            gsum = np.array(img.crop(self.get_detect_points('gauge')))[:,:,1].sum()
            bsum = np.array(img.crop(self.get_detect_points('gauge')))[:,:,2].sum()
            #print(rsum, gsum, bsum)
            if rsum < gsum:
                lamp = 'clear'
            else:
                if gsum > 200000:
                    lamp = 'class_clear'
                else:
                    lamp = 'hard'
        elif self.comp_images(img.crop(self.get_detect_points('lamp')), Image.open('resources/lamp_failed.png')):
            lamp = 'failed'

        if lamp == '':
            return False

        # 各パーツのリサイズ
        # 上4桁だけにする
        parts['difficulty_org'] = parts['difficulty']
        parts['difficulty'] = parts['difficulty'].resize((69,15))
        parts['score']      = parts['score'].resize((86,20))
        parts['rank']       = parts['rank'].resize((37,25))
        parts['rate']       = parts['rate'].resize((80,20))
        parts['jacket_org'] = parts['jacket']
        parts['jacket']     = parts['jacket'].resize((36,36))

        parts['lamp'] = Image.open(f'resources/log_lamp_{lamp}.png')
        parts['lamp_small'] = parts['lamp']
        parts['score_small'] = parts['score']
        parts['rank_small'] = parts['rank']
        parts['jacket_small'] = parts['jacket']
        parts['difficulty_small'] = parts['difficulty']
        self.result_parts = parts
        self.lamp = lamp
        return parts

    def put_result(self, img, bg, bg_small, idx):
        img_d = Image.open('resources/rank_d.png')
        # ランクDの場合は飛ばす
        if abs(imagehash.average_hash(img.crop(self.get_detect_points('log_crop_rank'))) - imagehash.average_hash(img_d)) < 10:
            if self.ignore_rankD:
                logger.debug(f'skip! (idx={idx})')
                return False
            
        parts = self.cut_result_parts(img)
        rowsize = self.params['log_rowsize']

        for i in self.params['log_parts']:
            bg.paste(parts[i],     (self.params[f"log_pos_{i}_sx"], self.params[f"log_pos_{i}_sy"]+rowsize*idx))

        for i in self.params['log_small_parts']:
            bg_small.paste(parts[i],     (self.params[f"log_pos_{i}_sx"], self.params[f"log_pos_{i}_sy"]+rowsize*idx))
        return True

    def generate_today_all(self, dst:str):
        logger.debug(f'called! ignore_rankD={self.ignore_rankD}, savedir={self.savedir}')
        if type(dst) == str:
            try:
                # 枚数を検出
                num = 0
                bg = Image.new('RGB', (500,500), (0,0,0))
                for f in self.get_result_files():
                    img = Image.open(f)
                    ts = os.path.getmtime(f)
                    now = datetime.datetime.fromtimestamp(ts)
                    if self.start.timestamp() > now.timestamp():
                        break
                    if self.is_result(img):
                        if self.put_result(img, bg, bg, 0) != False:
                            num += 1
                print(f"検出した枚数num:{num}")
                logger.debug(f"検出した枚数num:{num}")
                if num == 0:
                    print('本日のリザルトが1枚もありません。スキップします。')
                    return False
                # 画像生成
                idx = 0
                h = self.params['log_margin']*2 + max(num,self.params['log_maxnum'])*self.params['log_rowsize']
                bg = Image.new('RGB', (self.params['log_width'],h), (0,0,0))
                bg.putalpha(self.alpha)
                bg_small = Image.new('RGB', (self.params['log_small_width'],h), (0,0,0))
                for f in self.get_result_files():
                    img = Image.open(f)
                    ts = os.path.getmtime(f)
                    now = datetime.datetime.fromtimestamp(ts)
                    if self.start.timestamp() > now.timestamp():
                        break
                    if self.is_result(img):
                        if self.put_result(img, bg, bg_small, idx) != False:
                            idx += 1
                bg.save(dst)
            except Exception as e:
                logger.error(traceback.format_exc())
            return True
    
    # ジャケット画像を与えた時のOCR結果を返す(選曲画面からの利用を想定)
    # 返り値: 曲名, hash差分の最小値
    def ocr_only_jacket(self, jacket, nov, adv, exh, APPEND):
        hash_jacket = imagehash.average_hash(jacket)
        title = False
        minval = 99999
        sum_nov = np.array(nov).sum()
        sum_adv = np.array(adv).sum()
        sum_exh = np.array(exh).sum()
        sum_APPEND = np.array(APPEND).sum()
        max_sum = max(sum_nov, sum_adv, sum_exh, sum_APPEND)
        if max_sum == sum_nov:
            difficulty = 'nov'
        elif max_sum == sum_adv:
            difficulty = 'adv'
        elif max_sum == sum_exh:
            difficulty = 'exh'
        else:
            difficulty = 'APPEND'
        for h in self.musiclist_hash['jacket'][difficulty].keys():
            h = imagehash.hex_to_hash(h)
            if abs(h - hash_jacket) < minval:
                minval = abs(h - hash_jacket)
                title = self.musiclist_hash['jacket'][difficulty][str(h)]
        return title, minval, difficulty

    def ocr(self, notify:bool=False):
        ret = False
        difficulty = False
        detected = False
        try:
            diff = self.result_parts['difficulty_org'].crop((0,0,70,30))
            hash_nov = imagehash.average_hash(Image.open('resources/difficulty_nov.png'))
            hash_adv = imagehash.average_hash(Image.open('resources/difficulty_adv.png'))
            hash_exh = imagehash.average_hash(Image.open('resources/difficulty_exh.png'))
            hash_cur = imagehash.average_hash(diff)

            hash_jacket = imagehash.average_hash(self.result_parts['jacket_org'])
            hash_info   = imagehash.average_hash(self.result_parts['info'])
            rsum = np.array(diff)[:,:,0].sum()
            gsum = np.array(diff)[:,:,1].sum()
            bsum = np.array(diff)[:,:,2].sum()
            if (rsum<190000) and (gsum<180000) and (bsum>300000):
                difficulty = 'nov'
            elif (rsum>300000) and (gsum>260000) and (bsum<180000):
                difficulty = 'adv'
            elif (rsum>300000) and (gsum<180000) and (bsum<180000):
                difficulty = 'exh'
            else:
                difficulty = 'APPEND'
            self.difficulty = difficulty
            for h in self.musiclist_hash['jacket'][difficulty].keys():
                h = imagehash.hex_to_hash(h)
                if abs(h - hash_jacket) < 5:
                    self.hash_hit = h
                    if self.settings['save_jacketimg']:
                        tt = f"jackets/{str(h)}.png"
                        if not os.path.exists(tt):
                            self.result_parts['jacket_org'].save(tt)
                    detected = True
                    ret = self.musiclist_hash['jacket'][difficulty][str(h)]
                    logger.debug(f"OCR pass: {abs(h - hash_jacket)<5}, h:{str(h)}, cur:{str(hash_jacket)}, diff:{abs(h - hash_jacket)<5}")
                    break
            if not detected:
                if notify and self.settings['send_webhook']:
                    self.send_webhook()
                # 曲名エリアからの認識だと精度が悪いので放置
                #for h in self.musiclist_hash['info'][difficulty].keys():
                #    h = imagehash.hex_to_hash(h)
                #    if abs(h - hash_info) < 5:
                #        ret = self.musiclist_hash['info'][difficulty][str(h)]
                #        #break
            else:
                tmp = Image.open('resources/no_jacket.png')
                hash_no_jacket = imagehash.average_hash(tmp)
                if abs(hash_jacket - hash_no_jacket) < 5:
                    print('ジャケット削除済みの曲なので判定結果をクリアします。')
        except Exception:
            logger.debug(traceback.format_exc())
        return ret
    
    # OCRの動作確認用。未検出のものを見つけて報告するために使う。
    def chk_ocr(self, iternum=500):
        logger.debug(f'called! ignore_rankD={self.ignore_rankD}, savedir={self.savedir}')
        try:
            idx = 0
            for f in self.get_result_files():
                img = Image.open(f)
                if self.is_result(img):
                    cur,pre = self.get_score(img)
                    if self.cut_result_parts(img) != False:
                        idx+=1
                        ocr_result = self.ocr()
                        print(f"{f[-19:]}: {cur:,} ({pre:,}), {ocr_result}")
                        if ocr_result == False:
                            pass
                            #self.send_webhook()
                if idx >= iternum:
                    break
        except Exception as e:
            logger.error(traceback.format_exc())

    def get_result_files(self):
        return sorted(glob.glob(self.savedir+'/sdvx_*.png'), key=os.path.getmtime, reverse=True)

    def generate(self): # max_num_offset: 1日の最後など、全リザルトを対象としたい場合に大きい値を設定する
        logger.debug(f'called! ignore_rankD={self.ignore_rankD}, savedir={self.savedir}')

        try:
            #bg = Image.open('resources/summary_full_bg.png')
            #bg_small = Image.open('resources/summary_small_bg.png')
            # 背景の単色画像を生成する場合はこれ
            h = self.params['log_margin']*2 + self.params['log_maxnum']*self.params['log_rowsize']
            bg = Image.new('RGB', (self.params['log_width'],h), (0,0,0))
            bg_small = Image.new('RGB', (self.params['log_small_width'],h), (0,0,0))
            bg.putalpha(self.alpha) #背景を透過
            bg_small.putalpha(self.alpha)
            idx = 0
            for f in self.get_result_files():
                #logger.debug(f'f={f}')
                img = Image.open(f)
                ts = os.path.getmtime(f)
                now = datetime.datetime.fromtimestamp(ts)
                # 開始時刻より古いファイルに当たったら終了
                if self.start.timestamp() > now.timestamp():
                    break
                if self.is_result(img):
                    cur,pre = self.get_score(img)
                    if self.put_result(img, bg, bg_small, idx) != False:
                        idx += 1
                        #self.send_webhook()
                    if idx >= self.max_num:
                        break
            bg.save('out/summary_full.png')
            bg_small.save('out/summary_small.png')
        except Exception as e:
            logger.error(traceback.format_exc())

if __name__ == '__main__':
    start = datetime.datetime(year=2023,month=10,day=15,hour=0)
    a = GenSummary(start)
    a.generate()
    #a.generate_today_all('hoge.png')
    #a.chk_ocr(60)