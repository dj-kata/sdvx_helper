# sdvx_helper
コナステ版SOUND VOLTEX用の配信補助ツールです。  
OBSでの配信を想定しています。  
譜面付近のみを切り取ったレイアウトでも、曲情報を見やすく表示することができます。  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/5d33134e-942b-4fb6-a580-d81ad191e57a)

また、リザルト画像の自動保存や、保存したリザルト画像からプレーログ画像の作成も行うことができます。  
プレーログ画像はリザルト画像撮影のたびに自動更新されます。  
F6キーを押すことで、縦向きに直した画像を保存する機能もあります。  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/539cdcee-42da-4aa6-b8fe-fec6bb5279b1)

さらに、ゲーム内の各シーン(選曲画面、プレー画面、リザルト画面)でOBS上のソースに対して表示・非表示を切り替えたり、  
別のシーンに移行したりできます。  
(例: プレー画面だけ手元カメラを表示、リザルト画面だけVTuberのアバターを消す、等)

# インストール方法
[Releaseページ](https://github.com/dj-kata/sdvx_helper/releases)の一番上にあるsdvx_helper.zipをダウンロードし、好きなフォルダ(デスクトップ以外)に解凍してください。  
sdvx_helper.exeをクリックすると実行できます。

# 設定方法
## 1. OBS(28以降)でwebsocketが使えるように設定する。
OBSwebsocketについては、インストールされていない場合は[ここ](https://github.com/obsproject/obs-websocket/releases)から最新のalphaってついてないバージョンの(～Windows-Installer.exe)をDLしてインストールしてください。  
OBSのメニューバー内ツール→WebSocketサーバ設定で以下のように設定してあればOK。
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/7b4fd58e-9e0c-4ffc-a875-3ec427312012)

## 2. sdvx_helper.exeを実行し、メニューバーから設定を開く
## 3. 1で設定したポート番号とパスワードを入力する。
OBSに接続できませんの表示が出る場合はこの辺を疑いましょう。  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/6b63586e-8d9f-4429-876f-2fe12fefe459)

## 4. コナステ版SoundVoltexの設定画面で指定している画面の向きを選択する
回転しないレイアウトには現在未対応となります。  
SDVX側の設定と本ツールの設定は以下のように対応しています。  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/3ca2fd3f-8da4-47ee-b3b0-0b18d14c8fc9)

## 5. 設定画面を閉じる
## 6. メニューバーからOBS制御設定を開く
## 7. OBS配信や録画で使うシーン名を選択し、ゲーム画面のキャプチャに使うソース名を選択してから、ゲーム画面の横にあるsetを押す。
この設定をやらないとゲーム画面を取得できないので注意。  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/7fdd5401-c2cb-4b7a-af04-3bb98f511357)

## 8. OBSにout\nowplaying.htmlをドラッグ&ドロップする。
nowplaying.htmlはソースをダブルクリックして幅820,高さ900に設定すると余白がいい感じになります。  
また、OBS制御設定からプレー中のみ表示、みたいなこともできます。
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/f7a78147-7bc7-45a5-acdd-39ed55920d01)

ソース名がnowplaying.htmlまたはnowplayingでないと自動リロードされないので注意。  
outフォルダ内の画像を直接OBS上に配置する場合は自動でリロードされるようです。

## 9. OBSにout\summary_small.pngをドラッグ&ドロップする。
30曲分の履歴を表示するように作っていますが、曲数を減らしたい場合はAlt+マウスドラッグでトリミングしてください。  
本機能を使うためには以下2点に注意する必要があります。
1. 設定画面でリザルトの保存先フォルダを設定しておく
2. 起動してからリザルトが保存されている

2．について、全てのリザルトを自動保存する機能があるので、そちらを有効にすることを推奨します。  
サマリ画像生成時にはランクDのリザルトのみ弾く機能もあります。(今後もう少し拡張するかも)

主な仕様
- リザルト保存時にsummary_*.pngの更新が走る
- 起動よりも2時間前以降のリザルトを集計する
- 起動時にも一度更新処理が走る(2時間以内にリザルトが生成されていれば

仕様上、うまく動かない場合は一度アプリを再起動するとよいかもしれません。  
2時間の猶予を入れているので、再起動しても同じ画像が出てくるはずです。


# 使い方
上記設定ができていれば、OBS配信や録画を行う際に起動しておくだけでOKです。  
F6キーを押すと指定したフォルダにキャプチャ画像を正しい向きで保存することができます。

# その他
困った時は[本レポジトリのIssue](https://github.com/dj-kata/sdvx_helper/issues)またはTwitter(@[cold_planet_](https://twitter.com/cold_planet_))にご連絡ください。  
#ytlive_helper のハッシュタグも見るかもしれません。
