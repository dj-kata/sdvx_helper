#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import requests
import shutil
import subprocess
import threading
import time
from pathlib import Path
from packaging import version
import tkinter as tk
from tkinter import ttk, messagebox

import traceback
from bs4 import BeautifulSoup
from src.logger import get_logger
logger = get_logger(__name__)

class GitHubUpdater:
    def __init__(self, github_author='', github_repo='', current_version='', main_exe_name=None, updator_exe_name=None):
        """
        GitHub自動アップデータの初期化
        
        Args:
            github_repo (str): GitHubリポジトリ（例: "username/repository"）
            current_version (str): 現在のバージョン（例: "1.0.0"）
            main_exe_name (str): メインプログラムのexe名（例: "main.exe"）
            updator_exe_name (str): アップデート用プログラムのexe名 (例: "update.exe"）
        """
        self.github_author = github_author
        self.github_repo = github_repo
        self.current_version = current_version
        self.main_exe_name = main_exe_name or "main.exe"
        self.updator_exe_name = updator_exe_name or "update.exe"
        self.base_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.cwd()
        self.temp_dir = self.base_dir / "tmp"
        self.backup_dir = self.base_dir / "backup"
        logger.debug(f"base_dir:{self.base_dir}")
        
        # GUI関連
        self.root = None
        self.progress_var = None
        self.status_var = None
        self.progress_bar = None

    def ico_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def get_latest_version(self):
        # self.ico=self.ico_path('icon.ico')
        ret = None
        url = f'https://github.com/{self.github_author}/{self.github_repo}/tags'
        r = requests.get(url)
        soup = BeautifulSoup(r.text,features="html.parser")
        for tag in soup.find_all('a'):
            if 'releases/tag/' in tag['href']:
                logger.debug(f"tag = {tag}")
                ret = tag['href'].split('/')[-1]
                break # 1番上が最新なので即break
        return ret

    def check_for_updates(self):
        """
        GitHubで最新版をチェック
        
        Returns:
            tuple: (is_update_available, latest_version, download_url)
        """
        logger.debug(f"github_repo:{self.github_author}/{self.github_repo}")
        try:
            latest_version = self.get_latest_version()
            download_url = f"https://github.com/{self.github_author}/{self.github_repo}/releases/download/{latest_version}/{self.github_repo}.zip"
            logger.debug(f"latest_version:{latest_version}, current:{self.current_version}")
            
            # バージョン比較
            if version.parse(latest_version.split('v.')[-1]) > version.parse(self.current_version.split('v.')[-1]):
                return True, latest_version, download_url
            else:
                return False, latest_version, None
                
        except Exception as e:
            print(f"アップデートチェックエラー: {e}")
            return False, None, None
    
    def create_gui(self):
        """アップデート用GUIの作成"""
        self.root = tk.Tk()
        # self.icon = tk.PhotoImage(data=icon.icon_data)
        # self.root.iconphoto(False, self.icon)
        self.root.title("プログラム更新中...")
        self.root.geometry("500x200")
        self.root.resizable(False, False)
        
        # 中央に配置
        self.root.geometry("+%d+%d" % (
            (self.root.winfo_screenwidth() / 2 - 250),
            (self.root.winfo_screenheight() / 2 - 100)
        ))
        
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # タイトル
        title_label = ttk.Label(main_frame, text="プログラムを最新版に更新しています...", 
                               font=("Arial", 12, "bold"))
        title_label.pack(pady=(0, 20))
        
        # ステータステキスト
        self.status_var = tk.StringVar(value="更新確認中...")
        status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.pack(pady=(0, 10))
        
        # プログレスバー
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, 
                                          maximum=100, length=400)
        self.progress_bar.pack(pady=(0, 20))
        
        # キャンセルボタン
        cancel_button = ttk.Button(main_frame, text="キャンセル", 
                                 command=self.cancel_update)
        cancel_button.pack()
        
        self.root.protocol("WM_DELETE_WINDOW", self.cancel_update)
        
    def update_status(self, message, progress=None):
        """ステータス更新"""
        if self.status_var:
            self.status_var.set(message)
        if progress is not None and self.progress_var:
            self.progress_var.set(progress)
        if self.root:
            self.root.update()
    
    def download_file(self, url, filepath):
        """
        ファイルをダウンロード（進行状況表示付き）
        
        Args:
            url (str): ダウンロードURL
            filepath (Path): 保存先パス
        """
        self.update_status("最新版をダウンロード中...", 0)
        
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        downloaded_size = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=block_size):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    
                    if total_size > 0:
                        progress = (downloaded_size / total_size) * 50  # 50%まで
                        self.update_status(f"ダウンロード中... {downloaded_size // 1024}KB / {total_size // 1024}KB", 
                                         progress)
    
    def create_backup(self):
        """現在のファイルをバックアップ"""
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)
        
        self.backup_dir.mkdir()
        
        # 重要なファイルをバックアップ
        for item in self.base_dir.iterdir():
            if item.name not in ['temp_update', 'backup'] and item.is_file():
                shutil.copy2(item, self.backup_dir)
    
    def replace_files2(self):
        target_dir = '.'
        logger.debug(f'now moving..., repo:{self.github_repo}')
        p = Path(f'tmp/{self.github_repo}')
        failed_list = []
        logger.debug('now moving...')
        for f in p.iterdir():
            logger.debug(f"f:{f}, is_dir:{f.is_dir()}")
            if f.is_dir():
                subdir=f.relative_to(f'tmp/{self.github_repo}')
                logger.debug(f"mkdir {subdir}")
                os.makedirs(subdir, exist_ok=True)
        for f in p.glob('**/*.*'):
            try:
                base = str(f.relative_to(f'tmp/{self.github_repo}'))
                if self.updator_exe_name in str(f):
                    shutil.copy2(str(f), target_dir+'/new_'+base)
                    logger.debug(f"from={str(f)}, to={target_dir+'/new_'+base}")
                else:
                    shutil.move(str(f), target_dir+'/'+base)
                    logger.debug(f"from={str(f)}, to={target_dir+'/'+base}")
            except Exception:
                if self.updator_exe_name not in str(f):
                    failed_list.append(f)
                logger.debug(f"error! ({f})")
                logger.debug(traceback.format_exc())
        shutil.rmtree(f'tmp/{self.github_repo}')
        out = ''
        if len(failed_list) > 0:
            out = '更新に失敗したファイル(tmp/tmp.zipから手動展開してください): '
            out += '\n'.join(failed_list)

    def create_restart_script(self, new_exe_path):
        logger.info('')
        """再起動用スクリプト作成"""
        if sys.platform.startswith('win'):
            script_path = self.base_dir / "restart_update.bat"
            script_content = f"""@echo off
timeout /t 2 /nobreak >nul
move "{new_exe_path}" "{self.base_dir / self.updator_exe_name}"
start "" "{self.main_exe_name}"
del "%~f0"
"""
            with open(script_path, 'w', encoding='shift_jis') as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)
        
        logger.info(f"path:{script_path}")
        return script_path
    
    def cleanup(self):
        """一時ファイルの清掃"""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            print(f"清掃エラー: {e}")
    
    def cancel_update(self):
        """アップデートキャンセル"""
        self.cleanup()
        if self.root:
            self.root.destroy()
        sys.exit(0)
    
    def run_update(self):
        """アップデート実行"""
        try:
            # 最新版をチェック
            is_update_available, latest_version, download_url = self.check_for_updates()
            
            if not is_update_available:
                messagebox.showinfo("更新確認", "お使いのバージョンは最新です。")
                if self.root:
                    self.root.destroy()
                return False
            
            # GUIを表示
            if not self.root:
                self.create_gui()
            
            # ダウンロード
            zip_path = self.temp_dir / f"update_{latest_version}.zip"
            self.temp_dir.mkdir(exist_ok=True)
            
            self.download_file(download_url, zip_path)
            
            # 解凍・置き換え
            self.extract_and_replace_files(zip_path)

            self.update_status("更新完了！プログラムを再起動します...", 100)
            time.sleep(2)
            
            # 再起動スクリプトを実行
            script_path = self.base_dir / ("restart_update.bat" if sys.platform.startswith('win') 
                                         else "restart_update.sh")
            if script_path.exists():
                if sys.platform.startswith('win'):
                    subprocess.Popen([str(script_path)], shell=True)
                else:
                    subprocess.Popen(['/bin/bash', str(script_path)])
                
                if self.root:
                    self.root.destroy()
                sys.exit(0)
            
            return True
            
        except Exception as e:
            error_msg = f"更新エラー: {e}"
            print(error_msg)
            if self.root:
                messagebox.showerror("エラー", error_msg)
            self.cleanup()
            return False
    
    def extract_zip_file(self, zip_path):
        """zipファイルを解凍する。tmp直下にそのまま解凍する。

        Args:
            zip_path (str): path of zipfile
        """
        shutil.unpack_archive(zip_path, 'tmp')

    def check_and_update(self):
        """
        メインプログラムから呼び出す関数
        アップデートが必要な場合のみGUIを表示して更新実行
        
        Returns:
            bool: アップデートが実行された場合True
        """
        logger.info('check and update')
        try:
            # アップデート確認（GUIなし）
            is_update_available, latest_version, download_url = self.check_for_updates()
            logger.info(f"available:{is_update_available}, latest:{latest_version}, url:{download_url}")
            
            if is_update_available:
                self.create_gui()
                # 確認ダイアログ
                result = messagebox.askyesno(
                    "アップデート確認",
                    f"新しいバージョン（{latest_version}）が利用可能です。\n"
                    f"現在のバージョン: {self.current_version}\n\n"
                    "今すぐ更新しますか？"
                )
                
                if result:
                    self.cleanup()
                    
                    # 別スレッドで更新実行
                    def update_thread():
                        try:
                            # ダウンロード
                            zip_path = self.temp_dir / f"update_{latest_version}.zip"
                            logger.info(f'zip_path: {zip_path}')
                            self.temp_dir.mkdir(exist_ok=True)
                            
                            logger.info('download')
                            self.download_file(download_url, zip_path)
                            self.extract_zip_file(zip_path)
                            logger.info('replace')
                            self.replace_files2()
                            
                            new_exe_path = Path('.') / f"new_{self.updator_exe_name}"
                            # 更新完了後にメインプログラムを再起動するためのバッチファイルを作成
                            self.create_restart_script(new_exe_path)

                            self.update_status("更新完了！プログラムを再起動します...", 100)
                            #self.root.after(2000, self.restart_program)
                            self.restart_program()
                            
                        except Exception as e:
                            logger.error(traceback.format_exc())
                            error_msg = f"更新エラー: {e}"
                            self.root.after(0, lambda: messagebox.showerror("エラー", error_msg))
                            self.root.after(0, self.cancel_update)
                    
                    thread = threading.Thread(target=update_thread, daemon=True)
                    thread.start()
                    
                    self.root.mainloop()
                    return True
                else:
                    # 更新しない場合はGUIを閉じる
                    if self.root:
                        self.root.destroy()
                        self.root = None
                    return False
            else:
                logger.info('no update')
            return False
            
        except Exception as e:
            logger.debug(traceback.format_exc())
            print(f"アップデート確認エラー: {e}")
            return False
    
    def restart_program(self):
        """プログラム再起動"""
        logger.info('retart program')
        script_path = self.base_dir / ("restart_update.bat" if sys.platform.startswith('win') 
                                     else "restart_update.sh")
        if script_path.exists():
            if sys.platform.startswith('win'):
                subprocess.Popen([str(script_path)], shell=True)
            else:
                subprocess.Popen(['/bin/bash', str(script_path)])
            
            if self.root:
                self.root.destroy()
            sys.exit(0)


def main():
    try:
        with open('version.txt', 'r') as f:
            tmp = f.readline()
            print(tmp)
            SWVER = tmp.strip()[2:] if tmp.startswith('v') else tmp.strip()
    except Exception:
        logger.debug(traceback.format_exc())
        SWVER = "0.0.0"
    #SWVER='1.0.0' # for test

    updater = GitHubUpdater(
        github_author='dj-kata',
        github_repo='inf_daken_counter_obsw',
        current_version=SWVER,           # 現在のバージョン
        main_exe_name="notes_counter.exe",  # メインプログラムのexe名
        updator_exe_name="notes_counter.exe",           # アップデート用プログラムのexe名
    )
    
    # メインプログラムから呼び出す場合
    updater.check_and_update()


if __name__ == "__main__":
    main()
