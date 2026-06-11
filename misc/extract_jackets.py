import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent.parent))

from src.result_database import ResultDatabase
from src.screen_reader import ScreenReader
from src.config import Config

def main():
    print("保存済みリザルト画像からジャケット画像の一括抽出を開始します...")
    
    config = Config()
    # 暫定的にResultDatabaseを初期化
    db = ResultDatabase(config)
    
    # ジャケット抽出実行
    count = db.batch_generate_jackets(None)
    
    if count:
        print(f"完了しました。{count}枚のジャケットを抽出しました。")
    else:
        print("新規に抽出されたジャケットはありませんでした。")

if __name__ == "__main__":
    main()
