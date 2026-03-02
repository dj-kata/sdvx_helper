"""has_exscore.pngテンプレートをデバッグ画像から再生成する。"""
import glob
import imagehash
from PIL import Image, ImageDraw
from src.screen_reader import ScreenReader
from src.songinfo import SongDatabase
from src.define import HASH_HAS_EXSCORE, RECT_HAS_EXSCORE, RECT_SELECT_EXSCORE

sdb = SongDatabase()
sr = ScreenReader(sdb)

files = glob.glob('debug/select/*.png')
if not files:
    print('debug/select/ に画像がありません')
    exit(1)

f = files[0]
img = Image.open(f)
sr.update_screen(img)
rotated = sr._img
print(f'使用画像: {f}, rotated size: {rotated.size}')

# 回転後の画像全体を保存（座標確認用）
rotated.save('debug/rotated_select.png')
print('回転後の画像全体を debug/rotated_select.png に保存しました')

# select_exscore の周辺をハイライトした確認用画像
guide = rotated.copy()
draw = ImageDraw.Draw(guide)
# select_exscore 最初の桁の周辺（参考）
ex0 = RECT_SELECT_EXSCORE[0]
draw.rectangle([ex0[0]-50, ex0[1]-50, ex0[2]+200, ex0[3]+50], outline='red', width=2)
# 現在の has_exscore 座標
draw.rectangle(list(RECT_HAS_EXSCORE), outline='blue', width=2)
guide.save('debug/guide_select.png')
print(f'ガイド画像を debug/guide_select.png に保存しました')
print(f'  赤枠: select_exscore周辺 ({ex0[1]-50} ~ {ex0[3]+50}px)')
print(f'  青枠: 現在のhas_exscore座標 {RECT_HAS_EXSCORE}')
print()
print('guide_select.png を目視して、EXスコアラベルの座標を確認してください。')
print('座標が分かったら params.json の has_exscore_sx/sy/w/h を修正してください。')
print()

# 現在の座標で切り出した結果も保存
crop = rotated.crop(RECT_HAS_EXSCORE)
crop.save('debug/has_exscore_current.png')
print(f'現在の座標での切り出し → debug/has_exscore_current.png')
