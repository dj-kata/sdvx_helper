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
    #a['titles']['毒杯スワロウ'] = ['毒杯スワロウ', '猫又おかゆ', '140', 4,12,15,18]
    #a['titles']['カミサマ・ネコサマ'] = ['カミサマ・ネコサマ', '猫又おかゆ', '185', 3,10,14,17]
    #a['titles']['もぐもぐYUMMY!'] = ['もぐもぐYUMMY!', '猫又おかゆ', '140', 2,9,14,17]

    save(a)