#!/usr/bin/python3
import glob, os
from PIL import Image
import imagehash
import datetime

MAX_NUM = 30 # 最大何枚分遡るか

# 現在の画面がリザルト画面かどうか判定

class GenSummary:
    def __init__(self, now):
        self.start = now

    def is_result(self,img):
        cr = img.crop((340,1600,539,1639))
        tmp = imagehash.average_hash(cr)
        img_j = Image.open('resources/onresult.png')
        hash_target = imagehash.average_hash(img_j)
        ret = abs(hash_target - tmp) < 10
        cr = img.crop((0,0,1079,149))
        tmp2 = imagehash.average_hash(cr)
        img_j = Image.open('resources/onresult.png')
        hash_target2 = imagehash.average_hash(img_j)
        ret2 = abs(hash_target2 - tmp2) < 6

        return ret & ret2

    def put_result(self, img, bg, bg_small, idx):
        rank = img.crop((958,1034, 1045,1111)) # 88x78
        img_d = Image.open('resources/rank_d.png')
        if abs(imagehash.average_hash(rank) - imagehash.average_hash(img_d)) < 10:
            print('skip!')
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
        return True

    def generate(self):
        os.makedirs('out/log', exist_ok=True)
        bg = Image.open('resources/summary_full_bg.png')
        bg_small = Image.open('resources/summary_small_bg.png')
        # 背景の単色画像を生成する場合はこれ
        #bg = Image.new('RGB', (930,1300), (0,0,0))
        #bg_small = Image.new('RGB', (590,1300), (0,0,0))
        dir = 'pic'
        idx = 0

        for f in reversed(glob.glob(dir+'/sdvx_*.png')):
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

if __name__ == '__main__':
    start = datetime.datetime(year=2023,month=9,day=22)
    a = GenSummary(start)
    a.generate()