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
    a['titles']['エクシード仮面ちゃんのちょっと一線をえくしーどしたEXCEED講座'] = ['エクシード仮面ちゃんのちょっと一線をえくしーどしたEXCEED講座', '', '130', None,None,None,1]
    a['titles']['愛昧ショコラーテ'] = ['愛昧ショコラーテ', '角巻わため', '135', 2,9,13,16]
    a['titles']['曇天羊'] = ['曇天羊', '角巻わため', '135', 3,10,14,17]
    a['titles']['My song'] = ['My song', '角巻わため', '188', 5,12,15,18]
    a['titles']['What an amazing swing'] = ['What an amazing swing', '角巻わため', '125', 4,11,15,17]

    save(a)
