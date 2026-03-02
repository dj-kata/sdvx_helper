import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# ログ保存ディレクトリの作成
LOG_DIR = "log"
os.makedirs(LOG_DIR, exist_ok=True)

def get_logger(name=None):
    '''
    モジュール名に基づいてloggerを取得
    
    Args:
        name: モジュール名（通常は __name__ を渡す）
              Noneの場合はメインスクリプト名を使用
    
    Returns:
        logging.Logger: 指定されたモジュール用のlogger
    
    使用例:
        # 各モジュールで以下のように使用
        from src.logger import get_logger
        logger = get_logger(__name__)
    '''
    if name is None:
        # nameが指定されていない場合はメインスクリプト名を使用
        main_file = os.path.splitext(os.path.basename(sys.argv[0]))[0]
        log_file = os.path.join(LOG_DIR, f"{main_file}.log")
        logger_name = "app_logger"
    else:
        # モジュール名からファイル名を生成
        # 例: 'src.result' -> 'result'
        #     'result' -> 'result'
        module_name = name.split('.')[-1] if '.' in name else name
        log_file = os.path.join(LOG_DIR, f"{module_name}.log")
        logger_name = name

    # 指定された名前でloggerを取得
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    
    # 親loggerへの伝播を無効化（重複ログを防ぐ）
    logger.propagate = False

    # 既にハンドラがある場合は追加しない（二重出力を防ぐ）
    if not logger.handlers:
        # ログフォーマットの設定
        # 時刻, レベル, ファイル名:行数, 関数名, メッセージ
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(filename)s:%(lineno)d:%(funcName)s - %(message)s'
        )

        # ファイル出力設定 (2MB制限, 3世代までバックアップ)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8'
        )
        file_handler.setFormatter(formatter)

        # コンソール出力設定（デバッグ中に便利）
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

    return logger

# デフォルトインスタンス（後方互換性のため）
# 既存コードで `from src.logger import logger` を使っている場合に対応
logger = get_logger()
