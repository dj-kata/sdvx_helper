"""
認証情報ローダー - 暗号化されたcredentials_encrypted.pyから読み込み
"""

import base64
import json

def load_service_account_info():
    """
    暗号化された認証情報を復号化して読み込む
    
    Returns:
        dict: サービスアカウント情報
    """
    try:
        # 暗号化されたファイルから読み込み
        from .credentials_encrypted import ENCRYPTED_DATA, KEY
        
        # Base64デコード
        encrypted = base64.b64decode(ENCRYPTED_DATA)
        
        # XOR復号化
        decrypted = bytearray()
        for i, byte in enumerate(encrypted):
            decrypted.append(byte ^ KEY[i % len(KEY)])
        
        # JSON解析
        json_str = bytes(decrypted).decode('utf-8')
        return json.loads(json_str)
        
    except ImportError:
        # 開発時のフォールバック（credentials.pyから直接読み込み）
        try:
            from .credentials import service_account_info
            return service_account_info
        except ImportError:
            raise FileNotFoundError(
                "認証情報が見つかりません。\n"
                "開発時: src/credentials.py を作成\n"
                "ビルド用: python credentials_encryptor.py を実行"
            )

