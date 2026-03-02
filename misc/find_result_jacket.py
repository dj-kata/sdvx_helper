"""リザルト画面のジャケット座標を目視確認するためのスクリプト。

debug/result/ の1枚目の画像を回転補正し、
既存のスコア座標（赤枠）とガイドグリッドを描画して保存する。
"""
import glob
from PIL import Image, ImageDraw
from src.screen_reader import ScreenReader
from src.songinfo import SongDatabase
from src.define import (
    RECT_RESULT_SCORE_LARGE, RECT_RESULT_SCORE_SMALL,
    RECT_RESULT_EXSCORE,
)

files = sorted(glob.glob('debug/result/*.png'))
if not files:
    print('debug/result/ に画像がありません')
    exit(1)

f = files[0]
sdb = SongDatabase()
sr = ScreenReader(sdb)
img = Image.open(f)
sr.update_screen(img)
rotated = sr._img
print(f'使用画像: {f}, size: {rotated.size}')

# 回転後の画像全体を保存（確認用）
rotated.save('debug/rotated_result.png')

# スコア座標を赤枠で可視化したガイド画像
guide = rotated.copy()
draw = ImageDraw.Draw(guide)

# 既存スコア座標
for r in RECT_RESULT_SCORE_LARGE:
    draw.rectangle(list(r), outline='red', width=2)
for r in RECT_RESULT_SCORE_SMALL:
    draw.rectangle(list(r), outline='orange', width=2)
for r in RECT_RESULT_EXSCORE:
    draw.rectangle(list(r), outline='yellow', width=2)

# ジャケット候補領域のグリッド（上半分を100px刻みで分割）
w, h = rotated.size
for y in range(0, h // 2, 100):
    draw.line([(0, y), (w, y)], fill='gray', width=1)
    draw.text((5, y + 2), str(y), fill='gray')
for x in range(0, w, 100):
    draw.line([(x, 0), (x, h // 2)], fill='gray', width=1)
    draw.text((x + 2, 2), str(x), fill='gray')

guide.save('debug/guide_result.png')
print('debug/guide_result.png に保存しました')
print('  赤枠: result_score_large, 橙枠: result_score_small, 黄枠: result_exscore')
print('  グレーグリッド: 100px刻み座標')
print()
print('guide_result.png を目視して、ジャケットの左上 (sx, sy) と サイズ (w, h) を確認してください。')
