# maya2サーバとの通信関連の処理を一通りまとめておく
# 表記揺れの吸収もここでやる予定
from sdvxh_classes import *
from params_secret import maya2_url
import requests
import logging, logging.handlers
import traceback

os.makedirs('jackets', exist_ok=True)
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

class ManageMaya2:
    def __init__(self, url = maya2_url):
        self.url = url
        self.master_db = []
        if self.is_alive():
            self.get_musiclist()

    def is_alive(self):
        """サーバ側が生きているかどうかを確認
        """
        payload = {}
        try:
            r = requests.get(self.url+'/', params=payload)
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

    def get_musiclist(self):
        """曲マスタを受信する。何も受信できなかった場合はNoneを返す。
        """
        try:
            payload = {}
            r = requests.get(self.url+'/export/musics', params=payload)
            js = json.loads(r.text)

            musics = js['musics']
            self.master_db = musics
        except Exception:
            return False
        return True

    def search(self, title, fumen='APPEND'):
        """楽曲を検索する
        """
        ret = None
        fumen_list = ['nov', 'adv', 'exh', 'APPEND']
        fumen_idx  = fumen_list.index(fumen)
        for m in self.master_db:
            if m.get('title') == title:
                if fumen_idx < len(m.get('charts')):
                    ret = m.get('charts')[fumen_idx]
        return ret

if __name__ == '__main__':
    a = ManageMaya2()
    print(a.is_alive())
    print(a.search('V'))