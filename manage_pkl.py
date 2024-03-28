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
    a['titles'][''] = ['', '', '170', 6,12,15,18]

    save(a)