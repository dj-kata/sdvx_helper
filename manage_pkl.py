#!/usr/bin/python3
# musiclist.pklに手動追加するやつなど
import pickle

def load():
    ret = None
    with open('resources/musiclist.pkl', 'rb') as f:
        ret = pickle.load(f)
    return ret

def save(dat:dict):
    with open('resources/musiclist.pkl', 'wb') as f:
        pickle.dump(dat, f)

if __name__ == '__main__':
    a = load()

    ##a['titles']['title'] = ['title', 'artist', 'bpm', 6,12,15,None]
    a['titles']['弾幕信仰'] = ['弾幕信仰', '豚乙女×BEMANI Sound Team "PON"', '', 5,13,16,18]
    a['titles']['Blue Fire'] = ['Blue Fire', 'REDALiCE feat. 野宮あゆみ', '', 4,8,12,16]
    a['titles']['閉塞的フレーション'] = ['閉塞的フレーション', 'Pizuya\'s Cell VS BEMANI Sound Team "dj TAKA"', '', 4,12,15,18]
    a['titles']['SUPER HEROINE!!'] = ['SUPER HEROINE!!', 'Amateras Records vs BEMANI Sound Team "TATSUYA" feat. miko', '', 3,12,15,17]
    a['titles']['残像ニ繋ガレタ追憶ノHIDEAWAY'] = ['残像ニ繋ガレタ追憶ノHIDEAWAY', 'SOUND HOLIC Vs. BEMANI Sound Team "KE!JU" feat. Nana Takahashi', '', 3,11,14,17]

    save(a)
