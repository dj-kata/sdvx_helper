#!/usr/bin/python3
import glob, os
from PIL import Image
import imagehash
import datetime, json
import logging, logging.handlers, traceback
import numpy as np

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
        self.load_settings()
        self.max_num = self.params['log_maxnum']
        print(now, savedir)

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

    def get_detect_points(self, name):
        sx = self.params[f'{name}_sx']
        sy = self.params[f'{name}_sy']
        ex = self.params[f'{name}_sx']+self.params[f'{name}_w']-1
        ey = self.params[f'{name}_sy']+self.params[f'{name}_h']-1
        return (sx,sy,ex,ey)
    
    def comp_images(self, img1, img2, threshold=10):
        val1 = imagehash.average_hash(img1)
        val2 = imagehash.average_hash(img2)
        return abs(val2-val1) < threshold

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

    def put_result(self, img, bg, bg_small, idx):
        parts = {}
        parts['rank'] = img.crop(self.get_detect_points('log_crop_rank'))
        img_d = Image.open('resources/rank_d.png')
        # ランクDの場合は飛ばす
        if abs(imagehash.average_hash(parts['rank']) - imagehash.average_hash(img_d)) < 10:
            if self.ignore_rankD:
                logger.debug(f'skip! (idx={idx})')
                return False
            
        # 各パーツの切り取り
        for i in ('title', 'title_small', 'difficulty', 'rate', 'score', 'jacket'):
            parts[i] = img.crop(self.get_detect_points('log_crop_'+i))

        # クリアランプの抽出
        lamp = ''
        if self.comp_images(img.crop(self.get_detect_points('lamp')), Image.open('resources/lamp_puc.png')):
            lamp = 'puc'
        elif self.comp_images(img.crop(self.get_detect_points('lamp')), Image.open('resources/lamp_uc.png')):
            lamp = 'uc'
        elif self.comp_images(img.crop(self.get_detect_points('lamp')), Image.open('resources/lamp_clear.png')):
            if self.comp_images(img.crop(self.get_detect_points('gauge')), Image.open('resources/gauge_hard.png')):
                lamp = 'hard'
            else:
                lamp = 'clear'
        elif self.comp_images(img.crop(self.get_detect_points('lamp')), Image.open('resources/lamp_failed.png')):
            lamp = 'failed'

        # 各パーツのリサイズ
        # 上4桁だけにする
        parts['difficulty'] = parts['difficulty'].resize((69,15))
        parts['score']      = parts['score'].resize((86,20))
        parts['rank']       = parts['rank'].resize((37,25))
        parts['rate']       = parts['rate'].resize((80,20))
        parts['jacket']     = parts['jacket'].resize((36,36))

        rowsize = self.params['log_rowsize']
        parts['lamp'] = Image.open(f'resources/log_lamp_{lamp}.png')
        parts['lamp_small'] = parts['lamp']
        parts['score_small'] = parts['score']
        parts['rank_small'] = parts['rank']
        parts['jacket_small'] = parts['jacket']
        parts['difficulty_small'] = parts['difficulty']
        for i in self.params['log_parts']:
            bg.paste(parts[i],     (self.params[f"log_pos_{i}_sx"], self.params[f"log_pos_{i}_sy"]+rowsize*idx))

        for i in self.params['log_small_parts']:
            bg_small.paste(parts[i],     (self.params[f"log_pos_{i}_sx"], self.params[f"log_pos_{i}_sy"]+rowsize*idx))
        return True

    def generate(self):
        logger.debug(f'called! ignore_rankD={self.ignore_rankD}, savedir={self.savedir}')

        try:
            #bg = Image.open('resources/summary_full_bg.png')
            #bg_small = Image.open('resources/summary_small_bg.png')
            # 背景の単色画像を生成する場合はこれ
            h = self.params['log_margin']*2 + self.params['log_maxnum']*self.params['log_rowsize']
            bg = Image.new('RGB', (self.params['log_width'],h), (0,0,0))
            bg_small = Image.new('RGB', (self.params['log_small_width'],h), (0,0,0))
            idx = 0
            for f in reversed(glob.glob(self.savedir+'/sdvx_*.png')):
                #logger.debug(f'f={f}')
                img = Image.open(f)
                ts = os.path.getmtime(f)
                now = datetime.datetime.fromtimestamp(ts)
                # 開始時刻より古いファイルに当たったら終了
                if self.start.timestamp() > now.timestamp():
                    break
                if self.is_result(img):
                    if self.put_result(img, bg, bg_small, idx):
                        idx += 1
                    if idx >= self.max_num:
                        break
            bg.save('out/summary_full.png')
            bg_small.save('out/summary_small.png')
        except Exception as e:
            logger.error(traceback.format_exc())

if __name__ == '__main__':
    start = datetime.datetime(year=2023,month=9,day=24,hour=16)
    a = GenSummary(start, 'pic', ignore_rankD=False)
    a.generate()