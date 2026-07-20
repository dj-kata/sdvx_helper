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

## 検証に用いている環境
以下の環境で検証しています。  
```
OS: Windows11 Pro 64bit (25H2)
CPU: Intel Core i7-12700F
GPU: NVIDIA RTX4060
ウイルス対策ソフト: Windows Defender
OBS: 32.0.1 (64bit)
```

最新のWebSocket APIを使う都合上、OBSは28以降が必須となります。(WebSocket経由で画面取得する場合)
CPUはAMD系でも問題ないはずです。(websocket経由だと安定する模様)  
OBSとの通信(tcp4444)を行うため、ウイルス対策ソフトによってはブロックされる可能性があります。  

# ファイル一覧

|ファイル名|説明|
|-|-|
|sdvx_helper.exe|sdvx_helper本体のバイナリ|
|version.txt|バージョン情報|
|sdvx_helper.db|本ツールで取得したプレーログ|
|config.json|コンフィグ情報|
|resources/|画像認識などに必要なファイル一式|
|out/|曲名情報やプレーログなどの出力先フォルダ|
|log/|各ログファイルの出力先フォルダ|
|template/whole_layout_1.html|配信画面風HTML, ログが大きめ|
|template/whole_layout_2.html|配信画面風HTML, 少し画面が大きい、統計情報ビュー入り|
|template/nowplaying.html|曲情報表示用HTML(画像版)|
|template/nowplaying_v2.html|曲情報表示用HTML(文字表示版)|
|template/history_cursong.html|単曲ビュー表示用HTML|
|template/today_result.html|本日のプレー履歴表示用HTML|
|template/rival.html|ライバル欄表示用HTML|
|template/sdvx_stats.html|統計情報表示用HTML|
|各*.dll, lib/*|GUI実行のために必要なライブラリ類|

Windowsアプリ実行のためのライブラリ類も多数含まれていますが、削除しないようにしてください。

各HTMLはOBSへドラッグ&ドロップして使う想定です。  
Chromeなどの通常のブラウザからも確認できます。

# sdvx_helper設定方法
- [インストール・初期設定について](https://github.com/dj-kata/sdvx_helper/wiki/sdvx_helper%E8%A8%AD%E5%AE%9A%E6%96%B9%E6%B3%95)
- [各種HTMLの設定方法](https://github.com/dj-kata/sdvx_helper/wiki/%E5%90%84%E7%A8%AEHTML%E3%81%AE%E8%A8%AD%E5%AE%9A%E6%96%B9%E6%B3%95)
- [sdvx_helper v1からのデータ移行方法](https://github.com/dj-kata/sdvx_helper/wiki/sdvx_helper-v1%E3%81%8B%E3%82%89%E3%81%AE%E3%83%87%E3%83%BC%E3%82%BF%E5%8F%96%E3%82%8A%E8%BE%BC%E3%81%BF)

# インストール方法
[Releaseページ](https://github.com/dj-kata/sdvx_helper/releases)の一番上にあるsdvx_helper.zipをダウンロードし、好きなフォルダ(デスクトップ以外)に解凍してください。  
sdvx_helper.exeをクリックすると実行できます。

自動アップデート機能を搭載しており、更新データがある際は起動時にアップデートが走るようになっています。  

# sdvx_helperの設定方法
ゲーム画面について直接取得であれば設定不要で使うことができます。  
詳しくは以下を参照してください。
[sdvx_helper設定方法](https://github.com/dj-kata/sdvx_helper/wiki/sdvx_helper%E8%A8%AD%E5%AE%9A%E6%96%B9%E6%B3%95)

## その他の設定
必須ではないですが、その他の便利機能の設定方法について記しておきます。  
興味のある方はどうぞ。

### VOLFORCE対象曲一覧及び統計情報を表示する
(TBD)
OBSに```out/sdvx_stats.html```をドラッグ&ドロップすると、以下のようなビューを表示できます。  
(推奨サイズ: 幅3500，高さ2700)  
リザルト画面で更新されます。 
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/c471fea0-6d16-4b8f-834c-1ba635138fea)

プレイヤー名の部分は設定画面で入力した文字が使われます。日本語も使えます。  
ちなみに、```保存したリザルト画像をプレーログに反映```ボタンを押すと、過去のリザルト画像をプレーログに反映できます。曲名認識DBは日々更新されていますが、認識できなかった曲を後から反映する場合もこちらのボタンを使ってください。   
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/bcf5b915-9871-4bb5-87f6-21d8a2d5f220)

また、楽曲のジャケットはリザルト画面で保存するようにしています。  
```保存したリザルト画像からVFビュー用ジャケット画像を一括生成```ボタンを押す
ことでも保存できます。ジャケット画像はsdvx_helperフォルダ内のjackets以下に格納されます。  
全曲分生成すると200MB程度になる見込みですが、ディスク容量を気にされる方は
1. ```リザルト画面でジャケット画像を自動保存```のチェックを外し、
2. out/sdvx_stats.html(v2ではない方, 幅3000, 高さ2300)を設定する

とよいです。

### その日のプレー内容のサマリ画像を表示する
OBSにout\summary_small.pngをドラッグ&ドロップすることで表示できます。  
対象範囲内の履歴を全て表示するように作っていますが、曲数を減らしたい場合はAlt+マウスドラッグでトリミングしてください。  
out\summary_full.pngがもう少し大きい版となります。こちらはスコアレートも含みます。
設定画面の```レシート画像の最低曲数```で、リザルトが少ない場合の最低高さを指定できます。  
設定画面で```アプリ終了時にレシート画像を保存する```を有効にすると、終了時にout\summary_full.pngと同内容の画像がリザルト画像保存先へJPG形式で保存されます。  

本機能を使うためには以下2点に注意する必要があります。
1. 設定画面でリザルトの保存先フォルダを設定しておく
2. 起動してからリザルトが保存されている

2．について、全てのリザルトを自動保存する機能があるので、そちらを有効にすることを推奨します。  
サマリ画像生成時にはランクDのリザルトのみ弾く機能もあります。(今後もう少し拡張するかも)

主な仕様
- 設定画面で指定したリザルト置き場にあるリザルト画像をもとに生成
- リザルト保存時にsummary_*.pngの更新が走る
- **アプリ起動の2時間前**以降のリザルトを集計する
- 起動時にも一度更新処理が走る(2時間以内にリザルトが生成されていれば

仕様上、うまく動かない場合は一度アプリを再起動するとよいかもしれません。  
取得対象に2時間の猶予を入れているので、再起動しても同じ画像が出てくるはずです。  
また、リザルト取得に失敗して変な画像(ダブった、色が薄いなど)が入ってしまった場合は、  
該当するリザルト画像のファイルを削除すれば次の生成で直ります。

### リザルトをDiscordに自動投稿する
v.1.0.8からリザルトをDiscordに自動投稿できるようになりました。  
自分のDiscordサーバに以下のようなプレーログを自動投稿することができます。  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/afbf8025-fb9a-4362-a180-55d324c0bd42)

メニューバーの```カスタムWebhook設定```から設定できます。
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/69a31c9b-f68d-433f-b03e-68138d6414c6)

こんな使い方を想定しています。
- 全プレーのログを自分のdiscordに残しておく
- PUCのログのみを自分のdiscordに残しておく
- 知り合いと共通のサーバを利用してライバル機能の代替として使う

設定名、DiscordのwebhookのURLを入力した上で追加ボタンを押すと登録できます。  
送信対象とするLv(1～20)及びクリアランプも指定可能です。  
画像送信の有無も指定できます。

ちなみに、WebhookはDiscord上でテキストチャンネルを編集->連携サービス->ウェブフックから作成できます。  
ウェブフックURLをコピーしてsdvx_helperに入力してください。
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/a9b643e0-0203-4608-982b-0187c4d34c73)

本機能についての主な仕様は以下の通り。
- 通知時の名前は設定画面のプレーヤー名が使われる
- 通知時のアイコンはWebhookで指定したものが使われる
  - 複数人で共有するサーバを登録する場合でも、別々のwebhookを登録しておけばアイコンで区別可能
- Webhook設定は複数登録することが可能

### ライバル欄を表示する
[こちら](https://github.com/dj-kata/sdvx_helper/wiki/%E3%83%A9%E3%82%A4%E3%83%90%E3%83%AB%E6%A9%9F%E8%83%BD%E3%81%AE%E8%A8%AD%E5%AE%9A%E6%96%B9%E6%B3%95(Google%E3%83%89%E3%83%A9%E3%82%A4%E3%83%96%E9%96%A2%E9%80%A3))を参照してください。  

相手にもGoogleドライブ上に置いたcsvファイルのURLを教えてもらう必要があります。  
うまく設定できると、選曲画面やリザルト画面で以下のようなビュー(out\rival.html)が表示できます。
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/9bf84220-a720-4a67-97fb-65c10e2c0c4c)

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
