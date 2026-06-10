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
    #a['titles']['Prayer '] = ['Prayer ', '溝口ゆうま feat. 大瀬良あい', '183', 6,12,15,18] スペースでごまかしてる
    a = load()

    artist = '不知火フレア'
    title = '架空と本当'
    a['titles'][title] = [title, artist, '', 2,9,13,16]
    title = 'Silent Flame,Never Fade'
    a['titles'][title] = [title, artist, '', 3,11,14,17]
    title = 'Smile & Go!!'
    a['titles'][title] = [title, artist, '', 4,13,16,18]
    title = 'Homesick Pt.2&3'
    a['titles'][title] = [title, artist, '', 5,11,14,17]

    save(a)
