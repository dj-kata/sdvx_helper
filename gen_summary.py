#!/usr/bin/python3
import glob, os
from PIL import Image
import imagehash
import datetime, json
import logging, logging.handlers, traceback
import numpy as np

MAX_NUM = 30 # 最大何枚分遡るか
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

class GenSummary:
    def __init__(self, now, savedir, ignore_rankD=True):
        self.start = now
        self.savedir = savedir
        self.ignore_rankD = ignore_rankD
        with open('resources/params.json', 'r') as f:
            self.params = json.load(f)
        print(now, savedir)

    def get_detect_points(self, name):
        sx = self.params[f'{name}_sx']
        sy = self.params[f'{name}_sy']
        ex = self.params[f'{name}_sx']+self.params[f'{name}_w']-1
        ey = self.params[f'{name}_sy']+self.params[f'{name}_h']-1
        return (sx,sy,ex,ey)

    def is_result(self,img):
        cr = img.crop(self.get_detect_points('onresult_val0'))
        tmp = imagehash.average_hash(cr)
        img_j = Image.open('resources/onresult.png')
        hash_target = imagehash.average_hash(img_j)
        val0 = abs(hash_target - tmp) <5 

        cr = img.crop(self.get_detect_points('onresult_val1'))
        tmp = imagehash.average_hash(cr)
        img_j = Image.open('resources/onresult2.png')
        hash_target = imagehash.average_hash(img_j)
        val1 = abs(hash_target - tmp) < 5

        ret = val0 & val1
        if self.params['onresult_enable_head']:
            cr = img.crop(self.get_detect_points('onresult_head'))
            tmp = imagehash.average_hash(cr)
            img_j = Image.open('resources/result_head.png')
            hash_target2 = imagehash.average_hash(img_j)
            val2 = abs(hash_target2 - tmp) < 5
            ret &= val2
        return ret

    def put_result(self, img, bg, bg_small, idx):
        rank = img.crop((958,1034, 1045,1111)) # 88x78
        img_d = Image.open('resources/rank_d.png')
        if abs(imagehash.average_hash(rank) - imagehash.average_hash(img_d)) < 10:
            if self.ignore_rankD:
                logger.debug(f'skip! (idx={idx})')
                return False
        title = img.crop((379,1001, 905,1030)) # 527x30
        difficulty = img.crop((55,870, 192,899)) # 138x30
        rate = img.crop((680,1147, 776,1171)) # 97x25
        score = img.crop((421,1072, 793,1126)) # 373x55
        jacket = img.crop((57,916, 319,1178)) # 263x263

        score = score.crop((0,0, 229,54))
        difficulty = difficulty.resize((69,15))
        score = score.resize((86,20))
        rank  = rank.resize((37,25))
        rate  = rate.resize((80,20))
        jacket = jacket.resize((36,36))

        #diff_s0 = difficulty.crop((0,0,3,14))
        #diff_s1 = difficulty.crop((44,0,68,14))

        bg.paste(jacket,     (20, 17+40*idx))
        bg.paste(difficulty, (70, 28+40*idx))
        bg.paste(title,      (150, 20+40*idx))
        bg.paste(score,      (682, 25+40*idx))
        bg.paste(rank,       (780, 22+40*idx))
        bg.paste(rate,       (825, 25+40*idx))

        title_small = img.crop((379,1001, 665,1030)) # 527x30
        bg_small.paste(jacket,     (20, 17+40*idx))
        bg_small.paste(difficulty, (70, 28+40*idx))
        bg_small.paste(title_small,(150, 20+40*idx))
        bg_small.paste(score,      (442, 25+40*idx))
        bg_small.paste(rank,       (540, 22+40*idx))
        #logger.debug(f'processed (idx={idx})')
        return True

    def generate(self):
        logger.debug(f'called! ignore_rankD={self.ignore_rankD}, savedir={self.savedir}')

        try:
            bg = Image.open('resources/summary_full_bg.png')
            bg_small = Image.open('resources/summary_small_bg.png')
            # 背景の単色画像を生成する場合はこれ
            #bg = Image.new('RGB', (930,1300), (0,0,0))
            #bg_small = Image.new('RGB', (590,1300), (0,0,0))
            idx = 0
            for f in reversed(glob.glob(self.savedir+'/sdvx_*.png')):
                logger.debug(f'f={f}')
                img = Image.open(f)
                ts = os.path.getmtime(f)
                now = datetime.datetime.fromtimestamp(ts)
                # 開始時刻より古いファイルに当たったら終了
                if self.start.timestamp() > now.timestamp():
                    break
                if self.is_result(img):
                    if self.put_result(img, bg, bg_small, idx):
                        idx += 1
                    if idx >= MAX_NUM:
                        break
            bg.save('out/summary_full.png')
            bg_small.save('out/summary_small.png')
        except Exception as e:
            logger.error(traceback.format_exc())

if __name__ == '__main__':
    start = datetime.datetime(year=2023,month=9,day=24)
    a = GenSummary(start, 'pic', ignore_rankD=False)
    a.generate()