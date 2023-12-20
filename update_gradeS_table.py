import pickle
import requests
from bs4 import BeautifulSoup

with open('resources/musiclist.pkl', 'rb') as f:
    data = pickle.load(f)

for lv in [17,18,19]:
    key = f'gradeS_{lv}'
    url = f"https://sdvx.maya2silence.com/table/{lv}"

    # ページの取得
    response = requests.get(url)

    # BeautifulSoupを使用してHTMLを解析
    soup = BeautifulSoup(response.text, 'html.parser')

    # tierヘッダ
    tiers = soup.find_all('div', class_='tier_box')
    data[f"gradeS_lv{lv}"] = {}
    for t in tiers:
        songs = t.find_all('div', class_='song_info')
        key = f"tier{t['data-tier']}"
        data[f"gradeS_lv{lv}"][key] = []
        for s in songs:
            data[f"gradeS_lv{lv}"][s['data-title']] = t['data-tier']
            if t['data-tier'] == '-1':
                data[f"gradeS_lv{lv}"][s['data-title']] = '0+'
            elif t['data-tier'] == '0':
                data[f"gradeS_lv{lv}"][s['data-title']] = '0-'
            elif t['data-tier'] == '999':
                data[f"gradeS_lv{lv}"][s['data-title']] = 'N/A'

with open('resources/musiclist.pkl', 'wb') as f:
    pickle.dump(data, f)