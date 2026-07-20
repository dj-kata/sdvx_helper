# TODO
- 邪魔をしないで-MySongのhash修正
- RTA機能
- ブラスターゲージ最大時に音声で通知
- 認識用範囲の変更(best枠の影響排除)
- 挑戦状機能作成
- 最新の段位画像の切り抜き

English ver is [here](https://github.com/dj-kata/sdvx_helper/blob/main/en_README.md).

# sdvx_helper
コナステ版SOUND VOLTEX用の配信補助ツールです。  
OBSでの配信を想定しています。  

主な機能は以下。
- プレー中の曲情報を分かりやすく表示
- その日のプレーログを画像出力
- リザルト画像の自動保存(曲名やスコア等を含んだファイル名)
- VOLFORCE対象楽曲一覧の表示
- 自己ベストや全プレーログをCSV出力
- OBS制御機能(シーン、ソースの自動切り替え)
- Discordへのリザルト自動投稿
- スコアビューワによる自己ベスト確認
- ライバルとのスコア比較(Google Drive経由)
  - 他のコナステユーザの自己ベスト
  - ACの自己ベスト
- Vaddict上での各種画像作成([sdvx_helper portal](https://sh-portal.maya2silence.com)との連携機能)

[sdvx_helper portal](https://sh-portal.maya2silence.com)を利用することで、
Web上でコナステ版のスコアを確認したり、Vaddictから様々な画像を生成することができます。  
https://sh-portal.maya2silence.com  
<img width="900" alt="image" src="https://github.com/user-attachments/assets/d32d3f6b-1a11-48d9-afb3-7bb5d0f911d6" />
<img width="900" alt="image" src="https://github.com/user-attachments/assets/535d1f05-01e6-4e38-aabb-994c40749061" />



譜面付近のみを切り取ったレイアウトでも、曲情報を見やすく表示することができます。  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/5d33134e-942b-4fb6-a580-d81ad191e57a)

また、リザルト画像の自動保存や、保存したリザルト画像からプレーログ画像の作成も行うことができます。  
プレーログ画像はリザルト画像撮影のたびに自動更新されます。  
F6キーを押すことでキャプチャの手動保存もできます。  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/95173020-f846-4a4f-b320-9e8018cb5059)

コナステ版のVOLFORCE対象楽曲一覧を表示したりもできます。  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/c471fea0-6d16-4b8f-834c-1ba635138fea)

さらに、ゲーム内の各シーン(選曲画面、プレー画面、リザルト画面)でOBS上のソースに対して表示・非表示を切り替えたり、  
別のシーンに移行したりできます。  
(例: プレー画面だけ手元カメラを表示、リザルト画面だけVTuberのアバターを消す、等)

また、Googleドライブに自動保存されるcsvファイルをもとに、以下のようなライバル欄を表示する機能もあります。  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/9bf84220-a720-4a67-97fb-65c10e2c0c4c)

## 本アプリの原理について
念のために書いておきますが、本アプリの処理内容はリバースエンジニアリングの類ではありません。  
ゲーム画面を定期的にキャプチャし、画像処理によってどの画面かを判定しています。  

# sdvx_helper設定方法
[Releaseページ](https://github.com/dj-kata/sdvx_helper/releases)の一番上にあるsdvx_helper.zipをダウンロードし、好きなフォルダ(デスクトップ以外)に解凍してください。  
sdvx_helper.exeをクリックすると実行できます。

詳しくは以下を参照してください。

[インストール・初期設定について](https://github.com/dj-kata/sdvx_helper/wiki/sdvx_helper%E8%A8%AD%E5%AE%9A%E6%96%B9%E6%B3%95)


# ファイル一覧

|ファイル名|説明|
|-|-|
|`sdvx_helper.exe`|sdvx_helper本体のバイナリ|
|`version.txt`|バージョン情報|
|`sdvx_helper.db`|本ツールで取得したプレーログ|
|`config.json`|コンフィグ情報|
|`resources/`|画像認識などに必要なファイル一式|
|`out/`|曲名情報やプレーログなどの出力先フォルダ|
|`log/`|各ログファイルの出力先フォルダ|
|`template/whole_layout_1.html`|配信画面風HTML, ログが大きめ|
|`template/whole_layout_2.html`|配信画面風HTML, 少し画面が大きい、統計情報ビュー入り|
|`template/nowplaying.html`|曲情報表示用HTML(画像版)|
|`template/nowplaying_v2.html`|曲情報表示用HTML(文字表示版)|
|`template/history_cursong.html`|単曲ビュー表示用HTML|
|`template/today_result.html`|本日のプレー履歴表示用HTML|
|`template/rival.html`|ライバル欄表示用HTML|
|`template/sdvx_stats.html`|統計情報表示用HTML|
|`*.dll`, `lib/*`, `share/*`|GUI実行のために必要なライブラリ類|

Windowsアプリ実行のためのライブラリ類も多数含まれていますが、削除しないようにしてください。

各HTMLはOBSへドラッグ&ドロップして使う想定です。  
Chromeなどの通常のブラウザからも確認できます。

# 使い方
上記設定ができていれば、OBS配信や録画を行う際に起動しておくだけでOKです。  
F6キーを押すと指定したフォルダにキャプチャ画像を正しい向きで保存することができます。

# その他
ライセンスはApache2.0に準拠するものとします。  

クレジット表記などは特に必要ありませんが、概要欄などに書いてくれると喜びます。

[曲名認識用DB登録へのご協力のお願い](https://github.com/dj-kata/sdvx_helper/wiki/OCR%E6%A9%9F%E8%83%BD%E3%81%AEDB%E4%BD%9C%E6%88%90%E3%81%B8%E3%81%AE%E5%8D%94%E5%8A%9B%E4%BE%9D%E9%A0%BC)  
[開発用Discord](https://discord.gg/3krMhQyc)では曲名認識(OCR)機能の開発状況を確認することができます。  

[このページ](https://github.com/dj-kata/sdvx_helper/wiki/%E3%83%88%E3%83%A9%E3%83%96%E3%83%AB%E3%82%B7%E3%83%A5%E3%83%BC%E3%83%86%E3%82%A3%E3%83%B3%E3%82%B0)にトラブルシューティング情報をまとめていく予定です。

バグ報告や要望は[本レポジトリのIssue](https://github.com/dj-kata/sdvx_helper/issues)またはTwitter(@[cold_planet_](https://twitter.com/cold_planet_))にご連絡ください。  
sdvx_helper でエゴサしてるかもしれません。
